"""Adversarial novelty checking: run the searches, then refuse the sloppy verdicts.

The default stance is that somebody has already done this. Ten rounds try to
prove it, each from a different angle, and only when all ten fail does the idea
get to be called new - as a bounded negative, never as a fact about the world.

Two things here exist because a novelty verdict is the most over-claimed output
this system produces. Automated search can rule an idea out; it can never
establish that nothing exists. And searching abstracts is not reading papers -
scooping lives in secondary analyses and supplementary figures that no abstract
mentions.
"""

import time

import psycopg

import ops
from db import connect

VERDICTS = ("scooped", "incremental", "adjacent", "no_prior_art")

# Europe PMC is the source that answers most reliably from this deployment, and
# it is one service being asked ten questions in a row.
PAUSE = 0.4

# Three empty rounds in a row means the vocabulary is wrong, not that the field
# is empty. The skill is explicit that empty results in the early rounds usually
# mean the query is wrong, and adding more rounds in the same terminology is the
# way to turn a bad query into a confident false negative.
EMPTY_RUN = 3


def run_rounds(rounds, domain="general", limit=5):
    """Execute one search per round and report what each one found.

    Every paper in the output came back from an actual search. Nothing here
    invents an identifier, which is why the model downstream is given results to
    compare against rather than asked what it remembers.
    """
    out, seen_angles = [], set()
    for r in rounds or []:
        angle = (r.get("angle") or "").strip()
        query = (r.get("query") or "").strip()
        n = r.get("round")
        if not query:
            out.append({"round": n, "angle": angle, "query": None,
                        "error": "empty query", "n_hits": None})
            continue
        # A repeated angle is a paraphrase wearing a different number, and the
        # whole design of ten rounds is that they fail independently.
        key = angle.lower()
        if key and key in seen_angles:
            out.append({"round": n, "angle": angle, "query": query,
                        "error": "angle repeats an earlier round", "n_hits": None})
            continue
        seen_angles.add(key)

        try:
            res = ops.search_query(query, domain=domain,
                                   sources=r.get("sources"), limit=limit)
        except Exception as e:
            out.append({"round": n, "angle": angle, "query": query,
                        "error": f"{type(e).__name__}: {str(e)[:200]}",
                        "n_hits": None})
            time.sleep(PAUSE)
            continue

        papers = []
        for p in (res.get("results") or [])[:limit]:
            papers.append({k: p.get(k) for k in
                           ("title", "year", "doi", "pmid", "journal",
                            "citations", "source")
                           if p.get(k) is not None})
        out.append({
            "round": n, "angle": angle, "query": query,
            "vocabulary": r.get("vocabulary"),
            "n_hits": res.get("n", 0),
            "sources_answered": (res.get("attempt") or {}).get("answered"),
            "sources_failed": [f.get("source") for f in
                               ((res.get("attempt") or {}).get("failed") or [])],
            "papers": papers,
        })
        time.sleep(PAUSE)

    return {"n_rounds": len(out), "rounds": out,
            "empty_run": _longest_empty_run(out),
            "vocabularies": sorted({r.get("vocabulary") for r in out
                                    if r.get("vocabulary")})}


def _longest_empty_run(rounds):
    """The longest streak of rounds that found nothing.

    Reported rather than acted on here: what to do about it is the caller's
    decision, and the caller is the one that can write a query in another
    terminology.
    """
    best = run = 0
    for r in rounds:
        if r.get("n_hits") == 0:
            run += 1
            best = max(best, run)
        elif r.get("n_hits"):
            run = 0
    return best


def save_novelty(idea_id, verdict, rounds, run_id=None, closest_papers=None,
                 coverage_limits=None, facets=None, method="adversarial"):
    """Store an adversarial check, refusing verdicts nothing supports.

    Each refusal here corresponds to a way this output has been over-claimed:

    `scooped` and `incremental` are claims about a specific paper, so they need
    one. Without a citation they are an opinion wearing the clothes of a finding.

    `no_prior_art` is a bounded negative and needs its bounds. "The searches came
    up empty" and "nothing exists" are different statements and only the first
    is ever true; the coverage limits are what keeps them apart.

    Three consecutive empty rounds in one vocabulary means the query was wrong.
    Continuing in the same terminology and then calling the idea new is the
    dominant way false novelty claims are produced, so the check is structural.
    """
    v = (verdict or "").strip().lower() or None
    if v is not None and v not in VERDICTS:
        raise ValueError(f"verdict must be one of {', '.join(VERDICTS)}, or null")

    rounds = rounds or []
    angles = [(r.get("angle") or "").strip().lower() for r in rounds]
    dupes = sorted({a for a in angles if a and angles.count(a) > 1})
    if dupes:
        raise ValueError("these angles repeat, so those rounds are paraphrases "
                         "rather than independent attempts: " + ", ".join(dupes))

    if v in ("scooped", "incremental") and not (closest_papers or []):
        raise ValueError(f"`{v}` names a specific piece of prior work, so it "
                         "needs at least one paper from the searches. Without "
                         "one it is an opinion in the shape of a finding.")

    if v == "no_prior_art" and not (coverage_limits or "").strip():
        raise ValueError("`no_prior_art` is a bounded negative and needs its "
                         "bounds: which databases, which years, which "
                         "languages, and what was not searchable at all.")

    # A vocabulary switch is only demanded when the empties actually happened.
    empty = _longest_empty_run(rounds)
    vocabularies = {r.get("vocabulary") for r in rounds if r.get("vocabulary")}
    if v == "no_prior_art" and empty >= EMPTY_RUN and len(vocabularies) < 2:
        raise ValueError(
            f"{empty} rounds in a row found nothing and every round used the "
            "same terminology. Empty early rounds usually mean the query is "
            "wrong rather than the field is - run more rounds in a different "
            "vocabulary before calling this new.")

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO novelty_check (idea_id, run_id, verdict, rounds,"
                "  closest_papers, coverage_limits, method, facets, query_angles) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id, checked_at",
                (idea_id, run_id, v,
                 psycopg.types.json.Jsonb({"rounds": rounds,
                                           "longest_empty_run": empty}),
                 psycopg.types.json.Jsonb(closest_papers or []),
                 (coverage_limits or "").strip() or None,
                 method,
                 psycopg.types.json.Jsonb(facets) if facets else None,
                 psycopg.types.json.Jsonb([a for a in angles if a])))
            row = cur.fetchone()
        conn.commit()
    return {"novelty_check_id": str(row["id"]), "idea_id": idea_id,
            "verdict": v, "method": method, "n_rounds": len(rounds),
            "longest_empty_run": empty,
            "n_vocabularies": len(vocabularies),
            "checked_at": row["checked_at"].isoformat()}


def list_novelty(project_id=None, idea_ids=None, method="adversarial"):
    """The latest check of one kind per idea, with the direction written out."""
    where, args = ["n.method = %s"], [method]
    if project_id:
        where.append("i.project_id = %s")
        args.append(project_id)
    if idea_ids:
        where.append("n.idea_id = ANY(%s)")
        args.append(list(idea_ids))
    if len(where) == 1:
        raise ValueError("need project_id or idea_ids")

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT ON (n.idea_id) n.id, n.idea_id, n.verdict,"
            "       n.rounds, n.closest_papers, n.coverage_limits, n.facets,"
            "       n.query_angles, n.checked_at, i.code, i.title, i.statement "
            "FROM novelty_check n JOIN idea i ON i.id = n.idea_id "
            "WHERE " + " AND ".join(where) + " "
            "ORDER BY n.idea_id, n.checked_at DESC", args)
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            d["id"] = str(d["id"])
            d["idea_id"] = str(d["idea_id"])
            d["checked_at"] = d["checked_at"].isoformat()
            rows.append(d)

    by = {}
    for r in rows:
        by.setdefault(r["verdict"] or "no_ruling", []).append(r)
    return {"n": len(rows), "method": method,
            "counts": {k: len(v) for k, v in by.items()},
            "checks": rows}
