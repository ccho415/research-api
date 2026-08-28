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

This is tools/verify_directions.py with the file and console handling taken
out, so n8n can call it on directions that have never touched a disk.
"""

import json
import time
import urllib.parse
import urllib.request

import concepts as C

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

# Two requests per direction, one at a time, with a pause between.  Europe PMC
# is the only source this check has - there is no second opinion to fall back
# on - and the egress IP this runs from has already been blocked permanently by
# NCBI once.  Fifteen directions take about twenty seconds this way, which is
# not worth trading for the risk.
PAUSE = 0.4

# Three papers, not one.  A single hit is as often a coincidence of phrasing as
# a real prior study, and demanding three is what separated the directions that
# had genuinely been done from the ones that merely collided with a word.
SETTLED = 3


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


def verify(directions, cutoff=2015):
    """Verdict per direction, plus the counts and query behind each one.

    A direction that fails is recorded and the batch continues.  Each direction
    arriving here has already cost a model call, and losing fourteen of them
    because Europe PMC timed out on the fifteenth turns a nearly complete run
    into a failure.
    """
    tally = {}
    rows = []
    for r in directions:
        terms = [t for t in (r.get("search_terms") or []) if str(t).strip()]

        # An empty term list would build an empty query, leaving only the date
        # filter - which matches most of MEDLINE and comes back as ALREADY
        # DONE.  The most confident possible answer, from no evidence at all.
        if not terms:
            v = "NO TERMS"
            rows.append({**r, "verdict": v, "papers_before": None,
                         "papers_after": None, "query": None})
            tally[v.lower().replace(" ", "_")] = tally.get(v.lower().replace(" ", "_"), 0) + 1
            continue

        q = build(terms)
        try:
            pre = hits(f'{q} AND (FIRST_PDATE:[1800-01-01 TO {cutoff}-12-31]) AND SRC:MED')
            time.sleep(PAUSE)
            post = hits(f'{q} AND (FIRST_PDATE:[{cutoff + 1}-01-01 TO 3000-12-31]) AND SRC:MED')
            time.sleep(PAUSE)
        except Exception as e:
            v = "CHECK FAILED"
            rows.append({**r, "verdict": v, "papers_before": None,
                         "papers_after": None, "query": q,
                         "error": f"{type(e).__name__}: {str(e)[:200]}"})
            tally[v.lower().replace(" ", "_")] = tally.get(v.lower().replace(" ", "_"), 0) + 1
            continue

        v = ("ALREADY DONE" if pre >= SETTLED
             else ("PURSUED SINCE" if post >= SETTLED else "STILL OPEN"))
        tally[v.lower().replace(" ", "_")] = tally.get(v.lower().replace(" ", "_"), 0) + 1
        rows.append({**r, "papers_before": pre, "papers_after": post,
                     "verdict": v, "query": q,
                     "terms_expanded": [variants(t)[:3] for t in terms]})

    return {"cutoff": cutoff, "n": len(rows), "tally": tally, "rows": rows}
