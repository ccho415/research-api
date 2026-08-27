#!/usr/bin/env python
"""Time-slice validation for the ABC bridge finder.

Does the thing find gaps that later turned out to be worth filling, or does it
find gaps that stayed empty because nobody had a reason to look?  The only way
to know is to hide the future from it: build the whole pipeline out of papers
published before a cutoff, ask it for the top bridges, and then check what the
years since actually produced.

The pass marks are fixed before the run, in GATES below, because a threshold
chosen after seeing the numbers is not a threshold.

    python tools/timeslice_experiment.py --anchor "lung adenocarcinoma" \
        --cutoff 2015 --out timeslice.json

Costs roughly 150 requests to Europe PMC and no model tokens at all.
"""

import argparse
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import concepts  # noqa: E402

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
MAILTO = os.environ.get("ACADEMIC_MAILTO", "")
UA = {"User-Agent": f"research-api/1.0 (literature-based discovery validation; {MAILTO})"}

GATES = {
    # The headline test.  A bridge score that beats nothing is a ranking of
    # term frequency wearing a hypothesis costume.
    "top20_over_control": 2.0,
    # If the control itself lands most of the time, the candidate pool is made
    # of concepts that co-occur with everything eventually, and the experiment
    # cannot separate a good ranking from a bad one.  Not a failure - a void.
    "control_ceiling": 0.5,
    # What counts as "somebody did it": a single passing mention is noise.
    "min_papers_for_hit": 3,
}


def get(url, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            if attempt == tries - 1:
                raise
            print(f"    retry ({e})", file=sys.stderr)
            time.sleep(2 * (attempt + 1))


def date_clause(lo=None, hi=None):
    return f'(FIRST_PDATE:[{lo or "1800"}-01-01 TO {hi or "3000"}-12-31])'


def or_group(terms):
    """Synonyms OR'd together, restricted to title and abstract.

    Europe PMC searches the full text of open-access papers by default, and two
    common biomedical terms will co-occur somewhere in a full text almost every
    time - `lung adenocarcinoma` with `exercise` returns 3,508 papers that way
    and 33 when confined to title and abstract.  Full-text co-occurrence is a
    fact about typesetting; what a paper is *about* is in the title and the
    abstract, which is also where the LBD literature reads its concepts.
    """
    return "(" + " OR ".join(f'TITLE_ABS:"{t}"' for t in terms) + ")"


def hit_count(query):
    u = f"{EPMC}?format=json&pageSize=1&query={urllib.parse.quote(query)}"
    return get(u)["hitCount"]


def corpus(query, max_papers):
    """Titles and abstracts, paged, newest cursor style."""
    out, cursor = [], "*"
    while len(out) < max_papers:
        u = (f"{EPMC}?format=json&resultType=core&pageSize=1000"
             f"&cursorMark={urllib.parse.quote(cursor)}&query={urllib.parse.quote(query)}")
        d = get(u)
        rows = d["resultList"]["result"]
        if not rows:
            break
        out.extend(rows)
        cursor = d.get("nextCursorMark") or ""
        if not cursor:
            break
        time.sleep(0.35)
    return out[:max_papers]


def concepts_in(papers):
    """Concept UI -> number of papers it appears in (not raw mentions).

    Per paper, not per mention: a term repeated twenty times in one abstract is
    one paper's worth of evidence, and counting mentions would rank verbose
    abstracts above numerous ones.
    """
    seen = {}
    for p in papers:
        text = (p.get("title") or "") + ". " + (p.get("abstractText") or "")
        for ui in concepts.extract(text):
            seen[ui] = seen.get(ui, 0) + 1
    return seen


def build_pool(a_ui, a_terms, pre, n_b, a_papers, b_papers, min_depth, report):
    """Everything up to the ranked candidate list, so it can be cached.

    Fetching thirty corpora takes a quarter of an hour and asks Europe PMC for
    thirty thousand papers.  Doing that again to try a different filter is both
    slow and rude, and it also means the two runs are not comparing the same
    pool.
    """
    print(f"  fetching A corpus (<= {pre}) ...", file=sys.stderr)
    a_corpus = corpus(f"{or_group(a_terms)} AND {pre} AND SRC:MED", a_papers)
    a_concepts = concepts_in(a_corpus)
    report["a_corpus"] = {"n_papers": len(a_corpus), "n_concepts": len(a_concepts)}
    print(f"  {len(a_corpus)} papers, {len(a_concepts)} concepts", file=sys.stderr)

    b_list = [(ui, n) for ui, n in a_concepts.items()
              if ui != a_ui and concepts.is_specific(ui, min_depth)
              and not concepts.is_generic(ui)
              and not concepts.shares_branch(a_ui, ui)]
    b_list.sort(key=lambda kv: -kv[1])
    b_list = b_list[:n_b]
    report["b_terms"] = [{"ui": ui, "label": concepts.label(ui), "papers": n,
                          "semantic_types": concepts.semantic_types(ui),
                          "background_df": round(concepts.background_df(ui), 4)}
                         for ui, n in b_list]

    linking, pool_freq = {}, {}
    for idx, (b_ui, _) in enumerate(b_list, 1):
        q = f"{or_group(concepts.query_terms(b_ui))} AND {pre} AND SRC:MED"
        print(f"  [{idx}/{len(b_list)}] B = {concepts.label(b_ui)}", file=sys.stderr)
        try:
            b_corpus = corpus(q, b_papers)
        except Exception as e:
            print(f"      skipped ({e})", file=sys.stderr)
            continue
        for c_ui, n in concepts_in(b_corpus).items():
            if c_ui == a_ui or c_ui == b_ui or c_ui in a_concepts:
                continue
            if not concepts.is_specific(c_ui, min_depth) or concepts.is_generic(c_ui):
                continue
            if concepts.shares_branch(a_ui, c_ui) or concepts.shares_branch(b_ui, c_ui):
                continue
            linking.setdefault(c_ui, []).append(b_ui)
            pool_freq[c_ui] = pool_freq.get(c_ui, 0) + n
        time.sleep(0.35)
    return linking, pool_freq


def run(anchor, cutoff, n_b, a_papers, b_papers, top_n, seed, min_depth=3,
        cache=None, exclude=None, dump_candidates=None):
    rng = random.Random(seed)
    report = {"anchor": anchor, "cutoff": cutoff, "gates": GATES, "seed": seed}

    a_ui = concepts.load()["terms"].get(concepts.norm(anchor))
    if not a_ui:
        raise SystemExit(f"no MeSH concept matches {anchor!r}")
    a_terms = concepts.query_terms(a_ui)
    report["anchor_concept"] = {"ui": a_ui, "label": concepts.label(a_ui),
                                "terms": a_terms}
    print(f"A = {concepts.label(a_ui)} ({a_ui})", file=sys.stderr)

    pre = date_clause(hi=cutoff)
    if cache and os.path.exists(cache):
        with open(cache, encoding="utf-8") as fh:
            saved = json.load(fh)
        linking = {k: v for k, v in saved["linking"].items()}
        pool_freq = saved["pool_freq"]
        report["a_corpus"] = saved["a_corpus"]
        report["b_terms"] = saved["b_terms"]
        print(f"  pool loaded from {cache}", file=sys.stderr)
    else:
        linking, pool_freq = build_pool(a_ui, a_terms, pre, n_b, a_papers,
                                        b_papers, min_depth, report)
        if cache:
            with open(cache, "w", encoding="utf-8") as fh:
                json.dump({"linking": linking, "pool_freq": pool_freq,
                           "a_corpus": report["a_corpus"],
                           "b_terms": report["b_terms"]}, fh)

    # An excluded concept is one a reviewer has judged not to be a hypothesis.
    # It is dropped before ranking, not after: filtering the top twenty leaves
    # a top twenty of six, which is not the same list as the top twenty of what
    # was worth ranking in the first place.
    dropped = set(exclude or [])
    if dropped:
        before = len(linking)
        linking = {k: v for k, v in linking.items() if k not in dropped}
        print(f"  excluded {before - len(linking)} reviewed concepts",
              file=sys.stderr)
    report["n_excluded"] = len(dropped)

    ranked = sorted(linking.items(), key=lambda kv: (-len(kv[1]), -pool_freq[kv[0]]))
    report["pool_size"] = len(ranked)

    if dump_candidates:
        rows = [{"ui": ui, "label": concepts.label(ui),
                 "semantic_types": concepts.semantic_types(ui),
                 "ambiguous": any(t in concepts.AMBIGUOUS_TYPES
                                  for t in concepts.semantic_types(ui)),
                 "ltc": len(bs), "pool_freq": pool_freq[ui],
                 "linked_via": [concepts.label(b) for b in list(bs)[:8]]}
                for ui, bs in ranked[:dump_candidates]]
        with open(f"candidates_{anchor.replace(' ', '_')}.json", "w",
                  encoding="utf-8") as fh:
            json.dump({"anchor": concepts.label(a_ui), "cutoff": cutoff,
                       "candidates": rows}, fh, ensure_ascii=False, indent=1)
        print(f"  wrote candidates_{anchor.replace(' ', '_')}.json "
              f"({len(rows)} rows) - review, then re-run with --exclude",
              file=sys.stderr)
        return report
    print(f"  candidate pool: {len(ranked)}", file=sys.stderr)
    if len(ranked) < top_n * 3:
        raise SystemExit("candidate pool too small to compare against a control")

    checked = {}

    def pair_counts(c_ui):
        """Papers linking A and C, before and after the cutoff."""
        if c_ui in checked:
            return checked[c_ui]
        pair = f"{or_group(a_terms)} AND {or_group(concepts.query_terms(c_ui))}"
        before = hit_count(f"{pair} AND {pre} AND SRC:MED")
        time.sleep(0.35)
        after = hit_count(f"{pair} AND {date_clause(lo=cutoff + 1)} AND SRC:MED")
        time.sleep(0.35)
        checked[c_ui] = (before, after)
        return checked[c_ui]

    def row(c_ui):
        before, after = pair_counts(c_ui)
        return {"ui": c_ui, "label": concepts.label(c_ui),
                "semantic_types": concepts.semantic_types(c_ui),
                "ltc": len(linking[c_ui]), "pool_freq": pool_freq[c_ui],
                "papers_before_cutoff": before, "papers_after_cutoff": after,
                "hit": after >= GATES["min_papers_for_hit"]}

    # Absence has to be established by asking, not by not having looked.  A
    # candidate missing from the A corpus may simply be missing from the
    # thousand papers we sampled, so walk the ranking and keep the ones the
    # literature really is silent about before the cutoff.
    print("  selecting top (verifying pre-cutoff silence) ...", file=sys.stderr)
    top, scanned = [], 0
    for c_ui, _ in ranked:
        if len(top) >= top_n or scanned >= top_n * 8:
            break
        scanned += 1
        if pair_counts(c_ui)[0] == 0:
            top.append(c_ui)
            print(f"    {len(top):2d}. {concepts.label(c_ui)}"
                  f"  LTC={len(linking[c_ui])}", file=sys.stderr)
    report["n_scanned_for_top"] = scanned

    # Frequency-matched, and matched on the same silence.  LTC favours common
    # terms and common terms co-occur with everything given eleven years, so a
    # control that is neither matched nor silent would flatter any ranking.
    print("  selecting control (frequency-matched) ...", file=sys.stderr)
    rest = [ui for ui, _ in ranked[scanned:] if ui not in set(top)]
    control, used = [], set()
    for ui in top:
        target = pool_freq[ui]
        for cand in sorted((c for c in rest if c not in used),
                           key=lambda c: abs(pool_freq[c] - target))[:6]:
            used.add(cand)
            if pair_counts(cand)[0] == 0:
                control.append(cand)
                break

    report["top"] = [row(ui) for ui in top]
    report["control"] = [row(ui) for ui in control]

    def rate(rows):
        return (sum(r["hit"] for r in rows) / len(rows)) if rows else None, len(rows)

    top_rate, n_top = rate(report["top"])
    ctl_rate, n_ctl = rate(report["control"])
    report["result"] = {
        "top_hit_rate": top_rate, "n_top": n_top,
        "control_hit_rate": ctl_rate, "n_control": n_ctl,
        "mean_ltc_top": round(sum(r["ltc"] for r in report["top"]) / n_top, 2) if n_top else None,
        "mean_ltc_control": round(sum(r["ltc"] for r in report["control"]) / n_ctl, 2) if n_ctl else None,
        "ratio": (top_rate / ctl_rate) if (top_rate and ctl_rate) else None,
    }

    if ctl_rate is not None and ctl_rate > GATES["control_ceiling"]:
        report["verdict"] = "VOID - control hit rate above ceiling; pool too generic"
    elif report["result"]["ratio"] is None:
        report["verdict"] = "VOID - could not compute a ratio"
    elif report["result"]["ratio"] >= GATES["top20_over_control"]:
        report["verdict"] = "PASS"
    else:
        report["verdict"] = "FAIL"
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchor", required=True)
    ap.add_argument("--cutoff", type=int, default=2015)
    ap.add_argument("--n-b", type=int, default=30)
    ap.add_argument("--a-papers", type=int, default=1000)
    ap.add_argument("--b-papers", type=int, default=1000)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--min-depth", type=int, default=3)
    ap.add_argument("--cache", help="reuse (or write) the corpus pool here")
    ap.add_argument("--dump-candidates", type=int,
                    help="write the top N candidates for review, then stop")
    ap.add_argument("--exclude", help="JSON list of concept UIs to drop before ranking")
    ap.add_argument("--seed", type=int, default=20260828)
    ap.add_argument("--out", default="timeslice.json")
    a = ap.parse_args()

    started = time.time()
    exclude = None
    if a.exclude:
        with open(a.exclude, encoding="utf-8") as fh:
            exclude = json.load(fh)
    report = run(a.anchor, a.cutoff, a.n_b, a.a_papers, a.b_papers, a.top,
                 a.seed, a.min_depth, a.cache, exclude, a.dump_candidates)
    if a.dump_candidates:
        return
    report["seconds"] = round(time.time() - started, 1)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)

    r = report["result"]
    print(f"\n  verdict {report['verdict']}", file=sys.stderr)
    print(f"  top     {r['top_hit_rate']} over {r['n_top']}"
          f"  mean LTC {r['mean_ltc_top']}", file=sys.stderr)
    print(f"  control {r['control_hit_rate']} over {r['n_control']}"
          f"  mean LTC {r['mean_ltc_control']}", file=sys.stderr)
    print(f"  ratio   {r['ratio']}   gate {GATES['top20_over_control']}", file=sys.stderr)
    print(f"  wrote {a.out} in {report['seconds']}s", file=sys.stderr)


if __name__ == "__main__":
    main()
