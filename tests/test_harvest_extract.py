"""Does the Discussion actually come out of the XML we already paid to fetch?

This exists because the previous extractor threw away full text it was holding.
It required a <title> reading exactly `Discussion` or `Conclusions`, and it
refused any document under 20,000 characters. Both are our rules, not the
literature's, and neither announced itself: the harvest reported "no full text"
for a paper whose Discussion was sitting in memory.

Offline. Every fixture is a real JATS shape, and nothing here touches Europe PMC
- the network half is not what broke.

    python tests/test_harvest_extract.py
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import harvest  # noqa: E402

FAILURES = []


def check(name, got, want):
    ok = got == want
    print(f"  {'ok ' if ok else 'FAIL'} {name}  -> {got!r}")
    if not ok:
        FAILURES.append(f"{name}: got {got!r}, want {want!r}")


def extract(xml):
    """discussion_xml without the fetch, which is the half being tested."""
    saved = harvest._get
    harvest._get = lambda url, text=False, tries=3: xml
    try:
        return harvest.discussion_xml("PMC0")
    finally:
        harvest._get = saved


def body(inner):
    return "<article><front><abstract>a</abstract></front><body>" + inner + "</body></article>"


print("\n-- headings the old pattern refused --")

for heading in ["Discussion", "DISCUSSION", "Discussion and Conclusions",
                "Results and Discussion", "General Discussion",
                "4. Discussion", "Conclusion", "Limitations"]:
    xml = body(f"<sec><title>{heading}</title><p>Further studies are warranted here.</p></sec>")
    got = extract(xml)
    check(f"heading {heading!r}", bool(got and "Further studies are warranted" in got), True)

print("\n-- the length floor is gone, but stubs still return None --")

short = body("<sec><title>Discussion</title><p>Short but real.</p></sec>")
check("a short real full text survives", extract(short), "Short but real.")

stub = "<article><front><abstract><p>Only an abstract here.</p></abstract></front></article>"
check("abstract-only stub has no body -> None", extract(stub), None)
check("empty response -> None", extract(""), None)

print("\n-- sections marked by attribute rather than title --")

attr = ("<article><body><sec sec-type=\"discussion\">"
        "<p>It remains unclear whether this generalises.</p></sec></body></article>")
got = extract(attr)
check("sec-type=discussion is found",
      bool(got and "remains unclear" in got), True)

print("\n-- stops at the next section, does not swallow the rest --")

two = body("<sec><title>Discussion</title><p>KEEP this sentence.</p></sec>"
           "<sec><title>Methods</title><p>DROP this sentence.</p></sec>")
got = extract(two) or ""
check("keeps the Discussion", "KEEP" in got, True)
check("drops the next section", "DROP" in got, False)

print("\n-- a paper with no discussion section at all --")

none = body("<sec><title>Methods</title><p>We did things.</p></sec>")
check("no discussion -> None", extract(none), None)

print("\n-- markup is stripped, whitespace collapsed --")

marked = body("<sec><title>Discussion</title><p>One  <italic>two</italic>\n three.</p></sec>")
check("tags and whitespace", extract(marked), "One two three.")

print("\n-- the cue matcher still only takes sentences that claim a gap --")

hits = harvest.gap_sentences(
    "This is a plain result sentence that says nothing about what is missing at all. "
    "Further studies are warranted to determine whether KRT19 drives resistance in PDAC.")
check("one cue sentence found", len(hits), 1)
check("it is the right one",
      hits[0]["sentence"].startswith("Further studies are warranted"), True)

short_cue = harvest.gap_sentences("Further study is needed.")
check("too short to be a direction is dropped", len(short_cue), 0)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("all checks passed")
