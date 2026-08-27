"""Database access for the literature cache.

Backup goes through the pg_* command line tools because it needs pg_dump.
Everything else needs parameterised SQL against user-supplied text - paper
titles carry quotes, unicode and occasionally SQL-looking fragments - so it
goes through a real driver instead.

Connection settings come from backup.pg_env(), so both paths read the same
environment and there is one place where the database is configured.
"""

import re
import unicodedata
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

import backup


@contextmanager
def connect():
    env = backup.pg_env()
    conn = psycopg.connect(
        host=env["PGHOST"], port=int(env["PGPORT"]), user=env["PGUSER"],
        password=env.get("PGPASSWORD"), dbname=env["PGDATABASE"],
        connect_timeout=int(env.get("PGCONNECT_TIMEOUT", 15)),
        row_factory=dict_row,
    )
    try:
        yield conn
    finally:
        conn.close()


_PUNCT = re.compile(r"[^a-z0-9]+")


def title_key(title):
    """A title reduced to something two records of the same paper agree on.

    Sources differ in capitalisation, trailing full stops, accents and the
    amount of whitespace, so a raw title match misses obvious duplicates.
    This is only used for records that carry neither DOI nor PMID.
    """
    t = unicodedata.normalize("NFKD", title or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return _PUNCT.sub(" ", t).strip() or None


def _upsert_paper(cur, r):
    """Return (paper_id, was_new).

    DOI first, then PMID, then a normalised title. The first two have partial
    unique indexes; the title key only applies where both identifiers are
    absent, so a record that later arrives with a DOI is not merged into a
    title-matched row by accident.
    """
    doi = (r.get("doi") or "").strip().lower() or None
    pmid = str(r.get("pmid") or "").strip() or None
    tkey = None if (doi or pmid) else title_key(r.get("title"))

    cols = dict(
        doi=doi, pmid=pmid, openalex_id=r.get("openalex_id") or r.get("id"),
        title=(r.get("title") or "").strip() or "(untitled)",
        abstract=r.get("abstract"), year=r.get("year"), venue=r.get("venue"),
        authors=psycopg.types.json.Jsonb(r.get("authors") or []),
        citations=r.get("citations"), url=r.get("url"),
        source=r.get("source") or "unknown", title_key=tkey,
    )

    if doi:
        conflict = "(doi) WHERE doi IS NOT NULL"
    elif pmid:
        conflict = "(pmid) WHERE pmid IS NOT NULL"
    elif tkey:
        # Every condition of the index predicate has to appear here.  Postgres
        # infers the arbiter index by checking that this WHERE clause implies
        # the index's own, and `title_key IS NOT NULL` is part of the index, so
        # omitting it matches nothing and raises InvalidColumnReference on the
        # first record that carries neither DOI nor PMID.
        conflict = ("(title_key) WHERE doi IS NULL AND pmid IS NULL "
                    "AND title_key IS NOT NULL")
    else:
        conflict = None

    names = ", ".join(cols)
    marks = ", ".join(f"%({k})s" for k in cols)

    if conflict is None:
        # No identifier of any kind: insert and accept the duplicate rather
        # than silently merging two papers that only share a blank title.
        cur.execute(f"INSERT INTO paper ({names}) VALUES ({marks}) "
                    "RETURNING id, fetched_at", cols)
        row = cur.fetchone()
        return row["id"], True, row["fetched_at"]

    # xmax = 0 distinguishes a fresh insert from an update of an existing row,
    # which is what the cache hit rate is counting.
    cur.execute(
        f"INSERT INTO paper ({names}) VALUES ({marks}) "
        f"ON CONFLICT {conflict} DO UPDATE SET "
        "  abstract  = COALESCE(EXCLUDED.abstract,  paper.abstract),"
        "  year      = COALESCE(EXCLUDED.year,      paper.year),"
        "  venue     = COALESCE(NULLIF(EXCLUDED.venue,''), paper.venue),"
        "  citations = COALESCE(EXCLUDED.citations, paper.citations),"
        "  url       = COALESCE(EXCLUDED.url,       paper.url),"
        "  pmid      = COALESCE(paper.pmid,  EXCLUDED.pmid),"
        "  openalex_id = COALESCE(paper.openalex_id, EXCLUDED.openalex_id) "
        "RETURNING id, (xmax = 0) AS inserted, fetched_at", cols)
    row = cur.fetchone()
    return row["id"], bool(row["inserted"]), row["fetched_at"]


def start_run(topic, domain=None, project_id=None, run_id=None):
    """Ensure the search has something to belong to, and return it.

    A literature run can be started before any of the upstream workflow exists,
    so W2 creates its own project and run rather than leaving `run_id` null.
    An orphan search is allowed by the schema but should never actually happen;
    seeing one means something bypassed this.
    """
    with connect() as conn:
        with conn.cursor() as cur:
            if run_id:
                cur.execute("SELECT id, project_id, started_at FROM run WHERE id = %s",
                            (run_id,))
                row = cur.fetchone()
                if not row:
                    raise ValueError(f"no such run: {run_id}")
                if row["started_at"] is None:
                    cur.execute("UPDATE run SET started_at = now() WHERE id = %s "
                                "RETURNING started_at", (run_id,))
                    row = dict(row, started_at=cur.fetchone()["started_at"])
                conn.commit()
                return {"project_id": str(row["project_id"]), "run_id": str(row["id"]),
                        "started_at": row["started_at"].isoformat(), "created": False}

            if not project_id:
                cur.execute(
                    "INSERT INTO project (title, topic, status) VALUES (%s, %s, %s) "
                    "RETURNING id", (topic[:200], topic, "lit_search"))
                project_id = cur.fetchone()["id"]
            cur.execute(
                "INSERT INTO run (project_id, stage, status, started_at) "
                "VALUES (%s, 'lit_search', 'running', now()) RETURNING id, started_at",
                (project_id,))
            row = cur.fetchone()
        conn.commit()
    return {"project_id": str(project_id), "run_id": str(row["id"]),
            "started_at": row["started_at"].isoformat(), "created": True}


def done_queries(run_id):
    """Which searches this run has already stored, so a resumed run skips them.

    A run interrupted halfway has already paid the external-call cost for what
    it stored; re-running those would also inflate the query repeat rate with
    repeats caused by a crash rather than by the search going in circles.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT query_text, domain FROM search_query WHERE run_id = %s",
                    (run_id,))
        return [{"query_text": r["query_text"], "domain": r["domain"]}
                for r in cur.fetchall()]


def ingest(query_text, results, run_id=None, domain=None, sources=None,
           query_angle=None, axis_source=None):
    """Store one search and its results, reporting what was already held.

    Two different counts come out of this, and conflating them is how the
    acceptance test silently passes.  `n_cached` is within-run overlap - the
    same paper arriving from more than one of this run's queries - which is
    high on the very first run of a topic.  `n_reused` counts papers that were
    in the library *before this run started*, which is the number the 60%
    threshold is about.  `paper.fetched_at` is never touched by the upsert, so
    it still marks when the library first saw the paper.
    """
    n_new = n_cached = n_unidentified = n_reused = 0
    with connect() as conn:
        with conn.cursor() as cur:
            run_start = None
            if run_id:
                cur.execute("SELECT started_at FROM run WHERE id = %s", (run_id,))
                row = cur.fetchone()
                run_start = row and row["started_at"]

            cur.execute(
                "INSERT INTO search_query "
                "  (run_id, query_text, domain, sources, query_angle, axis_source, n_hits) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (run_id, query_text, domain,
                 psycopg.types.json.Jsonb(sources if sources is not None else []),
                 query_angle, axis_source, len(results)))
            sq_id = cur.fetchone()["id"]

            for rank, r in enumerate(results):
                if not (r.get("doi") or r.get("pmid")):
                    n_unidentified += 1
                pid, is_new, fetched_at = _upsert_paper(cur, r)
                n_new += is_new
                n_cached += not is_new
                if run_start and fetched_at and fetched_at < run_start:
                    n_reused += 1
                # The same paper can arrive twice in one result set from two
                # sources; keep the better rank rather than failing the insert.
                cur.execute(
                    "INSERT INTO search_hit (search_query_id, paper_id, rank) "
                    "VALUES (%s, %s, %s) ON CONFLICT (search_query_id, paper_id) "
                    "DO UPDATE SET rank = LEAST(search_hit.rank, EXCLUDED.rank)",
                    (sq_id, pid, rank))
        conn.commit()

    total = n_new + n_cached
    return {"search_query_id": str(sq_id), "n_results": len(results),
            "n_new": n_new, "n_cached": n_cached,
            "within_run_overlap": round(n_cached / total, 3) if total else None,
            "n_reused": n_reused,
            "paper_reuse_rate": round(n_reused / total, 3) if total else None,
            "n_without_identifier": n_unidentified}


def finish_run(run_id, status="done"):
    """Close the run and record its metrics, so the trend outlives the report.

    A single run's reuse rate says almost nothing; what matters is whether it
    climbs as the library grows, and that question cannot be answered later
    from a number that was only ever printed on screen.
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT started_at FROM run WHERE id = %s", (run_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"no such run: {run_id}")
            started = row["started_at"]

            cur.execute(
                "SELECT count(*) AS n_queries,"
                "       count(*) FILTER (WHERE n_hits = 0) AS n_empty,"
                "       coalesce(sum(n_hits), 0) AS n_hits"
                "  FROM search_query WHERE run_id = %s", (run_id,))
            q = dict(cur.fetchone())

            # Reuse and repeat are measured over the whole run, not per query:
            # the papers a run saw, against what the library held when it began.
            cur.execute(
                "SELECT count(DISTINCT h.paper_id) AS n_papers,"
                "       count(DISTINCT h.paper_id) FILTER (WHERE p.fetched_at < %s)"
                "         AS n_reused"
                "  FROM search_hit h JOIN paper p ON p.id = h.paper_id"
                " WHERE h.search_query_id IN (SELECT id FROM search_query WHERE run_id = %s)",
                (started, run_id))
            p = dict(cur.fetchone())

            # "The same query" is the normalised text plus the domain: the same
            # string routed to a different domain reaches different sources and
            # comes back with different papers.
            cur.execute(
                "SELECT count(*) AS n_repeat FROM search_query s"
                " WHERE s.run_id = %s AND EXISTS ("
                "   SELECT 1 FROM search_query o"
                "    WHERE o.id <> s.id AND o.executed_at < s.executed_at"
                "      AND lower(regexp_replace(o.query_text, '\\s+', ' ', 'g'))"
                "        = lower(regexp_replace(s.query_text, '\\s+', ' ', 'g'))"
                "      AND o.domain IS NOT DISTINCT FROM s.domain)", (run_id,))
            n_repeat = cur.fetchone()["n_repeat"]

            metrics = {
                "paper_reuse_rate": (p["n_reused"] / p["n_papers"]) if p["n_papers"] else None,
                "query_repeat_rate": (n_repeat / q["n_queries"]) if q["n_queries"] else None,
                "within_run_overlap": ((q["n_hits"] - p["n_papers"]) / q["n_hits"])
                                      if q["n_hits"] else None,
            }
            for name, value in metrics.items():
                if value is not None:
                    cur.execute(
                        "INSERT INTO health_metric (run_id, metric, value) "
                        "VALUES (%s, %s, %s)", (run_id, name, round(value, 4)))

            cur.execute("UPDATE run SET status = %s, finished_at = now() WHERE id = %s",
                        (status, run_id))
        conn.commit()

    return {"run_id": str(run_id), "n_queries": q["n_queries"],
            "n_empty_queries": q["n_empty"], "n_papers": p["n_papers"],
            "n_reused": p["n_reused"],
            **{k: (round(v, 4) if v is not None else None) for k, v in metrics.items()}}


def record_expansion(project_id, expansion):
    """Append this run's vocabulary expansion and report what moved since last.

    Kept rather than reused: MeSH is revised yearly and the ranking here is our
    own, so a stored expansion is a comparison point, not a cache.  Reusing it
    would freeze a bad first choice and hide it behind a flattering reuse rate.
    """
    entry = {"at": None, "concepts": [
        {"input": c.get("input"), "descriptor": c.get("descriptor"),
         "unique_id": c.get("unique_id"), "expanded": c.get("expanded")}
        for c in expansion.get("concepts") or []]}

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT vocab_expansion FROM project WHERE id = %s",
                        (project_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"no such project: {project_id}")
            history = row["vocab_expansion"] or []
            previous = history[-1] if history else None

            cur.execute(
                "UPDATE project SET vocab_expansion = "
                "  coalesce(vocab_expansion, '[]'::jsonb) || "
                "  jsonb_build_array(jsonb_set(%s::jsonb, '{at}', to_jsonb(now()))) "
                "WHERE id = %s",
                (psycopg.types.json.Jsonb(entry), project_id))
        conn.commit()

    drift = []
    if previous:
        was = {c.get("input"): c.get("unique_id") for c in previous.get("concepts") or []}
        for c in entry["concepts"]:
            before = was.get(c["input"], "__absent__")
            if before != "__absent__" and before != c["unique_id"]:
                drift.append({"input": c["input"], "was": before, "now": c["unique_id"]})
    return {"version": len(history) + 1, "drift": drift,
            "first_expansion": previous is None}


def corpus_stats():
    """Size of the literature cache, for the workflow to report and assert on."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT (SELECT count(*) FROM paper) AS papers,"
            "       (SELECT count(*) FROM search_query) AS queries,"
            "       (SELECT count(*) FROM search_hit) AS hits,"
            "       (SELECT count(*) FROM paper WHERE doi IS NULL AND pmid IS NULL)"
            "         AS papers_without_identifier")
        return dict(cur.fetchone())
