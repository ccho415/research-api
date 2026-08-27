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
        conflict = "(title_key) WHERE doi IS NULL AND pmid IS NULL"
    else:
        conflict = None

    names = ", ".join(cols)
    marks = ", ".join(f"%({k})s" for k in cols)

    if conflict is None:
        # No identifier of any kind: insert and accept the duplicate rather
        # than silently merging two papers that only share a blank title.
        cur.execute(f"INSERT INTO paper ({names}) VALUES ({marks}) RETURNING id", cols)
        return cur.fetchone()["id"], True

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
        "RETURNING id, (xmax = 0) AS inserted", cols)
    row = cur.fetchone()
    return row["id"], bool(row["inserted"])


def ingest(query_text, results, run_id=None, domain=None, sources=None,
           query_angle=None, axis_source=None):
    """Store one search and its results, reporting how much was already cached.

    The cache hit rate is the point of this endpoint as much as the storage:
    novelty checking runs many overlapping queries, and knowing how much
    overlap is actually being reused is what tells you the cache is working.
    """
    n_new = n_cached = n_unidentified = 0
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO search_query "
                "  (run_id, query_text, domain, sources, query_angle, axis_source, n_hits) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (run_id, query_text, domain,
                 psycopg.types.json.Jsonb(sources or []),
                 query_angle, axis_source, len(results)))
            sq_id = cur.fetchone()["id"]

            for rank, r in enumerate(results):
                if not (r.get("doi") or r.get("pmid")):
                    n_unidentified += 1
                pid, is_new = _upsert_paper(cur, r)
                n_new += is_new
                n_cached += not is_new
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
            "cache_hit_rate": round(n_cached / total, 3) if total else None,
            "n_without_identifier": n_unidentified}


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
