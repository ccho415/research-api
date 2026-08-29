"""Storage for the tournament: anchors, matches, standings, and who was cut.

Kept apart from db.py because it carries a rule the rest of the data layer does
not: the ordering is lexicographic on contribution, and feasibility only ever
breaks a tie. Several things here exist to stop that order being quietly
inverted, and they are easier to see together.
"""

from collections import defaultdict

import psycopg

from db import connect


def _groups(a):
    """The search slots, or nothing. Never an empty list.

    An empty list would reach the check as a direction with no terms, which
    builds a query of nothing but a date filter - that matches most of MEDLINE
    and comes back as the most confident possible answer from no evidence.
    """
    g = a.get("term_groups")
    if not g or not isinstance(g, list):
        return None
    return psycopg.types.json.Jsonb(g)


def _year(a):
    y = a.get("cutoff")
    try:
        y = int(y)
    except (TypeError, ValueError):
        return None
    return y if 1800 <= y <= 2100 else None


def save_anchors(anchors):
    """Seed or update the calibration anchors.

    Two grades, never one. An anchor rejected because the data was not
    obtainable is `grade_feasibility = weak` while its contribution may be
    strong - the VLA ultrasound case was rejected with "very novel, but cannot
    be finished in one to two years" written down. Collapsing those into a
    single score teaches the scale that important-but-hard work is bad, which
    is the exact inversion the lexicographic order exists to prevent.
    """
    out = []
    with connect() as conn:
        with conn.cursor() as cur:
            for a in anchors or []:
                title = (a.get("title") or "").strip()
                if not title:
                    continue
                origin = a.get("origin") or "local"
                # external_id is the identity; the title is only a label. An
                # anchor can be reframed - the quantum one was, from applying a
                # method to testing whether the method's claimed advantage holds
                # - and reframing rewrites the title. Keyed on the title, that
                # update silently becomes an insert, and the tournament then
                # has the same anchor twice at two different grades.
                ext = (a.get("external_id") or "").strip()
                if ext:
                    cur.execute("SELECT id FROM anchor WHERE external_id = %s"
                                "  AND origin = %s", (ext, origin))
                else:
                    cur.execute("SELECT id FROM anchor WHERE title = %s"
                                "  AND origin = %s", (title, origin))
                row = cur.fetchone()
                if row:
                    cur.execute(
                        "UPDATE anchor SET title = %s, statement = %s,"
                        "  evidence = %s, grade_contribution = %s,"
                        "  grade_feasibility = %s, field = %s,"
                        "  term_groups = %s, cutoff = %s"
                        " WHERE id = %s RETURNING id",
                        (title, a.get("statement"),
                         psycopg.types.json.Jsonb(a.get("evidence") or {}),
                         a.get("grade_contribution"), a.get("grade_feasibility"),
                         a.get("field"), _groups(a), _year(a), row["id"]))
                else:
                    cur.execute(
                        "INSERT INTO anchor (source, external_id, title, statement,"
                        "  evidence, grade_contribution, grade_feasibility, origin,"
                        "  field, term_groups, cutoff) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                        "RETURNING id",
                        (a.get("source"), a.get("external_id"), title,
                         a.get("statement"),
                         psycopg.types.json.Jsonb(a.get("evidence") or {}),
                         a.get("grade_contribution"), a.get("grade_feasibility"),
                         origin, a.get("field"), _groups(a), _year(a)))
                out.append(str(cur.fetchone()["id"]))
        conn.commit()
    return {"n": len(out), "anchor_ids": out}


def list_anchors(origin=None, limit=50):
    where, args = [], []
    if origin:
        where.append("origin = %s")
        args.append(origin)
    args.append(int(limit))
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, source, external_id, title, statement, evidence,"
            "       grade_contribution, grade_feasibility, origin, field,"
            "       term_groups, cutoff, added_at "
            "FROM anchor " + clause + " ORDER BY added_at LIMIT %s", args)
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            d["id"] = str(d["id"])
            d["added_at"] = d["added_at"].isoformat()
            rows.append(d)
    return {"n": len(rows), "anchors": rows}


def start_tournament(project_id, run_id=None, criteria=None, k_factor=32):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tournament (project_id, run_id, criteria, k_factor) "
                "VALUES (%s, %s, %s, %s) RETURNING id, created_at",
                (project_id, run_id, psycopg.types.json.Jsonb(criteria or []), k_factor))
            row = cur.fetchone()
        conn.commit()
    return {"tournament_id": str(row["id"]), "project_id": project_id,
            "run_id": run_id, "created_at": row["created_at"].isoformat()}


def save_field_reduction(tournament_id, removed):
    """Why each direction was cut before the tournament began.

    The reason column accepts two values and the database enforces it. A real
    run once eliminated candidates for being outside the researcher's own
    methods, which smuggles a personal constraint into a judgement that is
    supposed to be about contribution to the field. A rule that lives only in
    an instruction gets broken quietly and nothing afterwards can tell.
    """
    out = []
    with connect() as conn:
        with conn.cursor() as cur:
            for r in removed or []:
                if not r.get("idea_id"):
                    continue
                cur.execute(
                    "INSERT INTO field_reduction (tournament_id, idea_id, reason,"
                    "  detail, decided_by) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (tournament_id, r["idea_id"], r.get("reason"), r.get("detail"),
                     r.get("decided_by")))
                out.append(str(cur.fetchone()["id"]))
        conn.commit()
    return {"n": len(out)}


def _side(entry):
    """A competitor is an idea or an anchor, never both and never neither."""
    e = entry or {}
    kind = "anchor" if e.get("kind") == "anchor" else "idea"
    return kind, e.get("id")


def save_matches(tournament_id, matches):
    """Every judged pairing, anchor matches included.

    Anchor matches are what turn a relative ordering into a scale. Leaving them
    out would make the standings impossible to rebuild from the database, and
    the report has to be readable without re-running anything.
    """
    n = 0
    with connect() as conn:
        with conn.cursor() as cur:
            for m in matches or []:
                lk, lid = _side(m.get("left"))
                rk, rid = _side(m.get("right"))
                if not lid or not rid:
                    continue
                cur.execute(
                    "INSERT INTO tournament_match (tournament_id, batch, left_idea,"
                    "  right_idea, left_anchor, right_anchor, winner, reason,"
                    "  judged_by, judged_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,"
                    "        CASE WHEN %s::text IS NULL THEN NULL ELSE now() END)",
                    (tournament_id, m.get("batch"),
                     lid if lk == "idea" else None,
                     rid if rk == "idea" else None,
                     lid if lk == "anchor" else None,
                     rid if rk == "anchor" else None,
                     m.get("winner"), m.get("reason"), m.get("judged_by"),
                     m.get("winner")))
                n += 1
        conn.commit()
    return {"n_matches": n}


def save_rankings(tournament_id, rankings):
    n = 0
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ranking WHERE tournament_id = %s",
                        (tournament_id,))
            for r in rankings or []:
                kind, rid = _side(r)
                if not rid:
                    continue
                cur.execute(
                    "INSERT INTO ranking (tournament_id, idea_id, anchor_id, elo,"
                    "  wins, losses, ties, rank, calibration_band) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (tournament_id, rid if kind == "idea" else None,
                     rid if kind == "anchor" else None, r.get("elo"),
                     r.get("wins") or 0, r.get("losses") or 0, r.get("ties") or 0,
                     r.get("rank"), r.get("calibration_band")))
                n += 1
        conn.commit()
    return {"n_ranked": n}


def get_tournament(tournament_id):
    """The standings with every competitor's statement written out.

    Joined in rather than left as ids, for the same reason the deduplication
    view does it: a table of codes cannot be judged, and being judged is the
    entire purpose of showing it to anyone.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, project_id, run_id, criteria, k_factor, created_at "
                    "FROM tournament WHERE id = %s", (tournament_id,))
        t = cur.fetchone()
        if not t:
            return None

        cur.execute(
            "SELECT r.rank, r.elo, r.wins, r.losses, r.ties, r.calibration_band,"
            "       r.idea_id, r.anchor_id, i.code,"
            "       i.title AS idea_title, i.statement AS idea_statement,"
            "       a.title AS anchor_title, a.statement AS anchor_statement,"
            "       a.grade_contribution "
            "FROM ranking r "
            "LEFT JOIN idea i ON i.id = r.idea_id "
            "LEFT JOIN anchor a ON a.id = r.anchor_id "
            "WHERE r.tournament_id = %s ORDER BY r.rank NULLS LAST",
            (tournament_id,))
        standings = []
        for row in cur.fetchall():
            d = dict(row)
            is_anchor = d["anchor_id"] is not None
            standings.append({
                "rank": d["rank"],
                "elo": float(d["elo"]) if d["elo"] is not None else None,
                "wins": d["wins"], "losses": d["losses"], "ties": d["ties"],
                "is_anchor": is_anchor,
                "calibration_band": d["calibration_band"],
                "anchor_grade": d["grade_contribution"] if is_anchor else None,
                "id": str(d["anchor_id"] if is_anchor else d["idea_id"]),
                "code": d["code"],
                "title": d["anchor_title"] if is_anchor else d["idea_title"],
                "statement": d["anchor_statement"] if is_anchor else d["idea_statement"],
            })

        cur.execute("SELECT count(*) AS n, count(winner) AS judged "
                    "FROM tournament_match WHERE tournament_id = %s", (tournament_id,))
        m = cur.fetchone()
        cur.execute("SELECT fr.reason, count(*) AS n FROM field_reduction fr "
                    "WHERE fr.tournament_id = %s GROUP BY fr.reason", (tournament_id,))
        removed = {r["reason"]: r["n"] for r in cur.fetchall()}

    return {"tournament_id": str(t["id"]), "project_id": str(t["project_id"]),
            "run_id": None if t["run_id"] is None else str(t["run_id"]),
            "criteria": t["criteria"], "k_factor": float(t["k_factor"]),
            "created_at": t["created_at"].isoformat(),
            "n_matches": m["n"], "n_judged": m["judged"],
            "removed_before_start": removed,
            "standings": standings}


def resolve_duplicates(run_id, decided_by="rule", dry_run=False):
    """Decide which of each duplicated pair stays on the field.

    `dedup_pair` records that two directions are the same and stops there. Left
    like that both twins enter the tournament, split the wins between them and
    land mid-table, and nothing about the standings looks wrong - which is why
    this has to happen before pairing rather than being noticed after.

    Pairs are collapsed transitively. If A duplicates B and B duplicates C, one
    of the three survives, even though A and C were never compared directly; the
    alternative keeps two near-identical directions because a single pairwise
    call happened not to fire.

    Only `verdict = 'duplicate'` collapses. A null verdict is the model saying
    it could not tell, and the PRD routes those to a person - treating uncertain
    as duplicate would silently discard exactly the pairs that needed review.

    The survivor is the more complete record, ties broken by which was written
    first. Neither twin is more correct than the other, so the rule cannot be
    about merit; it is about losing the least, since the judge reads the
    statement and the fuller record gives it more to read. A person can overrule
    it, which is why nothing is deleted.
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT idea_a, idea_b FROM dedup_pair "
                "WHERE run_id = %s AND verdict = 'duplicate'", (run_id,))
            pairs = [(str(r["idea_a"]), str(r["idea_b"])) for r in cur.fetchall()]
            if not pairs:
                return {"run_id": run_id, "n_clusters": 0, "n_merged": 0,
                        "clusters": [], "dry_run": dry_run}

            parent = {}

            def find(x):
                parent.setdefault(x, x)
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            for a, b in pairs:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb

            members = defaultdict(list)
            for node in list(parent):
                members[find(node)].append(node)

            ids = sorted(parent)
            cur.execute(
                "SELECT id, code, title, statement, method_sketch,"
                "       required_variables, grounding, why_matters,"
                "       how_could_fail, created_at, merged_into,"
                "       merge_decided_by "
                "FROM idea WHERE id = ANY(%s)", (ids,))
            row = {str(r["id"]): dict(r) for r in cur.fetchall()}

            def completeness(i):
                r = row.get(i) or {}
                return sum(1 for f in ("method_sketch", "required_variables",
                                       "grounding", "why_matters",
                                       "how_could_fail") if r.get(f))

            clusters, merged = [], []
            for group in members.values():
                group = [g for g in group if g in row]
                if len(group) < 2:
                    continue
                # A person's earlier call on any member settles the whole
                # cluster: a rule must not quietly reverse a human decision on
                # the next run.
                human = [g for g in group
                         if (row[g].get("merge_decided_by") == "human"
                             and row[g].get("merged_into") is None)]
                if human:
                    keep = sorted(human, key=lambda i: row[i]["created_at"])[0]
                    basis = "kept by a person"
                else:
                    keep = sorted(group, key=lambda i: (-completeness(i),
                                                        row[i]["created_at"]))[0]
                    basis = "fullest record, then written first"
                losers = [g for g in group if g != keep]
                clusters.append({
                    "keep": keep, "keep_code": row[keep].get("code"),
                    "keep_title": row[keep].get("title"),
                    "basis": basis,
                    "merged": [{"id": g, "code": row[g].get("code"),
                                "title": row[g].get("title"),
                                "completeness": completeness(g)} for g in losers],
                })
                merged += [(g, keep) for g in losers]

            if not dry_run:
                for loser, keep in merged:
                    if row[loser].get("merge_decided_by") == "human":
                        continue
                    cur.execute(
                        "UPDATE idea SET merged_into = %s, merge_decided_by = %s,"
                        "  merge_decided_at = now() WHERE id = %s",
                        (keep, decided_by, loser))
        if not dry_run:
            conn.commit()

    return {"run_id": run_id, "n_clusters": len(clusters),
            "n_merged": len(merged), "clusters": clusters, "dry_run": dry_run}


def live_ideas(project_id=None, run_id=None, limit=200):
    """The directions still standing: nothing merged away, newest check attached.

    Separate from `db.list_ideas` on purpose. That one is what the review
    screens read and it must keep showing everything, merged rows included -
    "where did that direction go" is a question a person will ask. This one is
    what the tournament reads, and it must never return a merged row, because
    the way that fails is invisible in the standings.
    """
    where, args = ["i.merged_into IS NULL"], []
    if project_id:
        where.append("i.project_id = %s")
        args.append(project_id)
    if run_id:
        where.append("n.run_id = %s")
        args.append(run_id)
    args.append(int(limit))
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT i.id, i.code, i.title, i.statement, i.axis, i.track,"
            "       i.method_sketch, i.required_variables, i.grounding,"
            "       i.why_matters, i.how_could_fail, i.created_at,"
            "       n.verdict, n.rounds, n.coverage_limits "
            "FROM idea i "
            "LEFT JOIN LATERAL ("
            "    SELECT * FROM novelty_check c WHERE c.idea_id = i.id"
            "    ORDER BY c.checked_at DESC LIMIT 1"
            ") n ON true "
            "WHERE " + " AND ".join(where) + " "
            "ORDER BY i.created_at, i.code LIMIT %s", args)
        out = []
        for r in cur.fetchall():
            d = dict(r)
            d["id"] = str(d["id"])
            d["created_at"] = d["created_at"].isoformat()
            out.append(d)
    return {"n": len(out), "ideas": out}
