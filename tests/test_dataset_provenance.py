"""Can a described inventory pass itself off as a measured one?

The feasibility grader leans on the measured fields - it is told to judge row
structure separately from variables and to name real counts in its power note.
A `documented` inventory has none of them, and if it carries them anyway they
were invented. A tier A built on an invented missing rate reads exactly like one
built on a real measurement, which is the whole reason this marker exists.

Offline: `save_dataset` is exercised up to the point it would touch the
database, so the validation runs and the insert never does.

    python tests/test_dataset_provenance.py
"""

import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

# psycopg is a deployment dependency, not a test one. Everything being checked
# here happens before a connection is opened, so a stub keeps this runnable on a
# laptop - which is the only place it will ever actually be run.
if "psycopg" not in sys.modules:
    pg = types.ModuleType("psycopg")
    pg.rows = types.ModuleType("psycopg.rows")
    pg.rows.dict_row = object()
    pg.types = types.ModuleType("psycopg.types")
    pg.types.json = types.ModuleType("psycopg.types.json")
    pg.types.json.Jsonb = lambda v: v
    pg.Error = Exception
    sys.modules["psycopg"] = pg
    sys.modules["psycopg.rows"] = pg.rows
    sys.modules["psycopg.types"] = pg.types
    sys.modules["psycopg.types.json"] = pg.types.json

FAILURES = []


def check(name, got, want):
    ok = got == want
    print(f"  {'ok ' if ok else 'FAIL'} {name}  -> {got!r}")
    if not ok:
        FAILURES.append(f"{name}: got {got!r}, want {want!r}")


# connect() is the first thing the insert touches; stopping there keeps this
# offline while still running every check above it.
class Stop(Exception):
    pass


import db  # noqa: E402

db.connect = lambda *a, **k: (_ for _ in ()).throw(Stop("reached the insert"))

import datasets  # noqa: E402


def save(inv):
    """The error, or 'INSERT' when validation let it through."""
    try:
        datasets.save_dataset("p1", inv)
    except Stop:
        return "INSERT"
    except ValueError as e:
        return str(e)
    return "NO ERROR"


def col(**kw):
    base = {"name": "os_months", "dtype": "number"}
    base.update(kw)
    return base


def inv(provenance=None, column=None, extra=None):
    out = {"files": [{"filename": "clinical.csv",
                      "columns": [column or col()]}]}
    if provenance:
        out["provenance"] = provenance
    if extra:
        out.update(extra)
    return out


print("\n-- provenance defaults to measured, because it used to be the only kind --")
check("absent is accepted", save(inv()), "INSERT")
check("measured is accepted", save(inv("measured")), "INSERT")
check("documented is accepted", save(inv("documented")), "INSERT")
check("anything else is refused",
      save(inv("guessed")).startswith("provenance must be one of"), True)

print("\n-- a documented inventory may not carry measurements --")

for field, value in [("missing_rate", 0.03), ("n_unique", 180),
                     ("levels", ["alive", "dead"]), ("min", 0), ("max", 96)]:
    got = save(inv("documented", col(**{field: value})))
    check(f"documented + {field} is refused", field in got, True)

print("\n-- the same fields are exactly what a measured inventory is for --")

check("measured + missing_rate is fine",
      save(inv("measured", col(missing_rate=0.03))), "INSERT")
check("measured + levels is fine",
      save(inv("measured", col(name="vital_status", levels=["alive", "dead"]))),
      "INSERT")

print("\n-- what a documented inventory MAY carry --")

check("names, dtype, description, joins_on",
      save(inv("documented", col(dtype="number", description="總存活月數",
                                 joins_on="variants.tsv:barcode"))),
      "INSERT")
check("a null measurement is absence, not a value",
      save(inv("documented", col(missing_rate=None, n_unique=None))), "INSERT")

print("\n-- rows are refused whatever the provenance says --")

for banned in ["rows", "data", "records", "sample_rows", "head"]:
    got = save(inv("documented", extra={banned: [{"patient": "P001"}]}))
    check(f"`{banned}` is refused", banned in got, True)

print("\n-- a personal column still may not carry values --")

got = save(inv("measured", col(name="patient_id", personal=True,
                               levels=["P001", "P002"])))
check("personal + levels is refused", "personal" in got, True)

got = save(inv("documented", col(name="patient_id", personal=True)))
check("personal without values is fine", got, "INSERT")

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("all checks passed")
