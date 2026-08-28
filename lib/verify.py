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

Two things this file learned the hard way, on execution 52 of W3-TEST, where
thirteen of fifteen directions came back STILL OPEN and none of them meant it:

A conjunction cannot return more papers than its rarest term.  `MLH1 V384D` has
two papers in all of MEDLINE, so every direction built on it was decided before
it was asked - four of the fifteen.  A term that rare is not evidence of an open
question, it is the absence of evidence, and it now says so in its own verdict
rather than borrowing the one that means something.

Picking the shortest synonyms was wrong, and wrong in a way that looked
principled.  For `T-Lymphocytes, Regulatory` the shortest are `tr1 cell`,
`cell tr1`, `cell th3`, `th3 cell` - lab jargon and its own inversions, four
slots of a five-slot budget.  `regulatory t cells` sits eighteenth in that list
by length and never got in.  Synonyms are now deduplicated by token set, which
removes the inversions, and ranked by how much they share with the descriptor
name before length is considered at all.

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
# not how the thesaurus records them.  `Tregs` and `Treg` are in neither the
# descriptors nor the entry terms - the thesaurus has `treg cell` but not the
# bare plural everyone actually writes.  Known to be incomplete: a term arriving
# in a phrasing not listed here and not matching a MeSH label still produces a
# false zero, which reads as "nobody has done this" and is the one error in
# this file that costs the reader a year rather than an afternoon.
EXTRA = {
    "regulatory t cells": ["Tregs", "Treg"],
    "vascular endothelial growth factor a": ["VEGF-A", "VEGFA"],
    "epithelial mesenchymal transition": ["EMT"],
    "dna methylation": ["DNA methylation"],
}

# One request at a time with a pause between.  Europe PMC is the only source
# this check has - there is no second opinion to fall back on - and the egress
# IP this runs from has already been blocked permanently by NCBI once.
PAUSE = 0.4

# Three papers, not one.  A single hit is as often a coincidence of phrasing as
# a real prior study, and demanding three is what separated the directions that
# had genuinely been done from the ones that merely collided with a word.
SETTLED = 3

# Below this, a term cannot carry a verdict.  For a conjunction to reach SETTLED
# on a term with twenty-five papers, more than a tenth of everything ever
# written about it would have to also cover the other terms, which does not
# happen between concepts that were not already being studied together.  The
# number is a judgement, not a measurement, which is why it travels in the
# request and why the counts are reported next to the verdict.
MIN_TERM_PAPERS = 25

_EXTRA_BY_UI = None


def extra_by_ui():
    """The curated synonyms, keyed by concept rather than by spelling.

    Keyed by spelling they were unreachable: the table says `regulatory t
    cells` and the direction said `T-Lymphocytes, Regulatory`, which is the
    same concept, shares no tokens, and matched neither by equality nor by
    substring.  Resolving both through MeSH first makes the phrasing irrelevant.
    """
    global _EXTRA_BY_UI
    if _EXTRA_BY_UI is None:
        _EXTRA_BY_UI = {}
        terms = C.load()["terms"]
        for k, extra in EXTRA.items():
            ui = terms.get(C.norm(k))
            if ui:
                _EXTRA_BY_UI.setdefault(ui, []).extend(extra)
    return _EXTRA_BY_UI


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


def variants(term, cap=8):
    """How papers might write this term, most likely phrasings first.

    Curated synonyms come first because they exist precisely where MeSH is
    silent, so letting the cap cut them would remove the only phrasing that
    works.  Thesaurus synonyms follow, deduplicated by token set so a term and
    its own inversion do not take two slots, and ranked by overlap with the
    descriptor name: a synonym that rearranges the descriptor is how people
    write it, while one that shares nothing with it is usually a code or a
    narrower subtype.
    """
    out = [term]
    ui = C.load()["terms"].get(C.norm(term))

    if ui:
        out.extend(extra_by_ui().get(ui, []))

        pool = C.query_terms(ui, cap=64)
        label_tokens = set(C.norm(pool[0]).split()) if pool else set()
        seen_shape = set()
        scored = []
        for t in pool[1:]:
            shape = tuple(sorted(C.norm(t).split()))
            if not shape or shape in seen_shape:
                continue
            seen_shape.add(shape)
            scored.append((-len(label_tokens & set(shape)), len(t), t))
        scored.sort()
        out.extend(t for _, _, t in scored)

    # Terms MeSH does not carry at all still reach the table by spelling.
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


def group(terms_):
    return "(" + " OR ".join(f'TITLE_ABS:"{v}"' for v in terms_) + ")"


def build(terms):
    return " AND ".join(group(variants(t)) for t in terms)


def verify(directions, cutoff=2015, min_term_papers=MIN_TERM_PAPERS):
    """Verdict per direction, plus the counts and query behind each one.

    A direction that fails is recorded and the batch continues.  Each direction
    arriving here has already cost a model call, and losing fourteen of them
    because Europe PMC timed out on the fifteenth turns a nearly complete run
    into a failure.
    """
    tally = {}
    rows = []
    # Terms repeat across directions - `MLH1 V384D` appeared in four of fifteen
    # - and each lookup is a request against the one source this check has.
    seen_counts = {}

    def bump(v):
        k = v.lower().replace(" ", "_")
        tally[k] = tally.get(k, 0) + 1

    def term_papers(t):
        key = C.norm(t)
        if key not in seen_counts:
            seen_counts[key] = hits(f'{group(variants(t))} AND SRC:MED')
            time.sleep(PAUSE)
        return seen_counts[key]

    for r in directions:
        terms = [t for t in (r.get("search_terms") or []) if str(t).strip()]

        # An empty term list would build an empty query, leaving only the date
        # filter - which matches most of MEDLINE and comes back as ALREADY
        # DONE.  The most confident possible answer, from no evidence at all.
        if not terms:
            bump("NO TERMS")
            rows.append({**r, "verdict": "NO TERMS", "papers_before": None,
                         "papers_after": None, "query": None})
            continue

        try:
            counts = {t: term_papers(t) for t in terms}
        except Exception as e:
            bump("CHECK FAILED")
            rows.append({**r, "verdict": "CHECK FAILED", "papers_before": None,
                         "papers_after": None, "query": build(terms),
                         "error": f"{type(e).__name__}: {str(e)[:200]}"})
            continue

        thin = {t: n for t, n in counts.items() if n < min_term_papers}
        if thin:
            bump("TERM TOO RARE")
            rows.append({**r, "verdict": "TERM TOO RARE", "papers_before": None,
                         "papers_after": None, "query": build(terms),
                         "term_papers": counts, "rare_terms": thin,
                         "why": "the rarest term caps this conjunction below the "
                                f"{SETTLED}-paper threshold, so no verdict about "
                                "the question itself is possible"})
            continue

        q = build(terms)
        try:
            pre = hits(f'{q} AND (FIRST_PDATE:[1800-01-01 TO {cutoff}-12-31]) AND SRC:MED')
            time.sleep(PAUSE)
            post = hits(f'{q} AND (FIRST_PDATE:[{cutoff + 1}-01-01 TO 3000-12-31]) AND SRC:MED')
            time.sleep(PAUSE)
        except Exception as e:
            bump("CHECK FAILED")
            rows.append({**r, "verdict": "CHECK FAILED", "papers_before": None,
                         "papers_after": None, "query": q,
                         "term_papers": counts,
                         "error": f"{type(e).__name__}: {str(e)[:200]}"})
            continue

        v = ("ALREADY DONE" if pre >= SETTLED
             else ("PURSUED SINCE" if post >= SETTLED else "STILL OPEN"))
        bump(v)
        rows.append({**r, "papers_before": pre, "papers_after": post,
                     "verdict": v, "query": q, "term_papers": counts,
                     "terms_expanded": [variants(t)[:4] for t in terms]})

    return {"cutoff": cutoff, "n": len(rows), "min_term_papers": min_term_papers,
            "tally": tally, "rows": rows}
