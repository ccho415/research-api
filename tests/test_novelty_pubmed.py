"""Offline check of what a later PubMed pass may and may not conclude.

    python tests/test_novelty_pubmed.py

No network, no database: the two pure functions behind the merge are exercised
directly.

Why this file exists. Every adversarial novelty check in this system was
decided without PubMed, because W7 runs server-side and NCBI blocks that
deployment's IP from E-utilities. The queries were recorded, so the same
questions can be asked later from an address that is not blocked. The dangerous
part is what one then claims about the verdict already on record - so the rule
is kept narrow and tested here rather than left to whoever writes the screen.
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

# Same stub the other offline tests use: db.py imports psycopg at module level
# and nothing here touches a connection.
fake_pg = types.ModuleType("psycopg")
fake_pg.types = types.SimpleNamespace(json=types.SimpleNamespace(Jsonb=lambda x: x))
fake_pg.errors = types.SimpleNamespace(UniqueViolation=type("UniqueViolation",
                                                            (Exception,), {}))
sys.modules["psycopg"] = fake_pg
sys.modules["psycopg.types"] = fake_pg.types
sys.modules["psycopg.types.json"] = fake_pg.types.json
fake_rows = types.ModuleType("psycopg.rows")
fake_rows.dict_row = object()
sys.modules["psycopg.rows"] = fake_rows

import db  # noqa: E402


def check(name, cond):
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        raise SystemExit(1)


C = db._pubmed_contradiction

# --- the one thing that can be settled without judgement -------------------
# `no_prior_art` is a bounded negative and the bound was "these searches found
# nothing". A round that found nothing, asked again in the same words of a
# database the first pass could not reach, and now finding papers, is that
# bound failing - not a hint, not a suggestion.
c = C("no_prior_art", 4, [2, 5])
check("an empty round that is no longer empty contradicts `no_prior_art`",
      c and c["level"] == "contradicted")
check("...and the reason names the rounds, so it can be checked rather than "
      "trusted", c and "2, 5" in c["why"])

c = C("no_prior_art", 3, [])
check("papers added without reviving an empty round weaken rather than "
      "contradict - the coverage statement was written while PubMed was "
      "unavailable, which is a different problem",
      c and c["level"] == "weakened")


# --- what must stay a matter of judgement ----------------------------------
# The verdict was never computed from the rounds: `save_novelty` takes the
# model's word and refuses only what the evidence cannot support. So nothing
# here may recompute it, and a merge that adds papers to a verdict about
# closeness says nothing on its own.
for v in ("adjacent", "scooped", "incremental"):
    c = C(v, 6, [1, 2])
    check(f"`{v}` is reported as a count, never contradicted",
          c and c["level"] == "note")

check("adding nothing produces no claim at all", C("no_prior_art", 0, []) is None)
check("...for every verdict", all(C(v, 0, []) is None for v in
                                  ("adjacent", "scooped", "incremental")))


# --- paper identity, which decides what counts as "added" ------------------
K = db._paper_key
check("DOI wins, and case does not matter",
      K({"doi": "10.1/AB", "pmid": "1"}) == K({"doi": "10.1/ab", "pmid": "2"}))
check("PMID is the fallback when there is no DOI",
      K({"pmid": "123"}) == K({"pmid": "123", "title": "different wording"}))
check("title is the last resort rather than the first",
      K({"doi": "10.1/x", "title": "A"}) != K({"title": "A"}))
check("an empty record does not collide with everything else",
      K({}) == "" and K({"title": "  "}) == "")

print("\nall novelty PubMed-pass checks passed")
