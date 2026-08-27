#!/usr/bin/env python
"""Harvest what a field says about itself: its title vocabulary and its own
statements of what is still unknown.

Two sources, both written deliberately by authors, which is the point.

Titles are the one place every word was chosen on purpose. Concepts pulled from
abstract bodies include `Rosa` (from "levels rose"), `Lifting`, `Colour` and
`Achievement`; titles produce almost none of that.

Discussion sections state gaps outright. That is a stronger thing than a gap
inferred from two concepts never having co-occurred: a co-occurrence gap might
be silence, whereas "this relationship has not been well elucidated" is a
specialist saying so, in a sentence that can be quoted with its DOI.

The catch is that most such sentences are boilerplate - "further studies are
needed to confirm our findings" appears in every paper ever written - and this
harvester does not try to tell the difference. Counting MeSH concepts per
sentence looked like it would work and does not: "the mechanism underlying the
MLH1 V384D-associated EGFR-TKI resistance" names a variant and a resistance
pathway while matching no descriptor at all, and "elucidate the role of these
newly implicated functions" matches `Role` and says nothing. Both errors fall
on the sentences that matter most.

So everything a cue matched comes out, with its concepts attached as a hint and
its PMID, DOI and year attached as provenance. Judging specificity is a
judgement about meaning, and it belongs to whatever reads this next.

Measured on lung adenocarcinoma 2013-2015: of 60 papers, 34 had a retrievable
Discussion and 20 stated a gap in it.

    python tools/harvest_gaps.py --concepts "lung adenocarcinoma" \
        --from-year 2013 --to-year 2015 --papers 300 --out harvest.json
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import concepts as C  # noqa: E402

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
UA = {"User-Agent": "research-api/1.0 (research gap harvesting; "
                    + os.environ.get("ACADEMIC_MAILTO", "") + ")"}

# Phrases authors use when saying something is unfinished.  Deliberately wide:
# the specificity filter downstream is what separates a direction from a
# ritual, so this only has to find the sentence.
CUES = re.compile(
    r"(further (studies|research|work|investigation|trials)"
    r"|future (studies|research|work|direction|investigation)"
    r"|remains? (to be|unclear|unknown|poorly|largely)"
    r"|warrant(s|ed)? (further|investigation|study)"
    r"|(has|have) (yet|not) (to|been)"
    r"|little is known|not (yet )?(been )?(fully )?(investigated|explored|studied|elucidated|understood|characterized|characterised)"
    r"|unclear (whether|how|why|if)|it (is|remains) unclear"
    r"|should be (explored|investigated|examined|addressed)"
    r"|larger (studies|cohorts|samples)|prospective studies are (needed|required|warranted)"
    r"|no studies have|few studies have|studies are (needed|required|warranted)"
    r"|deserves? (further|investigation)|merits? (further|investigation))",
    re.I)

SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")


def get(url, text=False, tries=3):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                        timeout=120) as r:
                raw = r.read()
            return raw.decode("utf-8", "replace") if text else json.loads(raw.decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def or_group(terms):
    return "(" + " OR ".join(f'TITLE_ABS:"{t}"' for t in terms) + ")"


def search(query, n):
    out, cursor = [], "*"
    while len(out) < n:
        u = (f"{EPMC}/search?format=json&resultType=core&pageSize=1000"
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
    return out[:n]


def discussion_of(pmcid):
    """The Discussion or Conclusions text, or None if the paper has no full text."""
    xml = get(f"{EPMC}/{pmcid}/fullTextXML", text=True)
    if not xml or len(xml) < 20000:
        return None
    parts = []
    for m in re.finditer(r"<title>\s*(Discussion|Conclusions?|"
                         r"Discussion and Conclusions?)\s*</title>(.*?)(?=<sec |</body)",
                         xml, re.S | re.I):
        parts.append(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(2))))
    return " ".join(parts) or None


def gap_sentences(text):
    """Sentences that claim something is unfinished, with their concepts.

    `mesh_concepts` is a hint for the reviewer, deliberately not a filter.
    Measured on lung adenocarcinoma it misjudges in both directions, and the
    misses are the valuable ones: "the mechanism underlying the MLH1 V384D-
    associated EGFR-TKI resistance" names a variant and a resistance pathway
    and matches no MeSH descriptor at all, while "elucidate the role of these
    newly implicated functions" matches `Role` and says nothing.

    Specificity is a judgement about meaning; the rule can only report what it
    saw.
    """
    out = []
    for s in SENT.split(text or ""):
        s = s.strip()
        if not (60 <= len(s) <= 400) or not CUES.search(s):
            continue
        found = [ui for ui in C.extract(s) if not C.is_generic(ui)]
        out.append({"sentence": s,
                    "mesh_concepts": [{"ui": ui, "label": C.label(ui)} for ui in found]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concepts", nargs="+", required=True,
                    help="one or more concept terms; crossed with AND")
    ap.add_argument("--from-year", type=int, default=2013)
    ap.add_argument("--to-year", type=int, default=2015)
    ap.add_argument("--papers", type=int, default=300)
    ap.add_argument("--out", default="harvest.json")
    a = ap.parse_args()

    d = C.load()
    groups, resolved = [], []
    for term in a.concepts:
        ui = d["terms"].get(C.norm(term))
        terms = C.query_terms(ui) if ui else [term]
        resolved.append({"input": term, "ui": ui, "label": C.label(ui) if ui else None,
                         "terms": terms})
        groups.append(or_group(terms))

    window = f"(FIRST_PDATE:[{a.from_year}-01-01 TO {a.to_year}-12-31])"
    query = " AND ".join(groups) + f" AND {window} AND SRC:MED AND HAS_FT:Y"
    print(f"query: {query}", file=sys.stderr)

    papers = search(query, a.papers)
    print(f"{len(papers)} papers", file=sys.stderr)

    title_concepts, gaps, n_ft, n_disc = {}, [], 0, 0
    for i, p in enumerate(papers, 1):
        title = p.get("title") or ""
        for ui in C.extract(title):
            # The same filters the bridge work needed: titles are far cleaner
            # than abstract bodies but still carry `Neoplasms`, `Cells` and
            # `Association`.
            if C.is_generic(ui) or not C.is_specific(ui):
                continue
            e = title_concepts.setdefault(ui, {"ui": ui, "label": C.label(ui),
                                               "semantic_types": C.semantic_types(ui),
                                               "n_papers": 0, "examples": []})
            e["n_papers"] += 1
            if len(e["examples"]) < 3:
                e["examples"].append(title[:110])

        pmcid = p.get("pmcid")
        if not pmcid:
            continue
        try:
            text = discussion_of(pmcid)
        except Exception as e:
            print(f"  [{i}] {pmcid}: {e}", file=sys.stderr)
            continue
        time.sleep(0.25)
        if not text:
            continue
        n_ft += 1
        found = gap_sentences(text)
        if found:
            n_disc += 1
        for g in found:
            gaps.append({**g, "pmid": p.get("pmid"), "pmcid": pmcid,
                         "doi": p.get("doi"), "year": p.get("pubYear"),
                         "title": title})
        if i % 25 == 0:
            print(f"  {i}/{len(papers)} papers, {len(gaps)} gap sentences",
                  file=sys.stderr)

    ranked = sorted(title_concepts.values(), key=lambda e: -e["n_papers"])
    out = {
        "query": query, "resolved": resolved,
        "n_papers": len(papers), "n_with_discussion": n_ft,
        "n_papers_with_gaps": n_disc,
        "title_concepts": ranked,
        "gaps": gaps,
    }
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)

    print(f"\npapers with a Discussion   {n_ft}", file=sys.stderr)
    print(f"papers stating a gap       {n_disc}", file=sys.stderr)
    print(f"gap sentences              {len(gaps)}", file=sys.stderr)
    print(f"title concepts             {len(ranked)}", file=sys.stderr)
    print(f"wrote {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
