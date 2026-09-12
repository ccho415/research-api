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
import unicodedata
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
# Optional. Absent, every UMLS route below is skipped and nothing else
# changes - a licence is issued to a named individual, so this cannot be a
# shared default.
UMLS_KEY = os.environ.get("UMLS_API_KEY", "").strip()

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
    "env":      ["openalex", "pubmed", "europepmc", "crossref"],
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
    return parse_pubmed_xml(_get(u2))


def pubmed_term(q, year_from=None, year_to=None):
    """The PubMed `term` for this query, year clause included.

    Split out so that a caller which cannot reach E-utilities itself can hand
    the term to something that can - a browser on the researcher's own machine,
    which NCBI has not blocked - without rebuilding the syntax at the other end.
    """
    term = q
    if year_from or year_to:
        term += f" AND ({year_from or 1800}:{year_to or 3000}[dp])"
    return term


def parse_pubmed_xml(xml):
    """PubMed's efetch XML to the record shape every source here produces.

    Separate from fetching because the fetch and the parse can happen on
    different machines. NCBI blocks this deployment's IP, so the request has to
    be made from somewhere else; the parsing has no such problem and stays in
    one place, which is the point - a second copy of this in JavaScript would
    drift from this one within a month and nobody would notice, because a
    slightly-wrongly-parsed paper looks exactly like a correct one.
    """
    root = ET.fromstring(xml)
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
        # `_rec` puts the identifier in `id`, and `id` means a different thing
        # for every source, so the writer cannot tell a pmid from an arXiv id.
        # Named here because `db._upsert_paper` reads `pmid` - without this the
        # column stayed empty on every PubMed paper ever stored, and nothing
        # errored: the papers had DOIs, so they still matched and de-duplicated.
        r["pmid"] = str(pmid).strip() or None
        out.append(r)
    return out


def _epmc_venue(it):
    """Where Europe PMC actually keeps the journal name.

    Not in `journalTitle`. That key exists on the record and is empty on every
    one of them - measured at 0 of 150 across three unrelated searches, against
    149 of 150 for `journalInfo.journal.title`. Reading the empty one meant
    every Europe PMC paper was stored with no venue at all, and Europe PMC is
    the source that answers most clinical searches here because NCBI blocks
    this host from E-utilities. So the journal was missing for effectively the
    whole corpus, silently, since the first run.

    The full title is preferred over the Medline abbreviation because that is
    what reads properly in a report six months later, and matching is done with
    case-insensitive substrings that cope with either. Europe PMC writes it in
    sentence case and sometimes with a qualifier - `Lancet (London, England)`,
    `International journal of stroke : official journal of...` - which the
    substring patterns in `journals` are written to survive.
    """
    ji = it.get("journalInfo") or {}
    j = ji.get("journal") or {}
    return (j.get("title") or j.get("medlineAbbreviation")
            or it.get("journalTitle")
            or (it.get("bookOrReportDetails") or {}).get("publisher") or "")


def _epmc_mesh(it):
    """The MeSH descriptors Europe PMC carries for a MEDLINE record.

    The same indexing PubMed serves, from the source that is actually reachable
    from here - NCBI blocks this deployment's egress IP from E-utilities, so
    `s_pubmed` contributes nothing on a clinical search and its MeSH went with
    it. Measured coverage on indexed years is high (15/20 for 2018, 18/20 for
    2022) and low for the current year (6/20 for 2026), because NLM has not
    finished indexing recent papers yet. That gap is NLM's backlog and exists
    on PubMed identically; it is not caused by the block.

    Flat descriptor names, to match what `s_pubmed` produces - one shape for
    one column. `majorTopic_YN` is dropped rather than carried into a list that
    the other source cannot fill, which would make the field mean two different
    things depending on where the paper came from.
    """
    heads = ((it.get("meshHeadingList") or {}).get("meshHeading")) or []
    out, seen = [], set()
    for h in heads:
        name = ((h or {}).get("descriptorName") or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
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
        r = _rec("europepmc", it.get("id", ""), it.get("title", ""),
                        it.get("abstractText", ""),
                        int(it["pubYear"]) if str(it.get("pubYear", "")).isdigit() else None,
                        _epmc_venue(it),
                        [a.strip() for a in (it.get("authorString", "") or "").split(",")][:8],
                    it.get("doi", ""), it.get("citedByCount"),
                    f"https://europepmc.org/article/{it.get('source','MED')}/{it.get('id','')}",
                    it.get("pubType", ""))
        m = _epmc_mesh(it)
        if m:
            r["mesh"] = m
        # Europe PMC indexes MEDLINE, so most of its hits carry a pmid and it
        # is the same identifier PubMed would give. Keeping it means a paper
        # found both ways is one row rather than two.
        if it.get("pmid"):
            r["pmid"] = str(it["pmid"]).strip()
        out.append(r)
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
def vocab_mesh(term, limit=10):
    """MeSH lookup via id.nlm.nih.gov, falling back to E-utilities.

    id.nlm.nih.gov is preferred even where eutils is reachable.  It is the only
    one of the two that yields D-numbers, that resolves entry terms - so
    "lung adenocarcinoma" and "heart attack" find their descriptors at all - and
    that can be re-ranked, since eutils returns whatever its own relevance
    ordering decides and mixes Supplementary Concept and Pharmacological Action
    records in with topical descriptors.

    Preferring eutils would also make the system quietly get worse the day NCBI
    unblocks this deployment's egress IP, which is the opposite of how a
    fallback should behave.
    """
    try:
        entries = vocab_mesh_rdf(term, limit=limit)
        if entries:
            return entries
        _warn(f"no MeSH descriptor for {term!r} at id.nlm.nih.gov; trying E-utilities")
    except Exception as e:
        _warn(f"id.nlm.nih.gov MeSH unavailable ({e}); trying E-utilities")
    try:
        return _vocab_mesh_eutils(term)[:limit]
    except Exception as e:
        _warn(f"E-utilities MeSH unavailable ({e})")
        return []


def _vocab_mesh_eutils(term):
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


MESH_RDF = "https://id.nlm.nih.gov/mesh"

_MESH_SPARQL = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX meshv: <http://id.nlm.nih.gov/mesh/vocab#>
PREFIX mesh: <http://id.nlm.nih.gov/mesh/>
SELECT ?d ?tn ?broader ?note
FROM <http://id.nlm.nih.gov/mesh>
WHERE {
  VALUES ?d { %s }
  OPTIONAL { ?d meshv:treeNumber ?tnr . ?tnr rdfs:label ?tn }
  OPTIONAL { ?d meshv:broaderDescriptor ?br . ?br rdfs:label ?broader }
  OPTIONAL { ?d meshv:preferredConcept ?pc . ?pc meshv:scopeNote ?note }
}
"""


def _mesh_rdf_meta(ids):
    """Tree numbers, broader-descriptor labels and scope note, in one query.

    The three OPTIONALs cross-product, so a descriptor comes back as many rows
    carrying repeated values; collect into sets rather than reading row by row.
    """
    q = _MESH_SPARQL % " ".join("mesh:" + i for i in ids)
    rows = _get_json(f"{MESH_RDF}/sparql?format=JSON&limit=5000"
                     f"&query={urllib.parse.quote(q)}")["results"]["bindings"]
    meta = {}
    for b in rows:
        e = meta.setdefault(b["d"]["value"].rsplit("/", 1)[-1],
                            {"tree_numbers": set(), "broader": set(), "definition": ""})
        for field in ("tree_numbers", "broader"):
            src = "tn" if field == "tree_numbers" else "broader"
            if src in b:
                e[field].add(b[src]["value"])
        if "note" in b and not e["definition"]:
            e["definition"] = b["note"]["value"].strip()
    return meta


# Entry terms are where the natural phrasing lives.  `lookup/descriptor` only
# matches the descriptor's own label, and MeSH labels are inverted, so the way a
# researcher actually writes a concept misses: "lung adenocarcinoma" finds
# nothing while "adenocarcinoma of lung" finds it, and "heart attack" finds
# nothing at all.  Terms carry those phrasings, but under SKOS predicates
# (prefLabel/altLabel) rather than rdfs:label, and a descriptor reaches them by
# two disjoint paths - meshv:concept excludes the preferred concept, and
# meshv:term excludes the preferred term - so all four combinations are needed.
_MESH_ENTRY_SPARQL = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX meshv: <http://id.nlm.nih.gov/mesh/vocab#>
SELECT DISTINCT ?d ?dlabel
FROM <http://id.nlm.nih.gov/mesh>
WHERE {
  ?d a meshv:TopicalDescriptor .
  ?d rdfs:label ?dlabel .
  { ?d meshv:concept ?c } UNION { ?d meshv:preferredConcept ?c }
  { ?c rdfs:label ?x }
  UNION
  { { ?c meshv:term ?t } UNION { ?c meshv:preferredTerm ?t }
    { ?t meshv:prefLabel ?x } UNION { ?t meshv:altLabel ?x } }
  FILTER (LCASE(STR(?x)) = %s)
}
"""


def mesh_entry_match(term):
    """Descriptors whose label, concept label or any entry term equals `term`."""
    q = _MESH_ENTRY_SPARQL % json.dumps(_norm_space(term).lower())
    rows = _get_json(f"{MESH_RDF}/sparql?format=JSON&limit=30"
                     f"&query={urllib.parse.quote(q)}")["results"]["bindings"]
    return [{"label": b["dlabel"]["value"], "resource": b["d"]["value"], "via": "entry"}
            for b in rows if not b["dlabel"]["value"].startswith("[")]


def _norm_space(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


_MESH_NORM_SPARQL = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX meshv: <http://id.nlm.nih.gov/mesh/vocab#>
SELECT DISTINCT ?d ?dlabel
FROM <http://id.nlm.nih.gov/mesh>
WHERE {
  ?d a meshv:TopicalDescriptor .
  ?d rdfs:label ?dlabel .
  { ?d meshv:concept ?c } UNION { ?d meshv:preferredConcept ?c }
  { ?c rdfs:label ?x }
  UNION
  { { ?c meshv:term ?t } UNION { ?c meshv:preferredTerm ?t }
    { ?t meshv:prefLabel ?x } UNION { ?t meshv:altLabel ?x } }
  FILTER (REPLACE(LCASE(STR(?x)), "[^a-z0-9]", "") = %s)
}
"""


def _mesh_norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def mesh_normalised_match(term):
    """Entry-term match again, with punctuation removed from both sides.

    `lookup/descriptor?match=contains` is a literal substring match and the
    entry-term SPARQL is a literal equality, so a term differing from MeSH only
    in punctuation resolves to nothing. That is not a rare edge: MeSH writes
    `Dual Anti-Platelet Therapy` and registers no other spelling, while the
    field writes "dual antiplatelet therapy" almost exclusively - so a current,
    standard descriptor was unreachable, and that axis lost its MeSH-indexed
    query and its hierarchy for the sake of two hyphens.

    Normalising both sides in the FILTER also picks up word-order differences
    wherever MeSH registers them as entry terms, which it usually does:
    "lung adenocarcinoma" reaches `Adenocarcinoma of Lung`, and "non small cell
    lung carcinoma" reaches `Carcinoma, Non-Small-Cell Lung`.

    It stays an EQUALITY, not a similarity. Nonsense returns nothing rather
    than the nearest thing - which is the property that makes "not expanded" a
    signal worth printing. A matcher that always finds something would replace
    a loud failure with a quiet wrong answer.

    Costs about five seconds because the FILTER is computed over every term in
    MeSH, so it is only worth spending when the cheap lookups found nothing.
    One retry rather than the default two: a slow query should not be waited
    for three times over.
    """
    n = _mesh_norm(term)
    if not n:
        return []
    q = _MESH_NORM_SPARQL % json.dumps(n)
    rows = _get_json(f"{MESH_RDF}/sparql?format=JSON&limit=30"
                     f"&query={urllib.parse.quote(q)}",
                     timeout=30, retries=1)["results"]["bindings"]
    return [{"label": b["dlabel"]["value"], "resource": b["d"]["value"], "via": "entry"}
            for b in rows if not b["dlabel"]["value"].startswith("[")]


UMLS_WS = "https://uts-ws.nlm.nih.gov/rest"


def umls_mesh_names(term, limit=3):
    """What MeSH calls the same idea, according to UMLS. Names only.

    The Metathesaurus is the thing actually built for this question: it maps
    synonyms across 200-odd vocabularies onto one concept, and its
    `normalizedString` search runs the SPECIALIST Lexicon's normalisation -
    case, inflection, punctuation, word order - rather than comparing strings.
    It reaches synonyms MeSH does not register itself, which is exactly where
    the local normalised match runs out.

    NAMES, not descriptor ids, and that is the whole point of the design.
    Whatever comes back is looked up in MeSH by the routes already proven
    above, so this function cannot introduce a wrong descriptor: at worst it
    proposes a name MeSH does not recognise and the lookup finds nothing. UMLS
    proposes, MeSH disposes. It also means a mistake in my reading of the UMLS
    response shape costs a miss rather than a plausible wrong answer.

    Returns [] when no key is configured, which is the normal state until
    somebody has applied for a licence in their own name.
    """
    if not UMLS_KEY:
        return []
    u = (f"{UMLS_WS}/search/current?apiKey={urllib.parse.quote(UMLS_KEY)}"
         f"&string={urllib.parse.quote(term)}"
         "&searchType=normalizedString&sabs=MSH&pageSize=25")
    res = (_get_json(u, timeout=25, retries=1) or {}).get("result") or {}
    out, seen = [], set()
    for r in res.get("results") or []:
        name = _norm_space(r.get("name"))
        # A search with no matches answers with one placeholder row rather than
        # an empty list, so an unguarded caller "finds" a concept called NO
        # RESULTS and looks it up.
        if not name or name.upper() == "NO RESULTS" or r.get("ui") == "NONE":
            continue
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(name)
        if len(out) >= limit:
            break
    return out


_STOP = {"of", "the", "and", "a", "an", "in", "for", "with", "to", "on", "by"}


def _label_tokens(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return [t for t in re.split(r"[^a-z0-9]+", s) if t and t not in _STOP]


def label_score(term, label):
    """How well a MeSH descriptor label answers what was asked for.

    NLM returns `match=contains` hits in alphabetical order, not by relevance,
    which puts `Bird Fancier's Lung` and `Heart-Lung Machine` ahead of `Lung`
    and `Lung Neoplasms` for the term "lung".  Taking the first N of that list
    is close to taking N at random, so the ordering has to be rebuilt here.
    """
    tt, lt = _label_tokens(term), _label_tokens(label)
    if not tt or not lt:
        return 0
    if tt == lt:
        return 100
    if sorted(tt) == sorted(lt):
        return 90          # inverted label: "lung adenocarcinoma" / "Adenocarcinoma of Lung"
    if lt[:len(tt)] == tt:
        return 80          # "lung" -> "Lung Neoplasms"
    if set(tt) <= set(lt):
        return 70          # every word present, scattered: "lung" -> "Acute Lung Injury"
    if set(tt) & set(lt):
        return 40
    return 0


def _tree_bonus(trees, ref_trees):
    """How close a descriptor sits to the best hit in the MeSH hierarchy.

    Tree numbers are dotted paths, so a shared prefix is shared ancestry: the
    true narrower terms of the primary hit share it, while same-named things
    from unrelated branches do not.  Used only to break ties within a score
    band, never to overturn a label match.
    """
    best = 0
    for t in trees:
        for r in ref_trees:
            n = 0
            for a, b in zip(t.split("."), r.split(".")):
                if a != b:
                    break
                n += 1
            best = max(best, n)
    return best


def vocab_mesh_rdf(term, limit=10, pool=30):
    """MeSH lookup against id.nlm.nih.gov, shaped exactly like _parse_mesh.

    Over-fetches `pool` candidates from two routes - exact entry-term matches
    and substring matches on the descriptor label - then ranks and keeps
    `limit`.  Details are fetched only for the survivors, so the call count is
    three plus the number returned regardless of how wide the pool is.

    `previous_indexing` has no equivalent here and stays empty; `unique_id` is
    new and worth having, since the D-number is what a precise MeSH query needs.
    """
    hits = []
    seen = set()
    try:
        for h in mesh_entry_match(term):
            if h["resource"] not in seen:
                seen.add(h["resource"])
                hits.append(h)
    except Exception as e:
        _warn(f"MeSH entry-term lookup failed ({e}); using label match only")

    # The inverted form is worth one extra try: MeSH writes "Adenocarcinoma of
    # Lung", researchers write "lung adenocarcinoma", and only some of those
    # pairs are also registered as entry terms.
    variants = [term]
    parts = _norm_space(term).split()
    if 1 < len(parts) <= 4:
        variants.append(" ".join(reversed(parts)))
    def label_lookup(v):
        try:
            for h in _get_json(f"{MESH_RDF}/lookup/descriptor?match=contains&limit={pool}"
                               f"&label={urllib.parse.quote(v)}"):
                if h["resource"] not in seen:
                    seen.add(h["resource"])
                    hits.append(h)
        except Exception as e:
            _warn(f"MeSH label lookup failed for {v!r} ({e})")

    for v in variants:
        label_lookup(v)

    # Last resort: the same match again with punctuation normalised away.
    # Only reached when every cheap lookup found nothing, because it costs
    # about five seconds - see mesh_normalised_match for what it buys.
    if not hits:
        try:
            for h in mesh_normalised_match(term):
                if h["resource"] not in seen:
                    seen.add(h["resource"])
                    hits.append(h)
        except Exception as e:
            _warn(f"MeSH normalised match failed for {term!r} ({e})")

    # Still nothing: ask UMLS what MeSH calls this, then look THAT up here.
    #
    # Everything above compares spellings of the same words. UMLS compares
    # meanings across two hundred vocabularies, so it is the only route that
    # reaches a synonym MeSH does not register - which is the case the local
    # normalisation cannot touch no matter how it normalises.
    #
    # The names it proposes go through the same two lookups as any other term,
    # so nothing here can put a descriptor into the result that MeSH did not
    # confirm. Skipped entirely without a key.
    if not hits and UMLS_KEY:
        for name in umls_mesh_names(term):
            try:
                for h in mesh_entry_match(name):
                    if h["resource"] not in seen:
                        seen.add(h["resource"])
                        hits.append(h)
            except Exception as e:
                _warn(f"MeSH entry-term lookup failed for UMLS name {name!r} ({e})")
            label_lookup(name)
            if hits:
                break

    if not hits:
        return []

    ids = [h["resource"].rsplit("/", 1)[-1] for h in hits]
    meta = _mesh_rdf_meta(ids)

    # An exact entry-term hit is the vocabulary itself saying "this is what you
    # meant", which outranks any amount of label overlap: "breast cancer" is the
    # registered entry term for `Breast Neoplasms`, while `Breast Cancer
    # Lymphedema` merely starts with the same two words.
    scored = [(100 if h.get("via") == "entry" else label_score(term, h["label"]), h, i)
              for h, i in zip(hits, ids)]
    scored.sort(key=lambda s: -s[0])
    ref_trees = meta.get(scored[0][2], {}).get("tree_numbers", set())
    scored.sort(key=lambda s: (-s[0],
                               -_tree_bonus(meta.get(s[2], {}).get("tree_numbers", set()),
                                            ref_trees),
                               len(s[1]["label"])))

    out = []
    for _, hit, did in scored[:limit]:
        m = meta.get(did, {})
        d = _get_json(f"{MESH_RDF}/lookup/details?descriptor={did}")
        e = {"descriptor": hit["label"],
             "definition": m.get("definition", ""),
             "tree_numbers": sorted(m.get("tree_numbers", [])),
             "entry_terms": [t["label"] for t in d.get("terms", [])
                             if not t.get("preferred")],
             "subheadings": [q["label"] for q in d.get("qualifiers", [])],
             "see_also": [s.get("label", "") for s in d.get("seealso", [])],
             "previous_indexing": [],
             "broader": sorted(m.get("broader", [])),
             "unique_id": did}
        e["pubmed_query"] = _mesh_query(e)
        out.append(e)
    return out


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


_MESH_REL_SPARQL = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX meshv: <http://id.nlm.nih.gov/mesh/vocab#>
PREFIX mesh: <http://id.nlm.nih.gov/mesh/>
SELECT DISTINCT ?n ?nlabel ?dir ?tn
FROM <http://id.nlm.nih.gov/mesh>
WHERE {
  { ?n meshv:broaderDescriptor mesh:%(d)s . BIND("narrower" AS ?dir) }
  UNION
  { mesh:%(d)s meshv:broaderDescriptor ?n . BIND("broader" AS ?dir) }
  ?n a meshv:TopicalDescriptor .
  ?n rdfs:label ?nlabel .
  OPTIONAL { ?n meshv:treeNumber ?tnr . ?tnr rdfs:label ?tn }
}
"""


def mesh_relatives(descriptor_id, want_broader=True):
    """Descriptors one step down and one step up the MeSH hierarchy.

    Label matching alone cannot produce breadth for a precise concept: MeSH has
    exactly one descriptor for "lung adenocarcinoma", so crossing two precise
    concepts yields a single query.  The extra angles have to come from the
    hierarchy instead.

    Narrower descriptors are always useful.  Broader ones are only sometimes:
    `Adenocarcinoma of Lung` sits under `Lung Neoplasms`, which is a real and
    valuable widening, but `Endocrine Disruptors` sits under `Toxic Actions`,
    which crossed with anything is noise.  Depth in the tree separates the two,
    so shallow parents are dropped.
    """
    rows = _get_json(f"{MESH_RDF}/sparql?format=JSON&limit=200&query="
                     + urllib.parse.quote(_MESH_REL_SPARQL % {"d": descriptor_id})
                     )["results"]["bindings"]
    seen = {}
    for b in rows:
        did = b["n"]["value"].rsplit("/", 1)[-1]
        e = seen.setdefault(did, {"descriptor": b["nlabel"]["value"], "unique_id": did,
                                  "relation": b["dir"]["value"], "depth": 0})
        if "tn" in b:
            e["depth"] = max(e["depth"], b["tn"]["value"].count(".") + 1)

    out = [e for e in seen.values() if e["relation"] == "narrower"]
    if want_broader:
        # Four levels is where MeSH stops naming categories and starts naming
        # things: C04.588.894.797 is `Lung Neoplasms`, D27.505 is `Toxic Actions`.
        out += sorted((e for e in seen.values()
                       if e["relation"] == "broader" and e["depth"] >= 4),
                      key=lambda e: -e["depth"])
    return out


# --------------------------------------------------------------------------
# Query dialects
# --------------------------------------------------------------------------
# One query string does not travel.  `_mesh_query` writes PubMed syntax, and
# PubMed is the one source this deployment cannot reach; sent to Europe PMC the
# same string returns 7 hits where the concept really has 704, because the
# bracketed field tags are read as literal text.  Every source therefore gets
# its own rendering of the same concepts.  Measured hit counts, one exposure
# crossed with one outcome:
#
#     "X"[MeSH Terms] OR ...      -> Europe PMC      7
#     MESH:"X"                    -> Europe PMC    704   (single concept)
#     ("X" OR "x2") AND ("Y")     -> Europe PMC    145   <- what we send
#     X AND Y  (unquoted words)   -> Europe PMC    421   looser, noisier
#     MESH:"X" AND MESH:"Y"       -> Europe PMC      1   too strict to use
#
# Crossing is done on text, never on MeSH indexing: `MESH:"Adenocarcinoma of
# Lung"` is sparsely applied, so a strict crossing collapses to a single hit and
# the run would report "almost nobody has studied this" - which is the exact
# false negative this whole system exists to prevent.

def _terms_of(c, cap=4):
    """The descriptor plus its most useful synonyms, longest-first.

    Entry terms run to dozens on common descriptors, most of them inversions of
    each other, so a cap keeps the URL and the query sane.  Longer synonyms are
    the specific ones and make better phrase matches.
    """
    terms = [t for t in ([c.get("descriptor")] + list(c.get("terms") or [])) if t]
    seen, out = set(), []
    for t in sorted(terms, key=lambda s: -len(s)):
        k = " ".join(_label_tokens(t))
        if k and k not in seen:
            seen.add(k)
            out.append(_norm_space(t))
    return out[:cap]


def render_query(concepts, source):
    """Render crossed concepts into what `source` actually understands."""
    pairs = [(c, _terms_of(c)) for c in concepts]
    pairs = [(c, g) for c, g in pairs if g]
    if not pairs:
        return ""

    if source == "pubmed":
        parts = []
        for c, g in pairs:
            alts = ([f'"{c["descriptor"]}"[MeSH Terms]'] if c.get("descriptor") else [])
            alts += [f'"{t}"[tiab]' for t in g]
            parts.append("(" + " OR ".join(alts) + ")")
        return " AND ".join(parts)

    if source == "europepmc":
        # Quoted phrases OR'd within a concept, concepts AND'd together.
        parts = ["(" + " OR ".join(f'"{t}"' for t in g) + ")" for _, g in pairs]
        return " AND ".join(parts)

    # openalex, crossref, semanticscholar, arxiv: bag of words.  OpenAlex's
    # `title_and_abstract.search` already ANDs its terms and reads an explicit
    # AND as just another word; quoted OR groups measurably narrow it too far
    # (13 hits against 39).  Crossref ignores AND entirely - the same crossing
    # returns 1,075,599 either way - so precision comes from the ranking and the
    # limit, not the syntax.  arXiv wraps the whole string in `all:`, which
    # parenthesised booleans do not survive.
    #
    # The canonical descriptor goes in rather than the longest synonym: these
    # sources rank on term frequency, and the descriptor is the phrasing the
    # literature actually uses most.
    return " ".join((c.get("descriptor") or g[0]).replace(",", " ") for c, g in pairs)


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
