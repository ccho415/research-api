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


def resolve_pmcid(pmid=None, doi=None):
    """The PMCID for a paper, or None if it has no open full text.

    Takes either identifier because the cache mostly does not hold PMIDs.
    PubMed is permanently blocked from this egress IP, so W2's results arrive
    from Europe PMC, OpenAlex and Crossref, and those carry DOIs. Resolving by
    PMID only meant the harvest skipped nearly every paper it was given without
    making a single request - forty papers in two seconds, no full text found.

    The answer is written back to `paper` so this is crossed once ever.
    """
    if pmid:
        q = f"EXT_ID:{pmid} AND SRC:MED"
    elif doi:
        q = f'DOI:"{doi}"'
    else:
        return None
    u = f"{EPMC}/search?format=json&pageSize=1&query={urllib.parse.quote(q)}"
    d = _get(u)
    rows = ((d or {}).get("resultList") or {}).get("result") or []
    return (rows[0].get("pmcid") if rows else None) or None


# Section headings that mean "here is what we did not settle". Matched loosely
# on purpose: the previous pattern wanted a <title> reading exactly Discussion or
# Conclusions, so a paper titling its section `Results and Discussion`,
# `General Discussion`, `DISCUSSION` or `4. Discussion` yielded nothing at all
# while its full text sat in memory. Losing a paper we already fetched is worse
# than losing one we cannot reach.
DISCUSSION_TITLE = re.compile(
    r"<title>[^<]*\b(discussion|conclusion|concluding|"
    r"future (work|direction)|limitations?)\b[^<]*</title>", re.I)

# Some journals carry no <title> at all and mark the section with an attribute.
DISCUSSION_ATTR = re.compile(
    r'<sec[^>]*sec-type="[^"]*(discussion|conclusion)[^"]*"[^>]*>', re.I)


def _strip(xml_fragment):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml_fragment)).strip()


def discussion_xml(pmcid):
    """The Discussion or Conclusions text, or None if there is no full text.

    Two limits used to live here that were ours rather than the literature's: a
    hard 20,000-character floor on the XML, and a <title> pattern that only
    matched two exact words. Both silently discarded papers whose full text had
    already been fetched, which is the expensive half of this job.
    """
    xml = _get(f"{EPMC}/{pmcid}/fullTextXML", text=True)
    if not xml:
        return None
    # A record with no <body> is an abstract-only stub, which is the thing the
    # old length floor was really trying to catch. Checking for the body says
    # that directly instead of guessing at it with a byte count - a short but
    # real full text now survives.
    if "<body" not in xml.lower():
        return None

    parts = []
    for m in DISCUSSION_TITLE.finditer(xml):
        tail = xml[m.end():]
        stop = re.search(r"<sec[ >]|</body", tail)
        parts.append(_strip(tail[:stop.start()] if stop else tail))

    if not parts:
        for m in DISCUSSION_ATTR.finditer(xml):
            tail = xml[m.end():]
            stop = re.search(r"</sec>", tail)
            parts.append(_strip(tail[:stop.start()] if stop else tail))

    text = " ".join(p for p in parts if p)
    return text or None


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


def run_harvest(harvest_id, project_id=None, source_run_id=None, max_papers=200,
                refetch_missing=False):
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
        if refetch_missing:
            # A cached NULL means "looked, and there was no retrievable
            # Discussion" - which was partly a statement about the extractor
            # rather than about the paper. When that extractor changes, those
            # NULLs are stale answers, and keeping them would hide the fix
            # behind the cache that was meant to make the fix cheap.
            #
            # Only the NULLs are dropped. Text already fetched is still text.
            cached = {k: v for k, v in cached.items() if v}
        gaps = []
        n_fulltext = 0
        n_resolved = 0
        n_unidentified = 0
        # The two ways a paper with an identifier still yields nothing. They were
        # one number, and that number could not say whether the fix was to look
        # somewhere else for open access or to stop discarding text we already
        # had. Those are entirely different pieces of work.
        n_no_pmcid = 0
        n_pmcid_no_discussion = 0
        n_from_abstract = 0

        for p in papers:
            pid = p["id"]
            pmcid = p.get("pmcid")
            if pid in cached:
                text = cached[pid]          # may be None: known to have no full text
            else:
                looked = bool(pmcid)
                if not pmcid and (p.get("pmid") or p.get("doi")):
                    looked = True
                    n_resolved += 1
                    try:
                        pmcid = resolve_pmcid(p.get("pmid"), p.get("doi"))
                        time.sleep(PAUSE)
                    except Exception:
                        pmcid = None
                    if pmcid:
                        db.save_pmcid(pid, pmcid)
                    else:
                        n_no_pmcid += 1
                text = None
                if pmcid:
                    try:
                        text = discussion_xml(pmcid)
                        time.sleep(PAUSE)
                    except Exception:
                        text = None
                    if not text:
                        n_pmcid_no_discussion += 1
                # Only cache the answer when a lookup actually happened. A null
                # means "looked, and this paper has no retrievable Discussion",
                # which stops the next harvest paying again. Writing it for a
                # paper with no identifier would say that about a paper nobody
                # ever asked about, and would then hide it from any later fix
                # that gave it an identifier to be found by.
                if looked:
                    db.save_section(pid, "discussion", text)
                else:
                    n_unidentified += 1

            where = "discussion"
            if text:
                n_fulltext += 1
            else:
                # Falling back to the abstract, which is already in the cache and
                # costs nothing to read. Most of this corpus has no open full
                # text - that is a property of clinical publishing, not of any
                # API - so without this the majority of papers contribute
                # nothing at all.
                #
                # Tagged rather than mixed in. An abstract's closing "further
                # studies are warranted" is far more often ritual than a
                # Discussion's, and whoever reads these next has to be able to
                # weigh them differently. Silently blending the two would make
                # the harvest look twice as productive and be worse.
                text = p.get("abstract")
                where = "abstract"
                if text:
                    n_from_abstract += 1

            if not text:
                continue
            for g in gap_sentences(text):
                gaps.append({**g, "found_in": where,
                             "pmid": p.get("pmid"), "pmcid": pmcid,
                             "doi": p.get("doi"), "year": p.get("year"),
                             "title": p.get("title")})

        result = {
            "title_concepts": concepts_ranked,
            "gaps": gaps,
            "source": {"project_id": project_id, "source_run_id": source_run_id,
                       "n_papers": len(papers)},
        }
        # Counted so a harvest that found little says which little it was, and
        # so the next person knows which of two unrelated fixes is worth doing:
        # look elsewhere for open access, or stop discarding text already held.
        result["lookup"] = {
            "n_resolved": n_resolved,
            "n_without_identifier": n_unidentified,
            "n_with_fulltext": n_fulltext,
            "n_no_open_access": n_no_pmcid,
            "n_fulltext_but_no_discussion": n_pmcid_no_discussion,
            "n_fell_back_to_abstract": n_from_abstract,
        }
        result["gaps_by_source"] = {
            "discussion": sum(1 for g in gaps if g.get("found_in") == "discussion"),
            "abstract": sum(1 for g in gaps if g.get("found_in") == "abstract"),
        }
        db.finish_harvest(harvest_id, result=result, counts={
            "n_papers": len(papers), "n_with_fulltext": n_fulltext,
            "n_gap_sentences": len(gaps), "n_concepts": len(concepts_ranked)})
    except Exception as e:
        db.finish_harvest(harvest_id, error=f"{type(e).__name__}: {str(e)[:400]}")
