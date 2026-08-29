"""Adversarial iteration: two models argue, and the concession bar is structural.

The failure this file exists to prevent is a debate that reads beautifully and
changes nothing. Two rounds of "that is a fair point, let me sharpen that" and
the direction comes out softer, vaguer, and indistinguishable from the version
that went in - having survived nothing, because nothing was actually thrown at
it.

Three things keep that from happening, and none of them are instructions in a
prompt:

**An objection without a citation cannot end the debate.** Only objections
carrying `citation_support = 'strong'` count toward "is there anything still
standing". Pure reasoning still gets recorded and still gets answered; it just
cannot be the reason a round is the last one.

**Three or below does not concede.** The rubric comes from `devils-advocate`:
1 restates, 2 appeals to authority, 3 is plausible but unevidenced, 4 brings
specific evidence, 5 reveals a misconception. `resolved_by_evidence` needs a 4,
and the database refuses anything less - so "you make a good point, however..."
has nowhere to be written down.

**Drift outranks the round cap.** Ten rounds of small accommodations can walk a
direction into a different direction while every single step looks reasonable.
Drift is measured against the *original* statement, never the previous round,
because measuring against the previous round is exactly how the walk stays
invisible.

The distance trajectory is the other half. A revision that answers a novelty
objection has to move the direction *away* from the closest paper; a revision
that moves it closer has answered the objection by drifting toward the prior
work, which is the opposite of the point.
"""

import psycopg

import triage
from db import connect

MAX_ROUNDS = 10

# Jaccard 0.5 against the original means half the vocabulary is new. Calibrated
# on nothing yet - no debate has ever run - so every round records its raw drift
# whether or not it trips this, and the threshold can be re-set from the
# trajectories without re-running anything. If early debates all stop at round 2
# for drift, that is the number being wrong, and it will say so out loud in
# `termination_reason` rather than quietly shortening every debate.
DRIFT_MAX = 0.5

SEVERITIES = ("major", "minor")
AXES = ("contribution", "novelty", "soundness", "feasibility")
SUPPORT = ("strong", "weak", "irrelevant")
STATUSES = ("resolved_by_evidence", "resolved_by_revision", "unresolved")


def _sim(a, b):
    """Token overlap between two pieces of text, 0 to 1.

    Jaccard rather than the tf-idf cosine used for the tournament: idf over a
    two-document corpus assigns weight zero to every token the two share, which
    is precisely the signal being measured here.
    """
    return triage.jaccard(triage.tokens(a or ""), triage.tokens(b or ""))


def drift(original, current):
    return round(1.0 - _sim(original, current), 4)


def _distance_to_closest(text, papers):
    """How far the current statement sits from the nearest thing already published.

    Reported as a distance so the direction of improvement is unambiguous:
    bigger is further away is better. Comparing titles and abstracts by token
    overlap is crude, and it is meant to be - it is a trajectory across rounds
    of one idea, not a claim about any single number.
    """
    best = 0.0
    for p in papers or []:
        s = _sim(text, " ".join(str(p.get(k) or "") for k in ("title", "abstract")))
        best = max(best, s)
    return round(1.0 - best, 4) if papers else None


def _evidence_pool(cur, idea_id, limit=40):
    """Every paper an actual search returned for this idea.

    The critic cites from this list and from nothing else. A model asked to
    support an objection with a citation, and given no citations, will produce a
    plausible DOI - so the way to stop fabricated references is to never put the
    model in that position.
    """
    cur.execute(
        "SELECT rounds, closest_papers FROM novelty_check "
        "WHERE idea_id = %s AND method = 'adversarial' "
        "ORDER BY checked_at DESC LIMIT 1", (idea_id,))
    row = cur.fetchone()
    if not row:
        return []

    seen, pool = set(), []
    def take(p):
        if not isinstance(p, dict):
            return
        title = (p.get("title") or "").strip()
        key = (p.get("doi") or p.get("pmid") or title.lower())[:200]
        if not title or not key or key in seen:
            return
        seen.add(key)
        pool.append({k: p.get(k) for k in
                     ("title", "year", "doi", "pmid", "journal", "venue",
                      "citations", "source")
                     if p.get(k) is not None})

    for p in row["closest_papers"] or []:
        take(p)
    for r in ((row["rounds"] or {}).get("rounds") or []):
        for p in r.get("papers") or []:
            take(p)
    return pool[:limit]


def _match_paper(cur, cite):
    """Link a citation to the cached paper, when one is actually the same paper.

    Matched on identifiers only. Title matching would silently attach an
    objection to a different paper with a similar name, and a wrong citation is
    worse than a missing one because it reads as verified.
    """
    if not isinstance(cite, dict):
        return None
    for col in ("doi", "pmid"):
        v = (cite.get(col) or "").strip()
        if v:
            cur.execute(f"SELECT id FROM paper WHERE {col} = %s LIMIT 1", (v,))
            row = cur.fetchone()
            if row:
                return row["id"]
    return None


def debate_state(idea_id):
    """Where this direction's debate stands, and what the critic may cite.

    The current text is the last round's revision, falling back to the idea as
    it was written. The original is always the idea as written - drift is
    measured against that and never against the previous round.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, code, title, statement, project_id "
                    "FROM idea WHERE id = %s", (idea_id,))
        idea = cur.fetchone()
        if not idea:
            raise ValueError(f"no idea {idea_id}")

        cur.execute(
            "SELECT id, round_no, idea_version_after, drift_from_original,"
            "       closest_paper_distance, terminated, termination_reason,"
            "       proposer_model, critic_model, created_at "
            "FROM debate_round WHERE idea_id = %s ORDER BY round_no", (idea_id,))
        rounds = cur.fetchall()

        cur.execute(
            "SELECT o.statement, o.severity, o.axis, o.citation_support,"
            "       o.status, o.rebuttal_score, r.round_no "
            "FROM objection o JOIN debate_round r ON r.id = o.debate_round_id "
            "WHERE r.idea_id = %s ORDER BY r.round_no", (idea_id,))
        objections = [dict(o) for o in cur.fetchall()]

        pool = _evidence_pool(cur, idea_id)

    original = (idea["statement"] or idea["title"] or "").strip()
    current = original
    for r in rounds:
        if (r["idea_version_after"] or "").strip():
            current = r["idea_version_after"].strip()

    last = rounds[-1] if rounds else None
    standing = [o for o in objections
                if o["status"] == "unresolved" and o["citation_support"] == "strong"]

    return {
        "idea_id": str(idea_id),
        "project_id": str(idea["project_id"]),
        "code": idea["code"], "title": idea["title"],
        "original_statement": original,
        "current_statement": current,
        "rounds_done": len(rounds),
        "next_round": len(rounds) + 1,
        "terminated": bool(last and last["terminated"]),
        "termination_reason": last["termination_reason"] if last else None,
        "drift_so_far": (float(last["drift_from_original"])
                         if last and last["drift_from_original"] is not None else 0.0),
        "distance_trajectory": [
            {"round": r["round_no"],
             "distance": (float(r["closest_paper_distance"])
                          if r["closest_paper_distance"] is not None else None),
             "drift": (float(r["drift_from_original"])
                       if r["drift_from_original"] is not None else None)}
            for r in rounds],
        "n_standing_objections": len(standing),
        "standing_objections": standing,
        "objections": objections,
        "n_evidence": len(pool),
        "evidence": pool,
        "max_rounds": MAX_ROUNDS,
        "drift_max": DRIFT_MAX,
    }


def save_round(idea_id, proposer_model, critic_model, objections,
               idea_version_after=None, novelty_recheck_id=None,
               termination_reason=None):
    """Record one exchange, and decide from the record whether it was the last.

    Termination is computed here rather than accepted from the caller, because
    the caller is a workflow holding a model's opinion about whether it is done,
    and "am I finished arguing" is the one question the arguing model should not
    answer.
    """
    if not (proposer_model or "").strip() or not (critic_model or "").strip():
        raise ValueError("both models must be named; the two must differ, and "
                         "an unnamed model cannot be checked against that")
    if proposer_model.strip() == critic_model.strip():
        raise ValueError(
            "proposer and critic are the same model. A model arguing with "
            "itself shares its own blind spots, and the transcript looks like "
            "a debate while being a monologue.")

    state = debate_state(idea_id)
    if state["terminated"]:
        raise ValueError(
            f"this debate already stopped at round {state['rounds_done']} "
            f"({state['termination_reason']}); reopening it would append "
            "rounds after a recorded ending")
    round_no = state["next_round"]
    if round_no > MAX_ROUNDS:
        raise ValueError(f"round {round_no} exceeds the cap of {MAX_ROUNDS}")

    before = state["current_statement"]
    after = (idea_version_after or "").strip() or before
    d = drift(state["original_statement"], after)

    clean, rejected = vet_objections(objections)
    terminated, reason, n_open, open_cited = decide_termination(
        d, round_no, clean, termination_reason)

    with connect() as conn:
        with conn.cursor() as cur:
            distance = None
            if novelty_recheck_id:
                cur.execute("SELECT closest_papers FROM novelty_check "
                            "WHERE id = %s", (novelty_recheck_id,))
                row = cur.fetchone()
                if row:
                    distance = _distance_to_closest(after, row["closest_papers"])

            cur.execute(
                "INSERT INTO debate_round (idea_id, round_no, proposer_model,"
                "  critic_model, idea_version_before, idea_version_after,"
                "  novelty_recheck_id, closest_paper_distance,"
                "  drift_from_original, n_objections_open, terminated,"
                "  termination_reason) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (idea_id, round_no, proposer_model.strip(), critic_model.strip(),
                 before, after, novelty_recheck_id, distance, d, n_open,
                 terminated, reason))
            rid = cur.fetchone()["id"]

            for o in clean:
                cur.execute(
                    "INSERT INTO objection (debate_round_id, statement, severity,"
                    "  axis, cited_paper_id, citation_support, rebuttal,"
                    "  rebuttal_score, status, cited) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (rid, o["statement"], o["severity"], o["axis"],
                     _match_paper(cur, o["cited"]), o["citation_support"],
                     o["rebuttal"], o["rebuttal_score"], o["status"],
                     psycopg.types.json.Jsonb(o["cited"]) if o["cited"] else None))
        conn.commit()

    return {"debate_round_id": str(rid), "idea_id": str(idea_id),
            "round_no": round_no, "drift_from_original": d,
            "closest_paper_distance": distance,
            "n_objections_saved": len(clean),
            "n_objections_open": n_open,
            "n_cited_open": len(open_cited),
            "terminated": terminated, "termination_reason": reason,
            "rejected": rejected or None}


def vet_objections(objections):
    """Keep the objections that mean something; say why the others were dropped.

    Rejected one at a time rather than failing the whole round. A critic that
    produced four usable objections and one softened concession should lose the
    concession, not the round - and the caller gets told which, so a model that
    keeps writing the same unusable shape shows up as a pattern instead of as a
    quietly shorter list.
    """
    clean, rejected = [], []
    for o in objections or []:
        st = (o.get("statement") or "").strip()
        if not st:
            continue
        sev = (o.get("severity") or "").strip().lower() or None
        ax = (o.get("axis") or "").strip().lower() or None
        sup = (o.get("citation_support") or "").strip().lower() or None
        stat = (o.get("status") or "").strip().lower() or "unresolved"
        score = o.get("rebuttal_score")
        cite = o.get("cited") or o.get("cited_paper")

        for val, allowed, name in ((sev, SEVERITIES, "severity"),
                                   (ax, AXES, "axis"),
                                   (sup, SUPPORT, "citation_support"),
                                   (stat, STATUSES, "status")):
            if val is not None and val not in allowed:
                rejected.append({"statement": st[:120], "why":
                                 f"{name} must be one of {', '.join(allowed)}"})
                break
        else:
            if score is not None and not (1 <= int(score) <= 5):
                rejected.append({"statement": st[:120],
                                 "why": "rebuttal_score must be 1 to 5"})
                continue
            # The rubric, enforced where it cannot be talked around: a 3 is
            # "plausible but unevidenced", and plausible is not a concession.
            if stat == "resolved_by_evidence" and (score is None or int(score) < 4):
                rejected.append({
                    "statement": st[:120],
                    "why": "conceding to evidence needs a rebuttal_score of 4 "
                           "or 5. At 3 or below the objection is plausible but "
                           "unevidenced, and you do not concede to plausible."})
                continue
            if sup == "strong" and not cite:
                rejected.append({
                    "statement": st[:120],
                    "why": "`strong` means this objection stands on a real "
                           "paper. Without one it is an opinion, so it is "
                           "recorded as reasoning rather than as evidence."})
                continue
            clean.append({"statement": st, "severity": sev, "axis": ax,
                          "citation_support": sup, "status": stat,
                          "rebuttal": (o.get("rebuttal") or "").strip() or None,
                          "rebuttal_score": None if score is None else int(score),
                          "cited": cite})
    return clean, rejected


def decide_termination(d, round_no, clean, termination_reason=None):
    """Whether this round was the last one, and in whose words.

    Order matters more than any single rule here. Drift is checked first because
    the round cap can never rescue a direction that has already become a
    different direction, and a debate that walked away from its own premise
    should say that rather than reporting a tidy "ten rounds completed".
    """
    # Only cited objections count toward continuing. Uncited ones are still
    # recorded and still get answered - they just cannot keep the debate alive.
    open_cited = [o for o in clean
                  if o["status"] == "unresolved" and o["citation_support"] == "strong"]
    n_open = len([o for o in clean if o["status"] == "unresolved"])

    terminated, reason = False, None
    if d > DRIFT_MAX:
        # First, and outranking the round cap: past here the thing being
        # defended is no longer the thing that was proposed.
        terminated = True
        reason = (f"drift {d} exceeds {DRIFT_MAX}; the revision has moved far "
                  "enough from the original that it is a different direction")
    elif not open_cited:
        terminated = True
        reason = ("no objection with a citation is still open"
                  + (f"; {n_open} uncited objection(s) remain recorded"
                     if n_open else ""))
    elif round_no >= MAX_ROUNDS:
        terminated = True
        reason = f"round cap of {MAX_ROUNDS} reached with {len(open_cited)} cited objection(s) still open"
    elif (termination_reason or "").strip():
        terminated = True
        reason = termination_reason.strip()

    return terminated, reason, n_open, open_cited


def apply_revision(idea_id, note=None):
    """Record the survived version as a child direction, never over the original.

    The revision is a new row with `parent_idea_id` set and `generation`
    incremented - the columns the schema already carries for exactly this. It is
    not an update, for two reasons. Drift is measured against the original
    statement, so overwriting that statement would retroactively make every
    recorded drift number zero. And a reader comparing the direction that went
    in with the one that came out is the entire product of this stage; an update
    deletes one side of that comparison.

    Separate from `save_round` on purpose. A debate can end in a revision nobody
    should adopt - drift-stopped, or ended because the critic could not cite
    anything - and promoting the text as a side effect of recording the argument
    would make that indistinguishable from a direction that won.
    """
    state = debate_state(idea_id)
    if not state["terminated"]:
        raise ValueError("the debate has not stopped yet; adopting a revision "
                         "mid-argument records a winner before the argument ends")
    if state["current_statement"] == state["original_statement"]:
        return {"idea_id": str(idea_id), "changed": False,
                "note": "no round revised the statement"}

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM idea WHERE id = %s", (idea_id,))
            src = dict(cur.fetchone())
            cur.execute(
                "SELECT id FROM idea WHERE parent_idea_id = %s "
                "AND generation = %s LIMIT 1",
                (idea_id, (src["generation"] or 0) + 1))
            existing = cur.fetchone()
            if existing:
                return {"idea_id": str(idea_id), "changed": False,
                        "revised_idea_id": str(existing["id"]),
                        "note": "this debate's revision was already adopted"}

            cur.execute(
                "INSERT INTO idea (project_id, code, title, statement, axis,"
                "  track, origin, source_note, required_variables,"
                "  method_sketch, grounding, why_matters, how_could_fail,"
                "  parent_idea_id, generation, status) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "RETURNING id, code",
                (src["project_id"],
                 (src["code"] + "d") if src["code"] else None,
                 src["title"], state["current_statement"], src["axis"],
                 src["track"], src["origin"],
                 note or state["termination_reason"],
                 psycopg.types.json.Jsonb(src["required_variables"])
                 if src["required_variables"] else None,
                 psycopg.types.json.Jsonb(src["method_sketch"])
                 if src["method_sketch"] else None,
                 psycopg.types.json.Jsonb(src["grounding"])
                 if src["grounding"] else None,
                 src["why_matters"], src["how_could_fail"],
                 idea_id, (src["generation"] or 0) + 1, src["status"]))
            row = cur.fetchone()
        conn.commit()
    return {"idea_id": str(idea_id), "revised_idea_id": str(row["id"]),
            "code": row["code"], "changed": True,
            "rounds": state["rounds_done"],
            "drift_from_original": state["drift_so_far"],
            "termination_reason": state["termination_reason"]}


def get_debate(idea_id):
    """The whole transcript, with every objection under its round."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, round_no, proposer_model, critic_model,"
            "       idea_version_before, idea_version_after,"
            "       novelty_recheck_id, closest_paper_distance,"
            "       drift_from_original, n_objections_open, terminated,"
            "       termination_reason, created_at "
            "FROM debate_round WHERE idea_id = %s ORDER BY round_no", (idea_id,))
        rounds = []
        for r in cur.fetchall():
            d = dict(r)
            d["id"] = str(d["id"])
            d["novelty_recheck_id"] = (None if d["novelty_recheck_id"] is None
                                       else str(d["novelty_recheck_id"]))
            for k in ("closest_paper_distance", "drift_from_original"):
                d[k] = None if d[k] is None else float(d[k])
            d["created_at"] = d["created_at"].isoformat()
            d["objections"] = []
            rounds.append(d)

        by_id = {r["id"]: r for r in rounds}
        cur.execute(
            "SELECT o.* FROM objection o "
            "JOIN debate_round r ON r.id = o.debate_round_id "
            "WHERE r.idea_id = %s ORDER BY r.round_no", (idea_id,))
        for o in cur.fetchall():
            d = dict(o)
            d["id"] = str(d["id"])
            rid = str(d.pop("debate_round_id"))
            d["cited_paper_id"] = (None if d["cited_paper_id"] is None
                                   else str(d["cited_paper_id"]))
            if rid in by_id:
                by_id[rid]["objections"].append(d)

    return {"idea_id": str(idea_id), "n_rounds": len(rounds), "rounds": rounds}
