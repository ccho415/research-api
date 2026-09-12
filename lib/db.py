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


def openalex_id_of(r):
    """The OpenAlex id of a record, or None if it does not have one.

    A function rather than an inline expression so a test can call the same
    code the writer calls. It used to be `r.get("openalex_id") or r.get("id")`,
    and `id` is whatever the source calls its own identifier - so a pmid, an
    arXiv id, a Crossref DOI, a Europe PMC id and a Semantic Scholar paperId
    were all filed in the OpenAlex column, five of the six sources.

    That was not a cosmetic mix-up. The UPSERT COALESCEs this column, so the
    first wrong value stuck permanently: a paper first seen through PubMed kept
    a pmid here even after OpenAlex later returned its real id, and nothing
    ever errored because no reader checked the shape.
    """
    return (r.get("openalex_id")
            or (r.get("id") if r.get("source") == "openalex" else None))


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
        doi=doi, pmid=pmid, openalex_id=openalex_id_of(r),
        title=(r.get("title") or "").strip() or "(untitled)",
        abstract=r.get("abstract"), year=r.get("year"), venue=r.get("venue"),
        authors=psycopg.types.json.Jsonb(r.get("authors") or []),
        citations=r.get("citations"), url=r.get("url"),
        source=r.get("source") or "unknown", title_key=tkey,
        # `paper.mesh` has existed since the first schema and nothing ever
        # wrote to it: the column was created, PubMed's parser filled the field
        # on the record, and the insert never carried it across. So the MeSH
        # indexing was fetched and discarded on every run, silently, and no
        # screen could show it because there was nothing to show.
        mesh=psycopg.types.json.Jsonb(r.get("mesh") or []),
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
        # Kept if the newcomer has none: one source indexes a paper and another
        # does not, and the merge must not empty a field that was already
        # filled. Same rule the other columns use.
        "  mesh      = CASE WHEN jsonb_array_length(COALESCE(EXCLUDED.mesh,'[]'::jsonb)) > 0"
        "                   THEN EXCLUDED.mesh ELSE paper.mesh END,"
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
                # Re-running the same topic has to land in the same project,
                # or the stored vocabulary expansion never has a previous
                # version to be compared against and the drift check silently
                # does nothing.  Paper reuse becomes untrackable over time for
                # the same reason: a fresh project every run resets the history
                # that makes the number mean anything.
                cur.execute(
                    "SELECT id FROM project"
                    " WHERE lower(regexp_replace(topic, '\\s+', ' ', 'g'))"
                    "     = lower(regexp_replace(%s, '\\s+', ' ', 'g'))"
                    " ORDER BY created_at LIMIT 1", (topic,))
                row = cur.fetchone()
                if row:
                    project_id = row["id"]
                else:
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


def project_concepts(project_id):
    """What this project was searched for, and what those searches returned.

    `record_expansion` has written `project.vocab_expansion` since migration 002
    and nothing has ever read it back. So the one question a person asks after a
    run - "what did I actually search for?" - had no answer anywhere in the
    system, while the answer sat in a column.

    Two layers, and they are not the same thing:

      concepts  what a person typed, and the controlled-vocabulary descriptor it
                resolved to. `expanded: false` means it resolved in neither MeSH
                nor OpenAlex, so that axis searched one raw string and has
                roughly a tenth of the coverage of a normal one.
      queries   what was actually sent. The crossing of descriptors with their
                hierarchy produces many queries per concept, so this list is
                longer than the concept list and is the honest record of the
                search - a concept is an intention, a query is what ran.

    Every expansion is kept, not just the latest. MeSH is revised yearly and the
    ranking is ours, so a concept that resolved to a different descriptor on a
    re-run is a real event, and the only way to see it is to keep both.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, title, topic, vocab_expansion FROM project WHERE id = %s",
            (project_id,))
        p = cur.fetchone()
        if not p:
            raise ValueError(f"no project {project_id}")

        cur.execute(
            "SELECT q.query_text, q.query_angle, q.axis_source, q.domain,"
            "       q.n_hits, q.executed_at, q.run_id "
            "FROM search_query q JOIN run r ON r.id = q.run_id "
            "WHERE r.project_id = %s "
            "ORDER BY q.executed_at", (project_id,))
        queries = []
        for r in cur.fetchall():
            d = dict(r)
            d["run_id"] = str(d["run_id"]) if d["run_id"] else None
            d["executed_at"] = (d["executed_at"].isoformat()
                                if d["executed_at"] else None)
            d["n_hits"] = int(d["n_hits"] or 0)
            queries.append(d)

    history = p["vocab_expansion"] or []
    if not isinstance(history, list):
        history = []
    versions = []
    for i, e in enumerate(history):
        if not isinstance(e, dict):
            continue
        cs = e.get("concepts") or []
        versions.append({
            "version": i + 1,
            "at": e.get("at"),
            "concepts": [{"input": c.get("input"),
                          "descriptor": c.get("descriptor"),
                          "unique_id": c.get("unique_id"),
                          # Stored as a boolean by record_expansion. Normalised
                          # here so a screen can trust it: an older row could
                          # carry the term list this field used to hold.
                          "expanded": bool(c.get("expanded"))}
                         for c in cs if isinstance(c, dict)]})

    latest = versions[-1] if versions else None
    # Which concept a descriptor came from cannot be recovered from the query
    # text, so no attempt is made to attribute queries to concepts. Counting
    # them is honest; guessing the mapping would put a number next to a concept
    # that nothing supports.
    return {
        "project_id": str(p["id"]), "title": p["title"], "topic": p["topic"],
        "latest": latest,
        "n_versions": len(versions),
        "earlier": versions[:-1] if len(versions) > 1 else [],
        "queries": queries,
        "n_queries": len(queries),
        "n_empty_queries": sum(1 for q in queries if not q["n_hits"]),
        "n_hits_total": sum(q["n_hits"] for q in queries),
    }


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


# The schema's vocabulary for a novelty verdict is coarser than the one the
# check produces, because the check reports how it reached an answer as well as
# what the answer was.  The mapping is therefore lossy, and the original travels
# intact in `rounds` so nothing is lost by storing it.
_NOVELTY = {"ALREADY DONE": "scooped", "PURSUED SINCE": "scooped"}

# Verdicts that are not verdicts: the check declined to rule.  A null is the
# honest record of that, where any of the four schema words would assert
# something about the question that was never established.
_NO_RULING = ("TERM TOO RARE", "NO TERMS", "SINGLE GROUP", "CHECK FAILED")


def _verdict_of(row):
    """The check's verdict, under either name it travels by.

    The reporting step renames `verdict` to `verdict_tag` on purpose - four
    experiments established that the word is the least reliable field in the
    output, so it is demoted below the evidence when a person reads it. Reading
    only the original name here stored fifteen rows with a null verdict and no
    error, which is the quiet kind of wrong.
    """
    return row.get("verdict") or row.get("verdict_tag")


def _code_of(row):
    """The model's own ordering, under either name it travels by."""
    v = row.get("rank")
    if v is None:
        v = row.get("rank_from_model")
    return None if v is None else str(v)


def _novelty_verdict(row):
    v = _verdict_of(row)
    if v in _NOVELTY:
        return _NOVELTY[v]
    if v == "STILL OPEN":
        return "adjacent" if row.get("zone") == "ADJACENT" else "no_prior_art"
    return None


def _coverage_limits(row):
    """What the reader of this row has to know before trusting its verdict.

    Every number here was measured on 2026-08-28 and is written up in
    docs/experiments/2026-08-28-verify-directions-control.md.  It is repeated on
    the row because whoever reads a stored idea a year from now will not have
    that document open, and the verdict alone reads far more confidently than
    the evidence behind it deserves.
    """
    notes = []
    if _verdict_of(row) in _NO_RULING:
        notes.append("no ruling: " + str(row.get("why") or _verdict_of(row)))
    if len(row.get("groups") or row.get("term_groups") or []) >= 3:
        notes.append("three or more slots ANDed as exact phrases; directions of this "
                     "shape were pursued at 6% against 28% for two-slot ones, so a "
                     "not-done answer here is weaker than the same answer on two")
    if row.get("zone") == "NEVER MEET":
        notes.append("concepts never co-mentioned before the cutoff; none of the 28 "
                     "directions in this zone were pursued afterwards, which reads as "
                     "unrelated terms rather than an untouched question")
    # Only where `adjacent` is the verdict being relied on. Once the record has
    # already answered - scooped - what the zone would have hinted is moot, and
    # repeating it there buries the caveat that matters under one that does not.
    if row.get("zone") == "ADJACENT" and _verdict_of(row) == "STILL OPEN":
        notes.append("adjacent means these concepts are being written about together, "
                     "not that this is a good question; random recombinations of the "
                     "same words land here more often than reasoned ones")
    if row.get("co_mentions_before") is not None:
        notes.append("co-mention counted in the open-access subset only")
    return " | ".join(notes) or None


def save_directions(directions, topic=None, project_id=None, run_id=None, cutoff=None):
    """Store the directions and what the record said about each of them.

    Written here rather than left in the workflow log because an n8n execution
    is a transcript, not a record: it expires, it is not queryable, and the
    whole point of the check is to be read by a person later.

    Re-running the same material deliberately produces new rows rather than
    updating old ones.  The model returns different directions every time, so
    two runs of one topic are two observations, and collapsing them would throw
    away the variation that says how stable the output is.
    """
    if not directions:
        raise ValueError("no directions to save")

    with connect() as conn:
        with conn.cursor() as cur:
            if not project_id:
                if not topic:
                    raise ValueError("need either project_id or topic")
                cur.execute(
                    "SELECT id FROM project"
                    " WHERE lower(regexp_replace(topic, '\\s+', ' ', 'g'))"
                    "     = lower(regexp_replace(%s, '\\s+', ' ', 'g'))"
                    " ORDER BY created_at LIMIT 1", (topic,))
                row = cur.fetchone()
                if row:
                    project_id = row["id"]
                else:
                    cur.execute(
                        "INSERT INTO project (title, topic, status) "
                        "VALUES (%s, %s, %s) RETURNING id",
                        (topic[:200], topic, "ideation"))
                    project_id = cur.fetchone()["id"]

            if not run_id:
                cur.execute(
                    "INSERT INTO run (project_id, stage, status, started_at, params) "
                    "VALUES (%s, 'ideation', 'running', now(), %s) RETURNING id",
                    (project_id, psycopg.types.json.Jsonb({"cutoff": cutoff})))
                run_id = cur.fetchone()["id"]

            saved = []
            for d in directions:
                statement = (d.get("direction") or "").strip()
                if not statement:
                    continue

                # The title is the terms, not the opening of the statement.
                # triage.idea_text concatenates title and statement before
                # comparing ideas, so a title that is a prefix counts its own
                # words twice - and the words at the front of these are the
                # question stem, so two directions would score as near
                # duplicates for sharing "What is the relationship between".
                slots = d.get("term_groups") or d.get("groups") or []
                label = " x ".join(" / ".join(str(t) for t in g) for g in slots if g)
                title = label[:200] or statement[:200]
                # Absent rather than invented. A sketch the model never produced
                # is worse as an empty shell than as a null: the shell reads as
                # though the question of how to do this was answered.
                sketch = d.get("method_sketch") or None
                needs = d.get("required_variables") or None

                cur.execute(
                    "INSERT INTO idea (project_id, code, title, statement, axis,"
                    "                  origin, grounding, why_matters, status,"
                    "                  method_sketch, required_variables) "
                    "VALUES (%s, %s, %s, %s, 'topic', 'generated', %s, %s, 'candidate',"
                    "        %s, %s) "
                    "RETURNING id",
                    (project_id,
                     _code_of(d),
                     title, statement,
                     psycopg.types.json.Jsonb({
                         "built_from": d.get("built_from"),
                         "search_terms": d.get("search_terms"),
                         "term_groups": d.get("term_groups") or d.get("groups"),
                         "weak_terms": d.get("weak_terms") or None,
                         "grouping_applied": d.get("grouping_applied"),
                     }),
                     d.get("why_now"),
                     psycopg.types.json.Jsonb(sketch) if sketch else None,
                     psycopg.types.json.Jsonb(needs) if needs else None))
                idea_id = cur.fetchone()["id"]

                cur.execute(
                    "INSERT INTO novelty_check (idea_id, run_id, verdict, rounds,"
                    "                           coverage_limits) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (idea_id, run_id, _novelty_verdict(d),
                     psycopg.types.json.Jsonb({
                         "check_verdict": _verdict_of(d),
                         "zone": d.get("zone"),
                         "cutoff": cutoff,
                         "query": d.get("query"),
                         "papers_before": d.get("papers_before"),
                         "papers_after": d.get("papers_after"),
                         "co_mentions_before": d.get("co_mentions_before"),
                         "term_papers": d.get("term_papers"),
                         "rare_terms": d.get("rare_terms"),
                     }),
                     _coverage_limits(d)))
                saved.append({"idea_id": str(idea_id), "code": _code_of(d),
                              "verdict": _novelty_verdict(d),
                              "check_verdict": _verdict_of(d)})

            cur.execute("UPDATE run SET status = 'done', finished_at = now() "
                        "WHERE id = %s", (run_id,))
        conn.commit()

    return {"project_id": str(project_id), "run_id": str(run_id),
            "n_saved": len(saved), "ideas": saved}


def list_ideas(project_id=None, run_id=None, status=None, limit=200):
    """Read back the directions and the latest thing said about each.

    W4 needs this and there was no way to get an idea out of the database at
    all: `save_directions` wrote, and nothing read. The novelty check is joined
    on rather than fetched separately because a direction without its verdict
    and its coverage limits is exactly the half of the record that misleads -
    the statement always reads plausibly, and the caveats are what say how much
    to trust it.

    Only the most recent check per idea is returned. A direction that was
    re-checked has an older row too, and handing back both would double every
    idea in the deduplication that consumes this.
    """
    where, args = [], []
    if project_id:
        where.append("i.project_id = %s")
        args.append(project_id)
    if run_id:
        where.append("n.run_id = %s")
        args.append(run_id)
    if status:
        where.append("i.status = %s")
        args.append(status)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    args.append(int(limit))

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT i.id, i.project_id, i.code, i.title, i.statement, i.axis,"
            "       i.origin, i.source_note, i.status, i.grounding,"
            "       i.method_sketch, i.required_variables, i.why_matters,"
            "       i.created_at,"
            "       n.verdict, n.rounds, n.coverage_limits, n.checked_at,"
            "       n.run_id "
            "FROM idea i "
            "LEFT JOIN LATERAL ("
            "    SELECT * FROM novelty_check c"
            "    WHERE c.idea_id = i.id"
            "    ORDER BY c.checked_at DESC LIMIT 1"
            ") n ON true "
            f"{clause} "
            "ORDER BY i.created_at, i.code "
            "LIMIT %s", args)
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            for k in ("id", "project_id", "run_id"):
                if d.get(k) is not None:
                    d[k] = str(d[k])
            for k in ("created_at", "checked_at"):
                if d.get(k) is not None:
                    d[k] = d[k].isoformat()
            rows.append(d)

    return {"n": len(rows), "project_id": project_id, "ideas": rows}


def save_dedup_pairs(run_id, pairs):
    """Store what was judged about each candidate pair.

    A pair the model was unsure about is stored with a null verdict rather than
    forced to duplicate or distinct. That null is the review queue: the PRD asks
    for the uncertain ones to reach a person, and a guess written into the
    verdict column would remove exactly the pairs that needed the person.
    """
    if not run_id:
        raise ValueError("need run_id")
    rows = []
    with connect() as conn:
        with conn.cursor() as cur:
            for p in pairs or []:
                a, b = p.get("idea_a") or p.get("a"), p.get("idea_b") or p.get("b")
                if not a or not b:
                    continue
                verdict = (p.get("verdict") or "").strip().lower() or None
                if verdict not in ("duplicate", "distinct", None):
                    verdict = None
                cur.execute(
                    "INSERT INTO dedup_pair (run_id, idea_a, idea_b, score, cosine,"
                    "                        jaccard, verdict, decided_by, decided_at) "
                    # The cast is required: the last parameter appears only in a
                    # comparison against NULL, so Postgres has nothing to infer
                    # its type from and refuses the statement outright.
                    # Timestamped server-side rather than from Python so the row
                    # carries the database's clock, not the caller's.
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s,"
                    "        CASE WHEN %s::text IS NULL THEN NULL ELSE now() END) "
                    "RETURNING id",
                    (run_id, a, b, p.get("score"), p.get("cosine"), p.get("jaccard"),
                     verdict, p.get("decided_by") if verdict else None, verdict))
                rows.append({"id": str(cur.fetchone()["id"]), "idea_a": a,
                             "idea_b": b, "verdict": verdict})
        conn.commit()

    undecided = sum(1 for r in rows if r["verdict"] is None)
    return {"run_id": run_id, "n_saved": len(rows), "n_undecided": undecided,
            "pairs": rows}


def list_dedup_pairs(run_id, undecided_only=False, limit=200):
    """Candidate pairs with both directions written out in full.

    Both statements are joined in rather than left as ids because the display
    rule is not decoration: judging whether two directions are the same one
    needs both of them on screen, and their trial run found that a table of
    codes and truncated titles made the judgement impossible to make.
    """
    where, args = ["d.run_id = %s"], [run_id]
    if undecided_only:
        where.append("d.verdict IS NULL")
    args.append(int(limit))

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT d.id, d.score, d.cosine, d.jaccard, d.verdict, d.decided_by,"
            "       d.decided_at,"
            "       a.id AS a_id, a.code AS a_code, a.title AS a_title,"
            "       a.statement AS a_statement,"
            "       b.id AS b_id, b.code AS b_code, b.title AS b_title,"
            "       b.statement AS b_statement "
            "FROM dedup_pair d "
            "JOIN idea a ON a.id = d.idea_a "
            "JOIN idea b ON b.id = d.idea_b "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY d.verdict IS NOT NULL, d.score DESC NULLS LAST "
            "LIMIT %s", args)
        out = []
        for r in cur.fetchall():
            d = dict(r)
            for k in ("id", "a_id", "b_id"):
                d[k] = str(d[k])
            if d.get("decided_at") is not None:
                d["decided_at"] = d["decided_at"].isoformat()
            for k in ("score", "cosine", "jaccard"):
                if d.get(k) is not None:
                    d[k] = float(d[k])
            out.append(d)

    return {"run_id": run_id, "n": len(out),
            "n_undecided": sum(1 for x in out if x["verdict"] is None),
            "pairs": out}


def papers_for(project_id=None, source_run_id=None, limit=300):
    """The papers W2 already found, best venues first, then newest.

    Reached through the searches that returned them rather than by re-searching:
    that is the whole point of the cache, and the harvest was previously paying
    Europe PMC a second time for records already sitting in this table.

    The ordering matters because this is the step with a cap. The search is
    free and stays wide; fetching full text is neither, so only a few hundred
    of those papers get mined for the sentences where authors say what is still
    unknown. Which few hundred is therefore a real choice, and it used to be
    made on publication year alone.

    Venue tier comes first now - see `journals`, and note that it is a priority
    and not a filter: everything is still returned, in a different order. A
    paper with no venue recorded, which a real fraction of Europe PMC records
    are, scores zero and falls through to year and citations rather than being
    pushed behind anything.
    """
    where, args = [], []
    if source_run_id:
        where.append("q.run_id = %s")
        args.append(source_run_id)
    if project_id:
        where.append("r.project_id = %s")
        args.append(project_id)
    if not where:
        raise ValueError("need project_id or source_run_id")

    # The domain this project searched under, so the journal tiers follow the
    # project instead of being fixed. W2 stores it on every query, so it is
    # already here and needs no new parameter; a project from before it existed
    # gets no domain tier and the ordering is simply less precise.
    domain = None
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT q.domain FROM search_query q "
            "LEFT JOIN run r ON r.id = q.run_id "
            f"WHERE {' AND '.join(where)} AND q.domain IS NOT NULL "
            "ORDER BY q.executed_at DESC LIMIT 1", list(args))
        row = cur.fetchone()
        if row:
            domain = row["domain"]

    import journals
    gen, dom = journals.patterns(domain)
    # `ILIKE ANY` of an empty array matches nothing rather than failing, but a
    # value that cannot occur says what is meant more plainly than `{}`.
    gen = gen or ["__no_such_venue__"]
    dom = dom or ["__no_such_venue__"]

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            # The tier is selected rather than only ordered by, because under
            # SELECT DISTINCT Postgres requires every ORDER BY expression to be
            # in the select list. `venue` and `citations` come along for the
            # same reason, and the caller is free to ignore them.
            #
            # `abstract` is here because most of this corpus has no open full
            # text, and the harvest falls back to mining the abstract for the
            # papers that do not. It is already stored, so this costs one column.
            "SELECT DISTINCT p.id, p.pmid, p.pmcid, p.doi, p.title, p.year, "
            "       p.abstract, p.venue, p.citations, "
            "       (CASE WHEN p.venue ILIKE ANY(%s) THEN 2 "
            "             WHEN p.venue ILIKE ANY(%s) THEN 1 "
            "             ELSE 0 END) AS venue_tier "
            "FROM paper p "
            "JOIN search_hit h ON h.paper_id = p.id "
            "JOIN search_query q ON q.id = h.search_query_id "
            "LEFT JOIN run r ON r.id = q.run_id "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY venue_tier DESC, "
            "         p.year DESC NULLS LAST, "
            "         p.citations DESC NULLS LAST "
            "LIMIT %s", [gen, dom] + list(args) + [int(limit)])
        return [dict(r, id=str(r["id"])) for r in cur.fetchall()]

def cached_sections(paper_ids, kind="discussion"):
    """Which of these papers have already been fetched, and what came back.

    A NULL content is a cached answer, not a missing one: it records that the
    paper was looked up and has no retrievable full text. Without that
    distinction every harvest re-fetches the same papers that will never have
    full text, which is most of them.
    """
    if not paper_ids:
        return {}
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT paper_id, content FROM paper_section "
                    "WHERE kind = %s AND paper_id = ANY(%s)",
                    (kind, list(paper_ids)))
        return {str(r["paper_id"]): r["content"] for r in cur.fetchall()}


def save_section(paper_id, kind, content):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO paper_section (paper_id, kind, content) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (paper_id, kind) DO UPDATE "
                "SET content = EXCLUDED.content, fetched_at = now()",
                (paper_id, kind, content))
        conn.commit()


def save_pmcid(paper_id, pmcid):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE paper SET pmcid = %s WHERE id = %s AND pmcid IS NULL",
                        (pmcid, paper_id))
        conn.commit()


def start_harvest(project_id=None, source_run_id=None):
    with connect() as conn:
        with conn.cursor() as cur:
            if not project_id and source_run_id:
                cur.execute("SELECT project_id FROM run WHERE id = %s", (source_run_id,))
                row = cur.fetchone()
                project_id = row["project_id"] if row else None
            cur.execute(
                "INSERT INTO run (project_id, stage, status, started_at) "
                "VALUES (%s, 'harvest', 'running', now()) RETURNING id", (project_id,))
            run_id = cur.fetchone()["id"]
            cur.execute(
                "INSERT INTO harvest (project_id, run_id, source_run_id, status) "
                "VALUES (%s, %s, %s, 'running') RETURNING id",
                (project_id, run_id, source_run_id))
            harvest_id = cur.fetchone()["id"]
        conn.commit()
    return {"harvest_id": str(harvest_id), "run_id": str(run_id),
            "project_id": None if project_id is None else str(project_id)}


def finish_harvest(harvest_id, result=None, counts=None, error=None):
    counts = counts or {}
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE harvest SET status = %s, result = %s, error = %s,"
                "  n_papers = %s, n_with_fulltext = %s, n_gap_sentences = %s,"
                "  n_concepts = %s, finished_at = now() "
                "WHERE id = %s RETURNING run_id",
                ("failed" if error else "done",
                 psycopg.types.json.Jsonb(result) if result else None,
                 error, counts.get("n_papers"), counts.get("n_with_fulltext"),
                 counts.get("n_gap_sentences"), counts.get("n_concepts"),
                 harvest_id))
            row = cur.fetchone()
            if row:
                cur.execute("UPDATE run SET status = %s, error = %s, finished_at = now() "
                            "WHERE id = %s",
                            ("failed" if error else "done", error, row["run_id"]))
        conn.commit()


def get_harvest(harvest_id=None, project_id=None, include_result=True):
    """One harvest, or the most recent one for a project."""
    cols = ("id, project_id, run_id, source_run_id, status, n_papers,"
            " n_with_fulltext, n_gap_sentences, n_concepts, error,"
            " started_at, finished_at")
    if include_result:
        cols += ", result"
    with connect() as conn, conn.cursor() as cur:
        if harvest_id:
            cur.execute(f"SELECT {cols} FROM harvest WHERE id = %s", (harvest_id,))
        elif project_id:
            cur.execute(f"SELECT {cols} FROM harvest WHERE project_id = %s "
                        "ORDER BY started_at DESC LIMIT 1", (project_id,))
        else:
            raise ValueError("need harvest_id or project_id")
        row = cur.fetchone()

    if not row:
        return None
    d = dict(row)
    for k in ("id", "project_id", "run_id", "source_run_id"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    for k in ("started_at", "finished_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    return d


def list_health_metrics(project_id=None, run_id=None):
    """The measured health numbers, which until now nothing could read back.

    They were being written from the first week - reuse rate, within-run
    overlap, the tournament's order-flip rate - and there was no way to get
    them out again. A number that is recorded and never readable is a number
    that gets quietly recomputed somewhere else, differently.

    Grouped by metric with the newest first, because what a reader wants is
    "what is the flip rate now, and was it always that" rather than a flat
    log of every insert.
    """
    where, args = [], []
    if run_id:
        where.append("h.run_id = %s")
        args.append(run_id)
    if project_id:
        where.append("r.project_id = %s")
        args.append(project_id)
    if not where:
        raise ValueError("need project_id or run_id")

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT h.metric, h.value, h.recorded_at, h.run_id, r.stage "
            "FROM health_metric h LEFT JOIN run r ON r.id = h.run_id "
            "WHERE " + " AND ".join(where) + " "
            "ORDER BY h.metric, h.recorded_at DESC", args)
        by_metric = {}
        for r in cur.fetchall():
            by_metric.setdefault(r["metric"], []).append({
                "value": None if r["value"] is None else float(r["value"]),
                "stage": r["stage"],
                "run_id": None if r["run_id"] is None else str(r["run_id"]),
                "recorded_at": r["recorded_at"].isoformat()})

    return {"n_metrics": len(by_metric),
            "latest": {k: v[0]["value"] for k, v in by_metric.items()},
            "metrics": by_metric}


def _chain_state_of(stages):
    """Where one project's chain stands, from its latest run per stage.

    `stages` is {stage_name: {"status": ..., "finished_at": ...}} holding only
    the most recent run of each chain stage.

    Precedence matters and is not arbitrary. Parked comes first because it is
    the only state that is waiting on the person reading the list - everything
    else is information, that one is a job.

    **But a park with LATER activity after it is history, not a job.**
    `resume` flips the parked row itself to `pending`, so in theory a released
    chain stops looking parked the moment it moves. In practice the live
    database had a project parked at feasibility whose novelty, debate and
    report all ran afterwards: that chain was advanced with `chain/start`,
    which queues the next stage without ever touching the parked row. Trusting
    the park alone would put a finished project on the "waiting for you" list
    forever, and that list is only worth reading if everything on it is real.

    **Later means later in time, not merely further down the chain.** Judging
    it by position alone was wrong, and a real run proved it within the hour:
    a re-run debate parked at review ④ was dismissed as stale because a report
    row sat after it in the chain - a report written two days *earlier*. The
    system said `done` while it was in fact waiting for a person, which is
    this function's own failure mode pointing the other way.

    `stopped` is deliberately not `failed`. A chain somebody ended on purpose
    and a chain that broke need different reactions, and collapsing them makes
    the second one invisible among the first.
    """
    import chain

    if not stages:
        return "not_started", None

    order = [s.name for s in chain.STAGE_PLAN]

    def moved_on_after(i, parked_at):
        """Did a stage further down the chain do anything after this park?"""
        for n in order[i + 1:]:
            later = stages.get(n)
            if not later:
                continue
            # Queued or running is current by definition: it cannot have
            # started before a park that is still holding the chain up.
            if later["status"] in ("pending", "running"):
                return True
            f = later.get("finished_at")
            # No timestamp on one side leaves the two unorderable. Treated as
            # later, which is the old behaviour, and keeps rows written before
            # finished_at was set reliably from resurrecting as false alarms.
            if f and (not parked_at or f > parked_at):
                return True
        return False

    for i, s in enumerate(chain.STAGE_PLAN):
        r = stages.get(s.name)
        if r and r["status"] in ("awaiting_review", "paused_budget"):
            if moved_on_after(i, r.get("finished_at")):
                continue
            return "awaiting_you", {
                "stage": s.name, "label": s.label, "review_point": s.review,
                "status": r["status"],
                # Two rows carry `awaiting_review` and mean opposite things: one
                # finished and parked at a review point, the other never ran
                # because a precondition was missing. `resume` already tells
                # them apart by `finished_at` and so must anything that offers
                # the user a button - "press release" and "go upload your data"
                # are not the same request.
                "awaiting": ("review" if r["finished_at"] else "precondition")}

    vals = [r["status"] for r in stages.values()]
    if any(v in ("pending", "running") for v in vals):
        return "running", None
    if stages.get("report", {}).get("status") == "done":
        return "done", None
    if "failed" in vals:
        return "failed", None
    if "stopped" in vals:
        return "stopped", None
    return "idle", None


def list_projects(limit=50):
    """Projects with enough counts to tell them apart, and their chain state.

    Needed before anything can be pointed at a project: ids are uuids, and
    picking the right one from a list of uuids is not something a person or a
    workflow should be asked to do from memory. The counts are what make the
    row identifiable - which project has the literature, which has the ideas.

    Spend and chain state are joined in rather than left to the caller. The
    screen this feeds exists mainly to answer "which of these is waiting for
    me", and answering it per row meant one `/compute/chain/state` call per
    project - an N+1 that grows with the list. Both facts are one query each.

    `project.status` is NOT the same field as `chain_state` and the two are
    kept apart on purpose: the first is the project's own lifecycle flag, the
    second is where the six-stage chain stopped. Merging them would produce a
    single column that is sometimes one and sometimes the other.
    """
    import chain

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT p.id, p.title, p.topic, p.status, p.created_at,"
            "  p.usd_budget, p.usd_spent,"
            "  (SELECT count(*) FROM run r WHERE r.project_id = p.id) AS n_runs,"
            "  (SELECT count(DISTINCT h.paper_id) FROM search_query q"
            "     JOIN search_hit h ON h.search_query_id = q.id"
            "     JOIN run r2 ON r2.id = q.run_id"
            "    WHERE r2.project_id = p.id) AS n_papers,"
            "  (SELECT count(*) FROM idea i WHERE i.project_id = p.id) AS n_ideas "
            "FROM project p ORDER BY p.created_at DESC LIMIT %s", (int(limit),))
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            d["id"] = str(d["id"])
            if d.get("created_at") is not None:
                d["created_at"] = d["created_at"].isoformat()
            budget = None if d["usd_budget"] is None else float(d["usd_budget"])
            spent = float(d["usd_spent"] or 0)
            d["usd_budget"] = budget
            d["usd_spent"] = round(spent, 6)
            d["usd_remaining"] = None if budget is None else round(budget - spent, 6)
            rows.append(d)

        # One query for every listed project rather than one per project.
        latest = {}
        if rows:
            cur.execute(
                "SELECT DISTINCT ON (project_id, stage)"
                "       project_id, stage, status, finished_at "
                "FROM run WHERE project_id = ANY(%s) AND stage = ANY(%s) "
                "ORDER BY project_id, stage, started_at DESC NULLS LAST",
                ([d["id"] for d in rows], chain.STAGE_NAMES))
            for r in cur.fetchall():
                latest.setdefault(str(r["project_id"]), {})[r["stage"]] = {
                    "status": r["status"], "finished_at": r["finished_at"]}

    for d in rows:
        stages = latest.get(d["id"], {})
        d["chain_state"], d["parked"] = _chain_state_of(stages)
        d["n_stages_done"] = sum(1 for v in stages.values()
                                 if v["status"] == "done")
        d["n_stages"] = len(chain.STAGE_NAMES)

    return {"n": len(rows), "projects": rows,
            "n_awaiting_you": sum(1 for d in rows
                                  if d["chain_state"] == "awaiting_you")}


def list_runs(project_id, limit=50):
    """Runs of a project, newest first, with what each produced."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT r.id, r.stage, r.status, r.started_at, r.finished_at,"
            "  (SELECT count(*) FROM search_query q WHERE q.run_id = r.id) AS n_queries,"
            "  (SELECT count(*) FROM novelty_check n WHERE n.run_id = r.id) AS n_checked "
            "FROM run r WHERE r.project_id = %s "
            "ORDER BY r.started_at DESC NULLS LAST LIMIT %s",
            (project_id, int(limit)))
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            d["id"] = str(d["id"])
            for k in ("started_at", "finished_at"):
                if d.get(k) is not None:
                    d[k] = d[k].isoformat()
            rows.append(d)
    return {"project_id": project_id, "n": len(rows), "runs": rows}


def sync_prompts(entries):
    """Store each pack as a new version when its content has changed.

    Unchanged content does not get a new version. Otherwise every deploy would
    bump every pack, and `domain_frame` would point at versions that differ from
    their predecessor by nothing - which makes the version number useless for
    the one question it exists to answer.
    """
    out = []
    with connect() as conn:
        with conn.cursor() as cur:
            for e in entries:
                cur.execute("SELECT version, content FROM skill_prompt "
                            "WHERE key = %s ORDER BY version DESC LIMIT 1", (e["key"],))
                row = cur.fetchone()
                if row and row["content"] == e["content"]:
                    out.append({"key": e["key"], "version": row["version"],
                                "changed": False})
                    continue
                version = (row["version"] + 1) if row else 1
                cur.execute("INSERT INTO skill_prompt (key, version, content) "
                            "VALUES (%s, %s, %s)", (e["key"], version, e["content"]))
                out.append({"key": e["key"], "version": version, "changed": True})
        conn.commit()
    return {"n": len(out), "n_changed": sum(1 for x in out if x["changed"]),
            "prompts": out}


def get_prompt(key, version=None):
    with connect() as conn, conn.cursor() as cur:
        if version:
            cur.execute("SELECT key, version, content, updated_at FROM skill_prompt "
                        "WHERE key = %s AND version = %s", (key, version))
        else:
            cur.execute("SELECT key, version, content, updated_at FROM skill_prompt "
                        "WHERE key = %s ORDER BY version DESC LIMIT 1", (key,))
        row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["updated_at"] = d["updated_at"].isoformat()
    return d


def prompt_versions():
    """Which packs are loaded and at what version, without their contents."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT key, max(version) AS version, max(updated_at) AS updated_at "
                    "FROM skill_prompt GROUP BY key ORDER BY key")
        return {"prompts": [{"key": r["key"], "version": r["version"],
                             "updated_at": r["updated_at"].isoformat()}
                            for r in cur.fetchall()]}


def save_domain_frame(project_id, frame):
    """Record which frame a project reasons under, and which version of it.

    The versions are stored alongside the choice because the packs change. A
    report has to be readable six months later without re-running anything, and
    "observational" alone does not say which observational.
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE project SET domain_frame = %s WHERE id = %s "
                        "RETURNING id, title, topic",
                        (psycopg.types.json.Jsonb(frame), project_id))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"no such project: {project_id}")
        conn.commit()
    return {"project_id": str(row["id"]), "title": row["title"],
            "topic": row["topic"], "domain_frame": frame}


def get_domain_frame(project_id):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, title, topic, domain_frame FROM project WHERE id = %s",
                    (project_id,))
        row = cur.fetchone()
    if not row:
        return None
    return {"project_id": str(row["id"]), "title": row["title"],
            "topic": row["topic"], "domain_frame": row["domain_frame"]}


def novelty_pubmed_pending(project_id):
    """Novelty checks whose rounds have not had a PubMed pass yet.

    W7 runs its rounds server-side, where NCBI blocks E-utilities, so every
    adversarial check in this system was decided without PubMed. The queries it
    used are recorded, though, which is what makes a later pass possible at all:
    the same questions can be asked again from an address NCBI has not blocked,
    and the answers merged into the round they belong to.

    Only the latest check per idea is offered. An older one has already been
    superseded, and re-checking it would spend requests to update a row nothing
    reads.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT ON (n.idea_id) n.id, n.idea_id, n.verdict, "
            "       n.rounds, n.checked_at, i.code, i.title "
            "FROM novelty_check n "
            "JOIN idea i ON i.id = n.idea_id "
            "WHERE i.project_id = %s AND n.method = 'adversarial' "
            "ORDER BY n.idea_id, n.checked_at DESC", (project_id,))
        out = []
        for r in cur.fetchall():
            blob = r["rounds"] or {}
            if blob.get("pubmed_pass"):
                continue
            qs = []
            for rd in (blob.get("rounds") or []):
                q = (rd.get("query") or "").strip()
                if not q:
                    continue
                qs.append({"round": rd.get("round"), "query": q,
                           "n_hits": rd.get("n_hits"),
                           # Carried because an empty round that stops being
                           # empty is the single most informative outcome of
                           # this pass - see `_pubmed_contradiction`.
                           "was_empty": not (rd.get("papers") or [])})
            if not qs:
                continue
            out.append({"check_id": str(r["id"]), "idea_id": str(r["idea_id"]),
                        "code": r["code"], "title": r["title"],
                        "verdict": r["verdict"], "n_queries": len(qs),
                        "queries": qs})
        return {"project_id": project_id, "n": len(out), "checks": out}


def _paper_key(p):
    """What makes two records the same paper, in order of how much it is worth.

    Written as three exits rather than an `or` chain because the chain had a
    hole: `"pmid:" + ""` is `"pmid:"`, which is truthy, so every record with
    neither a DOI nor a PMID collided on that one string and the merge would
    have folded unrelated papers into one. A title is a weak key but it is a
    key; a prefix with nothing after it is not.
    """
    doi = (p.get("doi") or "").strip().lower()
    if doi:
        return doi
    pmid = str(p.get("pmid") or "").strip()
    if pmid:
        return "pmid:" + pmid
    return (p.get("title") or "").strip().lower()[:120]


def _pubmed_contradiction(verdict, added, revived):
    """Whether the merged evidence has made the recorded verdict untenable.

    Deliberately mechanical and narrow. The verdict itself was never computed
    from these rounds - `save_novelty` takes the model's word and only refuses
    what the evidence cannot support - so nothing here recomputes it. What can
    be established without judgement is a contradiction:

    `no_prior_art` is a bounded negative whose bound was "these searches found
    nothing". A round that found nothing and now, asked in the same words of a
    database the first pass could not reach, finds papers is not a hint that
    the verdict was optimistic. It is the bound failing.

    Everything else is reported as a count and left alone, because "PubMed
    added four papers to an `adjacent` verdict" needs somebody to read the four
    papers before it means anything.
    """
    if verdict == "no_prior_art" and revived:
        return {"level": "contradicted",
                "why": f"判定是「無前案」，但 PubMed 在原本空白的第 "
                       f"{', '.join(str(r) for r in revived)} 輪找到了論文。"
                       f"那個判定的依據是「這些檢索什麼都沒找到」，而依據不成立了。"}
    if verdict == "no_prior_art" and added:
        return {"level": "weakened",
                "why": f"判定是「無前案」，而 PubMed 另外找到 {added} 篇。"
                       f"沒有推翻空白輪次，但涵蓋範圍的說明是在 PubMed "
                       f"不可用的前提下寫的。"}
    if added:
        return {"level": "note",
                "why": f"PubMed 另外找到 {added} 篇。判定沒有被機械地推翻——"
                       f"要不要改判，得有人讀過那幾篇。"}
    return None


def novelty_merge_pubmed(check_id, by_round):
    """Merge a PubMed pass into a stored novelty check, round by round.

    Papers are unioned into the round that asked for them rather than appended
    to `closest_papers`. That list is the model's own selection of what came
    closest, and quietly growing it would turn a judgement into a pile. The
    debate's evidence pool reads the rounds as well, so nothing is lost by
    keeping the two apart - see `debate._evidence_pool`.

    `by_round` is {round number: [paper, ...]} already parsed by the caller.
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, verdict, rounds FROM novelty_check "
                        "WHERE id = %s", (check_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"no such novelty check: {check_id}")
            blob = dict(row["rounds"] or {})
            rounds = [dict(r) for r in (blob.get("rounds") or [])]

            added = 0
            revived = []
            for rd in rounds:
                new = by_round.get(rd.get("round")) or by_round.get(str(rd.get("round")))
                if not new:
                    continue
                have = {_paper_key(p) for p in (rd.get("papers") or [])}
                was_empty = not (rd.get("papers") or [])
                keep = []
                for p in new:
                    k = _paper_key(p)
                    if k and k not in have:
                        have.add(k)
                        keep.append({x: p.get(x) for x in
                                     ("title", "year", "doi", "pmid", "journal",
                                      "venue", "citations", "source")
                                     if p.get(x) is not None})
                if not keep:
                    continue
                rd["papers"] = (rd.get("papers") or []) + keep
                rd["n_hits"] = len(rd["papers"])
                rd["pubmed_added"] = len(keep)
                added += len(keep)
                if was_empty:
                    revived.append(rd.get("round"))

            contradiction = _pubmed_contradiction(
                (row["verdict"] or "").strip().lower(), added, revived)

            blob["rounds"] = rounds
            # Stamped whether or not anything was found. "PubMed added nothing"
            # and "PubMed was never asked" are different facts, and without this
            # the pass would be offered again for ever.
            blob["pubmed_pass"] = {
                "n_queries": len(by_round), "n_added": added,
                "rounds_no_longer_empty": revived,
                "contradiction": contradiction,
                "collected_by": "browser or local machine, because NCBI blocks "
                                "this deployment's IP from E-utilities",
            }
            cur.execute("UPDATE novelty_check SET rounds = %s WHERE id = %s",
                        (psycopg.types.json.Jsonb(blob), check_id))
        conn.commit()
    return {"check_id": str(check_id), "n_added": added,
            "rounds_no_longer_empty": revived, "contradiction": contradiction}


# The marker that says a PubMed pass has happened for a literature run. Written
# into `search_query.query_angle` by both collectors, so no schema change and no
# second source of truth: if a row like this exists, the pass has happened.
PUBMED_ANGLE_PREFIX = "pubmed via"


def pubmed_work(limit=12):
    """Everything on this deployment that still needs a PubMed pass.

    One call rather than a walk over every project, because the thing that runs
    this wakes up every few minutes, does nothing, and goes away again - and a
    worker that costs six requests to learn there is no work will be turned off.

    Two kinds of work, and they are separate because they fail separately:

      literature  a project whose literature run has no PubMed-collected query.
                  W2 plans the crossings and this repeats them from an address
                  NCBI has not blocked.
      novelty     an adversarial check whose rounds were decided without
                  PubMed. The queries were recorded, so they can be asked again
                  and merged into the round they belong to.

    `parked_after_novelty` says the chain is waiting and the worker may release
    it once the merge is done. It is deliberately a fact about the run rather
    than an instruction: releasing something that is not parked is how a chain
    gets pushed past a review point nobody looked at.
    """
    out = []
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT p.id, p.topic, p.title, p.vocab_expansion FROM project p "
            "WHERE p.status IS NULL OR p.status NOT IN ('archived','stopped') "
            "ORDER BY p.created_at DESC LIMIT %s", (int(limit),))
        projects = cur.fetchall()

        for p in projects:
            pid = str(p["id"])

            # --- the literature half -------------------------------------
            cur.execute(
                "SELECT r.id, "
                "       COUNT(*) FILTER (WHERE q.query_angle LIKE %s) AS n_pubmed, "
                "       MAX(q.domain) AS domain "
                "FROM run r LEFT JOIN search_query q ON q.run_id = r.id "
                "WHERE r.project_id = %s AND r.stage = 'lit_search' "
                "GROUP BY r.id ORDER BY MAX(q.executed_at) DESC NULLS LAST "
                "LIMIT 1", (PUBMED_ANGLE_PREFIX + "%", pid))
            lit = cur.fetchone()
            literature = None
            # A project with no recorded expansion has no concepts to plan a
            # PubMed crossing from, so this can never be done for it. Without
            # this it stays on the list for ever, is picked every five minutes,
            # skipped, and picked again - and while the bounded worker spends
            # its slots on those, real work behind them waits.
            if lit and not lit["n_pubmed"] and p["vocab_expansion"]:
                literature = {"run_id": str(lit["id"]),
                              "domain": lit["domain"] or "clinical"}

            # --- the novelty half ----------------------------------------
            nov = novelty_pubmed_pending(pid)
            novelty = nov["checks"] if nov["n"] else None

            # --- is the chain waiting on us ------------------------------
            cur.execute(
                "SELECT status FROM run WHERE project_id = %s AND stage = 'novelty' "
                "ORDER BY started_at DESC LIMIT 1", (pid,))
            nr = cur.fetchone()
            parked = bool(nr and nr["status"] == "awaiting_review")

            if literature or novelty or parked:
                out.append({"project_id": pid, "topic": p["topic"] or p["title"],
                            "literature": literature, "novelty": novelty,
                            "parked_after_novelty": parked})
    return {"n": len(out), "projects": out}
