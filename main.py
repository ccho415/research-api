"""Research API — the compute layer n8n calls over Zeabur's private network.

Wraps the literature-search and idea-triage scripts as HTTP endpoints.
Data profiling is deliberately NOT here: it stays on your own machine so raw
research data never leaves it.
"""

import os
import sys
import tempfile
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import backup  # noqa: E402
import ops  # noqa: E402

API_KEY = os.environ.get("API_KEY", "")

app = FastAPI(title="Research API", version="1.0.0")


def check_key(x_api_key: Optional[str]):
    if not API_KEY:
        raise HTTPException(500, "API_KEY is not set on the server")
    if x_api_key != API_KEY:
        raise HTTPException(401, "invalid or missing X-API-Key header")


# --------------------------------------------------------------------------
# health
# --------------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    """No auth: n8n and Zeabur use this to check the service is alive."""
    return {"ok": True, "service": "research-api", "version": "1.0.0"}


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------
class QueryIn(BaseModel):
    query: str
    domain: str = "general"
    sources: Optional[List[str]] = None
    limit: int = 25
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    sort: str = "relevance"
    # When given, each source is sent this crossing in its own dialect and
    # `query` is only what the search is called in the record.
    concepts: Optional[List[Dict[str, Any]]] = None


@app.post("/compute/search/query")
def search_query(body: QueryIn, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    return ops.search_query(body.query, body.domain, body.sources, body.limit,
                            body.year_from, body.year_to, body.sort, body.concepts)


class ExpandIn(BaseModel):
    concepts: List[str]
    domain: str = "general"
    per_concept: int = 10
    max_queries: int = 10
    # Recording the expansion needs the project it belongs to; without one the
    # expansion still runs, it just has nothing to be compared against later.
    project_id: Optional[str] = None


@app.post("/compute/search/expand")
def search_expand(body: ExpandIn, x_api_key: Optional[str] = Header(None)):
    """Resolve concepts to controlled vocabulary and plan the searches.

    Expansion and planning are one call because n8n has no reason to see the
    intermediate result, and because the plan is meaningless without the
    expansion that produced it.
    """
    check_key(x_api_key)
    try:
        expansion = ops.search_expand(body.concepts, body.domain, body.per_concept)
        plan = ops.plan_queries(expansion, body.max_queries)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")

    out = {"expansion": expansion, "plan": plan, "n_queries": len(plan),
           "degraded": expansion["degraded"]}
    if body.project_id:
        import db
        try:
            out["expansion_record"] = db.record_expansion(body.project_id, expansion)
        except Exception as e:
            out["expansion_record"] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    return out


class RunStartIn(BaseModel):
    topic: str
    domain: Optional[str] = None
    project_id: Optional[str] = None
    run_id: Optional[str] = None


@app.post("/compute/run/start")
def run_start(body: RunStartIn, x_api_key: Optional[str] = Header(None)):
    """Create (or adopt) the project and run this search belongs to."""
    check_key(x_api_key)
    import db
    try:
        return db.start_run(body.topic, body.domain, body.project_id, body.run_id)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


@app.get("/compute/run/{run_id}/done-queries")
def run_done_queries(run_id: str, x_api_key: Optional[str] = Header(None)):
    """What this run already stored, so a resumed run does not repeat it."""
    check_key(x_api_key)
    import db
    try:
        return {"run_id": run_id, "done": db.done_queries(run_id)}
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


class RunFinishIn(BaseModel):
    run_id: str
    status: str = "done"


@app.post("/compute/run/finish")
def run_finish(body: RunFinishIn, x_api_key: Optional[str] = Header(None)):
    """Close the run and write its metrics to health_metric."""
    check_key(x_api_key)
    import db
    try:
        return db.finish_run(body.run_id, body.status)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


class VocabIn(BaseModel):
    term: str
    domain: str = "general"


@app.post("/compute/search/vocab")
def search_vocab(body: VocabIn, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    return ops.search_vocab(body.term, body.domain)


class ChainIn(BaseModel):
    doi: str
    topic: Optional[str] = None
    depth: int = 1
    per_step: int = 6
    milestone: int = 1000


class IngestIn(BaseModel):
    query_text: str
    results: List[Dict[str, Any]]
    run_id: Optional[str] = None
    domain: Optional[str] = None
    # Either the plain list of source names, or the attempt-outcome object from
    # a search result: which sources were tried, which answered, which failed
    # and why.  PubMed makes those differ on every clinical search from here.
    sources: Optional[Any] = None
    query_angle: Optional[str] = None
    axis_source: Optional[str] = None


@app.post("/compute/search/ingest")
def search_ingest(body: IngestIn, x_api_key: Optional[str] = Header(None)):
    """Store one search and its results, and report how much was already cached.

    Ingest happens here rather than in n8n because a result set carries every
    abstract, and moving that between workflow nodes is the fastest way to
    exhaust a small instance. n8n sends it once and gets back counts.
    """
    check_key(x_api_key)
    import db
    try:
        return db.ingest(body.query_text, body.results, body.run_id, body.domain,
                         body.sources, body.query_angle, body.axis_source)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


@app.get("/compute/search/corpus")
def search_corpus(x_api_key: Optional[str] = Header(None)):
    """How big the literature cache is."""
    check_key(x_api_key)
    import db
    try:
        return db.corpus_stats()
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


@app.post("/compute/search/chain")
def search_chain(body: ChainIn, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    return ops.search_chain(body.doi, body.topic, body.depth,
                            body.per_step, body.milestone)


# --------------------------------------------------------------------------
# triage
# --------------------------------------------------------------------------
class DedupIn(BaseModel):
    ideas: List[Dict[str, Any]]
    threshold: float = 0.15
    top: int = 15


@app.post("/compute/triage/dedup")
def triage_dedup(body: DedupIn, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    if len(body.ideas) < 2:
        raise HTTPException(400, "need at least 2 ideas")
    return ops.triage_dedup(body.ideas, body.threshold, body.top)


class PairsIn(BaseModel):
    ideas: List[Dict[str, Any]]
    anchors: Optional[List[Dict[str, Any]]] = None
    criteria: Optional[List[str]] = None
    shuffle_seed: int = 0
    batch_size: int = 3


@app.post("/compute/triage/pairs")
def triage_pairs(body: PairsIn, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    try:
        return ops.triage_pairs(body.ideas, body.anchors, body.criteria,
                                body.shuffle_seed, body.batch_size)
    except ValueError as e:
        raise HTTPException(400, str(e))


class EloIn(BaseModel):
    matches: List[Dict[str, Any]]
    ideas: Optional[List[Dict[str, Any]]] = None
    anchors: Optional[List[Dict[str, Any]]] = None
    k: float = 32.0


@app.post("/compute/triage/elo")
def triage_elo(body: EloIn, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    try:
        return ops.triage_elo(body.matches, body.ideas, body.anchors, body.k)
    except ValueError as e:
        raise HTTPException(400, str(e))


# --------------------------------------------------------------------------
# backup
# --------------------------------------------------------------------------
@app.get("/admin/config")
def admin_config(x_api_key: Optional[str] = Header(None)):
    """Where the database settings came from. Never returns the password."""
    check_key(x_api_key)
    return backup.config_report()


@app.get("/admin/dbstats")
def admin_dbstats(x_api_key: Optional[str] = Header(None)):
    """Table count, row estimate and size - cheap enough to check every night."""
    check_key(x_api_key)
    try:
        return backup.stats()
    except Exception as e:
        raise HTTPException(500, str(e)[:500])


@app.get("/admin/backup")
def admin_backup(x_api_key: Optional[str] = Header(None)):
    """Return a pg_dump of the research database as a downloadable file.

    The row estimate travels in a header so the caller can refuse a dump that
    ran cleanly against an empty database - the failure that otherwise stays
    invisible until you need the backup.
    """
    check_key(x_api_key)
    if not backup.acquire():
        raise HTTPException(409, "a backup is already running")
    try:
        path, name, size = backup.dump()
        rows = backup.row_total()
    except Exception as e:
        backup.release()
        raise HTTPException(500, str(e)[:500])

    def done():
        try:
            os.unlink(path)
        except OSError:
            pass
        backup.release()

    return FileResponse(
        path, filename=name, media_type="application/octet-stream",
        headers={"X-Dump-Filename": name, "X-Dump-Bytes": str(size),
                 "X-Row-Estimate": "unknown" if rows is None else str(rows)},
        background=BackgroundTask(done))


@app.post("/admin/restore-drill")
async def admin_restore_drill(request: Request,
                              x_api_key: Optional[str] = Header(None)):
    """Restore a posted dump into a scratch database and report what came back.

    Post the dump file itself as the raw request body, so what gets verified
    is the archived artefact rather than a fresh dump that happens to work.
    """
    check_key(x_api_key)
    if not backup.acquire():
        raise HTTPException(409, "a backup or drill is already running")

    fd, path = tempfile.mkstemp(prefix="drill-", suffix=".dump")
    try:
        size = 0
        with os.fdopen(fd, "wb") as fh:
            async for chunk in request.stream():
                size += len(chunk)
                fh.write(chunk)
        if size == 0:
            raise HTTPException(400, "request body was empty; post the dump file")
        report = backup.restore_drill(path)
        report["dump_bytes"] = size
        return report
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e)[:800])
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
        backup.release()


# --------------------------------------------------------------------------
@app.exception_handler(Exception)
def unhandled(request, exc):
    # Never leak a stack trace to the caller; the log keeps the detail.
    print(f"[error] {type(exc).__name__}: {exc}", file=sys.stderr)
    return JSONResponse(status_code=500,
                        content={"error": type(exc).__name__, "detail": str(exc)[:300]})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
