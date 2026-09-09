#!/usr/bin/env python
"""Run this project's PubMed half from your own machine, and store what it finds.

    python tools/pubmed_local.py <project_id>              # dry run, writes nothing
    python tools/pubmed_local.py <project_id> --write      # store the results
    python tools/pubmed_local.py <project_id> --years 5 --limit 25

WHY THIS EXISTS

NCBI blocks the deployment's egress IP (43.133.34.49, a shared Tencent Cloud
address) from E-utilities. Not a rate limit - the block sits in front of the
quota, so an API key does not lift it. Every clinical search the server runs
therefore comes back with PubMed in `failed_sources` and answers from Europe
PMC and OpenAlex alone.

This is NOT a way around that block. It runs the searches from your own
connection, which NCBI has not blocked and which is the ordinary way anybody
uses E-utilities. The server never touches PubMed; you do, and you hand back
what you found.

WHAT IT IS WORTH

Measured on one clinical topic, PubMed and Europe PMC each returned 25 papers
with exactly ONE in common. Europe PMC does mirror MEDLINE, so the records
overlap - it is the relevance ranking that differs, and the top 25 of each are
therefore near-disjoint. Adding this roughly doubles the distinct papers a
query contributes, which matters because the harvest can only mine a few
hundred of them for the sentences where authors say what is still unknown.

WHAT IT DOES NOT DO

W7's novelty rounds are still Europe PMC only. Those queries are written by a
model in the middle of that workflow rather than planned in advance, so there
is nothing here to mirror; covering them would mean the workflow handing its
queries out and waiting, which is a different and larger change.

BE POLITE

E-utilities asks for at most 3 requests a second without a key, 10 with one.
This sleeps 0.4s between calls and does two calls per query, so a ten-query
project makes about twenty requests over ten seconds. Set NCBI_API_KEY if you
have one - it is free from your NCBI account and it is how you stay a good
citizen of a service that has already had to block one address in this story.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "lib"))

import ops    # noqa: E402
import search as lit  # noqa: E402

API = os.environ.get(
    "RESEARCH_API",
    "https://ccho415-research.zeabur.app/webhook"
    "/5165edde-989c-4cc2-a500-f5915745ef67/research/api")
KEY = os.environ.get("RESEARCH_FRONTEND_KEY", "").strip()


def call(route, method="GET", query=None, body=None):
    """One request through W-API, the same allow-listed door the frontend uses.

    The compute service is only on Zeabur's private network, so this cannot
    reach it directly and should not: the allow-list is what stops a token
    leaking into something that can call /admin/migrate.
    """
    if not KEY:
        raise SystemExit(
            "Set RESEARCH_FRONTEND_KEY to the frontend webhook token first.\n"
            "It is the same value the browser asks for on its key screen.")
    url = API + "/" + route
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"X-Frontend-Key": KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8", "replace") or "null")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise SystemExit(f"{route} -> HTTP {e.code}: {detail}")


def lit_run_id(project_id):
    """The literature run these searches belong to.

    Stored against that run rather than a new one so the corpus stays one
    corpus: `done_queries` can then see what has already been searched, and a
    second pass does not pay for the same queries twice.
    """
    runs = (call("runs", query={"project_id": project_id}) or {}).get("runs") or []
    lit_runs = [r for r in runs if r.get("stage") == "lit_search"]
    if not lit_runs:
        raise SystemExit(
            "this project has no lit_search run, so there is nothing to attach "
            "these results to. Has the literature layer run yet?")
    return lit_runs[0]["id"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("project_id")
    ap.add_argument("--write", action="store_true",
                    help="actually store the results. Without it, nothing is sent.")
    ap.add_argument("--years", type=int, default=5,
                    help="how far back to search. 0 for no limit. Default 5, "
                         "matching the frontend's default.")
    ap.add_argument("--limit", type=int, default=25, help="papers per query")
    ap.add_argument("--max-queries", type=int, default=10)
    a = ap.parse_args()

    year_from = None
    if a.years > 0:
        year_from = time.gmtime().tm_year - (a.years - 1)

    got = call("concepts", query={"project_id": a.project_id})
    latest = got.get("latest") or {}
    concepts = [c["input"] for c in (latest.get("concepts") or []) if c.get("input")]
    if not concepts:
        raise SystemExit(
            "this project has no recorded concepts, so there is nothing to "
            "search for. Only projects that went through the concept screen "
            "have them.")
    # Whatever the project searched under. Stored per query by W2, so the
    # PubMed pass runs against the same routing rather than a guess.
    domain = next((q.get("domain") for q in (got.get("queries") or [])
                   if q.get("domain")), "clinical")

    print(f"專案 {a.project_id}")
    print(f"題目 {got.get('topic') or '(無)'}")
    print(f"概念 {', '.join(concepts)}")
    print(f"領域 {domain}   年份 {year_from or '不限'} 起   每查詢 {a.limit} 篇")
    print()

    # Expanded locally with the same code the server runs, so the queries are
    # the ones this project would have used - not a separate idea of them.
    exp = ops.search_expand(concepts, domain=domain, per_concept=10)
    if exp.get("degraded"):
        print(f"⚠ 有概念沒展開：{', '.join(exp.get('unexpanded') or [])}")
    plans = ops.plan_queries(exp, max_queries=a.max_queries)
    print(f"{len(plans)} 個查詢要跑\n")

    run_id = lit_run_id(a.project_id) if a.write else None
    total = stored = 0
    for i, p in enumerate(plans, 1):
        q = lit.render_query(p["concepts"], "pubmed")
        if not q:
            print(f"[{i}/{len(plans)}] {p['label']}\n    (組不出 PubMed 查詢，跳過)")
            continue
        try:
            hits = lit.s_pubmed(q, a.limit, year_from, None)
        except Exception as e:
            # One query failing must not lose the ones already collected - the
            # same reason the server's own search keeps going.
            print(f"[{i}/{len(plans)}] {p['label']}\n    失敗：{type(e).__name__}: {str(e)[:160]}")
            time.sleep(0.4)
            continue
        total += len(hits)
        line = f"[{i}/{len(plans)}] {p['label']}\n    {len(hits)} 篇"
        if a.write:
            res = call("search-ingest", method="POST", body={
                "query_text": p["label"], "run_id": run_id, "domain": domain,
                "results": hits, "axis_source": "topic",
                # Named so the record says where these came from. Without it a
                # later reader cannot tell this pass from the server's own.
                "query_angle": "pubmed via local machine",
                "sources": {"attempted": ["pubmed"], "answered": ["pubmed"],
                            "failed": [], "sent": {"pubmed": q}}})
            n_new = (res or {}).get("n_new")
            stored += len(hits)
            line += f"，已存（新論文 {n_new if n_new is not None else '?'}）"
        print(line)
        time.sleep(0.4)

    print()
    if a.write:
        print(f"完成：送出 {stored} 筆結果到 run {run_id}")
        print("重複的論文會被合併，不會變成兩筆——paper 表以 DOI／PMID 去重。")
    else:
        print(f"試跑完成：找到 {total} 篇，一筆都沒有寫入。")
        print("確認結果合理之後，加上 --write 再跑一次。")


if __name__ == "__main__":
    main()
