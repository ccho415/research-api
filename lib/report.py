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


def _identify(cur, cite):
    """Find the cached paper(s) a citation points at, by identifier only.

    Title matching is deliberately not attempted. A near-miss on a title
    attaches the citation to a different paper with a similar name, and a wrong
    citation is worse than a missing one because it reads as verified.
    """
    found = {}
    for col, sql in (("doi", "SELECT id, title, year, venue, doi, pmid FROM paper "
                             "WHERE lower(doi) = lower(%s) LIMIT 1"),
                     ("pmid", "SELECT id, title, year, venue, doi, pmid FROM paper "
                              "WHERE pmid = %s LIMIT 1")):
        v = str(cite.get(col) or "").strip()
        if v:
            cur.execute(sql, (v,))
            row = cur.fetchone()
            if row:
                found[col] = dict(row)
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


def verify_citations(citations):
    """Split citations into the ones that survive and the ones that do not.

    Three ways to fail, and each is reported with its reason rather than being
    silently dropped - a shorter reference list with no explanation looks like
    the model was concise.
    """
    kept, dropped = [], []
    with connect() as conn, conn.cursor() as cur:
        for c in citations or []:
            if not isinstance(c, dict):
                continue
            found = _identify(cur, c)

            if not found:
                dropped.append({
                    "cited": c,
                    "why": "no paper with this DOI or PMID is in the cache, so "
                           "no search ever returned it. Citing it would send a "
                           "reader to something that may not exist."})
                continue

            # Both identifiers present and pointing at different papers: at
            # least one is wrong and nothing here can tell which.
            if len(found) == 2 and found["doi"]["id"] != found["pmid"]["id"]:
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
                "paper_id": str(row["id"]),
                "title": row["title"], "year": row["year"],
                "venue": row["venue"], "doi": row["doi"], "pmid": row["pmid"],
                "links": _links(row),
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

        # The citable pool: every paper an actual search returned for this
        # project. The writer cites from this and from nothing else.
        #
        # Reached through search_hit rather than by listing the paper table,
        # because "in the cache" and "a search for this project returned it"
        # are different sets, and only the second one can honestly be cited
        # in this report.
        cur.execute(
            "SELECT DISTINCT p.id, p.title, p.year, p.venue, p.doi, p.pmid,"
            "       p.citations FROM paper p "
            "JOIN search_hit h ON h.paper_id = p.id "
            "JOIN search_query q ON q.id = h.search_query_id "
            "JOIN run ru ON ru.id = q.run_id "
            "WHERE ru.project_id = %s "
            "ORDER BY p.citations DESC NULLS LAST LIMIT 60", (d["project_id"],))
        pool = []
        for p in cur.fetchall():
            row = dict(p)
            row["id"] = str(row["id"])
            row["links"] = _links(row)
            pool.append(row)

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


def save_report(idea_id, sections, citations=None, run_id=None, model=None,
                tier=None, rank=None):
    """Store one report, refusing the ones that read complete and are not."""
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

    kept, dropped = verify_citations(citations)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO report (idea_id, run_id, sections, citations,"
                "                    dropped, tier, rank, model) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id, created_at",
                (idea_id, run_id,
                 psycopg.types.json.Jsonb({k: str(sections[k]).strip()
                                           for k in SECTIONS}),
                 psycopg.types.json.Jsonb(kept),
                 psycopg.types.json.Jsonb(dropped) if dropped else None,
                 tier, rank, model))
            row = cur.fetchone()
        conn.commit()

    return {"report_id": str(row["id"]), "idea_id": str(idea_id),
            "n_citations": len(kept), "n_dropped": len(dropped),
            "dropped": dropped or None,
            "cross_validated": len([c for c in kept if c["cross_validated"]]),
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
