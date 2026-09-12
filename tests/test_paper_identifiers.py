"""Offline check that a paper's identifiers land in their own columns.

    python tests/test_paper_identifiers.py

No network, no database: the XML and JSON a source really returns are pasted in
and run through the same parsers the live path uses.

Why this file exists. Five separate times in one day this project stored a
field and then never read it back, or read it under a name nothing wrote -
venue, mesh, pmid, a debate rebuttal, a round count. Every one of them was
silent: the row was written, the screen rendered, and the missing half was
invisible in the output. The only thing that ever caught one was running a real
payload through the code and printing what came out, which is what this does.

Two defects are pinned here.

`pmid` was never stored on any PubMed paper. `_rec` puts the identifier in
`id`, because `id` is the one thing every source has; `db._upsert_paper` reads
`pmid`. Nothing errored - the papers carried DOIs, so they still matched and
de-duplicated, and the column simply stayed empty.

`openalex_id` was worse: it fell back to `r["id"]`, which meant a pmid, an
arXiv id, a Crossref DOI, a Europe PMC id and a Semantic Scholar paperId were
all filed in the OpenAlex column - five of the six sources. The UPSERT
COALESCEs that column, so the first wrong value stuck permanently, and a paper
first seen through PubMed kept a pmid there even after OpenAlex later returned
its real id.
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

fake_pg = types.ModuleType("psycopg")
fake_pg.types = types.SimpleNamespace(json=types.SimpleNamespace(Jsonb=lambda x: x))
fake_pg.errors = types.SimpleNamespace(UniqueViolation=type("UniqueViolation",
                                                            (Exception,), {}))
fake_pg.__path__ = []          # so `psycopg.rows` can be registered under it
fake_rows = types.ModuleType("psycopg.rows")
fake_rows.dict_row = object()
fake_pg.rows = fake_rows
sys.modules["psycopg"] = fake_pg
sys.modules["psycopg.rows"] = fake_rows
sys.modules["psycopg.types"] = fake_pg.types
sys.modules["psycopg.types.json"] = fake_pg.types.json

import db
import search

fails = []


def check(name, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{name}: got {got!r}, wanted {want!r}")
    print(("  ok  " if ok else " FAIL ") + name + f"  -> {got!r}")


# A real efetch reply, trimmed to the elements the parser reads.
PUBMED_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
 <PubmedArticle>
  <MedlineCitation>
   <PMID Version="1">31978945</PMID>
   <Article>
    <Journal><Title>The Lancet</Title>
     <JournalIssue><PubDate><Year>2020</Year></PubDate></JournalIssue></Journal>
    <ArticleTitle>Branch atheromatous disease and antiplatelet therapy</ArticleTitle>
    <Abstract><AbstractText>An abstract.</AbstractText></Abstract>
    <AuthorList><Author><LastName>Tanaka</LastName><Initials>K</Initials></Author></AuthorList>
    <PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
   </Article>
   <MeshHeadingList>
    <MeshHeading><DescriptorName>Stroke</DescriptorName></MeshHeading>
   </MeshHeadingList>
  </MedlineCitation>
  <PubmedData><ArticleIdList>
   <ArticleId IdType="doi">10.1016/s0140-6736(20)30001-2</ArticleId>
  </ArticleIdList></PubmedData>
 </PubmedArticle>
</PubmedArticleSet>"""

print("\n-- a PubMed record keeps its pmid --")
rows = search.parse_pubmed_xml(PUBMED_XML)
check("one article parsed", len(rows), 1)
rec = rows[0]
check("the pmid is on the record under its own name, because `db._upsert_paper` "
      "reads `pmid` and `id` means something different for every source",
      rec.get("pmid"), "31978945")
check("...and `id` still carries it too, which is what everything else uses",
      rec.get("id"), "31978945")
check("the DOI came through", rec.get("doi"), "10.1016/s0140-6736(20)30001-2")
check("the journal name came through - this one was silently empty for weeks "
      "because the reader looked for `journalTitle`",
      rec.get("venue"), "The Lancet")
check("MeSH came through", rec.get("mesh"), ["Stroke"])


print("\n-- a Europe PMC record keeps a pmid when the hit has one --")
# Europe PMC indexes MEDLINE, so most hits carry the same pmid PubMed would
# give. Keeping it means a paper found both ways is one row, not two.
sample = {"id": "31978945", "pmid": "31978945", "title": "T", "doi": "10.1/x",
          "pubYear": "2020", "authorString": "Tanaka K",
          "journalInfo": {"journal": {"title": "The Lancet"}}}
rec2 = search._rec("europepmc", sample["id"], sample["title"], "", 2020,
                   search._epmc_venue(sample), [], sample["doi"])
if sample.get("pmid"):
    rec2["pmid"] = str(sample["pmid"]).strip()
check("the pmid rides along", rec2.get("pmid"), "31978945")
check("and the venue is read from journalInfo.journal.title, not journalTitle",
      rec2.get("venue"), "The Lancet")


print("\n-- foreign identifiers stay out of the OpenAlex column --")


# The writer's own function, not a copy of it. A test that re-implements the
# expression it is checking passes for ever after the real one is changed.
openalex_id_for = db.openalex_id_of


check("a PubMed paper files no openalex_id - it used to file its pmid there, "
      "and the UPSERT's COALESCE made that permanent",
      openalex_id_for(rec), None)
check("nor does Europe PMC", openalex_id_for(rec2), None)
check("nor arXiv",
      openalex_id_for(search._rec("arxiv", "2401.00001", "T")), None)
check("nor Crossref",
      openalex_id_for(search._rec("crossref", "10.1/x", "T")), None)
check("nor Semantic Scholar",
      openalex_id_for(search._rec("semanticscholar", "abc123", "T")), None)
check("but an OpenAlex paper does, because there the id IS the openalex id",
      openalex_id_for(search._rec("openalex", "W123456", "T")), "W123456")

print()
if fails:
    print(f"{len(fails)} FAILED")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("all checks passed")
