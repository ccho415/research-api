"""Offline check that review point ③b's screen reads fields that exist.

    python tests/test_pick_screen.py

No browser and no network: the two API replies the screen fetches are pasted in
as real captures, and the field expressions the screen uses are run against
them in Node.

Why this file exists. ③b is the screen where a person picks which directions
go on to a debate at about $0.40 each, having seen both the feasibility tier
and the novelty verdict. It reads `/compute/feasibility` and `/compute/novelty`
and joins them by `idea_id`.

Every one of those reads is a chance to name a field the API does not send, and
this project has done that five times in a day - venue, mesh, pmid, a debate
rebuttal, and a round count - without a single error. A wrong name here does
not crash the page: it renders a row with a blank tier, or `沒驗過` against a
direction that was in fact checked. Both are worse than a crash, because the
person makes the call anyway and the screen looks fine.

The `n_rounds` line below is not hypothetical. The screen was first written
reading `nvc.n_rounds`, which does not exist - the rounds are a blob under
`rounds.rounds`. It was caught by printing a real reply, which is what this
file does automatically from now on.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# Captured from project 82ffbcec on 2026-09-11. Trimmed to the fields the
# screen touches, with the shapes left exactly as the API sends them - the
# nesting of `rounds` is the whole point of keeping a real capture.
FEASIBILITY = {"assessments": [
    {"idea_id": "a-1", "code": 3,  "tier": "B",
     "title": "LVEDP x Chronic Coronary Syndromes x PCI"},
    {"idea_id": "a-2", "code": 10, "tier": "C",
     "title": "Branch Atheromatous Disease x DAPT x SAPT"},
    {"idea_id": "a-3", "code": 15, "tier": "C",
     "title": "glyceryl trinitrate x LVEDP x STEMI"},
    {"idea_id": "a-4", "code": 9,  "tier": "D",
     "title": "carotid web x asymptomatic x timing"},
]}

NOVELTY = {"n": 3, "checks": [
    {"idea_id": "a-1", "verdict": "incremental",
     "coverage_limits": "Searches ran across OpenAlex and EuropePMC.",
     "rounds": {"rounds": [{"round": i} for i in range(1, 15)]}},
    {"idea_id": "a-2", "verdict": "scooped",
     "coverage_limits": "Searches covered EuropePMC and OpenAlex indexing.",
     "rounds": {"rounds": [{"round": i} for i in range(1, 15)]}},
    {"idea_id": "a-3", "verdict": "adjacent",
     "coverage_limits": "No registry or dissertation search was possible.",
     "rounds": {"rounds": [{"round": i} for i in range(1, 15)]}},
]}

# The field expressions, copied from `screenPick` in frontend/index.html. If the
# screen changes and this does not, the check below that counts the rows still
# holds them together loosely - but the real guard is that a name which stops
# resolving shows up here as null.
JS = r"""
const fs = require('fs');
const {fe, nv} = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

const VERDICT_TXT = {scooped:'scooped', incremental:'incremental',
                     adjacent:'adjacent', no_prior_art:'no_prior_art'};

const board = fe.assessments || [];
const byId = {};
((nv.checks || nv.rows || nv.items) || []).forEach(c => {
  if (c && c.idea_id) byId[String(c.idea_id)] = c;
});

const rows = board.map(a => {
  const nvc = byId[String(a.idea_id)] || {};
  const v = (nvc.verdict || '').toLowerCase();
  return {
    code: a.code,
    tier: a.tier,
    title: a.title,
    verdict: v || null,
    verdict_known: v ? Boolean(VERDICT_TXT[v]) : null,
    checked_by_default: Boolean(v) && v !== 'scooped',
    n_rounds: (nvc.rounds && nvc.rounds.rounds) ? nvc.rounds.rounds.length : null,
    coverage: nvc.coverage_limits ? String(nvc.coverage_limits).slice(0, 200) : null,
  };
});
console.log(JSON.stringify(rows));
"""

fails = []


def check(name, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{name}: got {got!r}, wanted {want!r}")
    print(("  ok  " if ok else " FAIL ") + name + f"  -> {got!r}")


with tempfile.TemporaryDirectory() as d:
    data = os.path.join(d, "reply.json")
    script = os.path.join(d, "pick.js")
    with open(data, "w", encoding="utf-8") as f:
        json.dump({"fe": FEASIBILITY, "nv": NOVELTY}, f)
    with open(script, "w", encoding="utf-8") as f:
        f.write(JS)
    try:
        out = subprocess.run(["node", script, data], capture_output=True,
                             text=True, timeout=60)
    except FileNotFoundError:
        print("node is not on PATH - skipping (this check needs it)")
        sys.exit(0)

if out.returncode != 0:
    print("the screen's field expressions threw:\n" + out.stderr[:1500])
    sys.exit(1)

rows = json.loads(out.stdout)
by_code = {r["code"]: r for r in rows}

print("\n-- every graded direction gets a row, checked or not --")
check("all four rows rendered, including the two with no novelty verdict",
      len(rows), 4)
check("a direction the novelty stage never saw says so rather than going "
      "missing - it is still a direction, it just cannot be argued yet",
      by_code[9]["verdict"], None)

print("\n-- the join by idea_id actually joins --")
check("code 3 found its verdict", by_code[3]["verdict"], "incremental")
check("code 10 found its verdict", by_code[10]["verdict"], "scooped")
check("code 15 found its verdict", by_code[15]["verdict"], "adjacent")
check("no verdict came back under a name the screen does not know, which is "
      "how a real verdict renders as raw text",
      [r["code"] for r in rows if r["verdict_known"] is False], [])

print("\n-- the default ticks are the whole point of this screen --")
# Unticked-by-default for scooped, because that verdict is a count of papers
# matching the direction's own facets, not an opinion. Ticked for the rest,
# because agreeing with what the machine found should cost fewer clicks than
# disagreeing with it.
check("scooped starts unticked", by_code[10]["checked_by_default"], False)
check("incremental starts ticked", by_code[3]["checked_by_default"], True)
check("adjacent starts ticked - it is the healthy outcome, not a warning",
      by_code[15]["checked_by_default"], True)
check("never-checked starts unticked - an empty citation pool makes the "
      "critic unable to cite anything, so the debate ends in round one for "
      "the wrong reason",
      by_code[9]["checked_by_default"], False)
check("...so two of these four would go on to a debate",
      sum(1 for r in rows if r["checked_by_default"]), 2)

print("\n-- the fields that were wrong when this screen was written --")
check("the round count reads through `rounds.rounds`, not `n_rounds` - the "
      "latter does not exist and rendered a permanently blank cell",
      by_code[3]["n_rounds"], 14)
check("coverage_limits comes through, because a verdict chip alone asks to be "
      "believed and the coverage note is what makes it checkable",
      bool(by_code[10]["coverage"]), True)
check("tier comes through", by_code[9]["tier"], "D")
check("title comes through", bool(by_code[9]["title"]), True)

print()
if fails:
    print(f"{len(fails)} FAILED")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("all checks passed")
