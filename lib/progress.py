"""One call that says where a project actually is, with the numbers to prove it.

The waiting screen shows ten rows: four steps that run before the chain and the
chain's own six. `chain/state` only knows the six, and for each of those it
knows a status and nothing else - so a screen built on it can say "done" but
never "done, and here is what came out". Answering that per row meant a
different endpoint per stage, and the four pre-chain steps had no home at all.

**Two things the waiting screen used to show are deliberately not here.**

Progress *within* a stage - "11 of 15 directions generated" - is not something
the backend knows. A stage is dispatched, it runs inside n8n, and it reports
once at the end. Inventing a fraction from nothing would be a number that moves
and means nothing.

A remaining-time estimate is not here either. There is no measured basis for
one: the durations vary with the size of the literature and with how long a
model batch sits in a queue, and this system has run the full chain a handful
of times. `eta_note` says the honest thing instead. A screen that promises
"about 25 minutes" and takes two hours has taught the reader to distrust every
other number on it, and most of those are real.
"""

from db import connect

# The four steps that happen before the chain takes over. They are listed here
# rather than in chain.STAGE_PLAN on purpose: the chain must not try to
# dispatch them. W2 stops mid-workflow to have a human confirm the search
# concepts, so auto-advancing into it would produce an execution that waits
# thirty minutes and then dies.
PRE_CHAIN = (
    ("literature", "W2 文獻層"),
    ("harvest", "採集缺口句"),
    ("frame", "W1 領域框架"),
    ("ideas", "W3 想點子"),
)

ETA_NOTE = ("整條鏈通常 30–60 分鐘，實際時間取決於文獻量與模型排隊。"
            "系統不會估算剩餘時間——沒有量測基礎的數字比沒有數字更糟。"
            "跑到需要你決定的地方會停下來，不需要你守在這裡。")


def _step(key, label, status, detail, in_chain, extra=None):
    d = {"key": key, "label": label, "status": status,
         "in_chain": in_chain, "detail": detail}
    if extra:
        d.update(extra)
    return d


def build_steps(detail, runs, frame_present, harvest_status):
    """The ten rows, from counts already read. Pure - no database, no clock.

    Split out for the reason `chain.decide_next` is: the part that has to be
    right is which rows exist and when a row may call itself done, and a rule
    that can only be exercised by running the whole chain does not get
    exercised.

    A pre-chain step reads its status from its own output, because nothing
    dispatches it and so no `run` row describes it. `harvest` is the exception
    - it is a job with a real status of its own, including `failed`, and
    inferring "done" from a row count would turn a failed harvest that wrote
    some rows into a successful one.
    """
    import chain

    steps = []
    for key, label in PRE_CHAIN:
        d = detail.get(key) or {}
        if key == "harvest":
            status = harvest_status or "not started"
        elif key == "frame":
            status = "done" if frame_present else "not started"
        else:
            status = "done" if any(d.values()) else "not started"
        steps.append(_step(key, label, status, d, False))

    for s in chain.STAGE_PLAN:
        r = runs.get(s.name)
        steps.append(_step(
            s.name, s.label, r["status"] if r else "not started",
            detail.get(s.name) or {}, True,
            {"review_point": s.review, "pauses_by_default": s.pause_by_default,
             "error": r.get("error") if r else None,
             "finished_at": (r["finished_at"].isoformat()
                             if r and r.get("finished_at") else None)}))
    return steps


def project_progress(project_id):
    """Every step of this project, with what each one produced."""
    import chain

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, title, topic, status, domain_frame, usd_budget,"
            "       usd_spent, created_at FROM project WHERE id = %s",
            (project_id,))
        p = cur.fetchone()
        if not p:
            raise ValueError(f"no project {project_id}")

        cur.execute(
            "SELECT count(DISTINCT q.id) AS n_queries,"
            "       count(DISTINCT h.paper_id) AS n_papers "
            "FROM search_query q JOIN run r ON r.id = q.run_id "
            "LEFT JOIN search_hit h ON h.search_query_id = q.id "
            "WHERE r.project_id = %s", (project_id,))
        lit = cur.fetchone()

        cur.execute(
            "SELECT status, n_papers, n_with_fulltext, n_gap_sentences "
            "FROM harvest WHERE project_id = %s "
            "ORDER BY started_at DESC LIMIT 1", (project_id,))
        hv = cur.fetchone()

        cur.execute("SELECT count(*) AS n FROM idea WHERE project_id = %s",
                    (project_id,))
        n_ideas = int(cur.fetchone()["n"] or 0)

        cur.execute(
            "SELECT count(*) AS n_pairs,"
            "       count(*) FILTER (WHERE d.verdict = 'duplicate') AS n_dup,"
            "       count(*) FILTER (WHERE d.decided_by = 'human') AS n_human "
            "FROM dedup_pair d JOIN run r ON r.id = d.run_id "
            "WHERE r.project_id = %s", (project_id,))
        dd = cur.fetchone()

        cur.execute(
            "SELECT id FROM tournament WHERE project_id = %s "
            "ORDER BY created_at DESC LIMIT 1", (project_id,))
        t = cur.fetchone()
        tournament_id = str(t["id"]) if t else None
        tour = {"tournament_id": tournament_id, "n_matches": 0,
                "n_undecided": 0, "n_ranked": 0}
        if tournament_id:
            # Undecided matches are counted rather than hidden. A model that
            # returned no winner is stored as no winner and skipped by the
            # scoring - guessing one would move an Elo rating on evidence that
            # does not exist - so the count is the only thing that says how
            # much of the field was actually judged.
            cur.execute(
                "SELECT count(*) AS n,"
                "       count(*) FILTER (WHERE winner IS NULL) AS undecided "
                "FROM tournament_match WHERE tournament_id = %s",
                (tournament_id,))
            m = cur.fetchone()
            cur.execute("SELECT count(*) AS n FROM ranking "
                        "WHERE tournament_id = %s", (tournament_id,))
            tour.update(n_matches=int(m["n"] or 0),
                        n_undecided=int(m["undecided"] or 0),
                        n_ranked=int(cur.fetchone()["n"] or 0))

        cur.execute(
            "SELECT f.tier, count(*) AS n FROM ("
            "  SELECT DISTINCT ON (f2.idea_id) f2.idea_id, f2.tier"
            "    FROM feasibility f2 JOIN idea i2 ON i2.id = f2.idea_id"
            "   WHERE i2.project_id = %s"
            "   ORDER BY f2.idea_id, f2.assessed_at DESC) f "
            "GROUP BY f.tier", (project_id,))
        tiers = {r["tier"]: int(r["n"]) for r in cur.fetchall()}

        cur.execute(
            "SELECT v.verdict, count(*) AS n FROM ("
            "  SELECT DISTINCT ON (n2.idea_id) n2.idea_id, n2.verdict"
            "    FROM novelty_check n2 JOIN idea i2 ON i2.id = n2.idea_id"
            "   WHERE i2.project_id = %s AND n2.method = 'adversarial'"
            "   ORDER BY n2.idea_id, n2.checked_at DESC) v "
            "GROUP BY v.verdict", (project_id,))
        verdicts = {r["verdict"]: int(r["n"]) for r in cur.fetchall()}

        cur.execute(
            "SELECT count(DISTINCT d.idea_id) AS n_ideas, count(*) AS n_rounds,"
            "       coalesce(sum(d.n_objections_open), 0) AS n_open "
            "FROM debate_round d JOIN idea i ON i.id = d.idea_id "
            "WHERE i.project_id = %s", (project_id,))
        db_ = cur.fetchone()

        cur.execute(
            "SELECT count(DISTINCT r.idea_id) AS n FROM report r "
            "JOIN idea i ON i.id = r.idea_id WHERE i.project_id = %s",
            (project_id,))
        n_reports = int(cur.fetchone()["n"] or 0)

        cur.execute(
            "SELECT DISTINCT ON (stage) stage, status, error, finished_at "
            "FROM run WHERE project_id = %s AND stage = ANY(%s) "
            "ORDER BY stage, started_at DESC NULLS LAST",
            (project_id, chain.STAGE_NAMES))
        runs = {r["stage"]: r for r in cur.fetchall()}

    frame = p["domain_frame"] or None
    detail = {
        "literature": {"n_queries": int(lit["n_queries"] or 0),
                       "n_papers": int(lit["n_papers"] or 0)},
        "harvest": ({"n_papers": int(hv["n_papers"] or 0),
                     "n_with_fulltext": int(hv["n_with_fulltext"] or 0),
                     "n_gap_sentences": int(hv["n_gap_sentences"] or 0)}
                    if hv else {}),
        "frame": ({"q1": frame.get("q1"), "q2": frame.get("q2"),
                   "q3": frame.get("q3"),
                   "second_pack_forced": frame.get("second_pack_forced")}
                  if isinstance(frame, dict) else {}),
        "ideas": {"n_ideas": n_ideas},
        "dedup": {"n_pairs": int(dd["n_pairs"] or 0),
                  "n_duplicates": int(dd["n_dup"] or 0),
                  "n_overridden_by_hand": int(dd["n_human"] or 0)},
        "tournament": tour,
        "feasibility": {"counts": {t: tiers.get(t, 0) for t in "ABCD"},
                        "n_graded": sum(tiers.values())},
        "novelty": {"by_verdict": verdicts, "n_verified": sum(verdicts.values())},
        "debate": {"n_directions": int(db_["n_ideas"] or 0),
                   "n_rounds": int(db_["n_rounds"] or 0),
                   "n_objections_open": int(db_["n_open"] or 0)},
        "report": {"n_reports": n_reports},
    }

    steps = build_steps(detail, runs, bool(frame),
                        hv["status"] if hv else None)

    budget = None if p["usd_budget"] is None else float(p["usd_budget"])
    spent = float(p["usd_spent"] or 0)

    import db as _db
    chain_state, parked = _db._chain_state_of(
        {k: {"status": v["status"], "finished_at": v["finished_at"]}
         for k, v in runs.items()})

    return {
        "project_id": str(p["id"]), "topic": p["topic"], "title": p["title"],
        "created_at": p["created_at"].isoformat() if p["created_at"] else None,
        "chain_state": chain_state, "parked": parked,
        "spend": {"usd_budget": budget, "usd_spent": round(spent, 6),
                  "usd_remaining": (None if budget is None
                                    else round(budget - spent, 6))},
        "tournament_id": tournament_id,
        "steps": steps,
        "eta_note": ETA_NOTE,
    }
