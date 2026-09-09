"""Offline check of the venue tiers used to order the harvest. No network, no DB.

    python tests/test_journals.py

This decides which papers get their full text fetched when only a few hundred
can be, so it decides which Discussion sections the whole idea-generation step
gets to read. It is a PRIORITY and never a filter, and several checks here
exist only to keep it that way - the moment it starts excluding papers it stops
feeding the thing it is meant to improve.
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

import journals as J  # noqa: E402


def check(name, cond):
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        raise SystemExit(1)


# --- the cross-disciplinary tier -------------------------------------------
# These publish across every disease, which is why they are not part of any one
# domain's list: a finding in cardiology and one in neurology can both land in
# the Lancet.
for v in ["The Lancet", "Lancet", "New England Journal of Medicine",
          "N Engl J Med", "JAMA", "Nature", "Science", "BMJ",
          "Annals of Internal Medicine"]:
    check("general tier: %r" % v, J.tier(v, "clinical") == 2)

# Subsidiaries come along by family name. Listing every one of them by hand
# would be out of date within a year.
for v in ["The Lancet Neurology", "Lancet Oncology", "JAMA Neurology",
          "JAMA Internal Medicine", "Nature Medicine",
          "Nature Reviews Cardiology", "Science Translational Medicine"]:
    check("subsidiary reaches the general tier: %r" % v,
          J.tier(v, "clinical") == 2)


# --- the tier that has to follow the project -------------------------------
check("a clinical venue scores under the clinical domain",
      J.tier("Stroke", "clinical") == 1 and J.tier("Circulation", "clinical") == 1)
check("...and the same venue is not special in another domain",
      J.tier("Stroke", "cs") == 0)
# Added after a live search returned it and it scored zero. The pattern that
# would also have caught `Journal of Stroke and Cerebrovascular Diseases` was
# rejected for that reason - see the check further down that still guards it.
check("a specialty venue seen in real results reaches the domain tier",
      J.tier("European stroke journal", "clinical") == 1)
check("an environmental venue scores under env, not clinical",
      J.tier("Environmental Health Perspectives", "env") == 1
      and J.tier("Environmental Health Perspectives", "clinical") == 0)
check("the general tier does not depend on the domain at all",
      J.tier("The Lancet", "cs") == 2 and J.tier("The Lancet", None) == 2)


# Europe PMC writes subsidiaries with a period, not a space. A family pattern
# of "circulation %" alone matched none of these, which is why the tiers are
# now checked against strings taken from a real search rather than from memory.
check("a period-separated subsidiary reaches its family's tier",
      J.tier("Circulation. Heart failure", "clinical") == 1
      and J.tier("Circulation. Cardiovascular interventions", "clinical") == 1
      and J.tier("Nature reviews. Cardiology", "clinical") == 2)
check("venues Europe PMC disambiguates by society still match",
      J.tier("Heart (British Cardiac Society)", "clinical") == 1
      and J.tier("BMJ (Clinical research ed.)", "clinical") == 2
      and J.tier("Lancet (London, England)", "clinical") == 2)


# --- what must NOT happen ---------------------------------------------------
# The corollary of "heart (%": a bare "heart%" would have taken these too, and
# the tier would stop distinguishing anything.
check("sharing a word with a listed venue is not enough",
      J.tier("Heart failure reviews", "clinical") == 0
      and J.tier("Heart rhythm", "clinical") == 0)
check("an ordinary venue scores zero rather than being excluded - a zero is a "
      "position in the queue, not a rejection",
      J.tier("Journal of Stroke and Cerebrovascular Diseases", "clinical") == 0)
check("a missing venue scores zero and is not penalised further; a real "
      "fraction of Europe PMC records have none",
      J.tier("", "clinical") == 0 and J.tier(None, "clinical") == 0)

# "cell" is the reason the patterns are written out rather than derived from a
# name: a bare substring match would sweep in every journal with "cells" in the
# title and the tier would stop meaning anything.
check("Cell and its family match", J.tier("Cell", "biomed") == 2
      and J.tier("Cancer Cell", "biomed") == 2
      and J.tier("Molecular Cell", "biomed") == 2)
check("a journal that merely contains the word does not",
      J.tier("Stem Cells and Development", "biomed") == 0
      and J.tier("Blood Cells, Molecules and Diseases", "biomed") == 0)

check("an unknown domain still gets the general tier and no second one",
      J.tier("The Lancet", "wibble") == 2 and J.tier("Stroke", "wibble") == 0)
check("patterns() hands back two lists so a caller can rank them apart",
      len(J.patterns("clinical")) == 2 and J.patterns("clinical")[1]
      and J.patterns("wibble")[1] == [])

print("\nall journal tier checks passed")
