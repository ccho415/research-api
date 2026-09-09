"""Offline checks on concept expansion and the query plan. No network, no DB.

    python tests/test_expansion.py

Both things checked here were found the same way: a user recognised a standard
term on the concepts screen and asked why the system said it could not resolve
it. `Dual Anti-Platelet Therapy` is a current MeSH descriptor that registers no
entry term for any other spelling, and both lookup routes match literally - so
"dual antiplatelet therapy", which is how the field writes it almost
exclusively, matched nothing and that axis lost its MeSH-indexed query.

The normalisation itself is checked here; the SPARQL that uses it needs the
network and is not part of this file.

The second check keeps a *record* honest rather than a search. An unexpanded
concept was labelled "?" in the query plan, so the stored query_text and every
screen reading it said `? x Stroke` - which reads as "the term was dropped"
when the term was in fact searched, as a bare phrase, in every source. The
search was right and the account of it was not, which is the harder failure to
notice.
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

import ops  # noqa: E402
import search  # noqa: E402


def check(name, cond):
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        raise SystemExit(1)


# --- normalising a term the way the MeSH filter does ----------------------
n = search._mesh_norm

check("punctuation is what stops the match, so punctuation is what goes",
      n("Dual Anti-Platelet Therapy") == n("dual antiplatelet therapy"))
check("commas and word order in the label are handled by MeSH's own entry "
      "terms, not by this - it only levels the spelling",
      n("Carcinoma, Non-Small-Cell Lung") == n("carcinoma non small cell lung"))
check("case alone never mattered, and still does not",
      n("COVID-19") == n("covid 19") == "covid19")
check("an empty or punctuation-only term normalises to nothing, and the "
      "caller must not send that as a filter - it would match every "
      "unlabelled node",
      n("") == "" and n("---") == "")
check("two genuinely different terms stay different",
      n("stroke") != n("strokes"))

# --- the query plan's label -------------------------------------------------
UNEXPANDED = {"input": "dual antiplatelet therapy", "expanded": False,
              "descriptor": None, "unique_id": None,
              "terms": ["dual antiplatelet therapy"], "alternatives": []}
EXPANDED = {"input": "stroke", "expanded": True, "descriptor": "Stroke",
            "unique_id": "D020521", "terms": ["Cerebrovascular Accident"],
            "alternatives": [{"descriptor": "Ischemic Stroke",
                              "unique_id": "D000083242"}]}

plan = ops.plan_queries({"concepts": [UNEXPANDED, EXPANDED]}, max_queries=4)
labels = [p["label"] for p in plan]

check("an unexpanded concept is named by what was typed, never by `?`",
      labels and all("?" not in l for l in labels)
      and labels[0].startswith("dual antiplatelet therapy"))
check("an expanded concept is still named by its descriptor",
      labels[0].endswith("Stroke"))

# The point of the label fix is that it changes the record only. A concept that
# could not be expanded must go on being searched as its own phrase, in every
# source - that was always true and is the thing a label change could quietly
# break.
first = plan[0]["concepts"]
check("the unexpanded term is still sent to PubMed as a phrase",
      '"dual antiplatelet therapy"[tiab]' in search.render_query(first, "pubmed"))
check("...and to Europe PMC",
      '"dual antiplatelet therapy"' in search.render_query(first, "europepmc"))
check("...and to the bag-of-words sources",
      "dual antiplatelet therapy" in search.render_query(first, "openalex"))

# A single concept still has to produce a plan; the crossing branch is separate
# code and this one used to read cs[0]["input"] directly.
solo = ops.plan_queries({"concepts": [UNEXPANDED]}, max_queries=4)
check("a lone unexpanded concept still plans a search, named after itself",
      len(solo) == 1 and solo[0]["label"] == "dual antiplatelet therapy")

print("\nall expansion checks passed")
