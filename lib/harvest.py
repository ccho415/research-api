"""Harvest what a field says about itself, out of the cache W2 already filled.

This is tools/harvest_gaps.py with its own literature search removed. That
script searched Europe PMC from scratch every time, which duplicated the work
W2 had already done and paid for: the papers were already in `paper`, reachable
through the run that found them.

Two halves, with very different costs.

Title concepts come free. W2 stored the titles, so ranking the concepts in them
is arithmetic over rows already present - no external call at all.

Gap sentences do not. They live in Discussion sections, and `paper` holds title
and abstract only, so the full text has to be fetched one paper at a time. That
is why this is a job rather than an endpoint that answers: three hundred papers
is several minutes of polite requests, and nothing should hold an HTTP
connection open that long.

The fetched sections are cached in `paper_section`, which is the point of doing
it this way. The second harvest over the same papers makes no external calls.
A paper with no retrievable full text is cached as NULL rather than left absent,
so it is not retried on every subsequent run.
"""

import json
import re
import time
import urllib.parse
import urllib.request

import concepts as C

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
UA = {"User-Agent": "research-api/1.0 (gap harvesting"
                    + (f"; {__import__('os').environ['ACADEMIC_MAILTO']}"
                       if __import__('os').environ.get("ACADEMIC_MAILTO") else "") + ")"}

# Phrases authors use when saying something is unfinished.  Deliberately wide:
# the specificity filter downstream is what separates a direction from a
# ritual, so this only has to find the sentence.
CUES = re.compile(
    r"(further (studies|research|work|investigation|trials)"
    r"|future (studies|research|work|direction|investigation)"
    r"|remains? (to be|unclear|unknown|poorly|largely)"
    r"|warrant(s|ed)? (further|investigation|study)"
    r"|(has|have) (yet|not) (to|been)"
    r"|little is known|not (yet )?(been )?(fully )?(investigated|explored|studied|elucidated|understood|characterized|characterised)"
    r"|unclear (whether|how|why|if)|it (is|remains) unclear"
    r"|should be (explored|investigated|examined|addressed)"
    r"|larger (studies|cohorts|samples)|prospective studies are (needed|required|warranted)"
    r"|no studies have|few studies have|studies are (needed|required|warranted)"
    r"|deserves? (further|investigation)|merits? (further|investigation))",
    re.I)

SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")

# One paper at a time with a pause between.  The egress IP this runs from has
# already been blocked permanently by NCBI once, and Europe PMC is the only
# source the gap harvest has.
PAUSE = 0.3


def _get(url, text=False, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
            return raw.decode("utf-8", "replace") if text else json.loads(raw.decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def resolve_pmcid(pmid):
    """The PMCID for a PMID, or None if the paper has no open full text.

    Europe PMC keys full text on PMCID and W2 stored PMIDs, so this gap has to
    be crossed once per paper.  The answer is written back to `paper` so it is
    crossed only once ever.
    """
    if not pmid:
        return None
    u = (f"{EPMC}/search?format=json&pageSize=1"
         f"&query={urllib.parse.quote(f'EXT_ID:{pmid} AND SRC:MED')}")
    d = _get(u)
    rows = ((d or {}).get("resultList") or {}).get("result") or []
    return (rows[0].get("pmcid") if rows else None) or None


def discussion_xml(pmcid):
    """The Discussion or Conclusions text, or None if there is no full text."""
    xml = _get(f"{EPMC}/{pmcid}/fullTextXML", text=True)
    if not xml or len(xml) < 20000:
        return None
    parts = []
    for m in re.finditer(r"<title>\s*(Discussion|Conclusions?|"
                         r"Discussion and Conclusions?)\s*</title>(.*?)(?=<sec |</body)",
                         xml, re.S | re.I):
        parts.append(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(2))))
    return " ".join(parts) or None


def gap_sentences(text):
    """Sentences claiming something is unfinished, with their concepts attached.

    `mesh_concepts` is a hint for whoever reads this next, deliberately not a
    filter.  Measured on lung adenocarcinoma it misjudges in both directions,
    and the misses are the valuable ones: "the mechanism underlying the MLH1
    V384D-associated EGFR-TKI resistance" names a variant and a resistance
    pathway and matches no MeSH descriptor at all, while "elucidate the role of
    these newly implicated functions" matches `Role` and says nothing.
    """
    out = []
    for s in SENT.split(text or ""):
        s = s.strip()
        if not (60 <= len(s) <= 400) or not CUES.search(s):
            continue
        found = [ui for ui in C.extract(s) if not C.is_generic(ui)]
        out.append({"sentence": s,
                    "mesh_concepts": [{"ui": ui, "label": C.label(ui)} for ui in found]})
    return out


def rank_title_concepts(papers):
    """What the field's own titles are about, most used first.

    Titles are the one place every word was chosen on purpose.  Concepts pulled
    from abstract bodies include `Rosa` (from "levels rose"), `Lifting` and
    `Achievement`; titles produce almost none of that.  The same two filters the
    bridge work needed still apply, because titles still carry `Neoplasms` and
    `Association`.
    """
    found = {}
    for p in papers:
        title = p.get("title") or ""
        for ui in C.extract(title):
            if C.is_generic(ui) or not C.is_specific(ui):
                continue
            e = found.setdefault(ui, {"ui": ui, "label": C.label(ui),
                                      "semantic_types": C.semantic_types(ui),
                                      "n_papers": 0, "examples": []})
            e["n_papers"] += 1
            if len(e["examples"]) < 3:
                e["examples"].append(title[:110])
    return sorted(found.values(), key=lambda e: -e["n_papers"])


def run_harvest(harvest_id, project_id=None, source_run_id=None, max_papers=200):
    """Do the work and record it. Called in the background, never awaited.

    Written to survive being interrupted: every fetched section is committed as
    it arrives, so a job killed halfway leaves the cache warmer than it found it
    and the next attempt skips what was already fetched. That matters here more
    than usual, because pushing code restarts this service and the fetch loop is
    minutes long.
    """
    import db

    try:
        papers = db.papers_for(project_id, source_run_id, limit=max_papers)
        if not papers:
            db.finish_harvest(harvest_id, error="no cached papers for that project or run")
            return

        concepts_ranked = rank_title_concepts(papers)

        cached = db.cached_sections([p["id"] for p in papers])
        gaps = []
        n_fulltext = 0

        for p in papers:
            pid = p["id"]
            if pid in cached:
                text = cached[pid]          # may be None: known to have no full text
            else:
                pmcid = p.get("pmcid")
                if not pmcid and p.get("pmid"):
                    try:
                        pmcid = resolve_pmcid(p["pmid"])
                        time.sleep(PAUSE)
                    except Exception:
                        pmcid = None
                    if pmcid:
                        db.save_pmcid(pid, pmcid)
                text = None
                if pmcid:
                    try:
                        text = discussion_xml(pmcid)
                        time.sleep(PAUSE)
                    except Exception:
                        text = None
                # Cached either way. A null means this paper was looked up and
                # has no retrievable Discussion, which stops the next harvest
                # paying for the same disappointment.
                db.save_section(pid, "discussion", text)

            if not text:
                continue
            n_fulltext += 1
            for g in gap_sentences(text):
                gaps.append({**g, "pmid": p.get("pmid"), "pmcid": p.get("pmcid"),
                             "doi": p.get("doi"), "year": p.get("year"),
                             "title": p.get("title")})

        result = {
            "title_concepts": concepts_ranked,
            "gaps": gaps,
            "source": {"project_id": project_id, "source_run_id": source_run_id,
                       "n_papers": len(papers)},
        }
        db.finish_harvest(harvest_id, result=result, counts={
            "n_papers": len(papers), "n_with_fulltext": n_fulltext,
            "n_gap_sentences": len(gaps), "n_concepts": len(concepts_ranked)})
    except Exception as e:
        db.finish_harvest(harvest_id, error=f"{type(e).__name__}: {str(e)[:400]}")
