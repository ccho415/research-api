"""The data layer for feasibility: what you have, what you want, what that allows.

Three tables that only make sense together. `dataset` is the field inventory
produced locally by `tools/inventory.py` - never rows, only the shape of them.
`research_profile` is what the researcher can actually do: the time they have,
the approvals they hold, the methods they know. `feasibility` is the grading of
one direction against both.

The rule that shapes this file is that the grading is a second axis and never a
reordering. A tier C direction can be worth far more than a tier A one, and
collapsing that into one number is how people end up doing whatever their data
happens to allow.
"""

import psycopg

from db import connect

TIERS = ("A", "B", "C", "D")


def save_dataset(project_id, inventory, filename=None, pack=None):
    """Store a field inventory. Refuses anything carrying rows.

    The local tool does not emit rows, but this endpoint is reachable with any
    body, and an inventory is exactly the shape a careless paste of the source
    data would also have. The check is cheap and the mistake is unrecoverable:
    once a clinical extract reaches a server it cannot be taken back.
    """
    if not isinstance(inventory, dict):
        raise ValueError("inventory must be an object")
    for banned in ("rows", "data", "records", "sample_rows", "head"):
        if banned in inventory:
            raise ValueError(
                f"inventory carries a `{banned}` key, which is where raw rows "
                "would be. Upload what tools/inventory.py produced, unedited.")

    files = inventory.get("files") or []
    pii = []
    for f in files:
        for c in f.get("columns") or []:
            if c.get("personal"):
                pii.append({"file": f.get("filename"), "column": c.get("name"),
                            "because": c.get("personal_because")})
            # A column flagged personal must not carry values. The local tool
            # already withholds them; this catches an inventory that was edited
            # by hand between profiling and upload.
            if c.get("personal") and (c.get("levels") or "min" in c):
                raise ValueError(
                    f"column `{c.get('name')}` is flagged personal but still "
                    "carries levels or a range. Re-run tools/inventory.py "
                    "rather than editing its output.")

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO dataset (project_id, filename, pack, inventory,"
                "                     pii_columns) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id, profiled_at",
                (project_id, filename or inventory.get("filename"),
                 pack or inventory.get("pack"),
                 psycopg.types.json.Jsonb(inventory),
                 psycopg.types.json.Jsonb(pii)))
            row = cur.fetchone()
        conn.commit()
    return {"dataset_id": str(row["id"]), "project_id": project_id,
            "n_files": len(files),
            "n_columns": sum(len(f.get("columns") or []) for f in files),
            "n_personal_columns": len(pii),
            "profiled_at": row["profiled_at"].isoformat()}


def list_datasets(project_id):
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, filename, pack, inventory, pii_columns, profiled_at "
            "FROM dataset WHERE project_id = %s ORDER BY profiled_at DESC",
            (project_id,))
        out = []
        for r in cur.fetchall():
            d = dict(r)
            d["id"] = str(d["id"])
            d["profiled_at"] = d["profiled_at"].isoformat()
            out.append(d)
    return {"project_id": project_id, "n": len(out), "datasets": out}


def save_profile(project_id, content, derived_from=None):
    """A new version of the research profile. Old versions are never rewritten.

    Each planning round has different conditions - a different dataset, a
    different deadline, a different set of approvals - so this is versioned per
    project rather than being one global setting. A report read later has to say
    which conditions it was graded under.
    """
    if not isinstance(content, dict) or not content:
        raise ValueError("content must be a non-empty object")
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT coalesce(max(version), 0) + 1 AS v "
                        "FROM research_profile WHERE project_id = %s",
                        (project_id,))
            version = cur.fetchone()["v"]
            cur.execute(
                "INSERT INTO research_profile (project_id, version, content,"
                "                              derived_from) "
                "VALUES (%s, %s, %s, %s) RETURNING id, uploaded_at",
                (project_id, version, psycopg.types.json.Jsonb(content),
                 derived_from))
            row = cur.fetchone()
        conn.commit()
    return {"profile_id": str(row["id"]), "project_id": project_id,
            "version": version, "uploaded_at": row["uploaded_at"].isoformat()}


def get_profile(project_id):
    """The current profile, or an explicit statement that there is none.

    A null here is not an empty result. The PRD requires that grading without a
    profile still runs, and that every tier it produces is marked as a generic
    default rather than a judgement about this researcher - so the absence has
    to travel, not be silently treated as an empty object.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, version, content, uploaded_at FROM research_profile "
            "WHERE project_id = %s ORDER BY version DESC LIMIT 1", (project_id,))
        row = cur.fetchone()
    if not row:
        return {"project_id": project_id, "profile": None,
                "note": "no research profile uploaded; feasibility tiers must "
                        "be marked as generic defaults rather than as "
                        "judgements about this researcher"}
    return {"project_id": project_id, "version": row["version"],
            "uploaded_at": row["uploaded_at"].isoformat(),
            "profile": row["content"]}


def save_feasibility(assessments, dataset_id=None):
    """Store one tier per direction, refusing the ones that say nothing.

    B and C mean "not yet, and here is the way there". Without the missing
    variable and the route, they mean "no" while looking like "maybe", which is
    the failure mode that matters here: a reader plans around a B they cannot
    actually reach.
    """
    saved, rejected = [], []
    with connect() as conn:
        with conn.cursor() as cur:
            for a in assessments or []:
                idea_id = a.get("idea_id")
                tier = (a.get("tier") or "").strip().upper()
                if not idea_id:
                    continue
                if tier not in TIERS:
                    rejected.append({"idea_id": idea_id, "tier": a.get("tier"),
                                     "why": "tier must be A, B, C or D"})
                    continue
                missing = a.get("missing")
                route = (a.get("route_to_tier_a") or "").strip()
                if tier in ("B", "C") and not (missing and route):
                    rejected.append({
                        "idea_id": idea_id, "tier": tier,
                        "why": "B and C must name the missing variable and the "
                               "route to A; without both the tier reads as "
                               "reachable when nothing says it is"})
                    continue
                cur.execute(
                    "INSERT INTO feasibility (idea_id, dataset_id, tier,"
                    "  missing, route_to_tier_a, design, power_note) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (idea_id, dataset_id or a.get("dataset_id"), tier,
                     psycopg.types.json.Jsonb(missing) if missing else None,
                     route or None, a.get("design"), a.get("power_note")))
                saved.append({"feasibility_id": str(cur.fetchone()["id"]),
                              "idea_id": idea_id, "tier": tier})
        conn.commit()
    return {"n_saved": len(saved), "n_rejected": len(rejected),
            "saved": saved, "rejected": rejected or None}


def list_feasibility(project_id=None, idea_ids=None):
    """The grading with each direction written out in full, in tournament order.

    Joined in rather than left as ids, for the reason the PRD gives about every
    screen in this system: a table of codes cannot be judged, and being judged
    is the entire purpose of showing it to anyone.

    The rank is joined in for a narrower reason. Every consumer of this endpoint
    takes the head of a tier and spends money on it - a novelty check, a debate
    between two models - and until this ordering existed the head was whichever
    direction happened to sort first by uuid. The callers said they were taking
    the highest-ranked and they were taking an arbitrary one, which is the exact
    shape of mistake this system is built to make impossible rather than
    unlikely. Directions with no ranking sort last rather than first, so an
    ungraded one never quietly wins the position.
    """
    where, args = [], []
    if project_id:
        where.append("i.project_id = %s")
        args.append(project_id)
    if idea_ids:
        where.append("f.idea_id = ANY(%s)")
        args.append(list(idea_ids))
    if not where:
        raise ValueError("need project_id or idea_ids")

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT ON (f.idea_id) f.id, f.idea_id, f.dataset_id,"
            "       f.tier, f.missing, f.route_to_tier_a, f.design,"
            "       f.power_note, f.assessed_at,"
            "       i.code, i.title, i.statement,"
            # The latest tournament for this idea's project, because a project
            # can be re-run and the older standings are not the current answer.
            "       (SELECT r.rank FROM ranking r"
            "          JOIN tournament t ON t.id = r.tournament_id"
            "         WHERE r.idea_id = f.idea_id AND t.project_id = i.project_id"
            "         ORDER BY t.created_at DESC LIMIT 1) AS rank "
            "FROM feasibility f JOIN idea i ON i.id = f.idea_id "
            "WHERE " + " AND ".join(where) + " "
            "ORDER BY f.idea_id, f.assessed_at DESC", args)
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            d["id"] = str(d["id"])
            d["idea_id"] = str(d["idea_id"])
            d["dataset_id"] = None if d["dataset_id"] is None else str(d["dataset_id"])
            d["assessed_at"] = d["assessed_at"].isoformat()
            rows.append(d)

    # DISTINCT ON forces its own ORDER BY, so the ranking is applied here rather
    # than in the query. Unranked last, then by code, then by title - never by
    # tier, which would make feasibility the primary axis by the back door.
    rows.sort(key=lambda d: (d["rank"] is None, d["rank"] or 0,
                             str(d["code"] or "~"), d["title"] or ""))

    # Grouped the way the PRD asks the board to read - doable now, needs
    # acquisition, parked - but never reordered within a group. The tournament
    # rank is the order, and re-sorting by tier here would quietly make
    # feasibility the primary axis.
    by_tier = {t: [r for r in rows if r["tier"] == t] for t in TIERS}
    return {"n": len(rows),
            "doable_now": by_tier["A"] + by_tier["B"],
            "needs_acquisition": by_tier["C"],
            "parked": by_tier["D"],
            "counts": {t: len(by_tier[t]) for t in TIERS},
            "assessments": rows}
