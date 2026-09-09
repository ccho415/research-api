"""Offline check of the ten rows the waiting screen shows. No database.

    python tests/test_progress.py

Two of these checks exist to keep something OUT. The waiting screen used to
show progress within a stage and a remaining-time estimate, and the backend can
supply neither: a stage runs inside n8n and reports once at the end, and nobody
has measured how long the chain takes. A screen that promises "about 25
minutes" and takes two hours has taught the reader to distrust every other
number on it, and most of those are real.
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
sys.modules["psycopg"] = fake_pg
sys.modules["psycopg.types"] = fake_pg.types
sys.modules["psycopg.types.json"] = fake_pg.types.json
fake_db = types.ModuleType("db")
fake_db.connect = lambda: (_ for _ in ()).throw(RuntimeError("no db in this test"))
sys.modules["db"] = fake_db

import progress

fails = []


def check(name, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{name}: got {got!r}, wanted {want!r}")
    print(("  ok  " if ok else " FAIL ") + name + f"  -> {got!r}")


FULL_DETAIL = {
    "literature": {"n_queries": 10, "n_papers": 200},
    "harvest": {"n_papers": 200, "n_with_fulltext": 69, "n_gap_sentences": 112},
    "frame": {"paradigms": ["observational", "measurement"],
              "field": "clinical", "confidence": "high",
              "second_pack_forced": True},
    "ideas": {"n_ideas": 15},
    "dedup": {"n_pairs": 20, "n_duplicates": 0, "n_overridden_by_hand": 0},
    "tournament": {"tournament_id": "t1", "n_matches": 283, "n_undecided": 3,
                   "n_ranked": 11},
    "feasibility": {"counts": {"A": 0, "B": 1, "C": 10, "D": 0}, "n_graded": 11},
    "novelty": {"by_verdict": {"adjacent": 1}, "n_verified": 3},
    "debate": {"n_directions": 3, "n_rounds": 4, "n_objections_open": 2},
    "report": {"n_reports": 1},
}
EMPTY_DETAIL = {k: ({"counts": {}, "n_graded": 0} if k == "feasibility"
                    else {"by_verdict": {}, "n_verified": 0} if k == "novelty"
                    else {k2: 0 for k2 in v})
                for k, v in FULL_DETAIL.items()}

steps = progress.build_steps(FULL_DETAIL, {}, True, "done")
by_key = {s["key"]: s for s in steps}

print("\n-- ten rows: four before the chain, then the chain's six --")
check("count", len(steps), 10)
check("the first four are not the chain's",
      [s["key"] for s in steps[:4]],
      ["literature", "harvest", "frame", "ideas"])
check("and are marked so", [s["in_chain"] for s in steps[:4]],
      [False] * 4)
check("the chain's six, in order", [s["key"] for s in steps[4:]],
      ["dedup", "tournament", "feasibility", "novelty", "debate", "report"])
check("all marked in_chain", all(s["in_chain"] for s in steps[4:]), True)

print("\n-- the two stages that stop are flagged before they are reached --")
check("feasibility is review ③", by_key["feasibility"]["review_point"], "③")
check("debate is review ④", by_key["debate"]["review_point"], "④")
check("and both pause by default",
      [by_key["feasibility"]["pauses_by_default"],
       by_key["debate"]["pauses_by_default"]], [True, True])
check("dedup and tournament do not stop",
      [by_key["dedup"]["pauses_by_default"],
       by_key["tournament"]["pauses_by_default"]], [False, False])

print("\n-- a pre-chain step reads its status from its own output --")
check("literature with queries is done", by_key["literature"]["status"], "done")
e = {s["key"]: s for s in progress.build_steps(EMPTY_DETAIL, {}, False, None)}
check("no queries is not started", e["literature"]["status"], "not started")
check("no frame is not started", e["frame"]["status"], "not started")
check("no harvest row is not started", e["harvest"]["status"], "not started")

print("\n-- a failed harvest that wrote rows is failed, not done --")
f = {s["key"]: s for s in progress.build_steps(FULL_DETAIL, {}, True, "failed")}
check("harvest keeps its own status", f["harvest"]["status"], "failed")
check("but still carries what it did get",
      f["harvest"]["detail"]["n_with_fulltext"], 69)

print("\n-- a chain stage with no run row has not started, not 'idle' --")
check("dedup", by_key["dedup"]["status"], "not started")
r = {s["key"]: s for s in progress.build_steps(
    FULL_DETAIL, {"dedup": {"status": "done", "error": None,
                            "finished_at": None},
                  "tournament": {"status": "running", "error": None,
                                 "finished_at": None}}, True, "done")}
check("done is carried through", r["dedup"]["status"], "done")
check("running is carried through", r["tournament"]["status"], "running")

print("\n-- the frame row carries the decision, not the reasoning --")
# The three routing answers are long prose nested under `routing`; the row
# wants the decision, which reads as "observational + measurement + clinical".
check("paradigms", by_key["frame"]["detail"]["paradigms"],
      ["observational", "measurement"])
check("field", by_key["frame"]["detail"]["field"], "clinical")
check("a forced second pack is visible",
      by_key["frame"]["detail"]["second_pack_forced"], True)
check("no q1/q2/q3 prose on the row",
      "q1" in by_key["frame"]["detail"], False)

print("\n-- the numbers travel with their denominators --")
check("full text keeps both",
      (by_key["harvest"]["detail"]["n_with_fulltext"],
       by_key["harvest"]["detail"]["n_papers"]), (69, 200))
check("undecided matches are counted, not hidden",
      by_key["tournament"]["detail"]["n_undecided"], 3)
check("an empty tier is a zero, not a missing key",
      by_key["feasibility"]["detail"]["counts"]["A"], 0)

class _T:
    """Just enough of a timestamp to be .isoformat()-ed."""
    def __init__(self, v): self.v = v
    def isoformat(self): return self.v


print("\n-- a stage says what it is doing while it does it --")
# Added 2026-09-09. A tournament sat in a queue for three hours and forty
# minutes having completed none of its requests, and nothing the backend
# returned could tell that apart from a stage that had just begun.
live = {s["key"]: s for s in progress.build_steps(
    FULL_DETAIL,
    {"tournament": {"status": "running", "error": None, "finished_at": None,
                    "reported_at": _T("2026-09-09T10:39:09+00:00"),
                    "report": {"batch_id": "msgbatch_x", "succeeded": 0,
                               "processing": 136, "billed_so_far": False}}},
    True, "done")}
check("a running stage carries its last report",
      live["tournament"]["report"]["processing"], 136)
check("and when it said it", live["tournament"]["reported_at"],
      "2026-09-09T10:39:09+00:00")
check("nothing completed means nothing billed yet",
      live["tournament"]["report"]["billed_so_far"], False)

# Free-shaped on purpose: progress means a different number in every stage,
# and one schema would force each to report the least useful thing they share.
gated = {s["key"]: s for s in progress.build_steps(
    FULL_DETAIL,
    {"tournament": {"status": "done", "error": None,
                    "finished_at": _T("2026-09-09T10:45:55+00:00"),
                    "reported_at": _T("2026-09-09T10:45:55+00:00"),
                    "report": {"all_gates_pass": False,
                               "order_flip_rate": 0.23}}},
    True, "done")}
check("a finished stage keeps what it found",
      gated["tournament"]["report"]["all_gates_pass"], False)
check("order_flip_rate finally has somewhere to live",
      gated["tournament"]["report"]["order_flip_rate"], 0.23)

print("\n-- silence is null, never zero --")
# A zero would read as "reported, and the number is zero", which is the one
# thing this field exists to tell apart from "said nothing at all".
check("no report is null", by_key["tournament"]["report"], None)
check("no timestamp is null", by_key["tournament"]["reported_at"], None)
check("pre-chain steps have no report field at all",
      "report" in by_key["literature"], False)


print("\n-- what the backend cannot measure must not appear --")
# Field names, not a substring search: "detail" contains the letters of "eta".
names = set()
for s in steps:
    names |= set(s)
    names |= set(s.get("detail") or {})
banned = {"eta", "eta_seconds", "remaining_seconds", "percent",
          "percent_complete", "progress", "n_done_so_far", "fraction"}
check("no countdown or fraction field", sorted(names & banned), [])
check("the note gives a range, not a countdown",
      "30–60" in progress.ETA_NOTE, True)
check("and says why there is no estimate",
      "沒有量測基礎" in progress.ETA_NOTE, True)

print()
if fails:
    print(f"{len(fails)} FAILED")
    for f_ in fails:
        print("  " + f_)
    sys.exit(1)
print("all checks passed")
