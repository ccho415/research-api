"""Research API — the compute layer n8n calls over Zeabur's private network.

Wraps the literature-search and idea-triage scripts as HTTP endpoints.
Data profiling is deliberately NOT here: it stays on your own machine so raw
research data never leaves it.
"""

import os
import sys
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
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


@app.post("/compute/search/query")
def search_query(body: QueryIn, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    return ops.search_query(body.query, body.domain, body.sources, body.limit,
                            body.year_from, body.year_to, body.sort)


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
@app.exception_handler(Exception)
def unhandled(request, exc):
    # Never leak a stack trace to the caller; the log keeps the detail.
    print(f"[error] {type(exc).__name__}: {exc}", file=sys.stderr)
    return JSONResponse(status_code=500,
                        content={"error": type(exc).__name__, "detail": str(exc)[:300]})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
