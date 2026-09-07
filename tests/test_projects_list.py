"""Offline check of the chain state shown on the project list. No database.

    python tests/test_projects_list.py

The list screen exists mainly to answer one question - "which of these is
waiting for me" - so the rule that decides `awaiting_you` is the rule that
decides whether the screen is worth having. It is pure, so it is pinned here
rather than exercised by starting a real chain and waiting for it to park.
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
fake_pg.connect = lambda **kw: (_ for _ in ()).throw(RuntimeError("no db here"))
sys.modules["psycopg"] = fake_pg
sys.modules["psycopg.types"] = fake_pg.types
sys.modules["psycopg.types.json"] = fake_pg.types.json
sys.modules["psycopg.rows"] = fake_pg.rows
fake_backup = types.ModuleType("backup")
fake_backup.pg_env = lambda: {}
sys.modules["backup"] = fake_backup

import db

fails = []


def check(name, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{name}: got {got!r}, wanted {want!r}")
    print(("  ok  " if ok else " FAIL ") + name + f"  -> {got!r}")


def run(**stages):
    """{stage: (status, finished)} -> the shape list_projects builds."""
    return {k: {"status": v[0], "finished_at": v[1]}
            for k, v in stages.items()}


DONE = ("done", "2026-09-05T00:00:00")
PARK = ("awaiting_review", "2026-09-05T00:00:00")

print("\n-- a project with no chain rows has not started, not 'idle' --")
state, parked = db._chain_state_of({})
check("state", state, "not_started")
check("nothing is parked", parked, None)

print("\n-- parked at a review point is the state the screen exists for --")
state, parked = db._chain_state_of(run(dedup=DONE, tournament=DONE,
                                       feasibility=PARK))
check("state", state, "awaiting_you")
check("names the stage", parked["stage"], "feasibility")
check("names the review point", parked["review_point"], "③")

print("\n-- two rows say awaiting_review and mean opposite things --")
_, a = db._chain_state_of(run(feasibility=PARK))
check("finished and parked -> review", a["awaiting"], "review")
_, b = db._chain_state_of(run(feasibility=("awaiting_review", None)))
check("never ran -> precondition", b["awaiting"], "precondition")

print("\n-- out of money is also waiting on you, and says so --")
state, parked = db._chain_state_of(run(dedup=DONE,
                                       tournament=("paused_budget", None)))
check("state", state, "awaiting_you")
check("keeps the raw status", parked["status"], "paused_budget")

print("\n-- when two stages are parked the earlier one in the chain wins --")
_, p = db._chain_state_of(run(feasibility=PARK, debate=PARK))
check("feasibility comes before debate", p["stage"], "feasibility")

print("\n-- moving beats everything that is only information --")
check("pending counts as running",
      db._chain_state_of(run(dedup=DONE, tournament=("pending", None)))[0],
      "running")
check("running counts as running",
      db._chain_state_of(run(dedup=("running", None)))[0], "running")

print("\n-- the chain is done when the last stage is, not when any stage is --")
check("report done",
      db._chain_state_of(run(dedup=DONE, report=DONE))[0], "done")
check("earlier stages done is not done",
      db._chain_state_of(run(dedup=DONE, tournament=DONE))[0], "idle")

print("\n-- stopped on purpose must not read as broken --")
check("failed",
      db._chain_state_of(run(dedup=DONE, tournament=("failed", None)))[0],
      "failed")
check("stopped",
      db._chain_state_of(run(dedup=DONE, tournament=("stopped", None)))[0],
      "stopped")
check("stopped is not failed",
      db._chain_state_of(run(tournament=("stopped", None)))[0] == "failed",
      False)

print("\n-- a park is never hidden behind a stage that also moved --")
check("parked wins over a done stage",
      db._chain_state_of(run(dedup=DONE, feasibility=PARK))[0], "awaiting_you")

print()
if fails:
    print(f"{len(fails)} FAILED")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("all checks passed")
