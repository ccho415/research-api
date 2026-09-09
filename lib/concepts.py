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
    # Bench technique and equipment.  Nine of the thirty bridge terms in the
    # 2026-08-28 lung adenocarcinoma run were these - `Immunohistochemistry`,
    # `Blotting, Western`, `In Situ Hybridization` - because every cancer paper
    # has a methods section.  Frequency cannot separate them: `Blotting,
    # Western` sits at 1.80% of a random sample and `Exercise` at 1.85%, so any
    # threshold that removes the technique removes the hypothesis too.  The
    # semantic type does separate them, cleanly.
    "Laboratory Procedure", "Molecular Biology Research Technique",
    "Medical Device", "Research Device", "Manufactured Object",
    "Biomedical Occupation or Discipline",
])

# Types that hold both bridges and rubbish, so no rule settles them.
# `Individual Behavior` covers `Smoking` and `Sedentary Behavior` alongside
# `Achievement` and `Gender Identity` - the first two are exactly what a
# hypothesis is made of and the last two are words that happen to be
# descriptors.  These are the ones worth spending a model call on.
AMBIGUOUS_TYPES = frozenset([
    "Individual Behavior", "Social Behavior", "Mental Process",
    "Diagnostic Procedure", "Therapeutic or Preventive Procedure",
    "Health Care Activity", "Natural Phenomenon or Process",
    "Biomedical or Dental Material", "Qualitative Concept",
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


_SQUASHED = None


def _squashed():
    """The same index again with punctuation removed rather than spaced out.

    `norm` turns punctuation into a space, so `Dual Anti-Platelet Therapy`
    becomes "dual anti platelet therapy" and never meets "dual antiplatelet
    therapy", which is how the field writes it. Built lazily and once; the
    dictionary is already resident, so this is a second set of keys over the
    same values.

    First key wins on collision. Two MeSH terms differing only in punctuation
    are near-synonyms in practice, and this index is a fallback consulted only
    after the exact one has missed - so the alternative to an imperfect answer
    here is no answer at all.
    """
    global _SQUASHED
    if _SQUASHED is None:
        _SQUASHED = {}
        for k, ui in load()["terms"].items():
            sq = k.replace(" ", "")
            if sq and sq not in _SQUASHED:
                _SQUASHED[sq] = ui
    return _SQUASHED


def lookup(term):
    """The descriptor id for `term`, tolerating a difference in punctuation.

    Every screen that tells somebody whether a term is "in MeSH" has to answer
    the same way the search itself will, or the person edits their concepts
    against a verdict that will not hold. `search.vocab_mesh_rdf` resolves
    "dual antiplatelet therapy" through NLM; this used to say it was unknown,
    so the confirmation screen advised dropping a term that in fact works.
    """
    key = norm(term)
    if not key:
        return None
    ui = load()["terms"].get(key)
    if ui:
        return ui
    return _squashed().get(key.replace(" ", ""))


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
