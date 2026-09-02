"""Offline check of the pricing maths. No database, no models.

Run with `python tests/test_budget.py` from the repository root.

The important case is the last one: the price table must reproduce the tournament
run that was actually measured (execution 144, $2.661). A price table that is
merely plausible is how a budget guardrail lets through the thing it exists to
stop, so it is pinned to a real bill.
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

fake_pg = types.ModuleType("psycopg")
fake_pg.types = types.SimpleNamespace(json=types.SimpleNamespace(Jsonb=lambda x: x))
sys.modules["psycopg"] = fake_pg
fake_db = types.ModuleType("db")
fake_db.connect = lambda: (_ for _ in ()).throw(RuntimeError("no db in this test"))
sys.modules["db"] = fake_db

import budget

fails = []


def check(name, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{name}: got {got!r}, wanted {want!r}")
    print(("  ok  " if ok else " FAIL ") + name + f"  -> {got!r}")


def close(name, got, want, tol):
    ok = abs(got - want) <= tol
    if not ok:
        fails.append(f"{name}: got {got!r}, wanted {want!r} +/- {tol}")
    print(("  ok  " if ok else " FAIL ") + name + f"  -> {got!r}")


print("\n-- per-model rates --")
check("sonnet 5, 1M in", budget.price("claude-sonnet-5", 1_000_000, 0), 2.0)
check("sonnet 5, 1M out", budget.price("claude-sonnet-5", 0, 1_000_000), 10.0)
check("haiku 4.5 is half of sonnet 5",
      budget.price("claude-haiku-4-5", 1_000_000, 1_000_000),
      budget.price("claude-sonnet-5", 1_000_000, 1_000_000) / 2)
check("opus 5, 1M out", budget.price("claude-opus-5", 0, 1_000_000), 25.0)
check("gemini 3 flash, 1M out",
      budget.price("models/gemini-3-flash-preview", 0, 1_000_000), 3.0)

print("\n-- an unpriced model is refused, not recorded as free --")
try:
    budget.price("claude-something-not-released", 1000, 1000)
    check("unpriced model raises", False, True)
except ValueError as e:
    check("unpriced model raises", True, True)
    check("and says why", "indistinguishable from a cheap run" in str(e), True)

print("\n-- batch and cache multipliers --")
full = budget.price("claude-sonnet-5", 100_000, 100_000)
check("batch is half price",
      budget.price("claude-sonnet-5", 100_000, 100_000, batch=True), full / 2)
close("a cache read is a tenth of the input rate",
      budget.price("claude-sonnet-5", 0, 0, cache_read_tokens=1_000_000),
      0.2, 1e-9)

print("\n-- the quote helper --")
q = budget.quote("claude-sonnet-5", 230_925, 219_917)
close("as sent matches the measured tournament", q["as_sent"], 2.661, 0.002)
close("batching saves half of it", q["batch_saves"], q["as_sent"] / 2, 1e-6)
close("if_batched is the other half", q["if_batched"], q["as_sent"] / 2, 1e-6)

print("\n-- pinned to a real bill: execution 144 --")
# 151 calls, 230,925 input, 219,917 output, Sonnet 5. Reported $2.661.
measured = budget.price("claude-sonnet-5", 230_925, 219_917)
close("the price table reproduces the measured $2.661", measured, 2.661, 0.002)
print(f"       input  ${230_925 * 2.0 / 1e6:.4f}")
print(f"       output ${219_917 * 10.0 / 1e6:.4f}")
print(f"       total  ${measured:.4f}   (measured $2.661)")

print("\n-- what the levers would have done to that run --")
print(f"       batch only          ${measured / 2:.4f}")
print(f"       haiku 4.5 instead   ${budget.price('claude-haiku-4-5', 230_925, 219_917):.4f}")
print(f"       haiku + batch       ${budget.price('claude-haiku-4-5', 230_925, 219_917, batch=True):.4f}")

print()
if fails:
    print(f"{len(fails)} FAILED")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("all checks passed")
