#!/usr/bin/env python
"""Do this deployment's PubMed half from a machine NCBI has not blocked.

    python tools/pubmed_worker.py            # one pass, then exit
    python tools/pubmed_worker.py --dry-run  # say what it would do, do nothing
    python tools/pubmed_worker.py --loop 300 # stay resident, check every 5 min

Meant to be run by Windows Task Scheduler every few minutes. It starts, asks
one question, and in the ordinary case exits about a tenth of a second later
having found nothing to do - measured at 105-120 ms on the machine this was
written for. Nothing is resident between runs.

WHAT IT IS FOR

NCBI blocks the deployment's egress IP from E-utilities: a shared cloud
address, blocked in front of the quota, so an API key does not lift it. PubMed
therefore answers nothing server-side while answering normally from the
researcher's own machine. Measured on one clinical topic, PubMed and Europe PMC
each returned 25 papers with ONE in common - the records overlap, the relevance
ranking does not, so the half the server cannot reach is most of the corpus.

This is not a way around the block. The requests come from one researcher's own
connection, at their own rate, which is how E-utilities is meant to be used.
The server never touches PubMed.

WHY NOT THE BROWSER

There is a browser path and it still works, but it needs the tab left open, and
a backgrounded tab has its timers throttled to roughly once a minute - which
turns a thirty-second pass into half an hour. Anything that has to survive the
tab being closed has to live here.

TWO KINDS OF WORK

  literature  a project whose literature run has no PubMed-collected query.
              W2 planned the crossings; this repeats them and stores the result
              in the same run, so the corpus stays one corpus.

  novelty     an adversarial check decided without PubMed - which is all of
              them. W7's queries were recorded, so they are asked again and
              merged into the round they belong to. When the chain is parked
              after novelty waiting for exactly this, the pass releases it.

IF THIS NEVER RUNS, NOTHING BREAKS. A chain parked after novelty sits at
`awaiting_review`, which is the same state review points ③ and ④ use: the
progress screen shows it and the release button works. The cost of this worker
never running is one fewer cross-check, not a stuck pipeline.

BE POLITE

E-utilities asks for at most 3 requests a second without a key, 10 with one.
This sleeps 0.4s between calls and makes two per query. Set NCBI_API_KEY if you
have one - it is free from an NCBI account, and this story already contains one
address that had to be blocked.
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

API = os.environ.get(
    "RESEARCH_API",
    "https://ccho415-research.zeabur.app/webhook"
    "/5165edde-989c-4cc2-a500-f5915745ef67/research/api")
KEY = os.environ.get("RESEARCH_FRONTEND_KEY", "").strip()
NCBI = os.environ.get("NCBI_API_KEY", "").strip()
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
GAP = 0.4
# Matches the frontend's default. The window a project was searched with is not
# recorded anywhere, so this is a choice rather than a lookup - said out loud
# because a silent one would be indistinguishable from a stored setting.
DEFAULT_YEARS = 5


def log(msg):
    print(time.strftime("%H:%M:%S "), msg, sep="", flush=True)


def call(route, method="GET", query=None, body=None):
    if not KEY:
        raise SystemExit("RESEARCH_FRONTEND_KEY is not set")
    url = API + "/" + route
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"X-Frontend-Key": KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8", "replace") or "null")


def eutils(path, params):
    if NCBI:
        params = dict(params, api_key=NCBI)
    u = EUTILS + path + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(u, timeout=90) as r:
        return r.read().decode("utf-8", "replace")


def search_pubmed_xml(term, retmax):
    """PMIDs for this term, then the efetch XML for them. None if empty.

    The XML is returned unparsed on purpose: it goes back to the server, which
    reads it with the same `parse_pubmed_xml` every other source path uses. A
    second implementation of PubMed's XML out here would drift from that one
    and nobody would notice, because a slightly-wrongly-parsed paper looks
    exactly like a correct one.
    """
    body = eutils("esearch.fcgi", {"db": "pubmed", "retmode": "json",
                                   "sort": "relevance", "retmax": retmax,
                                   "term": term})
    ids = (json.loads(body).get("esearchresult") or {}).get("idlist") or []
    if not ids:
        return None
    time.sleep(GAP)
    return eutils("efetch.fcgi", {"db": "pubmed", "retmode": "xml",
                                  "id": ",".join(ids)})


def do_literature(p, dry):
    lit = p["literature"]
    got = call("concepts", query={"project_id": p["project_id"]})
    concepts = [c["input"] for c in ((got.get("latest") or {}).get("concepts") or [])
                if c.get("input")]
    if not concepts:
        log("    沒有記錄到概念，跳過文獻補查")
        return
    year_from = time.gmtime().tm_year - (DEFAULT_YEARS - 1)
    plan = call("pubmed-plan", method="POST", body={
        "concepts": concepts, "domain": lit["domain"],
        "year_from": year_from, "max_queries": 10})
    qs = plan.get("queries") or []
    log(f"    文獻：{len(qs)} 個查詢（{year_from} 年起）")
    if dry:
        return
    stored = 0
    for q in qs:
        try:
            xml = search_pubmed_xml(q["term"], 25)
            if xml:
                res = call("pubmed-ingest", method="POST", body={
                    "run_id": lit["run_id"], "query_text": q["label"],
                    "domain": lit["domain"], "xml": xml})
                stored += (res or {}).get("n_parsed") or 0
        except Exception as e:
            # One query failing must not lose the ones already stored, and the
            # next run will not retry them either - the marker is per-run, not
            # per-query. Said out loud rather than swallowed.
            log(f"    查詢失敗（{q['label'][:40]}）：{type(e).__name__}")
        time.sleep(GAP)
    log(f"    文獻：收錄 {stored} 篇")


def do_novelty(p, dry):
    flagged = []
    for c in p["novelty"]:
        log(f"    新穎性 {c.get('code') or ''}：{c['n_queries']} 輪"
            f"（判定 {c.get('verdict')}）")
        if dry:
            continue
        results = []
        for qq in c["queries"]:
            try:
                xml = search_pubmed_xml(qq["query"], 5)
                if xml:
                    results.append({"round": qq["round"], "xml": xml})
            except Exception:
                pass
            time.sleep(GAP)
        if not results:
            continue
        m = call("novelty-pubmed-merge", method="POST",
                 body={"check_id": c["check_id"], "results": results})
        added = (m or {}).get("n_added") or 0
        con = (m or {}).get("contradiction")
        log(f"      合併 {added} 篇" + (f"　⚠ {con['level']}" if con else ""))
        if con and con.get("level") == "contradicted":
            flagged.append((c.get("code"), con.get("why")))
    return flagged


def one_pass(dry=False, only=None, max_projects=2):
    """One wake-up: take at most `max_projects` projects' worth of work.

    Bounded on purpose. The first unattended run of this found eight projects
    with outstanding work, one of them with six novelty checks - about 170
    requests if done in one go. NCBI has already blocked one address in this
    story, and a burst is exactly what gets an address blocked. A backlog
    drained two projects per five-minute tick is finished within the hour and
    never looks like abuse.
    """
    work = call("pubmed-work", query={"limit": 12})
    projects = work.get("projects") or []
    if only:
        projects = [p for p in projects if p["project_id"].startswith(only)]
        if not projects:
            log(f"{only} 沒有待辦，或不在最近 12 個專案裡")
            return 0
    total = len(projects)
    projects = projects[:max_projects]
    if not projects:
        return 0
    log(f"{total} 個專案有待辦" +
        (f"，這次處理 {len(projects)} 個" if total > len(projects) else ""))
    for p in projects:
        log(f"  {p['project_id'][:8]}　{(p.get('topic') or '')[:40]}")
        if p.get("literature"):
            do_literature(p, dry)
        flagged = do_novelty(p, dry) if p.get("novelty") else []
        for code, why in flagged:
            log(f"    ⚠ {code}　{why}")

        # Released only when the chain is actually parked there and the novelty
        # work is done. Releasing something that is not parked is how a chain
        # gets pushed past a review point nobody looked at, so the condition is
        # the server's `parked_after_novelty` rather than this worker's guess.
        if p.get("parked_after_novelty") and not dry:
            if p.get("novelty"):
                try:
                    call("release", method="POST", body={"project_id": p["project_id"]})
                    log("    補查完成，已放行給 W8")
                except Exception as e:
                    log(f"    放行失敗（鏈仍在等你，進度頁按放行即可）：{e}")
            else:
                # Parked with nothing to merge. Left alone deliberately: it may
                # be waiting for a person, and a worker that releases every
                # pause it meets is a worker that walks the chain past reviews.
                log("    鏈在等放行，但沒有待補查的項目——留給你決定")
    return len(projects)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="say what it would do and change nothing")
    ap.add_argument("--loop", type=int, default=0, metavar="SECONDS",
                    help="stay resident and repeat. Omit for one pass and exit, "
                         "which is what the scheduled task wants.")
    ap.add_argument("--project", metavar="ID",
                    help="only this project. A prefix is enough.")
    ap.add_argument("--max-projects", type=int, default=2, metavar="N",
                    help="how many projects one wake-up may work through. "
                         "Bounded so a backlog drains over several ticks "
                         "instead of arriving at NCBI as a burst.")
    a = ap.parse_args()
    while True:
        try:
            n = one_pass(a.dry_run, a.project, a.max_projects)
            if not n and a.loop:
                log("沒有待辦")
        except urllib.error.HTTPError as e:
            log(f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:200]}")
        except Exception as e:
            log(f"{type(e).__name__}: {str(e)[:200]}")
        if not a.loop:
            return
        time.sleep(a.loop)


if __name__ == "__main__":
    main()
