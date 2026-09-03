"""Offline check of the chain's ordering rules. No database, no n8n.

Run with `python tests/test_chain.py` from the repository root.

The rules being tested are the ones that decide whether $2.66 gets spent, and
they are exactly the rules a real run exercises once an hour at best. So they
are pulled out into `decide_next`, which is pure, and pinned here.
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

import chain

fails = []


def check(name, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{name}: got {got!r}, wanted {want!r}")
    print(("  ok  " if ok else " FAIL ") + name + f"  -> {got!r}")


print("\n-- the chain is the six stages, in this order --")
check("the order", list(chain.STAGE_NAMES),
      ["dedup", "tournament", "feasibility", "novelty", "debate", "report"])
check("W4 is the head", chain.STAGE_PLAN[0].workflow_id, "lzjAL1ONErAwLkoK")
check("the tournament link is W5B, not W5",
      chain.stage_at("tournament").workflow_id, "Ob0O5ufSMHF3XZrU")

print("\n-- migration 017's CHECK must list exactly these names --")
# A name in the plan but not in the CHECK cannot be written, and the chain
# dead-ends. A name in the CHECK but not the plan is a stage nothing can run.
sql = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "migrations",
                        "017_chain_can_only_queue_a_stage_once.sql"),
           encoding="utf-8").read()
for name in chain.STAGE_NAMES:
    check(f"`{name}` appears in the migration", f"'{name}'" in sql, True)

print("\n-- ordinary advance --")
check("dedup hands over to the tournament",
      chain.decide_next("dedup")[:2], ("done", "tournament"))
check("the tournament hands over to feasibility",
      chain.decide_next("tournament")[:2], ("done", "feasibility"))
check("novelty hands over to the debate",
      chain.decide_next("novelty")[:2], ("done", "debate"))
check("the report is the end of the chain",
      chain.decide_next("report")[:2], ("done", None))

print("\n-- the two review points that stop by default --")
# 3 and 4 park; everything downstream of them is expensive and hard to undo.
check("feasibility parks at review point 3",
      chain.decide_next("feasibility")[:2], ("awaiting_review", None))
check("the debate parks at review point 4",
      chain.decide_next("debate")[:2], ("awaiting_review", None))
check("dedup does NOT park at review point 1",
      chain.decide_next("dedup")[0], "done")
check("the tournament does NOT park at review point 2",
      chain.decide_next("tournament")[0], "done")

print("\n-- a parked stage says what would have run next --")
_, _, why = chain.decide_next("feasibility")
check("and names the stage it is holding back", "W7 新穎性驗證" in why, True)
check("and says how to release it", "chain/resume" in why, True)

print("\n-- pause_after overrides the default in both directions --")
check("feasibility can be told to run through",
      chain.decide_next("feasibility", pause_after=False)[:2], ("done", "novelty"))
check("dedup can be told to stop",
      chain.decide_next("dedup", pause_after=True)[0], "awaiting_review")

print("\n-- a failed stage stops the chain --")
status, nxt, why = chain.decide_next("tournament", ok=False)
check("status is failed", status, "failed")
check("nothing is queued after a failure", nxt, None)
check("and it says why that matters", "nothing downstream" in why, True)

print("\n-- an unknown stage is refused, not silently ignored --")
status, nxt, why = chain.decide_next("tournamnet")   # typo on purpose
check("a typo does not quietly end the chain", status, "failed")
check("and the reply lists the real stage names", "tournament" in why, True)

print("\n-- successor / stage_at agree with the plan --")
check("nothing follows the report", chain.successor("report"), None)
check("successor of an unknown stage is None", chain.successor("nope"), None)
check("stage_at of an unknown stage is None", chain.stage_at("nope"), None)

print("\n-- the front half is deliberately absent --")
for absent in ("lit_search", "harvest", "ideas", "domain_frame"):
    check(f"`{absent}` is not a chain stage", chain.stage_at(absent), None)


print("\n-- no stage is blocked on a precondition any more --")


class FakeCur:
    """Fails loudly if anything queries; nothing here should."""

    def __init__(self):
        self.asked = None

    def execute(self, sql, args=None):
        self.asked = sql

    def fetchone(self):
        return None


# A missing dataset used to block `feasibility`. It no longer does, and that is
# the point: W6 switches question instead of refusing, so a researcher with no
# data still gets told what each direction would cost to make answerable. A
# block here would quietly take that away again.
for stage in chain.STAGE_NAMES + ["nope"]:
    cur = FakeCur()
    check(f"`{stage}` is not blocked",
          chain.missing_precondition(cur, stage, "p1"), None)
    check(f"`{stage}` does not query", cur.asked, None)

print()
if fails:
    print(f"{len(fails)} FAILED")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("all checks passed")
