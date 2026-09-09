"""Offline check that the confirmation screen answers like the search will.

    python tests/test_concept_lookup.py

The real dictionary is 200MB and lives beside the deployed code, so a tiny
stand-in is installed as the cache here. What is being checked is the lookup
rule, not the data.

Why this file exists: the concept-confirmation screen labels each term "in
MeSH" or not, and a person edits their concepts against that label. It was
computed from `concepts.norm`, which turns punctuation into a SPACE - so "dual
antiplatelet therapy" did not meet `Dual Anti-Platelet Therapy` and the screen
said the term was unknown. Meanwhile `search.vocab_mesh_rdf` resolves that same
term against NLM perfectly well. The screen was advising people to drop terms
that work.
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

import concepts as C  # noqa: E402


def check(name, cond):
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        raise SystemExit(1)


# Keys as the real dictionary stores them: `norm` applied, so punctuation has
# already become a space.
C._DICT = {
    "terms": {
        "dual anti platelet therapy": "D000080903",
        "stroke": "D020521",
        "safety": "D012449",
        "covid 19": "D000086382",
        "carcinoma non small cell lung": "D002289",
    },
    "labels": {
        "D000080903": "Dual Anti-Platelet Therapy",
        "D020521": "Stroke",
        "D012449": "Safety",
        "D000086382": "COVID-19",
        "D002289": "Carcinoma, Non-Small-Cell Lung",
    },
    "semantic_types": {},
}
C._SQUASHED = None

check("an exact term still resolves, and by the fast path",
      C.lookup("stroke") == "D020521")
check("the case that started this: the unhyphenated spelling now resolves",
      C.lookup("dual antiplatelet therapy") == "D000080903")
check("the hyphenated spelling resolves too - the mismatch runs both ways",
      C.lookup("dual anti-platelet therapy") == "D000080903")
check("a term the field writes without a hyphen reaches a hyphenated label",
      C.lookup("COVID19") == "D000086382" and C.lookup("covid-19") == "D000086382")
check("commas in the stored label do not block a match either",
      C.lookup("carcinoma non-small-cell lung") == "D002289")

# The point of the fallback is to answer the same way the live search does. It
# is NOT a similarity search: something MeSH does not have has to come back
# empty, or "not in MeSH" stops being worth printing.
check("a term that is genuinely absent stays absent",
      C.lookup("wibble frobnicator") is None)
check("an empty or punctuation-only term is not a lookup",
      C.lookup("") is None and C.lookup("---") is None)

# `safety` IS a MeSH descriptor - an earlier version of the confirmation
# screen's advice said it was not. Kept as a check because the wrong advice was
# written twice.
check("safety is in MeSH, whatever anyone assumed", C.lookup("safety") == "D012449")

check("the squashed index is built once and cached",
      C._SQUASHED is not None and C.lookup("stroke") == "D020521")

C._DICT = None
C._SQUASHED = None
print("\nall concept lookup checks passed")
