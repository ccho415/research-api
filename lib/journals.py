"""Which venues get first claim on the harvest's limited slots.

This is a PRIORITY, never a filter. The search stays wide on purpose: it is
free, it feeds the vocabulary, and - the part that is easy to get backwards -
the material this system actually eats is authors saying what is still unknown,
and those sentences are not concentrated in the top journals. A trial in the
NEJM closes a question; the open ones accumulate in the specialist literature.

What the top journals do give is a field's genuinely new directions rather than
its replications, and that is worth having FIRST when only two hundred papers
can have their full text fetched. So they sort to the front of that queue and
nothing is excluded.

Two tiers, because they answer different questions:

  GENERAL   venues that publish across all of medicine or all of science. A
            major finding in cardiology and one in neurology can both land in
            the Lancet, so this tier does not change with the topic.
  BY_DOMAIN the venues that matter for one domain. This is the tier that has to
            follow the project.

MATCHING IS ON THE FAMILY NAME, so subsidiaries come along: "lancet" reaches
The Lancet Neurology and Lancet Oncology, "nature" reaches Nature Medicine and
Nature Reviews Cardiology, "jama" reaches JAMA Neurology. That is deliberate -
maintaining a list of every subsidiary would be wrong within a year.

HONEST LIMITS, because a curated list rots and this one will:

  - The medical tiers are the ones this project actually uses and the ones I am
    most confident in. `cs`, `env` and the rest are a starting point, not an
    authority. Correct them in place rather than working around them.
  - Venue is missing on a real fraction of Europe PMC records, and Europe PMC
    is the source that answers most clinical searches here since PubMed blocks
    this host. A paper with no venue scores zero and falls back to year and
    citations - it is not penalised beyond losing the boost it might have had.
  - Nothing here is a quality judgement about an individual paper. It decides
    reading order under a cap, and that is all it should ever decide.
"""

# SQL ILIKE patterns, matched against `paper.venue`. Written out rather than
# derived from a name so that short, ambiguous ones can be tightened: bare
# "%cell%" would pull in every journal with "cells" in the title.
GENERAL = [
    "%lancet%",
    "%new england journal of medicine%", "n engl j med%", "nejm%",
    "%jama%", "journal of the american medical association%",
    "nature", "nature %",                      # Nature Medicine, Nature Reviews ...
    "science", "science %", "sci transl med%", "science translational%",
    "cell", "cell %", "molecular cell", "cancer cell", "cell metabolism",
    "bmj", "bmj %", "british medical journal%",
    "annals of internal medicine%", "ann intern med%",
]

# The domains the frontend offers, plus the ones ROUTING knows. A domain absent
# here contributes no second tier, which is a weaker ordering rather than a
# broken one.
BY_DOMAIN = {
    "clinical": [
        "circulation", "circulation %", "circ %",
        "journal of the american college of cardiology%", "j am coll cardiol%",
        "european heart journal%", "eur heart j%",
        # "stroke%" is prefix-anchored on purpose - a bare "%stroke%" sweeps in
        # every journal with the word in its title and the tier stops meaning
        # anything. `european stroke journal` was added after showing up in a
        # live search and being missed.
        #
        # `journal of stroke%` was tried and removed: it also matched Journal
        # of Stroke and Cerebrovascular Diseases, which is not the same tier,
        # and a pattern that cannot tell two journals apart should not be
        # deciding between them. The test that caught it is kept.
        "stroke", "stroke %", "international journal of stroke%",
        "european stroke journal%",
        "neurology", "neurology %", "annals of neurology%", "brain",
        "journal of clinical oncology%", "j clin oncol%",
        "diabetes care%", "diabetologia%",
        "gut", "hepatology%", "gastroenterology%",
        "american journal of respiratory and critical care medicine%",
        "kidney international%", "journal of the american society of nephrology%",
        "intensive care medicine%", "critical care medicine%",
        "annals of the rheumatic diseases%", "arthritis %",
    ],
    "biomed": [
        "immunity", "cancer discovery%", "cell stem cell%", "neuron",
        "molecular psychiatry%", "nucleic acids research%",
        "journal of clinical investigation%", "j clin invest%",
        "embo journal%", "embo %", "genome biology%", "genome research%",
        "plos biology%", "elife", "proceedings of the national academy%",
        "pnas%",
    ],
    "publichealth": [
        "lancet public health%", "lancet global health%",
        "american journal of public health%",
        "international journal of epidemiology%",
        "epidemiology", "american journal of epidemiology%",
        "bulletin of the world health organization%",
        "health affairs%", "milbank quarterly%",
    ],
    "env": [
        "environmental health perspectives%", "environment international%",
        "environmental science & technology%", "environ sci technol%",
        "lancet planetary health%",
        "atmospheric chemistry and physics%",
        "environmental research%", "science of the total environment%",
    ],
    "psych": [
        "psychological science%", "psychological bulletin%",
        "psychological review%", "american journal of psychiatry%",
        "jama psychiatry%", "lancet psychiatry%",
        "biological psychiatry%", "molecular psychiatry%",
    ],
    "cs": [
        "communications of the acm%", "journal of machine learning research%",
        "ieee transactions on pattern analysis%", "ieee transactions on %",
        "acm transactions on %", "artificial intelligence",
    ],
}
# Same venues serve these, so they are aliases rather than copies.
BY_DOMAIN["ml"] = BY_DOMAIN["cs"]
BY_DOMAIN["ecology"] = BY_DOMAIN["env"]


def patterns(domain=None):
    """(general, domain-specific) ILIKE patterns for this project.

    Returned as two lists rather than one so the caller can rank a general-tier
    venue above a domain one. A domain nobody has curated yet returns an empty
    second list, which costs the ordering some precision and nothing else.
    """
    d = (domain or "").strip().lower()
    return list(GENERAL), list(BY_DOMAIN.get(d) or [])


def tier(venue, domain=None):
    """2 for a general top venue, 1 for a domain one, 0 otherwise.

    Python mirror of the SQL ordering, for tests and for anything that has the
    rows in hand already. `%` and `_` are the only wildcards used, and only at
    the end or around the whole string, so a plain prefix/substring test is
    faithful to what Postgres does with these patterns.
    """
    v = (venue or "").strip().lower()
    if not v:
        return 0
    gen, dom = patterns(domain)
    for score, pats in ((2, gen), (1, dom)):
        for p in pats:
            if _ilike(v, p):
                return score
    return 0


def _ilike(value, pattern):
    p = pattern.lower()
    if p.startswith("%") and p.endswith("%"):
        return p[1:-1] in value
    if p.endswith("%"):
        return value.startswith(p[:-1])
    if p.startswith("%"):
        return value.endswith(p[1:])
    return value == p
