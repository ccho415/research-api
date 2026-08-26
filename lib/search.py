#!/usr/bin/env python
"""Domain-adaptive academic literature search across free scholarly APIs.

Stdlib only. No API key required for any default source.

Subcommands
-----------
  query      Search one or more sources, merge and de-duplicate results.
  vocab      Look up controlled vocabulary (MeSH for biomed, OpenAlex concepts otherwise).
  related    Find papers related to a seed paper (PubMed ELink / OpenAlex citation graph).
  chain      Walk the citation graph forward+backward from a seed DOI (CoI-style).
  sources    Print the domain -> source routing table.

Examples
--------
  python search.py query "air pollution lung function" --domain biomed --limit 25
  python search.py query "sparse attention" --domain cs --year-from 2023 --out hits.json
  python search.py vocab "air pollution" --domain biomed
  python search.py related --pmid 31978945
  python search.py chain --doi 10.1038/s41586-021-03819-2 --depth 2
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# Windows consoles default to a legacy codepage (cp950/cp1252) that cannot encode
# the Unicode found in scholarly metadata.  Force UTF-8 on both streams.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

UA = "lit-search-skill/1.0 (academic research; stdlib urllib)"
MAILTO = os.environ.get("ACADEMIC_MAILTO", "").strip()
S2_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
NCBI_KEY = os.environ.get("NCBI_API_KEY", "").strip()

# --------------------------------------------------------------------------
# Domain -> source routing.  OpenAlex + Crossref are universal fallbacks and
# are appended to every domain so no field is ever left without coverage.
# --------------------------------------------------------------------------
ROUTING = {
    "biomed":   ["pubmed", "europepmc", "openalex"],
    "publichealth": ["pubmed", "europepmc", "openalex", "crossref"],
    "clinical": ["pubmed", "europepmc", "openalex"],
    "psych":    ["pubmed", "openalex", "crossref"],
    "cs":       ["arxiv", "openalex", "crossref"],
    "ml":       ["arxiv", "openalex", "crossref"],
    "physics":  ["arxiv", "openalex", "crossref"],
    "math":     ["arxiv", "openalex", "crossref"],
    "stats":    ["arxiv", "openalex", "crossref"],
    "chem":     ["openalex", "pubmed", "crossref"],
    "materials": ["openalex", "arxiv", "crossref"],
    "env":      ["openalex", "pubmed", "crossref"],
    "ecology":  ["openalex", "europepmc", "crossref"],
    "eng":      ["openalex", "arxiv", "crossref"],
    "econ":     ["openalex", "arxiv", "crossref"],
    "social":   ["openalex", "crossref"],
    "edu":      ["openalex", "crossref"],
    "humanities": ["crossref", "openalex"],
    "general":  ["openalex", "crossref"],
}
VOCAB_SOURCE = {"biomed", "publichealth", "clinical", "psych", "chem", "env", "ecology"}


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def _get(url, headers=None, timeout=30, retries=2):
    hdrs = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            if attempt == retries:
                raise
            time.sleep(1.5 * (attempt + 1))


def _get_json(url, **kw):
    raw = _get(url, **kw).decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # A 200 that is not JSON is the service refusing us in prose - a rate
        # limit page, a block notice, a maintenance banner.  The decoder's
        # message names none of those, so carry the body across.
        raise ValueError(f"{urllib.parse.urlsplit(url).netloc} returned "
                         f"non-JSON ({len(raw)} bytes): "
                         f"{' '.join(raw.split())[:200]}")


def _warn(msg):
    print(f"[warn] {msg}", file=sys.stderr)


def _clean(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(text))
    return re.sub(r"\s+", " ", text).strip()


def _rec(source, ident, title, abstract="", year=None, venue="", authors=None,
         doi="", citations=None, url="", ptype=""):
    return {
        "source": source, "id": str(ident), "doi": (doi or "").lower().replace("https://doi.org/", ""),
        "title": _clean(title), "abstract": _clean(abstract)[:2500], "year": year,
        "venue": _clean(venue), "authors": authors or [], "citations": citations,
        "type": ptype, "url": url,
    }


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------
def s_pubmed(q, limit, year_from, year_to):
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    key = f"&api_key={NCBI_KEY}" if NCBI_KEY else ""
    term = q
    if year_from or year_to:
        term += f" AND ({year_from or 1800}:{year_to or 3000}[dp])"
    u = (base + "esearch.fcgi?db=pubmed&retmode=json&sort=relevance"
         f"&retmax={limit}&term={urllib.parse.quote(term)}{key}")
    ids = _get_json(u).get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    time.sleep(0.34)
    u2 = base + f"efetch.fcgi?db=pubmed&retmode=xml&id={','.join(ids)}{key}"
    root = ET.fromstring(_get(u2))
    out = []
    for art in root.findall(".//PubmedArticle"):
        pmid = art.findtext(".//PMID", "")
        title = "".join(art.find(".//ArticleTitle").itertext()) if art.find(".//ArticleTitle") is not None else ""
        abst = " ".join("".join(a.itertext()) for a in art.findall(".//AbstractText"))
        yr = art.findtext(".//JournalIssue/PubDate/Year") or art.findtext(".//PubDate/MedlineDate", "")[:4]
        auths = [f"{a.findtext('LastName','')} {a.findtext('Initials','')}".strip()
                 for a in art.findall(".//Author")][:8]
        doi = ""
        for aid in art.findall(".//ArticleId"):
            if aid.get("IdType") == "doi":
                doi = aid.text or ""
        mesh = [m.findtext("DescriptorName", "") for m in art.findall(".//MeshHeading")]
        r = _rec("pubmed", pmid, title, abst, int(yr) if str(yr).isdigit() else None,
                 art.findtext(".//Journal/Title", ""), auths, doi,
                 url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                 ptype=", ".join(t.text or "" for t in art.findall(".//PublicationType"))[:120])
        r["mesh"] = [m for m in mesh if m]
        out.append(r)
    return out


def s_europepmc(q, limit, year_from, year_to):
    query = q
    if year_from or year_to:
        query += f" AND (FIRST_PDATE:[{year_from or 1800}-01-01 TO {year_to or 3000}-12-31])"
    u = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search?format=json&resultType=core"
         f"&pageSize={min(limit,100)}&query={urllib.parse.quote(query)}")
    res = _get_json(u).get("resultList", {}).get("result", [])
    out = []
    for it in res:
        out.append(_rec("europepmc", it.get("id", ""), it.get("title", ""),
                        it.get("abstractText", ""),
                        int(it["pubYear"]) if str(it.get("pubYear", "")).isdigit() else None,
                        it.get("journalTitle", "") or it.get("bookOrReportDetails", {}).get("publisher", ""),
                        [a.strip() for a in (it.get("authorString", "") or "").split(",")][:8],
                        it.get("doi", ""), it.get("citedByCount"),
                        f"https://europepmc.org/article/{it.get('source','MED')}/{it.get('id','')}",
                        it.get("pubType", "")))
    return out


def _openalex_abstract(inv):
    if not inv:
        return ""
    pos = {}
    for w, idxs in inv.items():
        for i in idxs:
            pos[i] = w
    return " ".join(pos[i] for i in sorted(pos))


def s_openalex(q, limit, year_from, year_to):
    filt = []
    if year_from:
        filt.append(f"from_publication_date:{year_from}-01-01")
    if year_to:
        filt.append(f"to_publication_date:{year_to}-12-31")
    base = "https://api.openalex.org/works?per-page=" + str(min(limit, 200))
    tail = ("&mailto=" + urllib.parse.quote(MAILTO)) if MAILTO else ""

    # title_and_abstract.search is far more precise than the bare `search=`
    # parameter, which also matches full text and drags in loosely related work.
    # It is a heavier index operation, though, and OpenAlex intermittently 503s
    # on it -- so fall back to the cheaper, always-available search parameter.
    precise = filt + ["title_and_abstract.search:" + q.replace(",", " ")]
    urls = [base + "&filter=" + urllib.parse.quote(",".join(precise), safe=":,") + tail,
            base + "&search=" + urllib.parse.quote(q)
            + (("&filter=" + urllib.parse.quote(",".join(filt), safe=":,")) if filt else "")
            + tail]
    data = None
    for i, u in enumerate(urls):
        try:
            data = _get_json(u)
            break
        except Exception as e:
            if i == 0:
                _warn(f"openalex precise search unavailable ({e}); using broad search")
            else:
                raise
    out = []
    for it in (data or {}).get("results", []):
        pl = it.get("primary_location") or {}
        src = (pl.get("source") or {}).get("display_name", "")
        out.append(_rec("openalex", (it.get("id") or "").rsplit("/", 1)[-1],
                        it.get("display_name", ""),
                        _openalex_abstract(it.get("abstract_inverted_index")),
                        it.get("publication_year"), src,
                        [a["author"]["display_name"] for a in it.get("authorships", [])[:8]],
                        (it.get("doi") or ""), it.get("cited_by_count"),
                        it.get("doi") or it.get("id", ""), it.get("type", "")))
    return out


def s_crossref(q, limit, year_from, year_to):
    u = ("https://api.crossref.org/works?rows=" + str(min(limit, 100))
         + "&select=DOI,title,abstract,issued,container-title,author,is-referenced-by-count,type"
         + "&query=" + urllib.parse.quote(q))
    if year_from:
        u += f"&filter=from-pub-date:{year_from}-01-01"
        if year_to:
            u += f",until-pub-date:{year_to}-12-31"
    elif year_to:
        u += f"&filter=until-pub-date:{year_to}-12-31"
    if MAILTO:
        u += "&mailto=" + urllib.parse.quote(MAILTO)
    out = []
    for it in _get_json(u).get("message", {}).get("items", []):
        parts = (it.get("issued", {}).get("date-parts") or [[None]])[0]
        out.append(_rec("crossref", it.get("DOI", ""), (it.get("title") or [""])[0],
                        it.get("abstract", ""), parts[0] if parts else None,
                        (it.get("container-title") or [""])[0],
                        [f"{a.get('given','')} {a.get('family','')}".strip()
                         for a in it.get("author", [])][:8],
                        it.get("DOI", ""), it.get("is-referenced-by-count"),
                        "https://doi.org/" + it.get("DOI", ""), it.get("type", "")))
    return out


def s_arxiv(q, limit, year_from, year_to):
    u = ("http://export.arxiv.org/api/query?sortBy=relevance&max_results=" + str(min(limit, 100))
         + "&search_query=" + urllib.parse.quote(f"all:{q}"))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(_get(u, headers={"Accept": "application/atom+xml"}))
    out = []
    for e in root.findall("a:entry", ns):
        pub = e.findtext("a:published", "", ns)[:4]
        yr = int(pub) if pub.isdigit() else None
        if year_from and yr and yr < year_from:
            continue
        if year_to and yr and yr > year_to:
            continue
        aid = e.findtext("a:id", "", ns)
        out.append(_rec("arxiv", aid.rsplit("/", 1)[-1], e.findtext("a:title", "", ns),
                        e.findtext("a:summary", "", ns), yr, "arXiv preprint",
                        [a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)][:8],
                        "", None, aid, "preprint"))
    return out


def s_semanticscholar(q, limit, year_from, year_to):
    fields = "title,abstract,year,venue,authors,externalIds,citationCount,publicationTypes"
    u = ("https://api.semanticscholar.org/graph/v1/paper/search?limit=" + str(min(limit, 100))
         + f"&fields={fields}&query=" + urllib.parse.quote(q))
    if year_from or year_to:
        u += f"&year={year_from or ''}-{year_to or ''}"
    hdr = {"x-api-key": S2_KEY} if S2_KEY else None
    out = []
    for it in _get_json(u, headers=hdr).get("data", []):
        ext = it.get("externalIds") or {}
        out.append(_rec("semanticscholar", it.get("paperId", ""), it.get("title", ""),
                        it.get("abstract", ""), it.get("year"), it.get("venue", ""),
                        [a["name"] for a in (it.get("authors") or [])[:8]],
                        ext.get("DOI", ""), it.get("citationCount"),
                        f"https://www.semanticscholar.org/paper/{it.get('paperId','')}",
                        ", ".join(it.get("publicationTypes") or [])))
    return out


SOURCES = {
    "pubmed": s_pubmed, "europepmc": s_europepmc, "openalex": s_openalex,
    "crossref": s_crossref, "arxiv": s_arxiv, "semanticscholar": s_semanticscholar,
}


# --------------------------------------------------------------------------
# Merge / de-duplicate across sources
# --------------------------------------------------------------------------
def _norm_title(t):
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())[:110]


def merge(batches):
    """Merge per-source hit lists, keeping each record's within-source relevance rank.

    Cross-source duplicates collapse into one record whose fields are filled in
    from whichever source had them, and whose rank is the best rank it achieved.
    """
    by_doi, by_title, out = {}, {}, []
    for recs in batches:
        for rank, r in enumerate(recs):
            if not r["title"]:
                continue
            r["rank"] = rank
            doi, nt = r["doi"], _norm_title(r["title"])
            hit = by_doi.get(doi) if doi else None
            if hit is None:
                hit = by_title.get(nt)
            if hit is not None:
                hit["also_in"] = sorted(set(hit.get("also_in", []) + [r["source"]]))
                hit["rank"] = min(hit["rank"], rank)
                for k in ("abstract", "doi", "venue", "url"):
                    if not hit.get(k) and r.get(k):
                        hit[k] = r[k]
                if r.get("citations") is not None:
                    hit["citations"] = max(hit.get("citations") or 0, r["citations"])
                if r.get("mesh") and not hit.get("mesh"):
                    hit["mesh"] = r["mesh"]
                continue
            out.append(r)
            if doi:
                by_doi[doi] = r
            by_title[nt] = r
    return out


# --------------------------------------------------------------------------
# Controlled vocabulary
# --------------------------------------------------------------------------
def vocab_mesh(term):
    key = f"&api_key={NCBI_KEY}" if NCBI_KEY else ""
    u = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=mesh&retmode=json&retmax=8"
         f"&term={urllib.parse.quote(term)}{key}")
    ids = _get_json(u).get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    time.sleep(0.34)
    u2 = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=mesh&retmode=text"
          f"&id={','.join(ids)}{key}")
    raw = _get(u2).decode("utf-8", "replace")
    return _parse_mesh(raw)


# Indented list blocks in the MeSH text record, keyed by the output field they fill.
_MESH_BLOCKS = {"Subheadings:": "subheadings", "Entry Terms:": "entry_terms",
                "See Also:": "see_also", "Previous Indexing:": "previous_indexing"}


def _parse_mesh(raw):
    """Parse the `efetch db=mesh retmode=text` record format.

    Each record starts with `N: Descriptor`, followed by a scope note, then
    indented blocks (Subheadings / Entry Terms / See Also) and finally the
    `All MeSH Categories` hierarchy, whose last-but-one line is the broader term.
    """
    out = []
    for chunk in re.split(r"\n(?=\d+:\s)", raw.strip()):
        lines = chunk.splitlines()
        if not lines or not re.match(r"^\d+:\s", lines[0]):
            continue
        e = {"descriptor": re.sub(r"^\d+:\s*", "", lines[0]).strip(), "definition": "",
             "tree_numbers": [], "entry_terms": [], "subheadings": [], "see_also": [],
             "previous_indexing": [], "broader": []}
        block, hierarchy = None, []
        for ln in lines[1:]:
            stripped = ln.strip()
            if not stripped:
                continue
            if stripped in _MESH_BLOCKS:
                block = _MESH_BLOCKS[stripped]
                continue
            if stripped.startswith("Tree Number(s):"):
                e["tree_numbers"] = [t.strip() for t in
                                     stripped.split(":", 1)[1].split(",") if t.strip()]
                block = None
                continue
            if stripped.startswith(("Year introduced", "Unique ID")):
                block = None
                continue
            if stripped == "All MeSH Categories" or hierarchy:
                hierarchy.append(stripped)
                block = None
                continue
            if block:
                e[block].append(stripped)
            elif not e["definition"]:
                e["definition"] = stripped
        # In the hierarchy the entry itself is last; its parent is the line above.
        if len(hierarchy) >= 2 and hierarchy[-1] == e["descriptor"]:
            e["broader"] = [hierarchy[-2]]
        e["pubmed_query"] = _mesh_query(e)
        out.append(e)
    return out


def _mesh_query(e):
    """Build a ready-to-paste PubMed query: MeSH descriptor OR every entry term."""
    terms = [f'"{e["descriptor"]}"[MeSH Terms]'] if e["descriptor"] else []
    terms += [f'"{t}"[tiab]' for t in ([e["descriptor"]] + e["entry_terms"])[:20] if t]
    return " OR ".join(terms)


def vocab_openalex(term):
    u = "https://api.openalex.org/concepts?per-page=8&search=" + urllib.parse.quote(term)
    if MAILTO:
        u += "&mailto=" + urllib.parse.quote(MAILTO)
    out = []
    for c in _get_json(u).get("results", []):
        out.append({"descriptor": c.get("display_name", ""), "level": c.get("level"),
                    "works_count": c.get("works_count"),
                    "entry_terms": (c.get("description") or "")[:200],
                    "related": [r["display_name"] for r in (c.get("related_concepts") or [])[:12]]})
    return out


# --------------------------------------------------------------------------
# Citation graph
# --------------------------------------------------------------------------
def related_pubmed(pmid, limit=20):
    key = f"&api_key={NCBI_KEY}" if NCBI_KEY else ""
    u = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=pubmed&db=pubmed"
         f"&linkname=pubmed_pubmed&retmode=json&id={pmid}{key}")
    data = _get_json(u)
    ids = []
    for ls in data.get("linksets", []):
        for db in ls.get("linksetdbs", []):
            ids.extend(db.get("links", []))
    ids = [i for i in ids if str(i) != str(pmid)][:limit]
    if not ids:
        return []
    time.sleep(0.34)
    return s_pubmed(" OR ".join(f"{i}[uid]" for i in ids), len(ids), None, None)


def _oa_work(doi_or_id):
    """Resolve a DOI, OpenAlex id, or paper title to an OpenAlex work record."""
    ident = doi_or_id.strip()
    if ident.lower().startswith("10."):
        ident = "https://doi.org/" + ident
    if ident.startswith("http") or re.match(r"^[WwAaSs]\d+$", ident):
        u = "https://api.openalex.org/works/" + urllib.parse.quote(ident, safe=":/.")
        if MAILTO:
            u += "?mailto=" + urllib.parse.quote(MAILTO)
        try:
            return _get_json(u)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            _warn(f"'{doi_or_id}' not indexed in OpenAlex - falling back to title search")
    # Fallback: treat the input as free text and take the best-matching work.
    u = ("https://api.openalex.org/works?per-page=1&filter=title_and_abstract.search:"
         + urllib.parse.quote(re.sub(r"^https?://doi\.org/", "", ident), safe=""))
    hits = _get_json(u).get("results", [])
    if not hits:
        raise SystemExit(f"could not resolve '{doi_or_id}' in OpenAlex; "
                         "try the paper title instead of the DOI")
    return hits[0]


def _oa_to_rec(it):
    pl = it.get("primary_location") or {}
    return _rec("openalex", (it.get("id") or "").rsplit("/", 1)[-1], it.get("display_name", ""),
                _openalex_abstract(it.get("abstract_inverted_index")), it.get("publication_year"),
                (pl.get("source") or {}).get("display_name", ""),
                [a["author"]["display_name"] for a in it.get("authorships", [])[:8]],
                it.get("doi") or "", it.get("cited_by_count"),
                it.get("doi") or it.get("id", ""), it.get("type", ""))


_CHAIN_STOP = set("""a an the and or of for to in on at by with from as is are was were be
this that these those it its their our we they not no than then so such but if while
which who using use used based novel new approach method study paper toward towards""".split())


def _sim_tokens(text):
    return {w for w in re.findall(r"[a-z][a-z0-9\-]{2,}", (text or "").lower())
            if w not in _CHAIN_STOP}


def _topic_sim(topic_toks, rec):
    """Jaccard-style overlap of a record's title+abstract with the topic terms."""
    if not topic_toks:
        return 0.0
    t = _sim_tokens(rec.get("title", "") + " " + (rec.get("abstract", "") or "")[:600])
    return round(len(topic_toks & t) / len(topic_toks), 3) if t else 0.0


def _role_signals(rec, seed_year, topic_toks):
    """Signals for the Chain-of-Ideas backward-selection criteria.

    CoI has an LLM pick the most relevant prior work as foundational, baseline, or
    same-topic. The script cannot make that judgement, so it surfaces the evidence
    the judgement needs and lets the model choose.
    """
    cites = rec.get("citations") or 0
    yr = rec.get("year") or 0
    gap = (seed_year - yr) if (seed_year and yr) else 0
    return {
        "foundational": round(min(cites / 1000, 1.0) * (1.0 if gap >= 5 else 0.6), 3),
        "baseline_like": round(min(cites / 300, 1.0) * (1.0 if 0 < gap <= 5 else 0.5), 3),
        "same_topic": _topic_sim(topic_toks, rec),
    }


def chain(seed, depth=1, per_step=6, milestone=1000, topic=None, _seen=None):
    """Bidirectional citation walk, following the Chain-of-Ideas construction rule.

    Backward: references ranked by the three signals CoI selects on (foundational,
    baseline-like, same-topic) rather than by whatever order the API returned.
    Forward: citing works ranked by topic relevance when a topic is given, since
    ranking purely by citation count drags in famous but off-topic work.
    Stops early on a milestone paper (>= `milestone` citations).
    """
    _seen = _seen if _seen is not None else set()
    root = _oa_work(seed)
    seed_rec = _oa_to_rec(root)
    _seen.add(seed_rec["id"])
    topic_toks = _sim_tokens(topic) if topic else _sim_tokens(seed_rec["title"])
    seed_year = seed_rec.get("year") or 0
    result = {"seed": seed_rec, "topic_terms": sorted(topic_toks)[:20],
              "backward": [], "forward": []}

    # --- backward: fetch a wider pool than needed, then rank -----------------
    pool = []
    for rid in (root.get("referenced_works") or [])[:per_step * 4]:
        try:
            pool.append(_oa_to_rec(_get_json(
                "https://api.openalex.org/works/" + rid.rsplit("/", 1)[-1])))
        except Exception as e:
            _warn(f"backward {rid}: {e}")
    for rec in pool:
        rec["role_signals"] = _role_signals(rec, seed_year, topic_toks)
    pool.sort(key=lambda r: -max(r["role_signals"].values()))
    result["backward"] = pool[:per_step]

    # --- forward: citing works, ranked by topic when we have one -------------
    oid = seed_rec["id"]
    try:
        u = (f"https://api.openalex.org/works?filter=cites:{oid}"
             f"&sort=cited_by_count:desc&per-page={min(per_step * 4, 50)}")
        fwd = []
        for w in _get_json(u).get("results", []):
            rec = _oa_to_rec(w)
            if rec["id"] == oid or rec["id"] in _seen:
                continue
            rec["topic_similarity"] = _topic_sim(topic_toks, rec)
            fwd.append(rec)
        fwd.sort(key=lambda r: (-r["topic_similarity"], -(r.get("citations") or 0)))
        result["forward"] = fwd[:per_step]
    except Exception as e:
        _warn(f"forward: {e}")

    result["milestones"] = [
        {"title": r["title"], "year": r["year"], "citations": r["citations"],
         "doi": r["doi"], "direction": d}
        for d, rs in (("backward", result["backward"]), ("forward", result["forward"]))
        for r in rs if (r.get("citations") or 0) >= milestone]

    # --- iterate forward along the most topic-relevant citing work -----------
    if depth > 1 and result["forward"]:
        nxt = result["forward"][0]
        if (nxt.get("citations") or 0) >= milestone:
            result["stopped"] = (f"reached milestone paper ({nxt['citations']} citations) "
                                 "- CoI treats this as the end of the chain")
        else:
            _seen.add(nxt["id"])
            try:
                result["next"] = chain(nxt.get("doi") or nxt["id"], depth - 1,
                                       per_step, milestone, topic, _seen)
            except Exception as e:
                _warn(f"depth: {e}")
    return result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def cmd_query(a):
    names = ([s.strip() for s in a.sources.split(",") if s.strip()]
             if a.sources else ROUTING.get(a.domain, ROUTING["general"]))
    batches = []
    for n in names:
        fn = SOURCES.get(n)
        if not fn:
            _warn(f"unknown source '{n}' - skipped")
            continue
        try:
            hits = fn(a.query, a.limit, a.year_from, a.year_to)
            _warn(f"{n}: {len(hits)} hits")
            batches.append(hits)
        except Exception as e:
            _warn(f"{n} FAILED ({type(e).__name__}: {e}) - continuing with other sources")
    merged = merge(batches)
    if a.sort == "citations":
        merged.sort(key=lambda r: -(r.get("citations") or 0))
    elif a.sort == "year":
        merged.sort(key=lambda r: -(r.get("year") or 0))
    else:  # relevance: interleave sources by their own ranking, best rank first
        merged.sort(key=lambda r: (r.get("rank", 999), -(len(r.get("also_in", [])))))
    payload = {"query": a.query, "domain": a.domain, "sources_used": names,
               "sort": a.sort, "n": len(merged), "results": merged}
    _emit(payload, a.out)


def cmd_vocab(a):
    use_mesh = a.domain in VOCAB_SOURCE
    try:
        data = vocab_mesh(a.term) if use_mesh else vocab_openalex(a.term)
    except Exception as e:
        _warn(f"primary vocab failed ({e}); falling back to OpenAlex concepts")
        data = vocab_openalex(a.term)
    _emit({"term": a.term, "vocabulary": "MeSH" if use_mesh else "OpenAlex concepts",
           "entries": data}, a.out)


def cmd_related(a):
    if a.pmid:
        data = related_pubmed(a.pmid, a.limit)
    elif a.doi:
        data = [_oa_to_rec(w) for w in
                _get_json(f"https://api.openalex.org/works?filter=cites:"
                          f"{_oa_work(a.doi).get('id','').rsplit('/',1)[-1]}"
                          f"&sort=cited_by_count:desc&per-page={a.limit}").get("results", [])]
    else:
        sys.exit("related: need --pmid or --doi")
    _emit({"n": len(data), "results": data}, a.out)


def cmd_chain(a):
    _emit(chain(a.doi, a.depth, a.per_step, a.milestone, a.topic), a.out)


def cmd_sources(a):
    rows = [f"{d:14s} -> {', '.join(s)}" for d, s in ROUTING.items()]
    print("Domain routing (OpenAlex/Crossref are universal fallbacks):\n")
    print("\n".join(rows))
    print("\nOptional env vars: ACADEMIC_MAILTO (polite pool), "
          "NCBI_API_KEY (PubMed rate), SEMANTIC_SCHOLAR_API_KEY")


def _emit(obj, out):
    txt = json.dumps(obj, ensure_ascii=False, indent=2)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"wrote {out} ({len(txt)} bytes)")
    else:
        print(txt)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("query", help="search and merge across sources")
    q.add_argument("query")
    q.add_argument("--domain", default="general", choices=sorted(ROUTING))
    q.add_argument("--sources", help="comma list, overrides --domain")
    q.add_argument("--limit", type=int, default=25)
    q.add_argument("--year-from", type=int, dest="year_from")
    q.add_argument("--year-to", type=int, dest="year_to")
    q.add_argument("--sort", default="relevance", choices=["relevance", "citations", "year"])
    q.add_argument("--out")
    q.set_defaults(fn=cmd_query)

    v = sub.add_parser("vocab", help="controlled-vocabulary expansion")
    v.add_argument("term")
    v.add_argument("--domain", default="general", choices=sorted(ROUTING))
    v.add_argument("--out")
    v.set_defaults(fn=cmd_vocab)

    r = sub.add_parser("related", help="papers related to a seed")
    r.add_argument("--pmid")
    r.add_argument("--doi")
    r.add_argument("--limit", type=int, default=20)
    r.add_argument("--out")
    r.set_defaults(fn=cmd_related)

    c = sub.add_parser("chain", help="bidirectional citation walk from a seed DOI")
    c.add_argument("--doi", required=True)
    c.add_argument("--depth", type=int, default=1)
    c.add_argument("--per-step", type=int, default=6, dest="per_step")
    c.add_argument("--milestone", type=int, default=1000)
    c.add_argument("--topic", help="rank the chain by relevance to this topic (CoI rule)")
    c.add_argument("--out")
    c.set_defaults(fn=cmd_chain)

    s = sub.add_parser("sources", help="print routing table")
    s.set_defaults(fn=cmd_sources)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
