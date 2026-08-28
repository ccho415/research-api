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
                 year_from=None, year_to=None, sort="relevance", concepts=None):
    """Mirrors `search.py query`.

    With `concepts`, each source is sent the crossing rendered in its own
    dialect rather than one string for all of them - see `render_query`.
    `query` then stands only for what the search is called in the record.
    """
    names = sources or lit.ROUTING.get(domain, lit.ROUTING["general"])
    batches, failed, answered, sent = [], [], [], {}
    for n in names:
        fn = lit.SOURCES.get(n)
        if not fn:
            failed.append({"source": n, "error": "unknown source"})
            continue
        q = lit.render_query(concepts, n) if concepts else query
        sent[n] = q
        if not q:
            failed.append({"source": n, "error": "no renderable query for this source"})
            continue
        try:
            hits = fn(q, limit, year_from, year_to)
            batches.append(hits)
            answered.append(n)
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
            # What gets stored in `search_query.sources`: which sources were
            # tried, which came back, and why the rest did not.  "used" and
            # "answered" are different facts, and PubMed makes them differ on
            # every clinical search from this deployment.
            "attempt": {"attempted": names, "answered": answered,
                        "failed": failed, "sent": sent},
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


def search_expand(concepts, domain="general", per_concept=10):
    """Resolve each concept term to controlled-vocabulary descriptors.

    A real research topic is two or more concepts crossed - an exposure and an
    outcome, or a disease and an aspect - not one term with narrower siblings.
    Each is expanded on its own, because MeSH matches a whole label and the two
    joined together match nothing.

    Never raises for a concept it cannot resolve: an unexpandable term is
    carried through as itself with `expanded: false`, and the caller is expected
    to show that prominently.  A run that searched one raw string has roughly a
    tenth of the coverage of one that expanded properly, and it must not look
    the same.
    """
    use_mesh = domain in lit.VOCAB_SOURCE
    out, degraded = [], False
    for term in concepts:
        term = (term or "").strip()
        if not term:
            continue
        entries, vocab, err = [], None, None
        for name, fn in ([("MeSH", lambda: lit.vocab_mesh(term, limit=per_concept))]
                         if use_mesh else []) + [("OpenAlex", lambda: lit.vocab_openalex(term))]:
            try:
                entries = fn() or []
            except Exception as e:
                err = f"{name}: {type(e).__name__}: {e}"
                continue
            if entries:
                vocab = name
                break
        if not entries:
            degraded = True
            out.append({"input": term, "expanded": False, "vocabulary": None,
                        "error": err, "descriptor": None, "terms": [term],
                        "alternatives": []})
            continue
        head = entries[0]
        alts = [{"descriptor": e.get("descriptor"), "unique_id": e.get("unique_id"),
                 "relation": "sibling"} for e in entries[1:per_concept]]

        # A precise concept has exactly one descriptor, so label matching alone
        # gives no alternatives and the crossing collapses to a single query.
        # The hierarchy is where the other angles are.
        if len(alts) < per_concept - 1 and head.get("unique_id"):
            have = {a["unique_id"] for a in alts}
            try:
                for r in lit.mesh_relatives(head["unique_id"]):
                    if r["unique_id"] not in have and len(alts) < per_concept - 1:
                        have.add(r["unique_id"])
                        alts.append(r)
            except Exception as e:
                # Losing the hierarchy costs breadth, not correctness: the
                # exact crossing still runs.  Say so rather than failing.
                lit._warn(f"MeSH relatives for {head['unique_id']} unavailable: "
                          f"{type(e).__name__}: {e}")

        out.append({
            "input": term, "expanded": True, "vocabulary": vocab,
            "descriptor": head.get("descriptor"),
            "unique_id": head.get("unique_id"),
            "definition": (head.get("definition") or "")[:400],
            "terms": [t for t in (head.get("entry_terms") or []) if t][:8],
            "alternatives": alts,
        })
    return {"domain": domain, "concepts": out, "degraded": degraded,
            "unexpanded": [c["input"] for c in out if not c["expanded"]]}


def plan_queries(expansion, max_queries=10):
    """Turn an expansion into the set of searches to run.

    One concept fans out into its narrower descriptors.  Two or more are
    crossed, best against best first, because the crossing is the question -
    "endocrine disruptors" alone and "lung adenocarcinoma" alone are both
    enormous and neither is what was asked.
    """
    cs = expansion.get("concepts") or []
    if not cs:
        return []

    def variants(c):
        v = [{"descriptor": c.get("descriptor"), "terms": c.get("terms") or [],
              "unique_id": c.get("unique_id")}]
        for alt in c.get("alternatives") or []:
            v.append({"descriptor": alt.get("descriptor"), "terms": [],
                      "unique_id": alt.get("unique_id")})
        return [x for x in v if x["descriptor"] or x["terms"]]

    if len(cs) == 1:
        return [{"concepts": [v], "label": v["descriptor"] or cs[0]["input"]}
                for v in variants(cs[0])[:max_queries]]

    # Enough per side to fill the budget once crossed, and no more: the pool is
    # ranked, so a wider side only adds worse descriptors.
    per_side = max(2, int(round(max_queries ** (1.0 / len(cs)))) + 1)
    sides = [variants(c)[:per_side] for c in cs]

    plans = []
    for combo in itertools.product(*[range(len(s)) for s in sides]):
        picked = [sides[i][j] for i, j in enumerate(combo)]
        plans.append((sum(combo), picked))
    plans.sort(key=lambda p: p[0])
    return [{"concepts": p, "label": " x ".join(
        c["descriptor"] or "?" for c in p)} for _, p in plans[:max_queries]]


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


# The lexicographic order, in order. Four, not five, and ranked rather than
# listed: a flat list of criteria reads as a scorecard, and a scorecard gets
# averaged, which is the one thing the ordering exists to prevent.
#
# "clarity" used to be in here and had to go. A weak direction that is written
# well beats a strong one that is written roughly on any criterion a judge
# reads as a checklist item, and how a sentence is phrased is not a property of
# the research.
CRITERIA = ["contribution", "novelty", "conclusiveness", "feasibility"]


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
            "criteria": criteria or CRITERIA,
            "competitors": {r["id"]: tri.idea_text(r)[:300] for r in field},
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

    # Only a pair judged in both orderings can disagree with itself, so only
    # those go in the denominator. Counting every distinct pair understates the
    # rate whenever the schedule is partial, and the gate this feeds - five to
    # twenty percent - reads an understated rate as a well-behaved judge.
    seen, flips, rejudged = {}, [], set()
    for m in played:
        key = tuple(sorted((m["left"], m["right"])))
        if key in seen:
            rejudged.add(key)
            if seen[key] != m["winner"]:
                flips.append({"pair": list(key),
                              "verdicts": [seen[key], m["winner"]]})
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
           "n_pairs_judged_both_ways": len(rejudged),
           "order_flip_rate": (round(len(flips) / len(rejudged), 3)
                               if rejudged else None),
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
        # "between the bands" is a claim about both ends, so it needs both ends.
        # With only one grade in play it used to be said anyway, which reads as
        # a calibration and is not one - the same failure as a novelty verdict
        # asserting what the query never established.
        both = strong is not None and weak is not None
        for r in table:
            if r["is_anchor"]:
                continue
            if strong is not None and r["elo"] >= strong:
                r["calibration"] = "at or above the strong anchors"
            elif weak is not None and r["elo"] <= weak:
                r["calibration"] = "at or below the weak anchors"
            elif both:
                r["calibration"] = "between the anchor bands"
            else:
                r["calibration"] = None
                r["calibration_note"] = (
                    "not calibrated: the anchors that played carry only "
                    + ", ".join(sorted(bands)) + " grades")
        out["anchor_bands"] = bands
    return out
