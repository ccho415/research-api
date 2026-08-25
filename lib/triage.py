#!/usr/bin/env python
"""Batch triage for research directions: near-duplicate detection and Elo ranking.

Stdlib only.  This script does the bookkeeping an LLM is bad at (pair generation,
rating arithmetic, lexical similarity) and deliberately leaves every *judgement*
to the model calling it.

Subcommands
-----------
  dedup    Flag candidate near-duplicate pairs for the model to adjudicate.
  pairs    Emit a round-robin schedule; every pair appears twice with the order
           swapped, which cancels the position bias of LLM pairwise judges.
  elo      Turn recorded match outcomes into Elo ratings and a ranked table.

Idea file format (JSON list, or JSONL):
  [{"id": "i01", "title": "...", "statement": "...", "rationale": "..."}, ...]
Only `id` plus at least one text field is required.

Examples
--------
  python triage.py dedup ideas.json --threshold 0.55 --out dupes.json
  python triage.py pairs ideas.json --out schedule.json
  python triage.py elo results.json --ideas ideas.json --out ranking.json
"""

import argparse
import itertools
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

STOP = set("""a an the and or of for to in on at by with from as is are was were be been being
this that these those it its their our we they you i not no than then so such but if while
which who whom whose what when where how why can could may might will would shall should must
do does did done have has had having very more most much many some any all each other others
between among during through against about into over under above below after before both same
study research paper propose proposed novel new approach method framework using use used based
effect effects impact impacts association associations relationship relationships analysis""".split())


# --------------------------------------------------------------------------
# Text handling
# --------------------------------------------------------------------------
def idea_text(rec):
    parts = [rec.get(k, "") for k in ("title", "statement", "rationale", "text", "idea", "gap")]
    return " ".join(p for p in parts if p).strip() or json.dumps(rec, ensure_ascii=False)


def tokens(text):
    """Word tokens for Latin script, plus character bigrams for CJK runs.

    CJK has no whitespace word boundaries, so bigrams are the standard cheap
    substitute; mixing both keeps the function usable for either language.
    """
    text = text.lower()
    words = [w for w in re.findall(r"[a-z][a-z0-9\-]{1,}", text) if w not in STOP and len(w) > 2]
    cjk_runs = re.findall(r"[一-鿿぀-ヿ]{2,}", text)
    bigrams = [run[i:i + 2] for run in cjk_runs for i in range(len(run) - 1)]
    return words + bigrams


def tfidf_vectors(docs):
    tokenised = [Counter(tokens(d)) for d in docs]
    df = Counter()
    for c in tokenised:
        df.update(c.keys())
    n = len(docs)
    vecs = []
    for c in tokenised:
        v = {}
        for t, tf in c.items():
            v[t] = (1 + math.log(tf)) * math.log((n + 1) / (df[t] + 1))
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({t: x / norm for t, x in v.items()})
    return vecs


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def jaccard(a, b):
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------
def load_ideas(path):
    with open(path, encoding="utf-8") as f:
        raw = f.read().strip()
    # Try whole-file JSON first.  Sniffing for JSONL by "starts with { and has a
    # newline" misfires on every pretty-printed JSON object, so only fall back to
    # line-by-line parsing once a full parse has actually failed.
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            data = [json.loads(l) for l in raw.splitlines() if l.strip()]
        except json.JSONDecodeError as e:
            sys.exit(f"{path}: not valid JSON or JSONL ({e})")
    if isinstance(data, dict):
        for key in ("ideas", "anchors", "results", "gaps", "candidates"):
            if isinstance(data.get(key), (list, dict)):
                data = data[key]
                break
        else:
            data = list(data.values())
    if isinstance(data, dict):   # e.g. {"a01": {...}, "a02": {...}}
        data = [dict(v, id=v.get("id", k)) if isinstance(v, dict) else {"id": k, "title": v}
                for k, v in data.items()]
    out = []
    for i, r in enumerate(data):
        if isinstance(r, str):
            r = {"title": r}
        r.setdefault("id", f"i{i + 1:02d}")
        out.append(r)
    if len(out) < 2:
        sys.exit("need at least 2 ideas")
    return out


def emit(obj, out):
    txt = json.dumps(obj, ensure_ascii=False, indent=2)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"wrote {out} ({len(txt)} bytes)")
    else:
        print(txt)


# --------------------------------------------------------------------------
# dedup
# --------------------------------------------------------------------------
def cmd_dedup(a):
    ideas = load_ideas(a.ideas)
    texts = [idea_text(r) for r in ideas]
    vecs = tfidf_vectors(texts)
    toks = [tokens(t) for t in texts]
    scored = []
    for i, j in itertools.combinations(range(len(ideas)), 2):
        cos, jac = cosine(vecs[i], vecs[j]), jaccard(toks[i], toks[j])
        scored.append({
            "a": ideas[i]["id"], "b": ideas[j]["id"],
            "score": round(0.7 * cos + 0.3 * jac, 3),
            "cosine": round(cos, 3), "jaccard": round(jac, 3),
            "a_text": texts[i][:400], "b_text": texts[j][:400],
            "verdict": None,  # the model fills this: "duplicate" | "distinct"
        })
    scored.sort(key=lambda p: -p["score"])

    # Absolute similarity runs low on short idea statements (a genuine restatement
    # often scores only ~0.2), but the *separation* is wide.  So take everything
    # over the threshold and always surface the top few regardless, rather than
    # letting a fixed cut-off return nothing.
    pairs = [p for p in scored if p["score"] >= a.threshold]
    for p in scored[:a.top]:
        if p not in pairs and p["score"] > 0:
            p["below_threshold"] = True
            pairs.append(p)
    pairs.sort(key=lambda p: -p["score"])
    top_score = scored[0]["score"] if scored else 0.0

    emit({
        "n_ideas": len(ideas), "threshold": a.threshold,
        "score_range": [scored[-1]["score"] if scored else 0.0, top_score],
        "n_candidate_pairs": len(pairs),
        "note": ("Lexical pre-filter only - it surfaces pairs worth reading and decides "
                 "nothing. Read each pair and set \"verdict\" to \"duplicate\" or "
                 "\"distinct\", then merge the duplicates. Judge by the RELATIVE gap, not "
                 "the absolute number: restatements of one idea typically score ~0.2 while "
                 "unrelated ideas sit near 0.0, so a pair an order of magnitude above the "
                 "rest is the signal. TWO BLIND SPOTS THIS SCRIPT CANNOT SEE, so skim the "
                 "full list yourself as well: (1) the same idea written in two different "
                 "languages scores 0.0, and (2) two ideas can share heavy vocabulary and "
                 "still be genuinely distinct."),
        "candidate_pairs": pairs,
    }, a.out)


# --------------------------------------------------------------------------
# pairs
# --------------------------------------------------------------------------
def cmd_pairs(a):
    ideas = load_ideas(a.ideas)
    anchors = []
    if a.anchors:
        anchors = load_ideas(a.anchors)
        for r in anchors:
            r["is_anchor"] = True
            r.setdefault("grade", "ungraded")
    field = ideas + anchors
    ids = [r["id"] for r in field]
    if len(set(ids)) != len(ids):
        sys.exit("anchor ids collide with idea ids - rename the anchors")

    sched = []
    for x, y in itertools.combinations(ids, 2):
        anchor_ids = {r["id"] for r in anchors}
        if x in anchor_ids and y in anchor_ids:
            continue          # anchors are the yardstick; they need not fight each other
        for first, second in ((x, y), (y, x)):
            sched.append({"match": len(sched) + 1, "left": first, "right": second,
                          "winner": None, "reason": None})

    payload = {
        "n_ideas": len(ideas), "n_anchors": len(anchors), "n_matches": len(sched),
        "criteria": a.criteria.split(","),
        "protocol": ("Judge each match on the listed criteria and set \"winner\" to the "
                     "id of the stronger idea (or \"tie\"), with a one-sentence \"reason\". "
                     "Every pair appears twice with left/right swapped - judge the two "
                     "independently and do not look back at the first verdict; "
                     "disagreement between the two orderings is real signal that the pair "
                     "is close. Then feed this file to `triage.py elo`."),
        "ideas": {r["id"]: idea_text(r)[:300] for r in field},
        "matches": sched,
    }
    if anchors:
        payload["anchors"] = {r["id"]: {"grade": r.get("grade"),
                                        "text": idea_text(r)[:300]} for r in anchors}
        payload["anchor_protocol"] = (
            "Anchors are ideas of independently known quality mixed into the field. Judge "
            "them exactly like any other idea - do NOT look at their grade while judging, "
            "and do not treat an anchor as automatically better or worse. Their only job "
            "is to put an absolute scale under the Elo numbers, so that 'best in this "
            "batch' can be distinguished from 'actually good'. Peeking at the grades "
            "destroys that.")
    emit(payload, a.out)


# --------------------------------------------------------------------------
# elo
# --------------------------------------------------------------------------
def cmd_elo(a):
    with open(a.results, encoding="utf-8") as f:
        doc = json.load(f)
    matches = doc.get("matches", doc if isinstance(doc, list) else [])
    played = [m for m in matches if m.get("winner")]
    if not played:
        sys.exit("no matches have a 'winner' set - fill in the schedule first")

    ids = sorted({m["left"] for m in played} | {m["right"] for m in played})
    rating = {i: 1200.0 for i in ids}
    record = {i: {"win": 0, "loss": 0, "tie": 0} for i in ids}

    for m in played:
        l, r, w = m["left"], m["right"], str(m["winner"]).strip()
        el = 1 / (1 + 10 ** ((rating[r] - rating[l]) / 400))
        if w == l:
            sl, record[l]["win"], record[r]["loss"] = 1.0, record[l]["win"] + 1, record[r]["loss"] + 1
        elif w == r:
            sl, record[r]["win"], record[l]["loss"] = 0.0, record[r]["win"] + 1, record[l]["loss"] + 1
        else:
            sl, record[l]["tie"], record[r]["tie"] = 0.5, record[l]["tie"] + 1, record[r]["tie"] + 1
        rating[l] += a.k * (sl - el)
        rating[r] += a.k * ((1 - sl) - (1 - el))

    # Order-flip disagreement: the same pair judged differently in both directions.
    seen, flips = {}, []
    for m in played:
        key = tuple(sorted((m["left"], m["right"])))
        if key in seen and seen[key] != m["winner"]:
            flips.append({"pair": list(key), "verdicts": [seen[key], m["winner"]]})
        seen[key] = m["winner"]

    titles = {}
    if a.ideas and os.path.exists(a.ideas):
        titles = {r["id"]: idea_text(r)[:160] for r in load_ideas(a.ideas)}
    anchor_grade = {}
    if a.anchors and os.path.exists(a.anchors):
        for r in load_ideas(a.anchors):
            anchor_grade[r["id"]] = r.get("grade", "ungraded")
            titles.setdefault(r["id"], idea_text(r)[:160])
    else:
        for aid, meta in (doc.get("anchors") or {}).items():
            anchor_grade[aid] = meta.get("grade", "ungraded")
            titles.setdefault(aid, meta.get("text", "")[:160])

    table = sorted(
        ({"rank": 0, "id": i, "elo": round(rating[i], 1), **record[i],
          "is_anchor": i in anchor_grade,
          "anchor_grade": anchor_grade.get(i), "text": titles.get(i, "")} for i in ids),
        key=lambda r: -r["elo"])
    for n, row in enumerate(table, 1):
        row["rank"] = n

    out = {
        "n_matches_played": len(played), "k_factor": a.k,
        "order_flip_disagreements": flips,
        "note": ("Elo separates a field that pointwise 1-10 scoring collapses into 7-8. "
                 f"{len(flips)} pair(s) flipped when the order was swapped - those are "
                 "genuinely too close to call, so do not read their gap as meaningful. "
                 "Carry only the top few forward to deep verification."),
        "ranking": table,
    }

    # Calibration: with graded anchors in the field, Elo stops being purely
    # relative to this batch and gains an absolute reference.
    if anchor_grade:
        anchors = [r for r in table if r["is_anchor"]]
        mine = [r for r in table if not r["is_anchor"]]
        by_grade = defaultdict(list)
        for r in anchors:
            by_grade[r["anchor_grade"]].append(r["elo"])
        bands = {g: {"mean_elo": round(sum(v) / len(v), 1), "n": len(v)}
                 for g, v in sorted(by_grade.items())}
        strong = bands.get("strong", {}).get("mean_elo")
        weak = bands.get("weak", {}).get("mean_elo")
        for r in mine:
            if strong is not None and r["elo"] >= strong:
                r["calibration"] = "at or above the strong anchors"
            elif weak is not None and r["elo"] <= weak:
                r["calibration"] = "at or below the weak anchors"
            else:
                r["calibration"] = "between the anchor bands"
        out["anchor_bands"] = bands
        out["calibration_note"] = (
            "Anchor bands give the Elo scale an absolute reference. An idea ranked first "
            "in this batch but sitting below the weak anchors is a weak idea in a weak "
            "batch - the ranking alone could never tell you that. Treat 'at or above the "
            "strong anchors' as the bar worth clearing, not the top rank. Anchors were "
            "judged blind to their grades; if a strong anchor finished bottom, distrust "
            "the whole run and re-judge rather than reporting it.")
    emit(out, a.out)


# --------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dedup", help="flag candidate near-duplicate pairs")
    d.add_argument("ideas")
    d.add_argument("--threshold", type=float, default=0.15)
    d.add_argument("--top", type=int, default=15,
                   help="always surface this many highest-scoring pairs, threshold or not")
    d.add_argument("--out")
    d.set_defaults(fn=cmd_dedup)

    q = sub.add_parser("pairs", help="round-robin schedule, each pair twice, order swapped")
    q.add_argument("ideas")
    q.add_argument("--anchors", help="graded anchor ideas to calibrate the Elo scale")
    q.add_argument("--criteria",
                   default="novelty,significance,feasibility,clarity,expected effectiveness")
    q.add_argument("--out")
    q.set_defaults(fn=cmd_pairs)

    e = sub.add_parser("elo", help="compute Elo ratings from judged matches")
    e.add_argument("results")
    e.add_argument("--ideas")
    e.add_argument("--anchors")
    e.add_argument("--k", type=float, default=32.0)
    e.add_argument("--out")
    e.set_defaults(fn=cmd_elo)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
