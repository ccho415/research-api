"""Read MeSH concepts out of free text.

Literature-based discovery is done on concepts, and the field reads them out of
titles and abstracts rather than trusting human indexing.  It has to: MeSH
indexing covers a small and lagging slice - `Endocrine Disruptors` has 675
indexed records against 24,831 that mention it - and a bridge nobody thought to
index is exactly the kind worth finding.

The reference implementations use MetaMap over UMLS, which needs a licence and
a server.  This is the same idea at a tenth of the weight: longest-match
lookup against every MeSH descriptor and Supplementary Concept Record term,
built once by tools/build_mesh_dict.py.
"""

import gzip
import json
import os
import re
import unicodedata

DICT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "mesh_terms.json.gz")

# The longest MeSH term worth scanning for.  Beyond this the match rate does not
# improve and every extra token multiplies the lookups per position.
MAX_SPAN = 6

# Semantic types that say nothing about what a paper is about.  This is how the
# LBD literature filters, rather than a hand-written stop list: `Humans`,
# `Animals`, `Female`, `Adult` are indexing check tags, and `Risk`, `Methods`,
# `Time Factors` are the vocabulary of any abstract whatsoever.  A bridge built
# out of these is an artefact of writing conventions, not of biology.
#
# Organisms are deliberately split: `Mammal` and `Rodent` are check tags, while
# `Bacterium`, `Virus` and `Fungus` are things a hypothesis can genuinely run
# through - the microbiome work this system is meant to reach depends on it.
UNINFORMATIVE_TYPES = frozenset([
    "Human", "Population Group", "Age Group", "Family Group", "Group",
    "Patient or Disabled Group", "Professional or Occupational Group",
    "Group Attribute", "Animal", "Mammal", "Rodent", "Vertebrate",
    "Amphibian", "Bird", "Fish", "Reptile",
    "Qualitative Concept", "Quantitative Concept", "Temporal Concept",
    "Spatial Concept", "Idea or Concept", "Functional Concept",
    "Conceptual Entity", "Intellectual Product", "Language",
    "Geographic Area", "Regulation or Law", "Classification",
    "Occupation or Discipline", "Occupational Activity", "Organization",
    "Health Care Related Organization", "Professional Society",
    "Self-help or Relief Organization",
    # How a study was done, not what it was about.  `Cross-Sectional Studies`
    # links every epidemiological literature to every other one.
    "Research Activity", "Governmental or Regulatory Activity",
    "Educational Activity", "Machine Activity",
])

_PUNCT = re.compile(r"[^a-z0-9]+")
_DICT = None


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return _PUNCT.sub(" ", s).strip()


def load(path=None):
    """Load and cache the dictionary.  ~1.8s and ~200MB resident, done once."""
    global _DICT
    if _DICT is None:
        with gzip.open(path or DICT_PATH, "rt", encoding="utf-8") as fh:
            _DICT = json.load(fh)
    return _DICT


def label(ui):
    return load()["labels"].get(ui, ui)


def semantic_types(ui):
    return load()["semantic_types"].get(ui, [])


def is_informative(ui):
    st = semantic_types(ui)
    return bool(st) and not any(t in UNINFORMATIVE_TYPES for t in st)


def tree_depth(ui):
    """Deepest position in the MeSH hierarchy, 1 for a top-level category.

    Supplementary records have no tree at all and are reported as None; they
    are specific by construction, being single substances and single diseases.
    """
    tns = load()["tree_numbers"].get(ui)
    if not tns:
        return None
    return max(t.count(".") + 1 for t in tns)


BACKGROUND_PATH = os.path.join(os.path.dirname(DICT_PATH), "background_df.json.gz")
_BACKGROUND = None

# Above this share of a random sample of abstracts, a concept says nothing
# about any particular paper.  Measured over 11,000 MEDLINE abstracts:
# `Methods` 39%, `Patients` 28%, `Role` 16%, `Association` 8%, and `Play and
# Playthings` 6.7% - that last one entirely from the phrase "plays a role".
MAX_BACKGROUND_DF = 0.02


def background():
    global _BACKGROUND
    if _BACKGROUND is None:
        try:
            with gzip.open(BACKGROUND_PATH, "rt", encoding="utf-8") as fh:
                _BACKGROUND = json.load(fh)
        except FileNotFoundError:
            _BACKGROUND = {"n_papers": 0, "df": {}}
    return _BACKGROUND


def background_df(ui):
    b = background()
    return (b["df"].get(ui, 0) / b["n_papers"]) if b["n_papers"] else 0.0


def is_generic(ui, max_df=MAX_BACKGROUND_DF):
    """Whether a concept is too widespread to carry information.

    Some MeSH descriptors are also ordinary English - `Role` is one, with the
    semantic type Social Behavior, and `Association` is another, Mental Process
    - so neither a semantic-type filter nor a hand-written stop list catches
    them.  Document frequency does, along with the ones nobody would think to
    list.
    """
    return background_df(ui) > max_df


def shares_branch(ui_a, ui_b):
    """Whether two concepts sit on the same path of the MeSH hierarchy.

    `Lung Neoplasms` is an ancestor of `Adenocarcinoma of Lung` and
    `Adenocarcinoma` is a sibling class of it; neither is a bridge to anything,
    they are the same subject at a different resolution.  Letting them through
    fills the ranking with rephrasings of the starting point.
    """
    ta = load()["tree_numbers"].get(ui_a) or []
    tb = load()["tree_numbers"].get(ui_b) or []
    for x in ta:
        for y in tb:
            if x == y or x.startswith(y + ".") or y.startswith(x + "."):
                return True
    return False


def is_specific(ui, min_depth=3):
    """Whether a concept is narrow enough to carry a hypothesis.

    Ranking concepts by how often they appear surfaces `Neoplasms`,
    `Mutation` and `Therapeutics` - true of the corpus, useless as a bridge,
    because they connect everything to everything.  Depth in the MeSH tree
    separates a category from a thing: `Neoplasms` is C04, while
    `Adenocarcinoma of Lung` is C04.588.894.797.520.109.
    """
    d = tree_depth(ui)
    return True if d is None else d >= min_depth


def extract(text, informative_only=True):
    """Concept UIs found in `text`, with how many times each was matched.

    Longest match wins and consumes its tokens, so "lung adenocarcinoma" is one
    hit for `Adenocarcinoma of Lung` rather than also counting `Adenocarcinoma`
    at the next position.  Overlapping matches would inflate every count in
    proportion to how compound the term is, which is precisely the bias the
    ranking must not have.
    """
    d = load()
    terms = d["terms"]
    toks = norm(text).split()
    out = {}
    i = 0
    while i < len(toks):
        span = 0
        ui = None
        for n in range(min(MAX_SPAN, len(toks) - i), 0, -1):
            hit = terms.get(" ".join(toks[i:i + n]))
            if hit:
                ui, span = hit, n
                break
        if ui:
            if not informative_only or is_informative(ui):
                out[ui] = out.get(ui, 0) + 1
            i += span
        else:
            i += 1
    return out


_BY_UI = None


def _by_ui():
    """Reverse index, built once: scanning 800k terms per lookup is not free."""
    global _BY_UI
    if _BY_UI is None:
        _BY_UI = {}
        for term, ui in load()["terms"].items():
            _BY_UI.setdefault(ui, []).append(term)
    return _BY_UI


def query_terms(ui, cap=4):
    """The descriptor's own name plus its shortest synonyms, for text search.

    Shortest rather than longest: a search wants the phrasing people write, and
    the long synonyms of a MeSH concept are usually its inverted or registry
    forms, which appear in the thesaurus and nowhere else.
    """
    name = load()["labels"].get(ui)
    if not name:
        return []
    key = norm(name)
    alts = sorted((t for t in _by_ui().get(ui, []) if t != key), key=len)
    return [name] + alts[:cap - 1]
