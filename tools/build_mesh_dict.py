#!/usr/bin/env python
"""Build the MeSH term dictionary used to pull concepts out of abstracts.

Literature-based discovery works on concepts, not words, and the field's own
tooling (MetaMap over UMLS) reads them out of titles and abstracts rather than
trusting human indexing.  It has to: MeSH indexing covers a small and lagging
slice of the literature - for `Endocrine Disruptors`, 675 indexed records
against 24,831 that mention it - and the rare bridges worth finding are exactly
the ones the indexers did not think to mark.

We cannot run MetaMap, so this builds the next best thing: every MeSH
descriptor together with all of its entry terms, normalised for matching, plus
the UMLS semantic types that say what kind of thing each one is.  Semantic
types are how the literature filters out concepts that carry no information -
`Humans`, `Animals`, `Female` are Population Group and Organism, not the
diseases and substances a hypothesis is made of.

Run once per MeSH year.  Writes data/mesh_terms.json.gz.
"""

import gzip
import json
import os
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET

BASE = "https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES"
DESC_URL = BASE + "/xmlmesh/desc2026.gz"
STYPE_URL = BASE + "/misc/umls_desc_st.txt"
SUPP_URL = BASE + "/xmlmesh/supp2026.gz"
SUPP_STYPE_URL = BASE + "/misc/umls_scr_st.txt"

# Supplementary Concept Records carry the specific substances a descriptor only
# gestures at - `Bisphenol A` is an SCR, while MeSH's descriptor for it is the
# whole class `Benzhydryl Compounds` - so an exposure study is unreadable
# without them.  There are roughly 350,000, though, most being registry names
# that never appear verbatim in an abstract, so they are filtered rather than
# taken wholesale.  Class 2 is trial protocols, which are not concepts anything
# can bridge through.
SCR_CLASSES = {"1", "3", "4"}          # chemical, rare disease, organism
SCR_MAX_TOKENS = 6

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
OUT = os.path.join(DATA, "mesh_terms.json.gz")

UA = {"User-Agent": "research-api/1.0 (academic use; one-off vocabulary build)"}

_PUNCT = re.compile(r"[^a-z0-9]+")


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return _PUNCT.sub(" ", s).strip()


def fetch(url, path):
    if os.path.exists(path):
        return path
    print(f"downloading {url}", file=sys.stderr)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600) as r:
        open(path, "wb").write(r.read())
    return path


def load_semantic_types(path):
    """concept UI -> semantic type names.  The file is keyed by M-number."""
    out = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("|")
            if len(parts) >= 2 and parts[0].startswith("M"):
                out.setdefault(parts[0], []).append(parts[1])
    return out


def build(desc_gz, stypes):
    terms, labels, sty, trees = {}, {}, {}, {}
    with gzip.open(desc_gz, "rb") as fh:
        for _, el in ET.iterparse(fh, events=("end",)):
            if el.tag != "DescriptorRecord":
                continue
            ui = el.findtext("DescriptorUI")
            label = el.findtext("DescriptorName/String")
            if ui and label:
                labels[ui] = label
                tn = [t.text for t in el.findall("TreeNumberList/TreeNumber") if t.text]
                if tn:
                    trees[ui] = tn
                seen = set()
                for concept in el.findall("ConceptList/Concept"):
                    cui = concept.findtext("ConceptUI")
                    if concept.get("PreferredConceptYN") == "Y" and cui in stypes:
                        sty[ui] = stypes[cui]
                    for s in concept.findall("TermList/Term/String"):
                        k = norm(s.text)
                        # A term shared by two descriptors is ambiguous, and an
                        # ambiguous match is worse than a missed one here: it
                        # invents a link that the literature does not contain.
                        if not k or len(k) < 4:
                            continue
                        if k in terms and terms[k] != ui:
                            terms[k] = None
                        elif k not in seen:
                            terms[k] = ui
                            seen.add(k)
            el.clear()

    dropped = sum(1 for v in terms.values() if v is None)
    terms = {k: v for k, v in terms.items() if v}
    return {"labels": labels, "terms": terms, "semantic_types": sty,
            "tree_numbers": trees, "dropped_ambiguous": dropped}


def _usable_scr_term(k):
    """Keep only what could actually be written in an abstract.

    Registry names - `1,1'-(2,2,2-trichloroethylidene)bis(4-chlorobenzene)` -
    are real terms nobody types, and they outnumber the readable ones several
    times over.  Length, token count and digit density separate the two well
    enough that nothing readable is lost.
    """
    if not (4 <= len(k) <= 60):
        return False
    if k.count(" ") + 1 > SCR_MAX_TOKENS:
        return False
    digits = sum(c.isdigit() for c in k)
    return digits * 5 <= len(k) * 2


def add_supplementary(data, supp_gz, stypes):
    """Fold in Supplementary Concept Records without letting them shadow MeSH.

    A descriptor always wins a term collision: it is the curated, more general
    concept, and a bridge found through it is the one a reviewer would
    recognise.
    """
    terms, labels, sty = data["terms"], data["labels"], data["semantic_types"]
    mapped, kept, skipped = {}, 0, 0

    with gzip.open(supp_gz, "rb") as fh:
        for _, el in ET.iterparse(fh, events=("end",)):
            if el.tag != "SupplementalRecord":
                continue
            if el.get("SCRClass") not in SCR_CLASSES:
                el.clear()
                skipped += 1
                continue
            ui = el.findtext("SupplementalRecordUI")
            label = el.findtext("SupplementalRecordName/String")
            if not (ui and label):
                el.clear()
                continue

            added = False
            for concept in el.findall("ConceptList/Concept"):
                cui = concept.findtext("ConceptUI")
                if concept.get("PreferredConceptYN") == "Y" and cui in stypes:
                    sty[ui] = stypes[cui]
                for s in concept.findall("TermList/Term/String"):
                    k = norm(s.text)
                    if not k or not _usable_scr_term(k) or k in terms:
                        continue
                    terms[k] = ui
                    added = True
            if added:
                labels[ui] = label
                heads = [h.text for h in el.findall("HeadingMappedToList/"
                                                    "HeadingMappedTo/DescriptorReferredTo/"
                                                    "DescriptorUI") if h.text]
                if heads:
                    # The '*' prefix marks the primary mapping in MeSH's own files.
                    mapped[ui] = [h.lstrip("*") for h in heads]
                kept += 1
            el.clear()

    data["mapped_to"] = mapped
    data["n_supplementary"] = kept
    data["n_supplementary_skipped"] = skipped
    return data


def main():
    os.makedirs(DATA, exist_ok=True)
    tmp = os.environ.get("TMPDIR") or DATA
    desc = fetch(DESC_URL, os.path.join(tmp, "desc2026.gz"))
    st = fetch(STYPE_URL, os.path.join(tmp, "umls_desc_st.txt"))

    data = build(desc, load_semantic_types(st))
    n_desc = len(data["labels"])
    n_desc_terms = len(data["terms"])

    supp = fetch(SUPP_URL, os.path.join(tmp, "supp2026.gz"))
    supp_st = fetch(SUPP_STYPE_URL, os.path.join(tmp, "umls_scr_st.txt"))
    data = add_supplementary(data, supp, load_semantic_types(supp_st))

    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)

    print(f"descriptors        {n_desc:,}", file=sys.stderr)
    print(f"  their terms      {n_desc_terms:,}", file=sys.stderr)
    print(f"  ambiguous dropped{data['dropped_ambiguous']:>8,}", file=sys.stderr)
    print(f"supplementary kept {data['n_supplementary']:,}"
          f"  (skipped by class {data['n_supplementary_skipped']:,})", file=sys.stderr)
    print(f"matchable terms    {len(data['terms']):,}", file=sys.stderr)
    print(f"with semantic type {len(data['semantic_types']):,}", file=sys.stderr)
    print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
