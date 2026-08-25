"""API-shaped wrappers around search.py and triage.py.

Those two files are copies of the Claude Code skill scripts and are kept
UNCHANGED so the skills keep working.  Their command-line entry points read and
write files, which does not suit an HTTP service, so the small amount of
orchestration each one does is re-expressed here against their pure functions.

If you edit a skill script, re-copy it into lib/ and re-run the equivalence
test in tests_equivalence.py.
"""

import itertools
from collections import defaultdict

import search as lit
import triage as tri


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------
def search_query(query, domain="general", sources=None, limit=25,
                 year_from=None, year_to=None, sort="relevance"):
    """Mirrors `search.py query`."""
    names = sources or lit.ROUTING.get(domain, lit.ROUTING["general"])
    batches, failed = [], []
    for n in names:
        fn = lit.SOURCES.get(n)
        if not fn:
            failed.append({"source": n, "error": "unknown source"})
            continue
        try:
            batches.append(fn(query, limit, year_from, year_to))
        except Exception as e:
            # One source going down must not kill the run - the skill behaves
            # the same way and reports which sources actually answered.
            failed.append({"source": n, "error": f"{type(e).__name__}: {e}"})
    merged = lit.merge(batches)
    if sort == "citations":
        merged.sort(key=lambda r: -(r.get("citations") or 0))
    elif sort == "year":
        merged.sort(key=lambda r: -(r.get("year") or 0))
    else:
        merged.sort(key=lambda r: (r.get("rank", 999), -len(r.get("also_in", []))))
    return {"query": query, "domain": domain, "sources_used": names,
            "failed_sources": failed, "sort": sort,
            "n": len(merged), "results": merged}


def search_vocab(term, domain="general"):
    """Mirrors `search.py vocab`."""
    use_mesh = domain in lit.VOCAB_SOURCE
    try:
        entries = lit.vocab_mesh(term) if use_mesh else lit.vocab_openalex(term)
    except Exception:
        entries = lit.vocab_openalex(term)
        use_mesh = False
    return {"term": term,
            "vocabulary": "MeSH" if use_mesh else "OpenAlex concepts",
            "entries": entries}


def search_chain(doi, topic=None, depth=1, per_step=6, milestone=1000):
    """Mirrors `search.py chain`."""
    return lit.chain(doi, depth, per_step, milestone, topic)


# --------------------------------------------------------------------------
# triage
# --------------------------------------------------------------------------
def _normalise(ideas):
    out = []
    for i, r in enumerate(ideas):
        if isinstance(r, str):
            r = {"title": r}
        r = dict(r)
        r.setdefault("id", f"i{i + 1:02d}")
        out.append(r)
    return out


def triage_dedup(ideas, threshold=0.15, top=15):
    """Mirrors `triage.py dedup`."""
    ideas = _normalise(ideas)
    texts = [tri.idea_text(r) for r in ideas]
    vecs = tri.tfidf_vectors(texts)
    toks = [tri.tokens(t) for t in texts]

    scored = []
    for i, j in itertools.combinations(range(len(ideas)), 2):
        cos, jac = tri.cosine(vecs[i], vecs[j]), tri.jaccard(toks[i], toks[j])
        scored.append({"a": ideas[i]["id"], "b": ideas[j]["id"],
                       "score": round(0.7 * cos + 0.3 * jac, 3),
                       "cosine": round(cos, 3), "jaccard": round(jac, 3),
                       "a_text": texts[i][:400], "b_text": texts[j][:400],
                       "verdict": None})
    scored.sort(key=lambda p: -p["score"])

    pairs = [p for p in scored if p["score"] >= threshold]
    for p in scored[:top]:
        if p not in pairs and p["score"] > 0:
            p["below_threshold"] = True
            pairs.append(p)
    pairs.sort(key=lambda p: -p["score"])

    return {"n_ideas": len(ideas), "threshold": threshold,
            "score_range": [scored[-1]["score"] if scored else 0.0,
                            scored[0]["score"] if scored else 0.0],
            "n_candidate_pairs": len(pairs), "candidate_pairs": pairs}


def triage_pairs(ideas, anchors=None, criteria=None, shuffle_seed=0, batch_size=3):
    """Mirrors `triage.py pairs`, and enforces batch isolation.

    The two orderings of a pair exist to detect position bias.  If both land in
    the same LLM call the judge sees them together and the check is worthless,
    so a random shuffle is not enough - it collides by chance.  Instead every
    (x,y) ordering is placed in the first half of the schedule and every (y,x)
    ordering in the second, each half shuffled independently.  The two halves
    are then at least `n_pairs` apart, which is far wider than any batch.
    """
    ideas = _normalise(ideas)
    anchors = _normalise(anchors or [])
    for a in anchors:
        a["is_anchor"] = True
        a.setdefault("grade_contribution", "ungraded")

    field = ideas + anchors
    ids = [r["id"] for r in field]
    if len(set(ids)) != len(ids):
        raise ValueError("anchor ids collide with idea ids")

    anchor_ids = {a["id"] for a in anchors}
    pairs = [(x, y) for x, y in itertools.combinations(ids, 2)
             if not (x in anchor_ids and y in anchor_ids)]

    import random
    rng = random.Random(shuffle_seed)
    first = [{"left": x, "right": y} for x, y in pairs]
    second = [{"left": y, "right": x} for x, y in pairs]
    rng.shuffle(first)
    rng.shuffle(second)

    sched = []
    for n, m in enumerate(first + second, 1):
        sched.append({"match": n, "batch": (n - 1) // batch_size,
                      "left": m["left"], "right": m["right"],
                      "winner": None, "reason": None})

    # Assert the property rather than trusting the construction.
    seen = {}
    for m in sched:
        key = tuple(sorted((m["left"], m["right"])))
        if key in seen and seen[key] == m["batch"]:
            raise AssertionError(f"batch isolation broken for {key}")
        seen[key] = m["batch"]

    return {"n_ideas": len(ideas), "n_anchors": len(anchors),
            "n_matches": len(sched), "batch_size": batch_size,
            "n_batches": (len(sched) + batch_size - 1) // batch_size,
            "criteria": criteria or ["contribution", "novelty",
                                     "expected effectiveness", "clarity",
                                     "feasibility"],
            "ideas": {r["id"]: tri.idea_text(r)[:300] for r in field},
            "anchors": {a["id"]: {"grade_contribution": a.get("grade_contribution"),
                                  "grade_feasibility": a.get("grade_feasibility"),
                                  "text": tri.idea_text(a)[:300]} for a in anchors},
            "matches": sched}


def triage_elo(matches, ideas=None, anchors=None, k=32.0):
    """Mirrors `triage.py elo`, calibrating only on contribution grades."""
    played = [m for m in matches if m.get("winner")]
    if not played:
        raise ValueError("no matches have a 'winner' set")

    ids = sorted({m["left"] for m in played} | {m["right"] for m in played})
    rating = {i: 1200.0 for i in ids}
    record = {i: {"win": 0, "loss": 0, "tie": 0} for i in ids}

    for m in played:
        l, r, w = m["left"], m["right"], str(m["winner"]).strip()
        el = 1 / (1 + 10 ** ((rating[r] - rating[l]) / 400))
        if w == l:
            sl = 1.0; record[l]["win"] += 1; record[r]["loss"] += 1
        elif w == r:
            sl = 0.0; record[r]["win"] += 1; record[l]["loss"] += 1
        else:
            sl = 0.5; record[l]["tie"] += 1; record[r]["tie"] += 1
        rating[l] += k * (sl - el)
        rating[r] += k * ((1 - sl) - (1 - el))

    seen, flips = {}, []
    for m in played:
        key = tuple(sorted((m["left"], m["right"])))
        if key in seen and seen[key] != m["winner"]:
            flips.append({"pair": list(key), "verdicts": [seen[key], m["winner"]]})
        seen[key] = m["winner"]

    titles = {r["id"]: tri.idea_text(r)[:160] for r in _normalise(ideas or [])}
    grade = {}
    for a in _normalise(anchors or []):
        grade[a["id"]] = a.get("grade_contribution", "ungraded")
        titles.setdefault(a["id"], tri.idea_text(a)[:160])

    table = sorted(({"rank": 0, "id": i, "elo": round(rating[i], 1), **record[i],
                     "is_anchor": i in grade, "anchor_grade": grade.get(i),
                     "text": titles.get(i, "")} for i in ids),
                   key=lambda r: -r["elo"])
    for n, row in enumerate(table, 1):
        row["rank"] = n

    out = {"n_matches_played": len(played), "k_factor": k,
           "order_flip_disagreements": flips,
           "order_flip_rate": round(len(flips) / max(len(seen), 1), 3),
           "ranking": table}

    if grade:
        by_grade = defaultdict(list)
        for r in table:
            if r["is_anchor"]:
                by_grade[r["anchor_grade"]].append(r["elo"])
        bands = {g: {"mean_elo": round(sum(v) / len(v), 1), "n": len(v)}
                 for g, v in sorted(by_grade.items())}
        strong = bands.get("strong", {}).get("mean_elo")
        weak = bands.get("weak", {}).get("mean_elo")
        for r in table:
            if r["is_anchor"]:
                continue
            if strong is not None and r["elo"] >= strong:
                r["calibration"] = "at or above the strong anchors"
            elif weak is not None and r["elo"] <= weak:
                r["calibration"] = "at or below the weak anchors"
            else:
                r["calibration"] = "between the anchor bands"
        out["anchor_bands"] = bands
    return out
