"""The budget guardrail: what a stage would cost, checked before it starts.

Three decisions shape this file.

**Prices live here, on the server, and nowhere else.** Ten workflows each
carrying their own copy of a price table is ten copies that drift, and a drifted
copy does not error - it quietly reports the wrong number. The workflow reports
tokens; this computes dollars.

**An unpriced model is refused, not estimated.** If a model is not in the table,
recording its spend raises instead of writing zero. A run that silently records
$0 for an unpriced model looks exactly like a cheap run, and the guardrail would
wave through the one thing it exists to stop.

**The check asks "may this stage start", not "have we already overspent".**
Those are different questions and only the first one is useful. Arriving at the
tournament with $0.10 left and no estimate, the second question says yes and
then $2.66 goes out of the door. So a caller declares roughly what the stage
will cost, and a stage that cannot fit is refused before it spends anything.

Checked at stage boundaries, never mid-stage - the PRD is explicit and it is
right: stopping the tournament at match 300 pays two thirds of the money for a
ranking that means nothing.

**The budget belongs to the project, not to a run.** What the cap is for is one
full pass of the pipeline - W1 through W10 - and all ten hang off one project; a
`run` is one segment's record. The workflows say the same thing: only W5 and W5B
carry a `run_id` at all, the other seven know only their project. `run_id` is
still recorded on each spend as detail.
"""

import psycopg

from db import connect

# USD per 1,000,000 tokens. Anthropic first-party rates.
PRICES = {
    "claude-fable-5-1":  (10.00, 50.00),
    "claude-fable-5":    (10.00, 50.00),
    "claude-opus-5":      (5.00, 25.00),
    "claude-opus-4-8":    (5.00, 25.00),
    "claude-opus-4-7":    (5.00, 25.00),
    "claude-opus-4-6":    (5.00, 25.00),
    "claude-sonnet-5":    (2.00, 10.00),
    "claude-sonnet-4-6":  (3.00, 15.00),
    "claude-haiku-4-5":   (1.00,  5.00),
    # Google, for the generation side.
    "models/gemini-3-flash-preview": (0.50, 3.00),
    "gemini-3-flash-preview":        (0.50, 3.00),
}

# A cache read is billed at roughly a tenth of the input rate.
CACHE_READ_MULTIPLIER = 0.1
# Writing to the cache costs MORE than plain input - about a quarter more.
# Omitting this term was a real undercount: W5B's first batch wrote 1,055 tokens
# to cache and the guardrail recorded $0.0013 less than the workflow's own
# reckoning. Small here, systematic everywhere, and a guardrail whose number is
# quietly low is the one thing this file cannot be.
CACHE_WRITE_MULTIPLIER = 1.25
# The Batch API runs the same request asynchronously at half price.
BATCH_MULTIPLIER = 0.5


def price(model, input_tokens=0, output_tokens=0, cache_read_tokens=0,
          cache_write_tokens=0, batch=False):
    """What one call cost, in dollars. Refuses models it has no price for."""
    key = (model or "").strip()
    if key not in PRICES:
        raise ValueError(
            f"no price is known for model `{key}`. Add it to lib/budget.py "
            "rather than letting this call record as free - a run that logs $0 "
            "for an unpriced model is indistinguishable from a cheap run, and "
            "the budget would never stop it.")
    pin, pout = PRICES[key]
    usd = (int(input_tokens or 0) * pin / 1e6
           + int(output_tokens or 0) * pout / 1e6
           + int(cache_read_tokens or 0) * pin * CACHE_READ_MULTIPLIER / 1e6
           + int(cache_write_tokens or 0) * pin * CACHE_WRITE_MULTIPLIER / 1e6)
    if batch:
        usd *= BATCH_MULTIPLIER
    return round(usd, 6)


def quote(model, input_tokens=0, output_tokens=0, cache_read_tokens=0,
          cache_write_tokens=0):
    """What the same call would cost under each option. Nothing is recorded.

    Exists so the batch and caching decisions can be argued from this
    deployment's own numbers rather than from a blog post.
    """
    live = price(model, input_tokens, output_tokens, cache_read_tokens,
                 cache_write_tokens)
    return {"model": model, "as_sent": live,
            "if_batched": price(model, input_tokens, output_tokens,
                                cache_read_tokens, cache_write_tokens,
                                batch=True),
            "batch_saves": round(live * (1 - BATCH_MULTIPLIER), 6)}


def budget_status(project_id, estimate=None):
    """Where a project stands, and whether the next stage may start.

    `estimate` is what the caller expects the next stage to cost. Without it
    this can only answer the weaker question - whether the money has already run
    out - which is the question that lets a $2.66 tournament start on $0.10.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, topic, usd_budget, usd_spent FROM project "
            "WHERE id = %s", (project_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"no project {project_id}")

        cur.execute(
            "SELECT stage, sum(cost_usd) AS usd, sum(input_tokens) AS tin,"
            "       sum(output_tokens) AS tout, count(*) AS calls "
            "FROM token_usage WHERE project_id = %s GROUP BY stage "
            "ORDER BY sum(cost_usd) DESC NULLS LAST", (project_id,))
        by_stage = [{"stage": r["stage"], "usd": float(r["usd"] or 0),
                     "input_tokens": int(r["tin"] or 0),
                     "output_tokens": int(r["tout"] or 0),
                     "calls": int(r["calls"])} for r in cur.fetchall()]

    budget = None if row["usd_budget"] is None else float(row["usd_budget"])
    spent = float(row["usd_spent"] or 0)
    remaining = None if budget is None else round(budget - spent, 6)

    may_start, why = True, None
    if budget is None:
        why = ("no budget is set on this project, so nothing here can stop a "
               "runaway stage. POST /compute/run/budget to set one.")
    elif remaining <= 0:
        may_start = False
        why = (f"this project has spent ${spent:.4f} of its ${budget:.2f} "
               "budget. Nothing further may start.")
    elif estimate is not None and float(estimate) > remaining:
        may_start = False
        why = (f"the next stage is expected to cost about ${float(estimate):.2f} "
               f"but only ${remaining:.4f} is left of the ${budget:.2f} budget. "
               "Refused before it starts rather than halfway through - a stage "
               "stopped in the middle costs the money and produces nothing.")

    return {"project_id": str(row["id"]), "topic": row["topic"],
            "usd_budget": budget, "usd_spent": round(spent, 6),
            "usd_remaining": remaining,
            "estimate": None if estimate is None else float(estimate),
            "may_start": may_start, "why": why,
            "by_stage": by_stage}


def record_spend(project_id, stage, model, input_tokens=0, output_tokens=0,
                 cache_read_tokens=0, cache_write_tokens=0, batch=False,
                 calls=1, run_id=None):
    """Record what a stage actually spent and report whether that broke the budget.

    Called at the END of a stage with the numbers the workflow already measured
    for its own cost report - so the guardrail and the report can never disagree
    about what happened. `run_id` is detail: it says which segment this was, not
    whose budget it comes out of.
    """
    usd = price(model, input_tokens, output_tokens, cache_read_tokens,
                cache_write_tokens, batch)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO token_usage (project_id, run_id, stage, model,"
                "  input_tokens, output_tokens, cache_read_tokens,"
                "  cache_write_tokens, batch, cost_usd) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (project_id, run_id, stage, model, int(input_tokens or 0),
                 int(output_tokens or 0), int(cache_read_tokens or 0),
                 int(cache_write_tokens or 0),
                 bool(batch), usd))
            cur.execute(
                "UPDATE project SET usd_spent = usd_spent + %s WHERE id = %s "
                "RETURNING usd_budget, usd_spent", (usd, project_id))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"no project {project_id}")

            budget = None if row["usd_budget"] is None else float(row["usd_budget"])
            spent = float(row["usd_spent"])
            over = budget is not None and spent >= budget
        conn.commit()

    return {"project_id": str(project_id), "run_id": run_id,
            "stage": stage, "model": model,
            "usd": usd, "calls": int(calls), "batched": bool(batch),
            "usd_budget": budget, "usd_spent": round(spent, 6),
            "usd_remaining": None if budget is None else round(budget - spent, 6),
            "over_budget": over,
            "note": ("this project is now over budget. The next stage will be "
                     "refused until usd_budget is raised.") if over else None}


def set_budget(project_id, usd_budget):
    """Set or raise the cap on a project - one full pass of the pipeline."""
    b = float(usd_budget)
    if b < 0:
        raise ValueError("a budget cannot be negative")
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE project SET usd_budget = %s WHERE id = %s "
                "RETURNING usd_budget, usd_spent", (b, project_id))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"no project {project_id}")
        conn.commit()
    return {"project_id": str(project_id),
            "usd_budget": float(row["usd_budget"]),
            "usd_spent": float(row["usd_spent"]),
            "usd_remaining": round(float(row["usd_budget"]) - float(row["usd_spent"]), 6)}
