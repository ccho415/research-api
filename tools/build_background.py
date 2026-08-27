#!/usr/bin/env python
"""Measure how often each MeSH concept shows up in biomedical writing at large.

Some MeSH descriptors are also ordinary English. `Role` is a descriptor with
the semantic type Social Behavior; `Association` is one with Mental Process.
Every abstract ever written contains "the role of" and "the association
between", so a concept extractor finds them everywhere, and a bridge finder
built on top ranks them as the thing that connects all of medicine to all of
medicine. Semantic types cannot catch this - both types are perfectly
legitimate - and a hand-written stop list only catches the ones you thought of.

Document frequency catches all of them at once, including the ones nobody
anticipated: a concept present in a large fraction of a random sample carries
no information about any particular paper.

Writes data/background_df.json.gz. Run once; re-run if the MeSH year changes.
"""

import argparse
import gzip
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import concepts  # noqa: E402

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "data", "background_df.json.gz")
UA = {"User-Agent": "research-api/1.0 (background frequency profile; "
                    + os.environ.get("ACADEMIC_MAILTO", "") + ")"}


def sample(n_papers, years):
    """A spread of MEDLINE abstracts, one slice per year to avoid a topic skew.

    Paging deeply into a single query returns whatever that query's relevance
    order puts first, which is not a sample of the literature. A year at a time
    is crude but it at least spans the corpus rather than one corner of it.
    """
    per_year = max(1, n_papers // len(years))
    out = []
    for y in years:
        q = f"SRC:MED AND (FIRST_PDATE:[{y}-01-01 TO {y}-12-31]) AND HAS_ABSTRACT:Y"
        cursor, got = "*", 0
        while got < per_year:
            u = (f"{EPMC}?format=json&resultType=core&pageSize=1000"
                 f"&cursorMark={urllib.parse.quote(cursor)}&query={urllib.parse.quote(q)}")
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=180) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            rows = d["resultList"]["result"]
            if not rows:
                break
            out.extend(rows)
            got += len(rows)
            cursor = d.get("nextCursorMark") or ""
            if not cursor:
                break
            time.sleep(0.35)
        print(f"  {y}: {got}", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--papers", type=int, default=6000)
    ap.add_argument("--from-year", type=int, default=2005)
    ap.add_argument("--to-year", type=int, default=2015)
    a = ap.parse_args()

    years = list(range(a.from_year, a.to_year + 1))
    papers = sample(a.papers, years)

    df = {}
    for p in papers:
        text = (p.get("title") or "") + ". " + (p.get("abstractText") or "")
        for ui in concepts.extract(text, informative_only=False):
            df[ui] = df.get(ui, 0) + 1

    n = len(papers)
    data = {"n_papers": n, "df": df}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        json.dump(data, fh)

    print(f"\n{n} papers, {len(df)} concepts seen", file=sys.stderr)
    print("most generic:", file=sys.stderr)
    for ui, c in sorted(df.items(), key=lambda kv: -kv[1])[:25]:
        print(f"   {c / n:5.1%}  {concepts.label(ui)}", file=sys.stderr)
    print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
