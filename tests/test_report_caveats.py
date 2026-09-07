"""Offline check of what a report records about its own limits. No database.

    python tests/test_report_caveats.py

`build_caveats` and `build_acquisition` take a cursor, so a fake one that hands
back canned rows exercises the part that has to be right: which number is the
denominator, whether excluded directions are named or only counted, and whether
every entry carries the consequence and not just the figure.

The reason these are worth pinning offline is the reason they exist at all.
W9's gate already computed these numbers, into an n8n execution output that
nothing persisted - so the only way to see them was to watch one run go past.
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

fake_pg = types.ModuleType("psycopg")
fake_pg.types = types.SimpleNamespace(json=types.SimpleNamespace(Jsonb=lambda x: x))
sys.modules["psycopg"] = fake_pg
sys.modules["psycopg.types"] = fake_pg.types
sys.modules["psycopg.types.json"] = fake_pg.types.json
fake_db = types.ModuleType("db")
fake_db.connect = lambda: (_ for _ in ()).throw(RuntimeError("no db in this test"))
sys.modules["db"] = fake_db

import report

fails = []


def check(name, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{name}: got {got!r}, wanted {want!r}")
    print(("  ok  " if ok else " FAIL ") + name + f"  -> {got!r}")


class When:
    """A stamp that only has to answer isoformat()."""

    def isoformat(self):
        return "2026-09-07T00:00:00"


class FakeCur:
    """Hands back one canned result per execute, in order."""

    def __init__(self, results):
        self.results = list(results)
        self.n = 0

    def execute(self, sql, args=None):
        self._rows = self.results[self.n] if self.n < len(self.results) else []
        self.n += 1

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


print("\n-- the acquisition list is copied from the grading, not retold --")
acq = report.build_acquisition(FakeCur([[{
    "tier": "C",
    "missing": ["變項 A", "變項 B"],
    "route_to_tier_a": "去某個聯盟談資料分享協議，約兩到三個月",
    "assessed_at": When()}]]), "idea-1")
check("tier", acq["tier"], "C")
check("missing stays a list", acq["missing"], ["變項 A", "變項 B"])
check("route is carried whole", acq["route"].startswith("去某個聯盟"), True)
check("says which one wins on disagreement", "以這一份為準" in acq["note"], True)

print("\n-- one missing variable stored as a bare string is still a list --")
acq2 = report.build_acquisition(FakeCur([[{
    "tier": "B", "missing": "只有一個變項",
    "route_to_tier_a": "申請公開資料", "assessed_at": When()}]]), "idea-1")
check("wrapped", acq2["missing"], ["只有一個變項"])

print("\n-- no grading means no list, not an empty one --")
check("None", report.build_acquisition(FakeCur([[]]), "idea-1"), None)

FULL = [{"n_papers": 200, "n_with_fulltext": 69, "n_gap_sentences": 112}]
NOVEL = [{"graded": 11, "unverified": 8}]
SCOOPED = [{"code": 3, "title": "被搶先的方向甲"},
           {"code": 7, "title": "被搶先的方向乙"}]
DEBATE = [{"round_no": 1, "drift_from_original": 0.778, "n_objections_open": 2,
           "terminated": True, "termination_reason": "漂移超標"}]

cav = report.build_caveats(FakeCur([FULL, NOVEL, SCOOPED, DEBATE]),
                           "idea-1", "proj-1")

print("\n-- the full-text entry gives both numbers and the consequence --")
check("numerator", cav["fulltext"]["n_with_fulltext"], 69)
check("denominator", cav["fulltext"]["n_papers"], 200)
check("names what the missing ones cost",
      "Discussion" in cav["fulltext"]["note"], True)
check("counts the silent ones", "131" in cav["fulltext"]["note"], True)

print("\n-- unverified is two numbers, never a bare percentage --")
check("unverified", cav["novelty_unverified"]["n_unverified"], 8)
check("graded is the denominator", cav["novelty_unverified"]["n_graded"], 11)
check("says unverified is not novel",
      "未驗證不等於新穎" in cav["novelty_unverified"]["note"], True)

print("\n-- excluded directions are named, not just counted --")
check("n", cav["excluded_as_already_done"]["n"], 2)
check("named",
      [d["title"] for d in cav["excluded_as_already_done"]["directions"]],
      ["被搶先的方向甲", "被搶先的方向乙"])

print("\n-- the debate entry carries drift and the open objections --")
check("rounds", cav["debate"]["n_rounds"], 1)
check("drift is a float", cav["debate"]["drift_from_original"], 0.778)
check("open objections", cav["debate"]["n_objections_open"], 2)
check("says who decided it stopped",
      "不是模型自稱" in cav["debate"]["note"], True)

print("\n-- nothing excluded still produces the entry, saying zero --")
c0 = report.build_caveats(FakeCur([FULL, NOVEL, [], DEBATE]),
                          "idea-1", "proj-1")
check("present", "excluded_as_already_done" in c0, True)
check("zero", c0["excluded_as_already_done"]["n"], 0)

print("\n-- a direction that was never debated says so rather than vanishing --")
c1 = report.build_caveats(FakeCur([FULL, NOVEL, [], []]), "idea-1", "proj-1")
check("entry exists", c1["debate"]["n_rounds"], 0)
check("says why", "沒有經過辯論" in c1["debate"]["note"], True)

print("\n-- every entry explains the consequence, not only the figure --")
for k, v in cav.items():
    check(f"{k} has a note", bool(str(v.get('note') or '').strip()), True)

print("\n-- an empty run degrades to entries it can measure, not to junk --")
c2 = report.build_caveats(FakeCur([[], [{"graded": 0, "unverified": 0}], [], []]),
                          "idea-1", "proj-1")
check("no harvest -> no fulltext entry", "fulltext" in c2, False)
check("nothing graded -> no novelty entry", "novelty_unverified" in c2, False)
check("excluded entry still there", c2["excluded_as_already_done"]["n"], 0)

print()
if fails:
    print(f"{len(fails)} FAILED")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("all checks passed")
