"""Offline check of the debate rules. No database, no models.

Run with `python tests/test_debate.py` from the repository root. The rules that
decide whether a debate stops - and whether a concession is allowed to be
recorded - are pure functions on purpose, so they can be checked without paying
two models to argue.
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

# db and psycopg are only touched on the write path; the rules are not.
fake_pg = types.ModuleType("psycopg")
fake_pg.types = types.SimpleNamespace(json=types.SimpleNamespace(Jsonb=lambda x: x))
sys.modules["psycopg"] = fake_pg
fake_db = types.ModuleType("db")
fake_db.connect = lambda: (_ for _ in ()).throw(RuntimeError("no db in this test"))
sys.modules["db"] = fake_db

import debate

fails = []
def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, wanted {want!r}")
    print(("  ok  " if got == want else " FAIL ") + name + f"  -> {got!r}")

ORIG = ("Whether long-term residential exposure to combined traffic noise and "
        "fine particulate matter is associated with hemorrhagic stroke "
        "incidence in adults over 50, beyond either exposure alone.")

print("\n-- drift --")
check("identical text drifts 0", debate.drift(ORIG, ORIG), 0.0)
tightened = ORIG.replace("adults over 50", "adults aged 50 to 75")
d_small = debate.drift(ORIG, tightened)
print(f"       tightening one clause -> {d_small}")
check("a tightened clause stays under the cap", d_small <= debate.DRIFT_MAX, True)
different = ("Whether hospital readmission after elective knee arthroplasty is "
             "predicted by preoperative frailty indices in a national registry.")
d_big = debate.drift(ORIG, different)
print(f"       a different direction -> {d_big}")
check("a different direction trips the cap", d_big > debate.DRIFT_MAX, True)

print("\n-- distance to the closest paper --")
near = [{"title": "Traffic noise, fine particulate matter and hemorrhagic "
                  "stroke incidence in adults", "abstract": ""}]
far = [{"title": "Frailty and knee arthroplasty readmission", "abstract": ""}]
dn = debate._distance_to_closest(ORIG, near)
df = debate._distance_to_closest(ORIG, far)
print(f"       near {dn}   far {df}")
check("a near paper sits closer than a far one", dn < df, True)
check("no papers means no number", debate._distance_to_closest(ORIG, []), None)

print("\n-- vetting: the concession bar --")
clean, rej = debate.vet_objections([
    {"statement": "The exposure window is not defined.", "severity": "major",
     "axis": "soundness", "citation_support": "weak", "status": "unresolved",
     "rebuttal": "Defined as 5 years.", "rebuttal_score": 3},
    {"statement": "Confounding by SES reverses this.", "severity": "major",
     "axis": "soundness", "citation_support": "strong", "status": "unresolved",
     "cited": {"title": "SES and air pollution", "doi": "10.1/x"},
     "rebuttal": "Adjusted.", "rebuttal_score": 2},
])
check("both usable objections kept", len(clean), 2)
check("nothing rejected", rej, [])

clean, rej = debate.vet_objections([
    {"statement": "Fair point, I will soften the claim.", "severity": "minor",
     "axis": "contribution", "citation_support": "weak",
     "status": "resolved_by_evidence", "rebuttal_score": 3},
])
check("a 3 cannot concede to evidence", len(clean), 0)
check("and it says why", "you do not concede to plausible" in (rej[0]["why"] if rej else ""), True)

clean, rej = debate.vet_objections([
    {"statement": "Prior work settles this.", "severity": "major",
     "axis": "novelty", "citation_support": "strong", "status": "unresolved"},
])
check("strong without a paper is refused", len(clean), 0)

clean, rej = debate.vet_objections([
    {"statement": "Concede.", "severity": "major", "axis": "novelty",
     "citation_support": "strong", "status": "resolved_by_evidence",
     "cited": {"pmid": "12345"}, "rebuttal_score": 5},
])
check("a 5 with a paper concedes", len(clean), 1)

clean, rej = debate.vet_objections([
    {"statement": "x", "severity": "catastrophic", "axis": "novelty",
     "citation_support": "weak", "status": "unresolved"},
])
check("an invented severity is refused", len(clean), 0)

print("\n-- termination --")
cited_open = [{"status": "unresolved", "citation_support": "strong"}]
uncited_open = [{"status": "unresolved", "citation_support": "weak"}]

t, why, n_open, oc = debate.decide_termination(0.1, 2, cited_open)
check("a cited objection keeps it going", t, False)

t, why, n_open, oc = debate.decide_termination(0.1, 2, uncited_open)
check("uncited objections cannot keep it going", t, True)
check("but they are still counted", n_open, 1)
print(f"       reason: {why}")

t, why, n_open, oc = debate.decide_termination(0.9, 2, cited_open)
check("drift stops it even with a cited objection open", t, True)
check("and drift is the reason given", why.startswith("drift"), True)

t, why, n_open, oc = debate.decide_termination(0.9, debate.MAX_ROUNDS, cited_open)
check("drift outranks the round cap", why.startswith("drift"), True)

t, why, n_open, oc = debate.decide_termination(0.1, debate.MAX_ROUNDS, cited_open)
check("the cap stops it at round 10", t, True)
print(f"       reason: {why}")

t, why, n_open, oc = debate.decide_termination(0.1, 2, cited_open, "the user stopped it")
check("a caller reason is honoured last", why, "the user stopped it")

print()
if fails:
    print(f"{len(fails)} FAILED")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("all checks passed")
