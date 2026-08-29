"""Research API — the compute layer n8n calls over Zeabur's private network.

Wraps the literature-search and idea-triage scripts as HTTP endpoints.
Data profiling is deliberately NOT here: it stays on your own machine so raw
research data never leaves it.
"""

import os
import sys
import tempfile
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
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
# verification
# --------------------------------------------------------------------------
class VerifyIn(BaseModel):
    directions: List[Dict[str, Any]]
    cutoff: int = 2015
    # How thin a term may be before the direction is reported as unjudgeable
    # rather than open. Travels in the request because it is a judgement.
    min_term_papers: int = 25
    # Whether to also ask full text whether the concepts meet at all. Two extra
    # requests per direction, and the only thing that separates "nobody has
    # done this" from "these words have nothing to do with each other".
    zones: bool = True


class DescribeTermsIn(BaseModel):
    terms: List[str]


@app.post("/compute/verify/terms")
def verify_terms(body: DescribeTermsIn, x_api_key: Optional[str] = Header(None)):
    """What MeSH knows about each term, and how many papers it reaches.

    This runs before the grouping decision rather than after, because the
    decision needs evidence the model does not have: MeSH covers only about a
    third of the entities that matter here, and a term it has never heard of
    that still reaches half a million papers is a word rather than an entity.
    Both facts are reported without a verdict attached - what to do about them
    is the caller's call.
    """
    check_key(x_api_key)
    if not body.terms:
        raise HTTPException(400, "need at least 1 term")
    import verify
    try:
        return {"terms": verify.describe_terms(body.terms)}
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


@app.post("/compute/verify/directions")
def verify_directions(body: VerifyIn, x_api_key: Optional[str] = Header(None)):
    """Count the papers behind each proposed direction rather than asking.

    Whether something has been done is a matter of record, so it is settled
    against the record.  The model that proposed these directions is forbidden
    from claiming novelty precisely because this endpoint exists.
    """
    check_key(x_api_key)
    if not body.directions:
        raise HTTPException(400, "need at least 1 direction")
    import verify
    try:
        return verify.verify(body.directions, body.cutoff, body.min_term_papers,
                             body.zones)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


class SaveDirectionsIn(BaseModel):
    directions: List[Dict[str, Any]]
    topic: Optional[str] = None
    project_id: Optional[str] = None
    run_id: Optional[str] = None
    cutoff: Optional[int] = None


# --------------------------------------------------------------------------
# domain frame
# --------------------------------------------------------------------------
@app.get("/compute/packs")
def packs_menu(x_api_key: Optional[str] = Header(None)):
    """What the router chooses between, plus the rules it chooses by.

    Summaries rather than the packs themselves. Routing needs to know what a
    pack is for; it does not need the pack. All thirteen in full is a hundred
    and thirty kilobytes of prompt to answer three questions, and on this model
    the thinking budget comes out of the same allowance as the reply.
    """
    check_key(x_api_key)
    import db
    import packs
    try:
        menu = packs.routing_menu()
        # The versions travel with the menu because the frame has to record
        # which version it chose, and a second round trip to fetch them is a
        # second chance to forget. It was forgotten once already: the first
        # frame written stored a null there.
        try:
            versions = {p["key"]: p["version"] for p in db.prompt_versions()["prompts"]}
        except Exception:
            versions = None
        return {**menu, "versions": versions, "rules": packs.routing_rules()}
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


@app.get("/compute/packs/{key}")
def packs_one(key: str, version: Optional[int] = None,
              x_api_key: Optional[str] = Header(None)):
    """One pack in full, at a given version. Downstream stages read this."""
    check_key(x_api_key)
    import db
    try:
        row = db.get_prompt(key, version)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")
    if not row:
        raise HTTPException(404, f"no such pack: {key}"
                                 " - run POST /admin/sync-packs first")
    return row


@app.post("/admin/sync-packs")
def packs_sync(x_api_key: Optional[str] = Header(None)):
    """Load the packs on disk into skill_prompt, versioning what changed.

    Disk is the source and this is the record of what was in force. Unchanged
    content does not get a new version, or every deploy would bump every pack
    and the version number would stop answering the only question it is for.
    """
    check_key(x_api_key)
    import db
    import packs
    try:
        return db.sync_prompts(packs.all_packs())
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


@app.get("/compute/prompts")
def prompts_list(x_api_key: Optional[str] = Header(None)):
    """Which packs are loaded and at what version, without their contents."""
    check_key(x_api_key)
    import db
    try:
        return db.prompt_versions()
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


class FrameIn(BaseModel):
    project_id: str
    frame: Dict[str, Any]


@app.post("/compute/frame/save")
def frame_save(body: FrameIn, x_api_key: Optional[str] = Header(None)):
    """Record which frame a project reasons under, with pack versions."""
    check_key(x_api_key)
    import db
    try:
        return db.save_domain_frame(body.project_id, body.frame)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


@app.get("/compute/frame")
def frame_get(project_id: str, section: Optional[str] = None,
              x_api_key: Optional[str] = Header(None)):
    """The domain frame, optionally with one named section of each pack.

    `section=Tier B` returns what is freely obtainable in this field, which is
    the one thing feasibility grading cannot work out for itself: in an
    observational field Tier B means joining area-level public data, and in a
    computational one it means public benchmarks while the real constraint is
    GPU-hours. A grader given only the pack's name guesses, and guesses in the
    direction of whatever field it saw last.

    One section rather than the whole pack. The rest carries novelty conventions
    and validity threats belonging to other steps, and adding them to a prompt
    that was just told not to judge novelty is how a step drifts off its own
    question.
    """
    check_key(x_api_key)
    import db
    try:
        row = db.get_domain_frame(project_id)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")
    if not row:
        raise HTTPException(404, "no such project")

    if section:
        import packs
        frame = row.get("domain_frame") or {}
        keys = frame.get("pack_keys") or []
        found = []
        for k in keys:
            got = packs.section(k, section)
            if got:
                found.append(got)
        row["sections"] = found
        # An empty list and a missing frame are different failures and the
        # caller has to tell them apart: no frame means nobody routed this
        # project, an empty list means the packs carry no such heading.
        row["sections_note"] = (
            "no domain frame for this project, so no pack could be consulted"
            if not keys else
            (f"no pack carries a section starting `{section}`" if not found
             else None))
    return row


@app.get("/compute/projects")
def projects_list(limit: int = 50, x_api_key: Optional[str] = Header(None)):
    """Projects with the counts that tell them apart.

    Nothing could be pointed at a project before this: the ids are uuids, and
    choosing between uuids from memory is not a thing to ask of a person or a
    workflow. The counts are what make a row identifiable.
    """
    check_key(x_api_key)
    import db
    try:
        return db.list_projects(limit)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


@app.get("/compute/projects/{project_id}/runs")
def project_runs(project_id: str, limit: int = 50,
                 x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    import db
    try:
        return db.list_runs(project_id, limit)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


@app.get("/compute/ideas")
def ideas_list(project_id: Optional[str] = None, run_id: Optional[str] = None,
               status: Optional[str] = None, limit: int = 200,
               x_api_key: Optional[str] = Header(None)):
    """The stored directions, each with the most recent check against them.

    The verdict and its coverage limits come back attached rather than on
    request, because a direction without them is the half of the record that
    misleads: the statement always reads plausibly and the caveats are what say
    how far to trust it.
    """
    check_key(x_api_key)
    if not (project_id or run_id):
        raise HTTPException(400, "need project_id or run_id")
    import db
    try:
        return db.list_ideas(project_id, run_id, status, limit)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


@app.post("/compute/ideas/save")
def ideas_save(body: SaveDirectionsIn, x_api_key: Optional[str] = Header(None)):
    """Store the directions and the record's answer about each one.

    An n8n execution is a transcript rather than a record: it expires, it
    cannot be queried, and the whole purpose of the check is to be read by a
    person afterwards. The caveats travel on the row itself because whoever
    reads it later will not have the experiment write-up open, and the verdict
    on its own reads far more confidently than its evidence deserves.
    """
    check_key(x_api_key)
    if not body.directions:
        raise HTTPException(400, "need at least 1 direction")
    if not (body.topic or body.project_id):
        raise HTTPException(400, "need either topic or project_id")
    import db
    try:
        return db.save_directions(body.directions, body.topic, body.project_id,
                                  body.run_id, body.cutoff)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


# --------------------------------------------------------------------------
# triage
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# gap harvest
# --------------------------------------------------------------------------
class HarvestStartIn(BaseModel):
    project_id: Optional[str] = None
    source_run_id: Optional[str] = None
    max_papers: int = 200


@app.post("/compute/harvest/start")
def harvest_start(body: HarvestStartIn, background: BackgroundTasks,
                  x_api_key: Optional[str] = Header(None)):
    """Begin harvesting concepts and gap statements. Returns before it finishes.

    A job rather than an answer because the expensive half cannot be hurried:
    gap statements live in Discussion sections, the cache holds title and
    abstract only, and each paper's full text is a separate polite request. Two
    hundred papers is minutes. Nothing should hold an HTTP connection open that
    long, and n8n should not be blocked waiting either.

    Poll GET /compute/harvest/{id} for the result.
    """
    check_key(x_api_key)
    if not (body.project_id or body.source_run_id):
        raise HTTPException(400, "need project_id or source_run_id")
    import db
    import harvest
    try:
        started = db.start_harvest(body.project_id, body.source_run_id)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")

    background.add_task(harvest.run_harvest, started["harvest_id"],
                        body.project_id, body.source_run_id, body.max_papers)
    return {**started, "status": "running",
            "poll": f"/compute/harvest/{started['harvest_id']}"}


@app.get("/compute/harvest/{harvest_id}")
def harvest_get(harvest_id: str, include_result: bool = True,
                x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    import db
    try:
        row = db.get_harvest(harvest_id=harvest_id, include_result=include_result)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")
    if not row:
        raise HTTPException(404, "no such harvest")
    return row


@app.get("/compute/harvest")
def harvest_latest(project_id: str, include_result: bool = True,
                   x_api_key: Optional[str] = Header(None)):
    """The most recent harvest for a project, so a caller need not track ids."""
    check_key(x_api_key)
    import db
    try:
        row = db.get_harvest(project_id=project_id, include_result=include_result)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")
    if not row:
        raise HTTPException(404, "no harvest for that project")
    return row


class SaveDedupIn(BaseModel):
    run_id: str
    pairs: List[Dict[str, Any]]


@app.post("/compute/dedup/save")
def dedup_save(body: SaveDedupIn, x_api_key: Optional[str] = Header(None)):
    """Store the judgement on each candidate pair.

    A pair nobody was sure about keeps a null verdict, which is what puts it in
    front of a person later. Writing a guess there would quietly remove the
    pairs that most needed looking at.
    """
    check_key(x_api_key)
    import db
    try:
        return db.save_dedup_pairs(body.run_id, body.pairs)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


@app.get("/compute/dedup")
def dedup_list(run_id: str, undecided_only: bool = False, limit: int = 200,
               x_api_key: Optional[str] = Header(None)):
    """Candidate pairs, with both directions written out in full.

    Both statements come back rather than ids because deciding whether two
    directions are the same one requires reading both, and their own trial run
    found that codes and truncated titles made that judgement impossible.
    """
    check_key(x_api_key)
    import db
    try:
        return db.list_dedup_pairs(run_id, undecided_only, limit)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


# --------------------------------------------------------------------------
# tournament
# --------------------------------------------------------------------------
class AnchorsIn(BaseModel):
    anchors: List[Dict[str, Any]]


@app.post("/compute/anchors/save")
def anchors_save(body: AnchorsIn, x_api_key: Optional[str] = Header(None)):
    """Seed or update calibration anchors.

    Anchors are on by default, not optional. Without them a ranking is only
    relative and nobody can say whether the first place is actually good enough.
    """
    check_key(x_api_key)
    import tourney
    try:
        return tourney.save_anchors(body.anchors)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


class AnchorSetIn(BaseModel):
    set: Optional[str] = None


ANCHOR_FILES = {
    "scholarideas": "scholarideas_anchors.json",
    "published": "published_anchors.json",
}


@app.post("/admin/load-anchors")
def anchors_load(body: AnchorSetIn = AnchorSetIn(),
                 x_api_key: Optional[str] = Header(None)):
    """Load one of the anchor sets that ship with the repository.

    Named sets rather than a path, because a caller-supplied filename here
    would read any file the process can reach.

    Neither set is graded by a model, which is what makes either usable as a
    scale at all: the tournament is judged by a model, so a yardstick a model
    also wrote would calibrate the ranking against its own taste and tell us
    nothing. `scholarideas` takes its grades from expert review rubrics;
    `published` ties each one to an external checkable fact - citation counts,
    guideline adoption, or a paper stating outright that a line of work stopped
    adding information.

    Feasibility is null throughout. Both sets grade what a direction would
    contribute to its field. Neither says anything about whether this
    researcher could obtain the data, and filling that in would put a guess
    into the axis the lexicographic order depends on keeping separate.
    """
    check_key(x_api_key)
    which = (body.set or "scholarideas").strip()
    if which not in ANCHOR_FILES:
        raise HTTPException(400, "set must be one of " + ", ".join(ANCHOR_FILES))
    name = ANCHOR_FILES[which]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", name)
    if not os.path.exists(path):
        raise HTTPException(404, f"data/{name} is not deployed")
    import json as _json
    import tourney
    try:
        with open(path, encoding="utf-8") as fh:
            payload = _json.load(fh)
        out = tourney.save_anchors(payload.get("anchors") or [])
        return {**out, "source": payload.get("source"),
                "grading": payload.get("grading")}
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


@app.get("/compute/anchors")
def anchors_list(origin: Optional[str] = None, limit: int = 50,
                 x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    import tourney
    try:
        return tourney.list_anchors(origin, limit)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


class TournamentStartIn(BaseModel):
    project_id: str
    run_id: Optional[str] = None
    criteria: Optional[List[str]] = None
    k_factor: float = 32
    removed: Optional[List[Dict[str, Any]]] = None


class ResolveIn(BaseModel):
    run_id: str
    decided_by: Optional[str] = "rule"
    dry_run: Optional[bool] = False


@app.post("/compute/dedup/resolve")
def dedup_resolve(body: ResolveIn, x_api_key: Optional[str] = Header(None)):
    """Collapse each duplicated cluster to one surviving direction.

    Between deduplication and the tournament there was nothing recording which
    twin stays. Both entered, split their wins, and settled mid-table with
    standings that look entirely reasonable - so this runs before pairing
    rather than being caught afterwards.

    `dry_run` returns the choices without writing them, which is what the
    review screen shows.
    """
    check_key(x_api_key)
    import tourney
    try:
        return tourney.resolve_duplicates(body.run_id, body.decided_by or "rule",
                                          bool(body.dry_run))
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


class KeepIn(BaseModel):
    idea_id: str
    decided_by: Optional[str] = "human"


@app.post("/compute/dedup/keep")
def dedup_keep(body: KeepIn, x_api_key: Optional[str] = Header(None)):
    """Pin one direction as the survivor of its cluster, overruling the rule.

    The resolver has always refused to overrule a person, but nothing could make
    it one - the state it looked for could not be produced by any endpoint. This
    is the primitive the deduplication review screen needs, and without it that
    branch was guarding a decision nobody could record.
    """
    check_key(x_api_key)
    import tourney
    try:
        out = tourney.keep_this_one(body.idea_id, body.decided_by or "human")
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")
    if not out:
        raise HTTPException(404, "no such idea")
    return out


@app.get("/compute/ideas/live")
def ideas_live(project_id: Optional[str] = None, run_id: Optional[str] = None,
               limit: int = 200, x_api_key: Optional[str] = Header(None)):
    """The field the tournament competes over: merged-away directions excluded.

    `/compute/ideas` keeps returning everything, because a review screen has to
    be able to answer "where did that direction go". This one cannot, because a
    merged row entering the tournament produces no visible symptom.
    """
    check_key(x_api_key)
    if not project_id and not run_id:
        raise HTTPException(400, "need project_id or run_id")
    import tourney
    try:
        return tourney.live_ideas(project_id, run_id, limit)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


class DatasetIn(BaseModel):
    project_id: str
    inventory: Dict[str, Any]
    filename: Optional[str] = None
    pack: Optional[str] = None


@app.post("/compute/dataset/save")
def dataset_save(body: DatasetIn, x_api_key: Optional[str] = Header(None)):
    """Store a field inventory produced locally by tools/inventory.py.

    Rejects anything carrying rows. The local tool does not emit them, but this
    endpoint accepts any body and an inventory is the same shape a careless
    paste of the source data would have. Once a clinical extract reaches a
    server it cannot be taken back, so the check is here rather than in a note.
    """
    check_key(x_api_key)
    import datasets
    try:
        return datasets.save_dataset(body.project_id, body.inventory,
                                     body.filename, body.pack)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


@app.get("/compute/dataset")
def dataset_list(project_id: str, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    import datasets
    try:
        return datasets.list_datasets(project_id)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


class ProfileIn(BaseModel):
    project_id: str
    content: Dict[str, Any]
    derived_from: Optional[str] = None


@app.post("/compute/profile/save")
def profile_save(body: ProfileIn, x_api_key: Optional[str] = Header(None)):
    """A new version of the research profile. Older versions are never rewritten."""
    check_key(x_api_key)
    import datasets
    try:
        return datasets.save_profile(body.project_id, body.content,
                                     body.derived_from)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


@app.get("/compute/profile")
def profile_get(project_id: str, x_api_key: Optional[str] = Header(None)):
    """The current profile, or an explicit statement that there is none.

    Grading runs either way. Without a profile every tier has to be marked a
    generic default rather than a judgement about this researcher, so the
    absence travels as a note instead of as an empty object.
    """
    check_key(x_api_key)
    import datasets
    try:
        return datasets.get_profile(project_id)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


class FeasibilityIn(BaseModel):
    assessments: List[Dict[str, Any]]
    dataset_id: Optional[str] = None


@app.post("/compute/feasibility/save")
def feasibility_save(body: FeasibilityIn, x_api_key: Optional[str] = Header(None)):
    """Store one tier per direction, refusing the ones that say nothing.

    A B or C without the missing variable and the route means "no" while
    reading as "maybe", and someone plans around a tier they cannot reach.
    """
    check_key(x_api_key)
    import datasets
    try:
        return datasets.save_feasibility(body.assessments, body.dataset_id)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


@app.get("/compute/feasibility")
def feasibility_list(project_id: Optional[str] = None,
                     x_api_key: Optional[str] = Header(None)):
    """The board, grouped but never reordered.

    Within each group the tournament's order stands. Sorting by tier would make
    feasibility the primary axis, and a tier C direction can be worth far more
    than a tier A one.
    """
    check_key(x_api_key)
    import datasets
    try:
        return datasets.list_feasibility(project_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


@app.post("/compute/tournament/start")
def tournament_start(body: TournamentStartIn,
                     x_api_key: Optional[str] = Header(None)):
    """Open a tournament and record who was cut before it began, and why.

    The reasons are constrained to two by the database. A run once eliminated
    candidates for being outside the researcher's own methods, which smuggles a
    personal constraint into a judgement meant to be about contribution to the
    field, and a rule that lives only in a prompt breaks without a trace.
    """
    check_key(x_api_key)
    import tourney
    try:
        started = tourney.start_tournament(body.project_id, body.run_id,
                                           body.criteria, body.k_factor)
        if body.removed:
            started["reduction"] = tourney.save_field_reduction(
                started["tournament_id"], body.removed)
        return started
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


class MatchesIn(BaseModel):
    tournament_id: str
    matches: List[Dict[str, Any]]


@app.post("/compute/tournament/matches")
def tournament_matches(body: MatchesIn, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    import tourney
    try:
        return tourney.save_matches(body.tournament_id, body.matches)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


class RankingsIn(BaseModel):
    tournament_id: str
    rankings: List[Dict[str, Any]]


@app.post("/compute/tournament/rankings")
def tournament_rankings(body: RankingsIn, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    import tourney
    try:
        return tourney.save_rankings(body.tournament_id, body.rankings)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")


@app.get("/compute/tournament/{tournament_id}")
def tournament_get(tournament_id: str, x_api_key: Optional[str] = Header(None)):
    check_key(x_api_key)
    import tourney
    try:
        row = tourney.get_tournament(tournament_id)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:400]}")
    if not row:
        raise HTTPException(404, "no such tournament")
    return row


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
    """Where the database settings came from, and what code is actually live.

    The deployed routes are listed because that is the question actually being
    asked. A whole day went into guessing from the clock whether a push had
    finished building, and the guess was wrong at least once: a run started two
    minutes after the deploy was registered, while builds take three to six.

    Routes, and deliberately not a commit hash. The hash was added once in
    `0b84350` and reverted by the user four minutes later in `dac5d6a`, so it
    stays out. The route list is a different answer to the same question and a
    better one: a hash tells you which revision only if you can map revisions to
    behaviour from memory, while the route list is the deployment observed
    rather than inferred - if the endpoint you just wrote is in it, your push is
    live.
    """
    check_key(x_api_key)
    report = backup.config_report()
    routes = sorted({r.path for r in app.routes if getattr(r, "path", None)})
    report["build"] = {"n_routes": len(routes), "routes": routes}
    return report


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


class MigrateIn(BaseModel):
    file: str
    # Not optional, and not defaulted. The n8n instance and this project have
    # separate databases on the same server, and a migration applied to the
    # wrong one is both silent and hard to undo. Naming the expected database
    # makes the check structural instead of something the caller remembers.
    expect_database: str


@app.post("/admin/migrate")
def admin_migrate(body: MigrateIn, x_api_key: Optional[str] = Header(None)):
    """Apply one migration file from the repository, in a transaction.

    The file is read from `migrations/` rather than posted in, so what runs is
    what is version-controlled. Transcribing SQL into a workflow would make the
    schema and the file two separate truths, and a typo between them does not
    announce itself.
    """
    check_key(x_api_key)

    name = os.path.basename(body.file)
    if not name.endswith(".sql") or name != body.file:
        raise HTTPException(400, "file must be a plain .sql name in migrations/")
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations", name)
    if not os.path.exists(path):
        raise HTTPException(404, f"no such migration: {name}")

    import db
    try:
        with db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database() AS db")
                actual = cur.fetchone()["db"]
                if actual != body.expect_database:
                    raise HTTPException(
                        400, f"connected to '{actual}', not '{body.expect_database}' "
                             "- refusing to migrate")
                cur.execute("SELECT count(*) AS n FROM information_schema.tables "
                            "WHERE table_schema = 'public'")
                before = cur.fetchone()["n"]

                with open(path, encoding="utf-8") as fh:
                    cur.execute(fh.read())

                cur.execute("SELECT count(*) AS n FROM information_schema.tables "
                            "WHERE table_schema = 'public'")
                after = cur.fetchone()["n"]
            conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {str(e)[:500]}")

    return {"file": name, "database": actual, "applied": True,
            "tables_before": before, "tables_after": after}


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
