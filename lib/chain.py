"""Stage auto-advance: what runs next, and where it stops for a human.

`run.pause_after` and `run.auto_advance_to` have been in `schema.sql` since day
one and **no line of code has ever touched them** - the same state the budget
guardrail was in. Until now every stage was advanced by a person opening the
next form.

Four decisions shape this file.

**The chain state lives in `run` rows, not in a hanging execution.** The PRD is
explicit about why: a workflow parked waiting for a human is an execution that
dies on a restart, times out, and takes the work with it. So a stage writes its
result, ends, and the *next* stage is a row somebody else picks up. Power loss
costs you the stage in flight, never the chain.

**The chain does not re-check the budget precisely.** Every stage workflow
already opens with its own `May We Afford This` node carrying that stage's
estimate. A second estimate here would be a second copy of the same number, and
a drifted copy does not error - it quietly disagrees. So this asks only the
coarse question ("is there any money left at all") and lets each stage refuse
itself with the number it actually knows.

**Stopping for a human is per-stage, and two stages stop by default.** The four
review points are ① after dedup, ② after the tournament, ③ after feasibility
grading, ④ after the debate. ③ and ④ default to stopping because everything
downstream of them is expensive and hard to walk back - grading decides which
directions get bought at $0.061 each, and the debate is what the report is
written from. ① and ② run through: de-duplication and ranking can be read
afterwards and re-run cheaply.

**A stage may only be queued once per project.** Two dispatcher ticks reading
the same pending row would start the tournament twice, and the tournament costs
$2.66. The unique index in migration 017 makes that impossible rather than
unlikely, and claiming is a single atomic UPDATE.
"""

import psycopg
from psycopg.types.json import Jsonb

import budget
from db import connect


class Stage:
    """One link in the chain.

    `rough_usd` is documentation and a sanity figure for the coarse check - it
    is deliberately NOT the number that guards the stage. That number lives in
    the stage's own workflow, computed from the field size it can actually see.
    """

    __slots__ = ("name", "label", "workflow_id", "rough_usd", "review", "pause_by_default")

    def __init__(self, name, label, workflow_id, rough_usd, review, pause_by_default):
        self.name = name
        self.label = label
        self.workflow_id = workflow_id
        self.rough_usd = rough_usd
        self.review = review
        self.pause_by_default = pause_by_default

    def as_dict(self):
        return {"stage": self.name, "label": self.label,
                "workflow_id": self.workflow_id, "rough_usd": self.rough_usd,
                "review_point": self.review,
                "pauses_by_default": self.pause_by_default}


# The chain, in order. W1/W2/harvest/W3 are deliberately not here: W2 stops
# mid-workflow for a human to confirm the search concepts, so auto-advancing
# into it would produce an execution that waits thirty minutes and then dies -
# exactly the pattern the PRD's design one exists to avoid.
STAGE_PLAN = (
    Stage("dedup",       "W4 去重",       "lzjAL1ONErAwLkoK", 0.05, "①", False),
    Stage("tournament",  "W5B 錦標賽",    "Ob0O5ufSMHF3XZrU", 0.30, "②", False),
    Stage("feasibility", "W6 可行性分級", "xKB9e0sepZPaPTYM", 0.06, "③", True),
    Stage("novelty",     "W7 新穎性驗證", "1PrxDrB7760V5vom", 0.25, None, False),
    Stage("debate",      "W8 唱反調",     "PSqvLA7DS4huNrSU", 0.50, "④", True),
    Stage("report",      "W9 最終報告",   "FIWgMalCUagYln9M", 0.30, None, False),
)

# Lists, not tuples, and every query below says `= ANY(%s)` rather than
# `IN %s`. psycopg2 expanded a tuple into an IN list; **psycopg3 does not** -
# it sends the parameter as one value and Postgres answers
# `syntax error at or near "$1"`. Caught by the first real call, because a
# database-free test cannot see it.
STAGE_NAMES = [s.name for s in STAGE_PLAN]

# Statuses that mean "this stage is spoken for". Used by the unique index and
# by the claim, and named once so the two cannot drift apart.
ACTIVE = ["pending", "running"]


def stage_at(name):
    for s in STAGE_PLAN:
        if s.name == name:
            return s
    return None


def successor(name):
    for i, s in enumerate(STAGE_PLAN):
        if s.name == name:
            return STAGE_PLAN[i + 1] if i + 1 < len(STAGE_PLAN) else None
    return None


def decide_next(stage, ok=True, pause_after=None):
    """What happens after `stage` finished. Pure - no database, no clock.

    Returns `(finished_status, next_stage_name, reason)`.

    Split out from the database work so the ordering rules can be tested
    without a connection, for the same reason `debate.decide_termination` is:
    the rule is the part that has to be right, and a rule that can only be
    exercised by spending money on a real run does not get exercised.
    """
    s = stage_at(stage)
    if s is None:
        return "failed", None, (
            f"`{stage}` is not a stage in the chain. Known stages: "
            + ", ".join(STAGE_NAMES))

    if not ok:
        # A failed stage stops the chain. Advancing past it would build the
        # report out of whatever half-finished state the failure left behind,
        # and that report would look exactly like a real one.
        return "failed", None, (
            f"{s.label} failed, so nothing downstream may start. Fix it, "
            "re-run this stage, and the chain resumes from here.")

    pause = s.pause_by_default if pause_after is None else bool(pause_after)
    nxt = successor(stage)

    if pause:
        where = f"審閱點 {s.review}" if s.review else "a pause set on this stage"
        if nxt is None:
            return "done", None, f"{s.label} was the last stage."
        return "awaiting_review", None, (
            f"{s.label} finished and the chain is parked at {where}. "
            f"Next would be {nxt.label}. POST /compute/chain/resume to continue.")

    if nxt is None:
        return "done", None, f"{s.label} was the last stage. The chain is complete."

    return "done", nxt.name, f"{s.label} finished; {nxt.label} is queued."


def missing_precondition(cur, stage_name, project_id):
    """What this stage needs that the project does not have yet, or None.

    Nothing blocks on a missing dataset any more. W6 used to throw when a
    project had no field inventory, so the chain refused to dispatch it; W6 now
    switches question instead - from "can this be done with what you have" to
    "what would it take to do this at all" - which is the more useful answer for
    somebody who has not collected anything yet, because it says what to go and
    get. Blocking here would take that away.

    Kept as the place stage preconditions go. It exists because dispatching a
    stage that is certain to fail is worse than not dispatching it: the first
    real chain queued feasibility, started W6, and W6 threw 0.3 seconds later,
    leaving a run stuck at `running`, a red execution and an alert - none of it
    news, because the condition was knowable beforehand. The next stage that
    genuinely cannot start without something belongs here rather than in a form
    field, because a form is answered once at the beginning about a state that
    changes later.
    """
    return None


def _queue(cur, project_id, stage_name, params):
    """Create the next run row, parked if the project cannot start it yet.

    Two reasons to park rather than queue: the money has run out, or the stage
    needs something the project does not have. Both are known here, and finding
    out later costs a failed execution and a stranded run row.

    The coarse budget question only. The precise one - can *this* stage afford
    to start - is asked by the stage's own first node, which knows the field
    size.
    """
    status, note = "pending", None

    blocked = missing_precondition(cur, stage_name, project_id)
    if blocked:
        # awaiting_review rather than paused_budget: this is waiting for a
        # person to supply something, which is what that status means, and
        # /compute/chain/resume already knows how to release it.
        status, note = "awaiting_review", blocked

    if status == "pending":
        try:
            b = budget.budget_status(project_id=project_id)
            if not b["may_start"]:
                status, note = "paused_budget", b["why"]
        except Exception as e:                          # noqa: BLE001
            # A budget lookup that errors must not silently queue the stage.
            status = "paused_budget"
            note = f"could not read the budget: {type(e).__name__}: {str(e)[:200]}"

    # Every stage is told which project it is for, whatever else the previous
    # stage handed forward. Without this a stage inherits `{}` and has no way
    # to find its own work - and the failure looks like an empty result rather
    # than a missing parameter.
    params = dict(params or {})
    params["project_id"] = str(project_id)

    s = stage_at(stage_name)
    nxt = successor(stage_name)
    cur.execute(
        "INSERT INTO run (project_id, stage, status, params, pause_after,"
        "                 auto_advance_to) "
        "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
        (project_id, stage_name, status, Jsonb(params or {}),
         s.pause_by_default, nxt.name if nxt else None))
    return str(cur.fetchone()["id"]), status, note


def advance(project_id=None, stage=None, ok=True, error=None, params=None,
            pause_after=None, run_id=None):
    """Record that `stage` finished for this project and queue what follows.

    Called by the stage workflow itself as its last act. The workflow does not
    decide what comes next and does not know the chain order - one place knows
    it, and that place is `STAGE_PLAN`.

    `run_id` is accepted instead of `project_id` for the same reason the budget
    endpoints accept it: W4's form asks for a run and nothing else, and making
    every form carry a second id the user was never shown is how ids get pasted
    wrong. Resolving it here costs one query.
    """
    finished_status, next_stage, reason = decide_next(stage, ok, pause_after)

    with connect() as conn:
        with conn.cursor() as cur:
            project_id = budget.project_of(cur, project_id, run_id)
            # Close the run this stage was dispatched as, if there was one. A
            # stage started by hand from its own form has no row, so one is
            # written retroactively - otherwise a manually re-run stage would
            # leave a hole in the chain's history and look like it never ran.
            # What this stage wants to hand forward is kept on its own row, not
            # only passed along. When the chain parks at a review point there is
            # no next stage to queue yet, so without this the handoff is dropped
            # on the floor and `resume` - which runs minutes or days later -
            # queues the next stage knowing only the project id.
            #
            # That is not a small loss. W6 works out which tiers are worth
            # looking at and passes `tiers`; lose it and W7 falls back to its
            # default A,B, which on a project with no data selects almost
            # nothing. The chain would carry on looking healthy while quietly
            # skipping ten of eleven directions.
            handoff = Jsonb(dict(params or {})) if params else None

            cur.execute(
                "UPDATE run SET status = %s, error = %s, finished_at = now(),"
                "               params = COALESCE(params,'{}'::jsonb)"
                "                        || jsonb_build_object('handoff',"
                "                               COALESCE(%s,'null'::jsonb)) "
                "WHERE id = (SELECT id FROM run WHERE project_id = %s "
                "            AND stage = %s AND status = ANY(%s) "
                "            ORDER BY started_at DESC NULLS LAST LIMIT 1) "
                "RETURNING id",
                (finished_status, error, handoff, project_id, stage, ACTIVE))
            row = cur.fetchone()
            if row:
                finished_run = str(row["id"])
            else:
                cur.execute(
                    "INSERT INTO run (project_id, stage, status, error, params,"
                    "                 started_at, finished_at) "
                    "VALUES (%s,%s,%s,%s,"
                    "        jsonb_build_object('handoff',"
                    "            COALESCE(%s,'null'::jsonb)), now(), now()) "
                    "RETURNING id",
                    (project_id, stage, finished_status, error, handoff))
                finished_run = str(cur.fetchone()["id"])

            queued_id, queued_status, note = (None, None, None)
            if next_stage:
                try:
                    queued_id, queued_status, note = _queue(
                        cur, project_id, next_stage, params)
                except psycopg.errors.UniqueViolation:
                    # The unique index did its job: this stage is already
                    # queued or running. Two dispatcher ticks racing is the
                    # normal cause, and the right answer is to do nothing.
                    conn.rollback()
                    return {"project_id": str(project_id), "stage": stage,
                            "finished_run": finished_run,
                            "finished_status": finished_status,
                            "next_stage": next_stage, "queued": False,
                            "reason": (f"{next_stage} is already queued or "
                                       "running for this project; nothing "
                                       "further was started.")}
        conn.commit()

    out = {"project_id": str(project_id), "stage": stage,
           "finished_run": finished_run, "finished_status": finished_status,
           "next_stage": next_stage, "reason": reason}
    if next_stage:
        s = stage_at(next_stage)
        out.update({"queued": queued_status == "pending",
                    "queued_run": queued_id, "queued_status": queued_status,
                    "next_workflow_id": s.workflow_id,
                    "next_label": s.label, "note": note})
    else:
        out["queued"] = False
    return out


def claim_next(limit=5):
    """Hand the dispatcher the stages that are due, and mark them taken.

    The claim is one atomic UPDATE rather than a read followed by a write: two
    dispatcher ticks a second apart would otherwise both see the same pending
    row and both start it, and starting the tournament twice costs $2.66 twice.
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE run SET status = 'running', started_at = now() "
                "WHERE id IN (SELECT id FROM run WHERE status = 'pending' "
                "             AND stage = ANY(%s) ORDER BY id LIMIT %s) "
                "RETURNING id, project_id, stage, params",
                (STAGE_NAMES, int(limit)))
            rows = cur.fetchall()
        conn.commit()

    out = []
    for r in rows:
        s = stage_at(r["stage"])
        out.append({"run_id": str(r["id"]), "project_id": str(r["project_id"]),
                    "stage": r["stage"], "label": s.label,
                    "workflow_id": s.workflow_id,
                    "params": r["params"] or {}})
    return {"claimed": len(out), "runs": out}


def state(project_id):
    """Where this project's chain stands, stage by stage."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT ON (stage) stage, id, status, error, params,"
            "       started_at, finished_at "
            "FROM run WHERE project_id = %s AND stage = ANY(%s) "
            "ORDER BY stage, started_at DESC NULLS LAST",
            (project_id, STAGE_NAMES))
        seen = {r["stage"]: r for r in cur.fetchall()}

    steps, parked = [], None
    for s in STAGE_PLAN:
        r = seen.get(s.name)
        step = s.as_dict()
        step["status"] = r["status"] if r else "not started"
        step["run_id"] = str(r["id"]) if r else None
        step["error"] = r["error"] if r else None
        step["finished_at"] = (r["finished_at"].isoformat()
                               if r and r["finished_at"] else None)
        if r and r["status"] in ("awaiting_review", "paused_budget") and not parked:
            parked = {"stage": s.name, "label": s.label,
                      "status": r["status"], "review_point": s.review}
        steps.append(step)

    return {"project_id": str(project_id), "steps": steps, "parked": parked,
            "note": ("nothing is parked; the chain is either running or has "
                     "not been started") if parked is None else None}


def stop(project_id, reason=None):
    """End a chain on purpose, so it stops looking like one that got stuck.

    A project with no data can never pass `feasibility`, and everything after it
    reads that stage's graded board - so the honest end of such a chain is the
    tournament ranking. Without this the run sits at `awaiting_review` for ever,
    which is the same thing a chain waiting on a person looks like. Somebody
    reading the board in three months cannot tell "nobody got round to it" from
    "this was the end, deliberately", and those call for opposite actions.

    Whatever is parked or queued is closed as `stopped`; finished stages are
    left alone, because they did happen.
    """
    why = (reason or "").strip() or "stopped by hand"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE run SET status = 'stopped', finished_at = now(),"
                "               error = %s "
                "WHERE project_id = %s AND stage = ANY(%s) "
                "  AND status IN ('pending','running','awaiting_review',"
                "                 'paused_budget') "
                "RETURNING stage",
                (f"chain stopped: {why}", project_id, STAGE_NAMES))
            closed = [r["stage"] for r in cur.fetchall()]
        conn.commit()

    return {"project_id": str(project_id), "stopped": True,
            "closed_stages": closed, "reason": why,
            "note": ("nothing further will be dispatched for this project. "
                     "POST /compute/chain/start to begin again from any stage "
                     "once whatever was missing is in place.")}


def resume(project_id, pause_after=False, params=None):
    """Unpark a chain that stopped at a review point or ran out of money.

    This is what the review interfaces will call once they exist. Until then it
    is called by hand - which is clunky, but it is honest: the alternative was
    running past the review points without telling anyone.

    `params` overrides what the finished stage handed forward. A review point is
    exactly where somebody learns something that should change the next stage:
    you read the graded board and only then know how many directions are worth
    verifying, or how many debate rounds the remaining budget will take. Without
    this the only way to adjust was to bypass `resume` entirely with a fresh
    `start`, which leaves the reviewed stage parked for ever and makes
    `chain/state` say the chain is waiting when it has already moved on.
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, stage, status, finished_at, params FROM run "
                "WHERE project_id = %s AND stage = ANY(%s) "
                "  AND status IN ('awaiting_review','paused_budget') "
                "ORDER BY finished_at DESC NULLS LAST, started_at DESC LIMIT 1",
                (project_id, STAGE_NAMES))
            row = cur.fetchone()
            if not row:
                return {"project_id": str(project_id), "resumed": False,
                        "reason": ("nothing is parked for this project. Either "
                                   "the chain never stopped, or it already "
                                   "resumed - check GET /compute/chain/state.")}

            # Two rows can wear `awaiting_review` and they mean opposite things.
            # One is a stage that ran, finished, and stopped at its review point.
            # The other was created parked because a precondition was missing and
            # has never run at all. Treating the second like the first would mark
            # the stage done and queue its successor - skipping it entirely,
            # silently, which is the exact failure the precondition check exists
            # to prevent. `finished_at` is what tells them apart.
            if row["status"] == "awaiting_review" and row["finished_at"] is None:
                still = missing_precondition(cur, row["stage"], project_id)
                if still:
                    return {"project_id": str(project_id), "resumed": False,
                            "stage": row["stage"], "reason": still}
                cur.execute("UPDATE run SET status = 'pending' WHERE id = %s",
                            (row["id"],))
                conn.commit()
                return {"project_id": str(project_id), "resumed": True,
                        "stage": row["stage"],
                        "reason": (f"{row['stage']} was waiting on something "
                                   "that is now present; it is queued.")}

            if row["status"] == "paused_budget":
                # This row IS the next stage - it was created parked, never
                # ran. Re-ask the coarse question rather than assuming the
                # budget was raised just because somebody pressed resume.
                b = budget.budget_status(project_id=project_id)
                if not b["may_start"]:
                    return {"project_id": str(project_id), "resumed": False,
                            "stage": row["stage"], "reason": b["why"]}
                cur.execute("UPDATE run SET status = 'pending' WHERE id = %s",
                            (row["id"],))
                conn.commit()
                return {"project_id": str(project_id), "resumed": True,
                        "stage": row["stage"],
                        "reason": f"{row['stage']} is queued again."}

            # awaiting_review: that stage really did finish. Close it and queue
            # what follows, with pause_after off so it does not park again on
            # the same point the moment it is released.
            cur.execute("UPDATE run SET status = 'done' WHERE id = %s",
                        (row["id"],))
            nxt = successor(row["stage"])
            if nxt is None:
                conn.commit()
                return {"project_id": str(project_id), "resumed": True,
                        "stage": row["stage"], "next_stage": None,
                        "reason": "that was the last stage; the chain is complete."}
            # What the finished stage asked to hand forward, kept on its row by
            # `advance` for exactly this moment. Releasing a review point is the
            # one transition where the handoff has to survive a gap of minutes
            # or days, and passing only the project id here silently undid the
            # work the stage did to decide what the next one should look at.
            handoff = ((row.get("params") or {}).get("handoff")) or {}
            if not isinstance(handoff, dict):
                handoff = {}
            forward = dict(handoff)
            # Merged over the handoff rather than replacing it: the reviewer is
            # changing one or two things they just learned about, not restating
            # everything the finished stage worked out. Passing `{"max_ideas":3}`
            # must not silently drop the `tiers` W6 spent a model call deciding.
            forward.update({k: v for k, v in (params or {}).items()
                            if v is not None})
            forward["project_id"] = str(project_id)

            try:
                queued_id, queued_status, note = _queue(
                    cur, project_id, nxt.name, forward)
            except psycopg.errors.UniqueViolation:
                conn.rollback()
                return {"project_id": str(project_id), "resumed": False,
                        "reason": f"{nxt.name} is already queued or running."}
            conn.commit()

    return {"project_id": str(project_id), "resumed": True,
            "stage": row["stage"], "next_stage": nxt.name,
            "next_label": nxt.label, "queued_run": queued_id,
            "queued_status": queued_status, "note": note,
            # Reported so that a handoff going missing is visible here rather
            # than only in the next stage's behaviour, where it looks like the
            # stage found nothing rather than like it was told nothing.
            "carried_forward": {k: v for k, v in forward.items()
                                if k != "project_id"} or None}


def start(project_id, stage="dedup", params=None):
    """Put a project onto the chain at a given stage.

    Defaults to the head of the chain. The stage before this - W3 writing ideas
    into the database - is still started by hand, and that is the seam the
    front half of the pipeline lives on.
    """
    if stage_at(stage) is None:
        raise ValueError(f"`{stage}` is not a chain stage. "
                         "Known: " + ", ".join(STAGE_NAMES))
    with connect() as conn:
        with conn.cursor() as cur:
            try:
                queued_id, queued_status, note = _queue(
                    cur, project_id, stage,
                    params or {"project_id": str(project_id)})
            except psycopg.errors.UniqueViolation:
                conn.rollback()
                raise ValueError(
                    f"`{stage}` is already queued or running for this project. "
                    "Two of the same stage would spend the money twice.")
        conn.commit()
    s = stage_at(stage)
    return {"project_id": str(project_id), "stage": stage, "label": s.label,
            "workflow_id": s.workflow_id, "run_id": queued_id,
            "status": queued_status, "note": note}


def set_pause(project_id, stage, pause_after):
    """Mark (or unmark) "stop here" on a stage before the chain reaches it."""
    if stage_at(stage) is None:
        raise ValueError(f"`{stage}` is not a chain stage.")
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE run SET pause_after = %s WHERE project_id = %s "
                "AND stage = %s AND status = ANY(%s) RETURNING id",
                (bool(pause_after), project_id, stage, ACTIVE))
            rows = cur.fetchall()
        conn.commit()
    return {"project_id": str(project_id), "stage": stage,
            "pause_after": bool(pause_after), "rows_updated": len(rows),
            "note": ("no queued or running row for that stage yet, so nothing "
                     "was marked. The default for this stage still applies: "
                     f"{stage_at(stage).pause_by_default}.") if not rows else None}
