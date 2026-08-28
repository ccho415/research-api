"""Count the papers behind each direction, asking the way papers are written.

Terms come back in thesaurus form and papers are not written in thesaurus form.
`regulatory T-lymphocytes` is how MeSH says it and returns nothing; `regulatory
T cells` or `Tregs` is how authors say it and returns four papers - so the
direction that looked untouched had in fact been touched, and the check was
wrong rather than the field being empty.

Each term is therefore expanded through the MeSH synonym dictionary and OR'd
with its own synonyms before the terms are ANDed together.  Gene names,
variants and constructs like `MLH1 V384D` are not in MeSH at all and go
through unchanged, which is correct: there is only one way to write them.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request

REPO = r"D:\n8n_Claude\research-api"
sys.path.insert(0, os.path.join(REPO, "lib"))
import concepts as C  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
UA = {"User-Agent": "research-api/1.0 (direction verification; popo1664@gmail.com)"}

# Synonyms MeSH does not carry because they are how people abbreviate in prose,
# not how the thesaurus records them.  Known to be incomplete: a term arriving
# in a phrasing not listed here and not matching a MeSH label still produces a
# false zero, which reads as "nobody has done this" and is the one error in
# this file that costs the reader a year rather than an afternoon.
EXTRA = {
    "regulatory t cells": ["Tregs", "Treg"],
    "vascular endothelial growth factor a": ["VEGF-A", "VEGFA"],
    "epithelial mesenchymal transition": ["EMT"],
    "dna methylation": ["DNA methylation"],
}


def hits(query, tries=3):
    u = f"{EPMC}?format=json&pageSize=1&query={urllib.parse.quote(query)}"
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA),
                                        timeout=90) as r:
                return json.loads(r.read().decode())["hitCount"]
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def variants(term, cap=5):
    """How papers might write this term, longest-lived first."""
    out = [term]
    ui = C.load()["terms"].get(C.norm(term))
    if ui:
        for t in C.query_terms(ui, cap=cap):
            if C.norm(t) != C.norm(term):
                out.append(t)
    for k, extra in EXTRA.items():
        if C.norm(term) == C.norm(k) or C.norm(k) in C.norm(term):
            out.extend(extra)
    seen, uniq = set(), []
    for t in out:
        k = C.norm(t)
        if k and k not in seen:
            seen.add(k)
            uniq.append(t)
    return uniq[:cap]


def build(terms):
    groups = []
    for t in terms:
        vs = variants(t)
        groups.append("(" + " OR ".join(f'TITLE_ABS:"{v}"' for v in vs) + ")")
    return " AND ".join(groups)


def main(path, cutoff=2015, expect=None):
    rows = json.load(open(path, encoding="utf-8"))
    tally = {"already_done": 0, "pursued_since": 0, "still_open": 0}
    out = []
    print(f"{'#':>2}  {'pre':>4} {'post':>5}  {'verdict':<14}  terms (expanded)")
    for r in rows:
        terms = r.get("search_terms") or []
        q = build(terms)
        pre = hits(f'{q} AND (FIRST_PDATE:[1800-01-01 TO {cutoff}-12-31]) AND SRC:MED')
        time.sleep(0.4)
        post = hits(f'{q} AND (FIRST_PDATE:[{cutoff + 1}-01-01 TO 3000-12-31]) AND SRC:MED')
        time.sleep(0.4)
        v = "ALREADY DONE" if pre >= 3 else ("PURSUED SINCE" if post >= 3 else "STILL OPEN")
        tally[v.lower().replace(" ", "_")] += 1
        shown = " + ".join("/".join(variants(t)[:3]) for t in terms)
        print(f"{r.get('rank', '?'):>2}  {pre:>4} {post:>5}  {v:<14}  {shown[:96]}")
        out.append({**r, "papers_before": pre, "papers_after": post,
                    "verdict": v, "query": q})

    print()
    print(json.dumps(tally, indent=1))
    if expect:
        caught = sum(1 for r in out if r["verdict"] == expect)
        print(f"expected {expect}: {caught}/{len(out)}")
    json.dump(out, open(path.replace(".json", "_verified3.json"), "w",
                        encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], expect=(sys.argv[2] if len(sys.argv) > 2 else None))
