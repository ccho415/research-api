"""The final report: eight sections, and every citation checked back to a search.

Two rules from the PRD shape this file, and they pull in opposite directions.

The report has to be **persuasive** - the narrative structure it asks for
(scale, state of the art, gap, proposal, scenario, comparison) is borrowed from
deep-research writing because that is what makes a reader see why a direction
matters. And the report has to be **honest**, which is the harder half: a
paragraph that reads beautifully and cites nothing real is worse than a dull
one, because the polish is what gets it believed.

So the persuasion is left to the prompt and the honesty is enforced here:

**Every citation is matched back to a paper an actual search returned.** Not
checked for plausibility - matched. A DOI that resolves to nothing in the cache
is removed from the citations and recorded in `dropped`, where the reader can
see that the model tried to cite something that does not exist.

**A DOI and a PMID that disagree are both refused.** When a citation carries
both identifiers and they resolve to two different papers, at least one is
wrong and there is no way to tell which. Citing either would send somebody to
the wrong paper while looking verified, so neither is used.

**All eight sections or it is not a report.** A report missing its unresolved-
objections section does not read as incomplete; it reads as a direction with no
unresolved objections. That is the failure this refusal exists for.
"""

import psycopg

from db import connect

SECTIONS = ("title", "background", "method", "references",
            "novelty", "feasibility", "objections", "prework")

# What each section is for, sent to the writer so the keys are not guessed at.
SECTION_BRIEF = {
    "title": "the answerable question in full - population, exposure or "
             "predictor, outcome, design. Never truncated, never a code.",
    "background": "why this matters, in the order scale, state of the art, "
                  "gap, proposal, scenario, comparison. Every claim cited.",
    "method": "three named components, each with why not the default choice.",
    "references": "every paper with journal, year, DOI and a clickable link.",
    "novelty": "which angles were searched, what the closest papers did, how "
               "this differs, and what was NOT searchable.",
    "feasibility": "what data is needed, what exists, what is missing, where "
                   "to get it, how long, and whether the scale is sufficient.",
    "objections": "each objection still unresolved after the debate, and how "
                  "badly it threatens the study.",
    "prework": "the cheapest checks that would kill this before you invest: "
               "data inventory, power, approvals, a pilot, and the "
               "abandonment criterion agreed in advance.",
}


def citable_set(cur, idea_id, project_id):
    """Every paper an actual search returned for this idea, indexed by identifier.

    Two sources, because the searches in this system write to two different
    places and neither one alone is the answer:

    `search_hit` holds what W2's literature layer found, joined back through the
    run that found it.

    The latest adversarial `novelty_check` holds what W7's fourteen rounds
    returned - and those never reach the `paper` table at all, because
    `ops.search_query` returns results without persisting them. Leaving that
    source out was a real defect: W7 verified forty papers for this idea and
    none of them were citable, so the report would have had nothing to cite and
    every citation it did make would have been rejected as invented.

    **This is the same set the writer is shown and the same set a citation is
    checked against.** Those two being different sets is how a model gets
    punished for citing exactly what it was given.
    """
    rows, seen = [], set()

    def take(p, origin):
        if not isinstance(p, dict):
            return
        title = str(p.get("title") or "").strip()
        doi = str(p.get("doi") or "").strip()
        pmid = str(p.get("pmid") or "").strip()
        key = (doi.lower() or pmid or title.lower())[:200]
        if not title or not key or key in seen:
            return
        seen.add(key)
        row = {"title": title, "year": p.get("year"),
               "venue": p.get("venue") or p.get("journal"),
               "doi": doi or None, "pmid": pmid or None,
               "citations": p.get("citations"), "found_by": origin}
        row["links"] = _links(row)
        rows.append(row)

    cur.execute(
        "SELECT rounds, closest_papers FROM novelty_check "
        "WHERE idea_id = %s AND method = 'adversarial' "
        "ORDER BY checked_at DESC LIMIT 1", (idea_id,))
    nov = cur.fetchone()
    if nov:
        for p in nov["closest_papers"] or []:
            take(p, "novelty check")
        for r in ((nov["rounds"] or {}).get("rounds") or []):
            for p in r.get("papers") or []:
                take(p, "novelty check")

    cur.execute(
        "SELECT DISTINCT p.title, p.year, p.venue, p.doi, p.pmid, p.citations "
        "FROM paper p "
        "JOIN search_hit h ON h.paper_id = p.id "
        "JOIN search_query q ON q.id = h.search_query_id "
        "JOIN run ru ON ru.id = q.run_id "
        "WHERE ru.project_id = %s "
        "ORDER BY p.citations DESC NULLS LAST LIMIT 60", (project_id,))
    for p in cur.fetchall():
        take(dict(p), "literature search")

    by_doi = {r["doi"].lower(): r for r in rows if r["doi"]}
    by_pmid = {r["pmid"]: r for r in rows if r["pmid"]}
    return rows, by_doi, by_pmid


def _identify(cite, by_doi, by_pmid):
    """Which entries a citation points at, by identifier only.

    Title matching is deliberately not attempted. A near-miss on a title
    attaches the citation to a different paper with a similar name, and a wrong
    citation is worse than a missing one because it reads as verified.
    """
    found = {}
    doi = str(cite.get("doi") or "").strip().lower()
    pmid = str(cite.get("pmid") or "").strip()
    if doi and doi in by_doi:
        found["doi"] = by_doi[doi]
    if pmid and pmid in by_pmid:
        found["pmid"] = by_pmid[pmid]
    return found


def _links(row):
    """Clickable links, built only from identifiers that exist."""
    out = {}
    if row.get("doi"):
        out["doi"] = f"https://doi.org/{row['doi']}"
    if row.get("pmid"):
        out["pubmed"] = f"https://pubmed.ncbi.nlm.nih.gov/{row['pmid']}/"
        out["europepmc"] = ("https://europepmc.org/article/MED/"
                            f"{row['pmid']}")
    return out


def verify_citations(citations, idea_id, project_id):
    """Split citations into the ones that survive and the ones that do not.

    Three ways to fail, and each is reported with its reason rather than being
    silently dropped - a shorter reference list with no explanation looks like
    the model was concise.
    """
    kept, dropped = [], []
    with connect() as conn, conn.cursor() as cur:
        _, by_doi, by_pmid = citable_set(cur, idea_id, project_id)

        for c in citations or []:
            if not isinstance(c, dict):
                continue
            found = _identify(c, by_doi, by_pmid)

            if not found:
                dropped.append({
                    "cited": c,
                    "why": "no search for this direction returned a paper with "
                           "this DOI or PMID. Citing it would send a reader to "
                           "something that may not exist."})
                continue

            # Both identifiers present and pointing at different papers: at
            # least one is wrong and nothing here can tell which.
            if len(found) == 2 and found["doi"]["title"] != found["pmid"]["title"]:
                dropped.append({
                    "cited": c,
                    "why": "the DOI and the PMID resolve to two different "
                           "papers. One of them is wrong and there is no way "
                           "to tell which, so neither is cited.",
                    "doi_resolves_to": found["doi"]["title"],
                    "pmid_resolves_to": found["pmid"]["title"]})
                continue

            row = found.get("doi") or found.get("pmid")
            kept.append({
                "title": row["title"], "year": row["year"],
                "venue": row["venue"], "doi": row["doi"], "pmid": row["pmid"],
                "links": row["links"], "found_by": row["found_by"],
                "cross_validated": len(found) == 2,
                "used_for": c.get("used_for") or c.get("claim") or None})

    return kept, dropped


def report_inputs(idea_id):
    """Everything the writer needs, assembled from five tables in one call.

    Assembled here rather than left to the workflow because a report written
    from four of the five would still produce eight sections. The missing one
    would just be written from nothing, and nothing in the output would say so.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT i.id, i.project_id, i.code, i.title, i.statement, i.axis,"
            "       i.track, i.origin, i.source_note, i.required_variables,"
            "       i.method_sketch, i.grounding, i.why_matters,"
            "       i.how_could_fail, i.generation, i.parent_idea_id "
            "FROM idea i WHERE i.id = %s", (idea_id,))
        idea = cur.fetchone()
        if not idea:
            raise ValueError(f"no idea {idea_id}")
        d = dict(idea)
        d["id"] = str(d["id"])
        d["project_id"] = str(d["project_id"])
        d["parent_idea_id"] = (None if d["parent_idea_id"] is None
                               else str(d["parent_idea_id"]))

        cur.execute(
            "SELECT verdict, rounds, closest_papers, coverage_limits, facets,"
            "       query_angles, checked_at FROM novelty_check "
            "WHERE idea_id = %s AND method = 'adversarial' "
            "ORDER BY checked_at DESC LIMIT 1", (idea_id,))
        nov = cur.fetchone()

        cur.execute(
            "SELECT tier, missing, route_to_tier_a, design, power_note "
            "FROM feasibility WHERE idea_id = %s "
            "ORDER BY assessed_at DESC LIMIT 1", (idea_id,))
        feas = cur.fetchone()

        cur.execute(
            "SELECT r.rank, r.elo, r.calibration_band FROM ranking r "
            "JOIN tournament t ON t.id = r.tournament_id "
            "WHERE r.idea_id = %s AND t.project_id = %s "
            "ORDER BY t.created_at DESC LIMIT 1", (idea_id, d["project_id"]))
        rank = cur.fetchone()

        # Only the objections still standing. The resolved ones were answered
        # and belong in the transcript, not in a section about what threatens
        # the study.
        cur.execute(
            "SELECT o.statement, o.severity, o.axis, o.citation_support,"
            "       o.rebuttal, o.rebuttal_score, o.cited, dr.round_no "
            "FROM objection o JOIN debate_round dr ON dr.id = o.debate_round_id "
            "WHERE dr.idea_id = %s AND o.status = 'unresolved' "
            "ORDER BY dr.round_no", (idea_id,))
        open_objections = [dict(o) for o in cur.fetchall()]

        cur.execute(
            "SELECT count(*) AS n, max(round_no) AS rounds,"
            "       bool_or(terminated) AS ended,"
            "       max(termination_reason) AS why "
            "FROM debate_round WHERE idea_id = %s", (idea_id,))
        debate = dict(cur.fetchone())

        # The citable pool - built by the same function that later checks the
        # citations, so what the writer is shown and what survives verification
        # cannot drift apart.
        pool, _, _ = citable_set(cur, idea_id, d["project_id"])

    missing = []
    if not nov:
        missing.append("no adversarial novelty check - section 5 would be "
                       "written from nothing")
    if not feas:
        missing.append("no feasibility grading - section 6 would be written "
                       "from nothing")
    if not debate.get("n"):
        missing.append("no debate has been run - section 7 cannot list what "
                       "survived an argument that never happened")
    if not pool:
        missing.append("no search ever returned a paper for this direction, so "
                       "there is nothing this report may cite. Sections 2 and 4 "
                       "cannot be written - run W2 or W7 first")

    return {
        "idea": d,
        "novelty": dict(nov) if nov else None,
        "feasibility": dict(feas) if feas else None,
        "rank": dict(rank) if rank else None,
        "debate": {"n_rounds": debate.get("n") or 0,
                   "ended": debate.get("ended"),
                   "termination_reason": debate.get("why")},
        "open_objections": open_objections,
        "n_open_objections": len(open_objections),
        "citable_papers": pool,
        "n_citable": len(pool),
        "sections_required": list(SECTIONS),
        "section_brief": SECTION_BRIEF,
        # Travels with the inputs so the caveat can be written into the report
        # rather than being noticed by whoever reads it six months later.
        "missing_inputs": missing or None,
    }


def build_acquisition(cur, idea_id):
    """What still has to be obtained, copied from the grading rather than retold.

    The report already has a feasibility section, and the model writes it. This
    is the same content taken straight from `feasibility`, and both are kept
    because they fail differently: prose omits an item and reads fine without
    it, a copied list cannot omit anything because nothing restates it.

    Copied and not referenced, for the reason `tier` and `rank` are copied onto
    the report: the grading can be re-run, and a report that silently starts
    describing a later grading is describing something that was never true at
    the moment it was written.
    """
    cur.execute(
        "SELECT tier, missing, route_to_tier_a, assessed_at "
        "FROM feasibility WHERE idea_id = %s "
        "ORDER BY assessed_at DESC LIMIT 1", (idea_id,))
    row = cur.fetchone()
    if not row:
        return None
    missing = row["missing"]
    if isinstance(missing, str):
        missing = [missing]
    return {
        "tier": row["tier"],
        "missing": list(missing or []),
        "route": row["route_to_tier_a"],
        "assessed_at": row["assessed_at"].isoformat(),
        "note": "這一份是報告產出當下從分級抄寫下來的，不經模型。"
                "模型寫在可行性那節的散文會漏，這一份不會——"
                "兩份不一致時以這一份為準。",
    }


def build_caveats(cur, idea_id, project_id):
    """What this run did not cover, measured rather than recalled.

    Computed here and never accepted from the caller, for the same reason the
    debate's termination is: the caller is holding a model's account of its own
    limits, and that is the one question the model should not be answering.

    Three of the four are about the run and one is about this direction. That
    mixture is correct - a reader deciding how much to believe a report needs
    to know both that the debate stopped after one round and that a third of
    the literature was never read.
    """
    out = {}

    cur.execute(
        "SELECT n_papers, n_with_fulltext, n_gap_sentences FROM harvest "
        "WHERE project_id = %s AND status = 'done' "
        "ORDER BY started_at DESC LIMIT 1", (project_id,))
    h = cur.fetchone()
    if h:
        n, full = int(h["n_papers"] or 0), int(h["n_with_fulltext"] or 0)
        out["fulltext"] = {
            "n_with_fulltext": full, "n_papers": n,
            "n_gap_sentences": int(h["n_gap_sentences"] or 0),
            "note": f"全文只拿到 {n} 篇裡的 {full} 篇，其餘只有摘要。"
                    "缺口句只存在 Discussion，摘要沒有——"
                    f"所以那 {n - full} 篇對想點子那一步是靜音的。"}

    # The denominator is the graded pool, not every idea ever generated: that
    # is the set novelty verification could have been spent on. Naming both
    # numbers rather than a percentage, because a bare percentage hides which
    # of the two moved.
    cur.execute(
        "SELECT count(*) AS graded,"
        "       count(*) FILTER (WHERE nc.idea_id IS NULL) AS unverified "
        "FROM (SELECT DISTINCT f2.idea_id FROM feasibility f2"
        "        JOIN idea i2 ON i2.id = f2.idea_id"
        "       WHERE i2.project_id = %s) f "
        "LEFT JOIN (SELECT DISTINCT idea_id FROM novelty_check"
        "            WHERE method = 'adversarial') nc"
        "       ON nc.idea_id = f.idea_id", (project_id,))
    nv = cur.fetchone()
    if nv and int(nv["graded"] or 0):
        out["novelty_unverified"] = {
            "n_unverified": int(nv["unverified"] or 0),
            "n_graded": int(nv["graded"] or 0),
            "note": "未驗證不等於新穎。這些方向沒有跑過對抗式新穎性檢查，"
                    "也沒有參加排序。"}

    # Named, not counted. A report quietly not written for a direction looks
    # exactly like a direction that never existed, and that is the difference
    # this entry is here to make visible.
    cur.execute(
        "SELECT i.code, i.title FROM idea i WHERE i.project_id = %s AND ("
        "  SELECT n.verdict FROM novelty_check n WHERE n.idea_id = i.id"
        "    AND n.method = 'adversarial'"
        "  ORDER BY n.checked_at DESC LIMIT 1) = 'scooped' "
        "ORDER BY i.code", (project_id,))
    scooped = [{"code": r["code"], "title": r["title"]} for r in cur.fetchall()]
    out["excluded_as_already_done"] = {
        "n": len(scooped), "directions": scooped,
        "note": "這些方向被判定已經有人做過，所以沒有寫報告。"
                "安靜地少寫一份，在輸出上跟「這個方向不存在」長得一模一樣，"
                "所以在這裡點名。"}

    cur.execute(
        "SELECT round_no, drift_from_original, n_objections_open,"
        "       terminated, termination_reason FROM debate_round "
        "WHERE idea_id = %s ORDER BY round_no DESC LIMIT 1", (idea_id,))
    d = cur.fetchone()
    if d:
        out["debate"] = {
            "n_rounds": int(d["round_no"] or 0),
            "drift_from_original": (None if d["drift_from_original"] is None
                                    else float(d["drift_from_original"])),
            "n_objections_open": int(d["n_objections_open"] or 0),
            "terminated": bool(d["terminated"]),
            "termination_reason": d["termination_reason"],
            "note": "終止是系統從紀錄算出來的，不是模型自稱打完了——"
                    "輪數少不代表沒認真跑。"}
    else:
        out["debate"] = {"n_rounds": 0, "note": "這個方向沒有經過辯論。"}

    return out


def save_report(idea_id, sections, citations=None, run_id=None, model=None,
                tier=None, rank=None):
    """Store one report, refusing the ones that read complete and are not.

    `caveats` and `acquisition` are measured here rather than taken as
    arguments. They are the two things a writer is worst placed to supply -
    what it left out, and what it still needs - and W9's own gate already
    computed them into an n8n execution output that nothing persisted. A
    report outlives an execution log, so the report carries them.
    """
    if not isinstance(sections, dict):
        raise ValueError("sections must be an object keyed by section name")

    blank = [k for k in SECTIONS
             if not str(sections.get(k) or "").strip()]
    if blank:
        raise ValueError(
            "these sections are missing or empty: " + ", ".join(blank) +
            ". A report short of a section does not read as incomplete - it "
            "reads as a direction that had nothing to say there, which is a "
            "different and false claim.")

    # Prose, not bullet fragments. The PRD asks for paragraphs because the
    # point of this document is to be read by a person six months from now.
    thin = [k for k in SECTIONS if len(str(sections[k]).strip()) < 120]
    if thin:
        raise ValueError(
            "these sections are too short to be the paragraphs this report is "
            "for: " + ", ".join(thin))

    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT project_id FROM idea WHERE id = %s", (idea_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"no idea {idea_id}")
        project_id = str(row["project_id"])

    kept, dropped = verify_citations(citations, idea_id, project_id)

    with connect() as conn:
        with conn.cursor() as cur:
            acquisition = build_acquisition(cur, idea_id)
            caveats = build_caveats(cur, idea_id, project_id)
            # Copied for the reason `tier` and `rank` are copied: the novelty
            # section was written from one particular check, and that check can
            # be re-run. A referenced verdict would quietly start disagreeing
            # with the prose beside it, and nothing would raise.
            cur.execute(
                "SELECT verdict FROM novelty_check WHERE idea_id = %s "
                "AND method = 'adversarial' ORDER BY checked_at DESC LIMIT 1",
                (idea_id,))
            nv = cur.fetchone()
            novelty_verdict = nv["verdict"] if nv else None
            cur.execute(
                "INSERT INTO report (idea_id, run_id, sections, citations,"
                "                    dropped, tier, rank, model,"
                "                    caveats, acquisition, novelty_verdict) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "RETURNING id, created_at",
                (idea_id, run_id,
                 psycopg.types.json.Jsonb({k: str(sections[k]).strip()
                                           for k in SECTIONS}),
                 psycopg.types.json.Jsonb(kept),
                 psycopg.types.json.Jsonb(dropped) if dropped else None,
                 tier, rank, model,
                 psycopg.types.json.Jsonb(caveats) if caveats else None,
                 psycopg.types.json.Jsonb(acquisition) if acquisition else None,
                 novelty_verdict))
            row = cur.fetchone()
        conn.commit()

    # Returned as well as stored so the workflow's own log shows what was
    # recorded. A caveat block that only exists in the database is one nobody
    # notices went missing.
    return {"report_id": str(row["id"]), "idea_id": str(idea_id),
            "n_citations": len(kept), "n_dropped": len(dropped),
            "dropped": dropped or None,
            "cross_validated": len([c for c in kept if c["cross_validated"]]),
            "caveats": caveats, "acquisition": acquisition,
            "novelty_verdict": novelty_verdict,
            "created_at": row["created_at"].isoformat()}


def get_report(idea_id=None, report_id=None):
    where, args = [], []
    if report_id:
        where.append("r.id = %s")
        args.append(report_id)
    if idea_id:
        where.append("r.idea_id = %s")
        args.append(idea_id)
    if not where:
        raise ValueError("need idea_id or report_id")

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT r.*, i.code, i.title AS idea_title FROM report r "
            "JOIN idea i ON i.id = r.idea_id "
            "WHERE " + " AND ".join(where) + " "
            "ORDER BY r.created_at DESC LIMIT 1", args)
        row = cur.fetchone()
    if not row:
        return {"idea_id": idea_id, "report": None}
    d = dict(row)
    d["id"] = str(d["id"])
    d["idea_id"] = str(d["idea_id"])
    d["run_id"] = None if d["run_id"] is None else str(d["run_id"])
    d["created_at"] = d["created_at"].isoformat()
    return {"report": d}


def list_reports(project_id):
    """Every report for a project, in tournament order.

    Ordered by rank because the PRD is explicit that the report covers all A
    and B directions, not just the winner, and that it is presented in
    contribution order.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT ON (r.idea_id) r.id, r.idea_id, r.tier, r.rank,"
            "       r.citations, r.dropped, r.created_at, i.code, i.title "
            "FROM report r JOIN idea i ON i.id = r.idea_id "
            "WHERE i.project_id = %s "
            "ORDER BY r.idea_id, r.created_at DESC", (project_id,))
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            d["id"] = str(d["id"])
            d["idea_id"] = str(d["idea_id"])
            d["created_at"] = d["created_at"].isoformat()
            d["n_citations"] = len(d.pop("citations") or [])
            d["n_dropped"] = len(d.pop("dropped") or [])
            rows.append(d)

    rows.sort(key=lambda d: (d["rank"] is None, d["rank"] or 0))
    return {"project_id": project_id, "n": len(rows), "reports": rows}
