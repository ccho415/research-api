"""Profile a local dataset into a field inventory that is safe to upload.

Runs on your machine and nowhere else. What it emits is a list of columns and
what shape they are - never a row, never a cell, and for anything that looks
like personal data, never even a level name.

That restriction is the whole point of the tool rather than a caveat on it. The
feasibility grader needs to know whether a smoking-status variable exists, how
much of it is missing, and whether the rows repeat per patient. It does not need
to know that row 4,102 is a 67-year-old man in Tainan, and once that reaches a
server it cannot be taken back.

    python tools/inventory.py data/cohort.csv --pack observational
    python tools/inventory.py data/ --pack computational --out inventory.json

Upload the JSON with POST /compute/dataset/save. Read it first - it is short,
and it is the only thing standing between a clinical extract and the internet.
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter

# Columns whose contents identify a person. Matched on the name, because by the
# time you are looking at values to decide, you have already read them.
#
# Deliberately over-broad: a false positive costs one line of the inventory, a
# false negative uploads example values of somebody's medical record number.
PII_NAME = [
    r"姓名|name$|^name|patient.*name|full.?name",
    r"身分證|身份證|national.?id|id.?(no|num|number)$|^idno|^uid$|ssn",
    r"病歷|chart.?(no|num)|mrn|medical.?record",
    r"電話|手機|phone|tel$|mobile|contact.?no",
    r"地址|address|addr$|postcode|zip.?code|郵遞",
    r"email|e.?mail|信箱",
    r"生日|出生|birth|dob$",
    r"身份|identity|passport|護照",
    r"帳號|account|insurance.?(no|id)|健保",
    # Free text is where personal data hides in plain sight: a note column is
    # not called `name` and contains the name, the address and the diagnosis.
    r"note|備註|remark|comment|描述|主訴|病摘|摘要|diagnos.*text|free.?text",
]

# Value shapes that identify a person even when the column is called something
# bland. Checked against a sample, and the sample never leaves this process.
PII_VALUE = [
    (r"^[A-Z][12]\d{8}$", "national id"),
    (r"^09\d{8}$", "mobile number"),
    (r"^[\w.+-]+@[\w-]+\.[\w.]+$", "email address"),
]

# Columns that join to public data. This is what separates Tier B - doable after
# a join to open data - from Tier C, so it is worth reporting explicitly rather
# than leaving the grader to infer it from names.
#
# Matched on tokens rather than by regex. Substring matching made `clinical_note`
# joinable on site because it contains `clinic`, and word boundaries did not fix
# it: `_` is a word character, so date misses `visit_date` and lat
# misses `latitude`. Column names are snake_case far more often than they are
# prose, so they are split and the pieces compared.
LINKABLE = {
    "area": {"district", "districts", "township", "county", "city", "area",
             "region", "zone", "town", "village", "ward"},
    "time": {"date", "dates", "time", "year", "month", "week", "day", "visit",
             "admission", "discharge", "index", "dt", "datetime", "timestamp"},
    "site": {"hospital", "site", "center", "centre", "clinic", "facility",
             "institution", "ward"},
    "coordinate": {"lat", "lon", "lng", "latitude", "longitude", "coord",
                   "coords", "geometry", "geocode"},
}

# CJK has no separators to split on, so those match as substrings.
LINKABLE_CJK = [("區", "area"), ("鄉鎮", "area"), ("縣市", "area"),
                ("日期", "time"), ("時間", "time"), ("收案", "time"),
                ("就診", "time"), ("醫院", "site"), ("院所", "site"),
                ("經度", "coordinate"), ("緯度", "coordinate")]

TOKENS = re.compile(r"[a-z]+")

DATE = re.compile(r"^\d{4}[-/]\d{1,2}([-/]\d{1,2})?$|^\d{8}$")
INT = re.compile(r"^-?\d+$")
NUM = re.compile(r"^-?\d*\.?\d+([eE][-+]?\d+)?$")

# Below this many distinct values a non-personal column reports its levels. The
# grader needs them: "does this dataset record smoking status" is answered by
# seeing never/former/current, and not by being told the column is categorical.
LEVEL_CAP = 12

# How many rows to read. Enough to type a column and measure missingness on a
# large file without loading it; the whole file is read when it is smaller.
SAMPLE = 20000


def weight(s):
    """Length in information rather than in characters.

    CJK is about twice as dense as Latin per character, and every length
    threshold in this file is really about how much a value can say.
    """
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)


def looks_personal(name, values):
    """Whether this column identifies a person, by name or by value shape."""
    low = name.strip().lower()
    for pat in PII_NAME:
        if re.search(pat, low, re.I):
            return True, "column name"
    for v in values[:200]:
        for pat, what in PII_VALUE:
            if re.match(pat, v):
                return True, what
    # Long free text is the other way personal data arrives: a clinical note
    # column is not called `name` and contains everything.
    #
    # Measured in weight, not characters. The threshold was 80 characters and a
    # 44-character Chinese clinical note - a complete one, naming the complaint,
    # the smoking history and the examination findings - went straight through
    # and was emitted verbatim as a category level. A CJK character carries
    # roughly twice what a Latin one does, so it counts twice.
    if values:
        long_ones = sum(1 for v in values[:200] if weight(v) > 80)
        if long_ones > len(values[:200]) * 0.3:
            return True, "free text"
    return False, None


def linkable_as(name):
    """What public data this column could join to, or nothing.

    `ward` appears under both area and site because it means both, and which
    one it is cannot be decided from the name. Reported as area, and the join
    still has to be checked by a person - which is what the grader is told.
    """
    low = name.strip().lower()
    for needle, kind in LINKABLE_CJK:
        if needle in low:
            return kind
    parts = set(TOKENS.findall(low))
    for kind in ("area", "time", "site", "coordinate"):
        if parts & LINKABLE[kind]:
            return kind
    return None


def dtype_of(values):
    """The narrowest type every non-empty value fits."""
    if not values:
        return "empty"
    if all(DATE.match(v) for v in values):
        return "date"
    if all(INT.match(v) for v in values):
        return "integer"
    if all(NUM.match(v) for v in values):
        return "number"
    return "text"


def profile_column(name, raw):
    """One column, described without quoting it unless that is safe."""
    values = [v.strip() for v in raw]
    present = [v for v in values if v != ""]
    personal, why = looks_personal(name, present)
    uniq = len(set(present))

    col = {
        "name": name,
        "dtype": dtype_of(present),
        "missing_rate": round(1 - len(present) / len(values), 4) if values else None,
        "n_unique": uniq,
        "personal": personal,
    }
    if personal:
        # No levels, no range, no examples. The type and the missing rate say
        # whether the column can carry the analysis; nothing else is needed and
        # everything else is identifying.
        col["personal_because"] = why
        return col

    if linkable_as(name):
        col["joins_on"] = linkable_as(name)
    if col["dtype"] in ("integer", "number") and present:
        nums = [float(v) for v in present]
        col["min"], col["max"] = min(nums), max(nums)
    elif col["dtype"] == "date" and present:
        col["min"], col["max"] = min(present), max(present)
    elif uniq and uniq <= LEVEL_CAP and all(weight(v) <= 40 for v in set(present)):
        # Levels, in frequency order, so the grader can see whether a category
        # has enough rows to support a subgroup question. Only short ones: a
        # column with four distinct values is not safe to quote if each value is
        # a paragraph.
        col["levels"] = [{"value": v, "n": n}
                         for v, n in Counter(present).most_common()]
    if uniq == len(present) and len(present) > 1:
        col["unique_per_row"] = True
    return col


def detect_structure(cols, rows, header):
    """Cross-sectional, longitudinal or clustered - and on which column.

    This decides more feasibility questions than the variable list does. A
    repeated-measures question needs rows that repeat per subject, and a
    variable list alone cannot say whether they do.
    """
    id_like = [c for c in cols
               if re.search(r"^id$|_id$|subject|patient|案號|編號|chart", c["name"], re.I)
               and not c.get("unique_per_row")]
    dates = [c for c in cols if c["dtype"] == "date"]
    if not id_like:
        return {"shape": "cross-sectional",
                "why": "no identifier column repeats across rows"}
    key = id_like[0]["name"]
    idx = header.index(key)
    counts = Counter(r[idx] for r in rows if idx < len(r) and r[idx].strip())
    repeats = sum(1 for n in counts.values() if n > 1)
    if not repeats:
        return {"shape": "cross-sectional", "why": f"`{key}` is one row per value"}
    out = {"shape": "longitudinal" if dates else "clustered",
           "key": key,
           "n_groups": len(counts),
           "max_rows_per_group": max(counts.values()),
           "why": (f"`{key}` repeats across rows"
                   + (f" and `{dates[0]['name']}` gives them an order" if dates
                      else " with no date column to order them"))}
    return out


def profile_file(path, sample=SAMPLE):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        head = fh.read(8192)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(head, delimiters=",\t;|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(fh, dialect)
        try:
            header = next(reader)
        except StopIteration:
            raise SystemExit(f"{path}: empty file")
        rows, truncated = [], False
        for i, r in enumerate(reader):
            if i >= sample:
                truncated = True
                break
            rows.append(r)

    cols = []
    for i, name in enumerate(header):
        cols.append(profile_column(name, [r[i] if i < len(r) else "" for r in rows]))

    return {
        "filename": os.path.basename(path),
        "n_rows_read": len(rows),
        "rows_truncated_at": sample if truncated else None,
        "n_columns": len(header),
        "structure": detect_structure(cols, rows, header),
        "joinable": sorted({c["joins_on"] for c in cols if c.get("joins_on")}),
        "columns": cols,
    }


def main():
    ap = argparse.ArgumentParser(
        description="Profile a dataset into an uploadable field inventory. "
                    "Raw rows never leave this machine.")
    ap.add_argument("path", help="a CSV/TSV file, or a directory of them")
    ap.add_argument("--pack", help="paradigm pack the grading will use "
                                   "(observational, computational, ...)")
    ap.add_argument("--out", help="write JSON here instead of stdout")
    ap.add_argument("--sample", type=int, default=SAMPLE,
                    help=f"rows to read per file (default {SAMPLE})")
    args = ap.parse_args()

    if os.path.isdir(args.path):
        paths = [os.path.join(args.path, f) for f in sorted(os.listdir(args.path))
                 if f.lower().endswith((".csv", ".tsv", ".txt"))]
        if not paths:
            raise SystemExit(f"{args.path}: no .csv/.tsv/.txt files")
    else:
        paths = [args.path]

    files = [profile_file(p, args.sample) for p in paths]
    n_pii = sum(1 for f in files for c in f["columns"] if c["personal"])
    out = {
        "pack": args.pack,
        "n_files": len(files),
        "n_personal_columns_withheld": n_pii,
        "contains": "column names, types, missing rates and structure only - "
                    "no rows, no cells, and no example values for any column "
                    "flagged personal",
        "files": files,
    }

    text = json.dumps(out, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(text)

    # To stderr so it is seen even when the JSON is piped somewhere.
    print(f"\n{len(files)} file(s), "
          f"{sum(f['n_columns'] for f in files)} columns, "
          f"{n_pii} flagged personal and reported without values.\n"
          f"Read the JSON before uploading it.", file=sys.stderr)


if __name__ == "__main__":
    main()
