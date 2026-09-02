"""Collision watch: re-run the searches, and only pay a model when something moved.

The question this asks daily is narrow: **has a paper appeared that was not
there last time?** Not "is this still novel" - that is a judgement, it needs a
model, and asking it every day about directions that have not changed is paying
for the same answer repeatedly.

So the watch is split. The diff is mechanical and free: same queries, same
sources, compare the identifiers that come back against the ones stored. Only
when the diff is non-empty does anything reach a model, and only for the
directions where something actually appeared.

That ordering is the whole design. A watch that costs money on quiet days gets
switched off, and a watch that is switched off finds nothing.

**What counts as watched**: a direction with an adversarial novelty check. That
check is what produced the queries this re-runs and the baseline it compares
against, so a direction without one has nothing to watch it with.
"""

import psycopg

import novelty
from db import connect


def watchlist(project_id, limit=20):
    """Directions worth re-checking, with the queries that first checked them.

    Ordered by tournament rank so that if a cap is applied it falls on the
    directions nobody is going to pursue rather than on the leaders.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT ON (n.idea_id) n.idea_id, n.id AS baseline_id,"
            "       n.rounds, n.closest_papers, n.verdict, n.checked_at,"
            "       i.code, i.title, i.statement,"
            "       (SELECT r.rank FROM ranking r"
            "          JOIN tournament t ON t.id = r.tournament_id"
            "         WHERE r.idea_id = n.idea_id AND t.project_id = i.project_id"
            "         ORDER BY t.created_at DESC LIMIT 1) AS rank "
            "FROM novelty_check n JOIN idea i ON i.id = n.idea_id "
            "WHERE i.project_id = %s AND n.method = 'adversarial' "
            "ORDER BY n.idea_id, n.checked_at DESC", (project_id,))
        rows = [dict(r) for r in cur.fetchall()]

        # The most recent watch per idea, so the diff is against what was known
        # last time rather than against the original check every day - otherwise
        # the same new paper is reported as new for the rest of time.
        cur.execute(
            "SELECT DISTINCT ON (idea_id) idea_id, rounds, checked_at "
            "FROM novelty_check WHERE method = 'collision_watch' "
            "  AND idea_id = ANY(%s) "
            "ORDER BY idea_id, checked_at DESC",
            ([r["idea_id"] for r in rows] or [None],))
        last_watch = {str(w["idea_id"]): dict(w) for w in cur.fetchall()}

    out = []
    for r in rows:
        idea_id = str(r["idea_id"])
        queries, seen = [], set()
        for rd in ((r["rounds"] or {}).get("rounds") or []):
            q = (rd.get("query") or "").strip()
            a = (rd.get("angle") or "").strip()
            if not q or a.lower() in seen:
                continue
            seen.add(a.lower())
            queries.append({"round": len(queries) + 1, "angle": a,
                            "vocabulary": rd.get("vocabulary"), "query": q})

        known = set()
        for rd in ((r["rounds"] or {}).get("rounds") or []):
            for p in rd.get("papers") or []:
                known.add(_key(p))
        for p in r["closest_papers"] or []:
            known.add(_key(p))

        # Anything a previous watch already reported is part of the baseline
        # now. Without this the first new paper is "new" every single day.
        w = last_watch.get(idea_id)
        if w:
            for rd in ((w["rounds"] or {}).get("rounds") or []):
                for p in rd.get("papers") or []:
                    known.add(_key(p))

        out.append({
            "idea_id": idea_id, "code": r["code"], "title": r["title"],
            "statement": r["statement"], "rank": r["rank"],
            "baseline_verdict": r["verdict"],
            "baseline_checked_at": r["checked_at"].isoformat(),
            "last_watched_at": (w["checked_at"].isoformat() if w else None),
            "queries": queries, "n_queries": len(queries),
            "known_keys": sorted(k for k in known if k),
            "n_known": len([k for k in known if k])})

    out.sort(key=lambda d: (d["rank"] is None, d["rank"] or 0))
    return {"project_id": project_id, "n": len(out),
            "watching": out[:limit],
            "note": ("a direction is watchable only once W7 has run on it - "
                     "that check supplies both the queries this re-runs and "
                     "the baseline it compares against")
            if not out else None}


def _key(p):
    if not isinstance(p, dict):
        return ""
    return (str(p.get("doi") or "").strip().lower()
            or str(p.get("pmid") or "").strip()
            or str(p.get("title") or "").strip().lower()[:80])


def diff_against(known_keys, rounds):
    """Which papers in this re-run were not in the baseline.

    Compared by identifier rather than by count. A count going up says the
    search was noisier today; a new identifier says a paper exists now that did
    not before, and only the second one is worth waking anybody for.
    """
    known = set(known_keys or [])
    fresh, seen = [], set()
    for rd in rounds or []:
        for p in rd.get("papers") or []:
            k = _key(p)
            if not k or k in known or k in seen:
                continue
            seen.add(k)
            fresh.append({"key": k, "angle": rd.get("angle"),
                          "query": rd.get("query"),
                          "title": p.get("title"), "year": p.get("year"),
                          "doi": p.get("doi"), "pmid": p.get("pmid"),
                          "citations": p.get("citations")})
    return fresh


def save_watch(idea_id, rounds, new_papers=None, verdict=None,
               coverage_limits=None, run_id=None):
    """Record one day's watch. Stored even when nothing changed.

    The quiet days are the evidence that the watch is running. Without them a
    watch that silently stopped a month ago looks exactly like a direction
    nobody has scooped.
    """
    fresh = new_papers or []
    limits = (coverage_limits or "").strip() or None
    if verdict in ("scooped", "incremental") and not fresh:
        raise ValueError(
            f"`{verdict}` says a specific paper has appeared, but this watch "
            "found nothing that was not already in the baseline. A verdict "
            "about prior work needs the work.")
    if verdict == "no_prior_art":
        raise ValueError(
            "a collision watch cannot conclude `no_prior_art`. It re-runs the "
            "queries the original check already used, so finding nothing new "
            "means nothing new was found by those queries - not that nothing "
            "exists. Leave the verdict null.")

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO novelty_check (idea_id, run_id, verdict, rounds,"
                "  closest_papers, coverage_limits, method) "
                "VALUES (%s,%s,%s,%s,%s,%s,'collision_watch') "
                "RETURNING id, checked_at",
                (idea_id, run_id, verdict,
                 psycopg.types.json.Jsonb({"rounds": rounds or [],
                                           "new_papers": fresh}),
                 psycopg.types.json.Jsonb(fresh),
                 limits))
            row = cur.fetchone()
        conn.commit()

    return {"watch_id": str(row["id"]), "idea_id": str(idea_id),
            "verdict": verdict, "n_new_papers": len(fresh),
            "collision": bool(fresh),
            "checked_at": row["checked_at"].isoformat()}


def watch_history(idea_id, limit=30):
    """Every watch for one direction, newest first."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, verdict, closest_papers, coverage_limits, checked_at "
            "FROM novelty_check "
            "WHERE idea_id = %s AND method = 'collision_watch' "
            "ORDER BY checked_at DESC LIMIT %s", (idea_id, int(limit)))
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            d["id"] = str(d["id"])
            d["n_new_papers"] = len(d.pop("closest_papers") or [])
            d["checked_at"] = d["checked_at"].isoformat()
            rows.append(d)
    return {"idea_id": str(idea_id), "n": len(rows), "watches": rows}


def run_watch_searches(queries, domain="clinical", limit=5):
    """Re-run the stored queries. Free - no model is involved."""
    return novelty.run_rounds(queries, domain=domain, limit=limit)
