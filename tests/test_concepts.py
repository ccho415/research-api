"""Offline check of the concepts screen's payload. No database.

    python tests/test_concepts.py

`project.vocab_expansion` has been written since migration 002 and nothing ever
read it back, so its shape has never been exercised by a reader. These checks
exist because that column is an append-only history written by three different
code paths over three weeks, and the screen that now reads it must not fall over
on a row it did not expect - a project whose search never ran, a version entry
that is not a dict, an `expanded` field that was a list before it was a boolean.

The last check keeps something OUT: no query is attributed to a concept. The
descriptor a query was crossed from is not recoverable from its text, and a
count printed next to a concept that nothing supports is worse than no count.
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

fake_pg = types.ModuleType("psycopg")
fake_pg.types = types.SimpleNamespace(json=types.SimpleNamespace(Jsonb=lambda x: x))
fake_pg.errors = types.SimpleNamespace(UniqueViolation=type("UniqueViolation",
                                                            (Exception,), {}))
fake_pg.rows = types.SimpleNamespace(dict_row=object())
sys.modules["psycopg"] = fake_pg
sys.modules["psycopg.types"] = fake_pg.types
sys.modules["psycopg.types.json"] = fake_pg.types.json
sys.modules["psycopg.rows"] = fake_pg.rows
sys.modules["backup"] = types.ModuleType("backup")

import db  # noqa: E402


class _T:
    """Just enough of a timestamp to be serialised the way psycopg's would be."""

    def __init__(self, s):
        self.s = s

    def isoformat(self):
        return self.s


class _Cur:
    """Answers the two queries `project_concepts` makes, in order."""

    def __init__(self, project, queries):
        self.project, self.queries = project, queries
        self.n = 0

    def execute(self, sql, args=None):
        self.n += 1

    def fetchone(self):
        return self.project

    def fetchall(self):
        return self.queries

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Conn:
    def __init__(self, cur):
        self.c = cur

    def cursor(self):
        return self.c

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def stub(project, queries=()):
    cur = _Cur(project, list(queries))
    db.connect = lambda: _Conn(cur)


PROJ = {"id": "p1", "title": "雙抗", "topic": "DAPT in BAD", "vocab_expansion": None}


def check(name, cond):
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        raise SystemExit(1)


# --- a project whose search never ran ---------------------------------------
stub(dict(PROJ))
d = db.project_concepts("p1")
check("no expansion yet -> latest is null, not an empty object",
      d["latest"] is None and d["n_versions"] == 0 and d["earlier"] == [])
check("no queries yet -> zero, and the totals agree",
      d["queries"] == [] and d["n_queries"] == 0
      and d["n_empty_queries"] == 0 and d["n_hits_total"] == 0)

# --- the normal case, two expansions ----------------------------------------
hist = [
    {"at": "2026-09-01T00:00:00+00:00", "concepts": [
        {"input": "dual antiplatelet therapy", "descriptor": "Dual Anti-Platelet Therapy",
         "unique_id": "D000078328", "expanded": True}]},
    {"at": "2026-09-08T00:00:00+00:00", "concepts": [
        {"input": "dual antiplatelet therapy", "descriptor": "Platelet Aggregation Inhibitors",
         "unique_id": "D010975", "expanded": True},
        {"input": "branch atheromatous disease", "descriptor": None,
         "unique_id": None, "expanded": False}]},
]
qs = [
    {"query_text": "A AND B", "query_angle": "topic", "axis_source": "topic",
     "domain": "clinical", "n_hits": 25, "executed_at": _T("2026-09-08T01:00:00"),
     "run_id": "r1"},
    {"query_text": "A AND C", "query_angle": "broader", "axis_source": "topic",
     "domain": "clinical", "n_hits": 0, "executed_at": _T("2026-09-08T01:01:00"),
     "run_id": "r1"},
    {"query_text": "A AND D", "query_angle": None, "axis_source": "topic",
     "domain": "clinical", "n_hits": None, "executed_at": None, "run_id": "r1"},
]
stub(dict(PROJ, vocab_expansion=hist), qs)
d = db.project_concepts("p1")

check("the newest expansion is the one on show",
      d["latest"]["version"] == 2 and len(d["latest"]["concepts"]) == 2)
check("what the person typed survives verbatim",
      d["latest"]["concepts"][0]["input"] == "dual antiplatelet therapy")
check("an unexpanded concept keeps expanded false rather than being dropped",
      d["latest"]["concepts"][1]["expanded"] is False
      and d["latest"]["concepts"][1]["descriptor"] is None)
check("earlier expansions are kept, so a descriptor that moved can be seen",
      len(d["earlier"]) == 1 and d["earlier"][0]["version"] == 1
      and d["earlier"][0]["concepts"][0]["unique_id"] == "D000078328")
check("n_versions counts every expansion, not just the earlier ones",
      d["n_versions"] == 2)

check("a query with no hits is counted as empty, not dropped",
      d["n_queries"] == 3 and d["n_empty_queries"] == 2)
check("a null n_hits is 0, not an error",
      d["queries"][2]["n_hits"] == 0)
check("a null executed_at stays null rather than becoming a fake time",
      d["queries"][2]["executed_at"] is None)
check("hits total across the queries", d["n_hits_total"] == 25)

# --- rows the column could hold from before this reader existed --------------
stub(dict(PROJ, vocab_expansion=[{"at": "x", "concepts": [
    {"input": "a", "expanded": ["term1", "term2"]}]}]))
d = db.project_concepts("p1")
check("an `expanded` that used to be a term list normalises to a boolean",
      d["latest"]["concepts"][0]["expanded"] is True)

stub(dict(PROJ, vocab_expansion=["not a dict", None,
                                 {"at": "y", "concepts": ["also not a dict"]}]))
d = db.project_concepts("p1")
check("junk entries are skipped, not crashed on",
      d["n_versions"] == 1 and d["latest"]["concepts"] == [])

stub(dict(PROJ, vocab_expansion={"concepts": []}))
d = db.project_concepts("p1")
check("a non-list column reads as no history rather than throwing",
      d["n_versions"] == 0 and d["latest"] is None)

# --- a project that is not there --------------------------------------------
stub(None)
try:
    db.project_concepts("nope")
    check("an unknown project raises rather than returning an empty screen", False)
except ValueError:
    check("an unknown project raises rather than returning an empty screen", True)

# --- the thing deliberately absent ------------------------------------------
stub(dict(PROJ, vocab_expansion=hist), qs)
d = db.project_concepts("p1")
check("no query is attributed to a concept - the mapping is not recoverable",
      all("n_queries" not in c and "queries" not in c
          for c in d["latest"]["concepts"]))

print("\nall concept checks passed")
