"""The report as a file you can take away.

Download was never a nice-to-have here: a report that can only be read inside
the tool it was made in is a report nobody circulates, and circulating it is
the point. So this renders one to Markdown and to PDF.

**The caveats and the acquisition list are part of the document, not part of
the screen.** They are the two things most likely to be dropped when a report
is copied somewhere else, and they are exactly the two that decide how much of
it to believe. A PDF of the eight sections without "what this does not cover"
reads as a finished piece of work rather than a partial one.

PDF generation is deliberately optional at import time. reportlab is one more
dependency on a deployment whose last build broke on an apt fetch, so if it is
missing the Markdown path still works and the PDF path says so plainly instead
of taking the module down with it.
"""

import io

SECTION_TITLES = [
    ("title", "題目與問句"),
    ("background", "背景與缺口"),
    ("method", "方法草圖"),
    ("references", "引用文獻"),
    ("novelty", "新穎性判決"),
    ("feasibility", "可行性與取得清單"),
    ("objections", "未解決的反對"),
    ("prework", "動手前要先讀什麼"),
]

VERDICT_MEANING = {
    "no_prior_art": "找不到前案",
    "adjacent": "沒人做過，但有鄰近文獻——這是健康的結果",
    "incremental": "有人做過很接近的",
    "scooped": "已經被做過了",
}


def _blocks(rep):
    """The document as an ordered list of (kind, payload) pairs.

    Built once and rendered twice. Two renderers walking the same list cannot
    disagree about what the document contains, which is the failure that
    matters: a PDF quietly missing the caveats that the Markdown has.
    """
    out = []
    title = (rep.get("sections") or {}).get("title") or rep.get("idea_title") or ""
    out.append(("h1", title))

    meta = [f"報告 {str(rep.get('id') or '')[:8]}",
            (rep.get("created_at") or "")[:10]]
    verdict = rep.get("novelty_verdict")
    if verdict:
        meta.append(f"新穎性 {verdict}")
    if rep.get("tier"):
        meta.append(f"可行性 {rep['tier']} 級")
    n_cit = len(rep.get("citations") or [])
    n_drop = len(rep.get("dropped") or [])
    meta.append(f"引用 {n_cit} 筆 · 捏造 {n_drop} 筆")
    out.append(("meta", " · ".join(m for m in meta if m)))
    if verdict and verdict in VERDICT_MEANING:
        out.append(("note", f"{verdict}＝{VERDICT_MEANING[verdict]}。"))

    sections = rep.get("sections") or {}
    for i, (key, label) in enumerate(SECTION_TITLES, start=1):
        body = (sections.get(key) or "").strip()
        if not body:
            continue
        out.append(("h2", f"{i:02d} {label}"))
        out.append(("p", body))

        if key == "feasibility":
            acq = rep.get("acquisition")
            if acq:
                out.append(("h3", "要去弄什麼資料（直接從資料庫產生，不經模型）"))
                missing = acq.get("missing") or []
                if missing:
                    out.append(("ul", [str(m) for m in missing]))
                if acq.get("route"):
                    out.append(("p", "去路：" + str(acq["route"])))
                out.append(("note", acq.get("note") or ""))

    cav = rep.get("caveats")
    if cav:
        out.append(("h2", "這份沒有涵蓋什麼"))
        items = []
        for k in ("fulltext", "novelty_unverified",
                  "excluded_as_already_done", "debate"):
            v = cav.get(k)
            if not v:
                continue
            note = (v.get("note") or "").strip()
            if k == "excluded_as_already_done" and v.get("directions"):
                named = "、".join(d.get("title") or str(d.get("code"))
                                  for d in v["directions"])
                note = f"{note}（{named}）"
            if note:
                items.append(note)
        if items:
            out.append(("ul", items))
    return out


def to_markdown(rep):
    lines = []
    for kind, payload in _blocks(rep):
        if kind == "h1":
            lines += [f"# {payload}", ""]
        elif kind == "h2":
            lines += ["", f"## {payload}", ""]
        elif kind == "h3":
            lines += ["", f"### {payload}", ""]
        elif kind == "meta":
            lines += [f"*{payload}*", ""]
        elif kind == "note":
            lines += [f"> {payload}", ""]
        elif kind == "ul":
            lines += [f"- {i}" for i in payload] + [""]
        else:
            lines += [payload, ""]
    return "\n".join(lines).strip() + "\n"


def to_pdf(rep):
    """The same blocks on paper. Raises RuntimeError if reportlab is absent."""
    try:
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import (ListFlowable, ListItem, Paragraph,
                                        SimpleDocTemplate, Spacer)
    except ImportError as e:
        raise RuntimeError(
            "PDF export needs reportlab, which is not installed in this "
            f"deployment ({e}). Add `reportlab` to requirements.txt, or use "
            "format=markdown, which needs nothing.")

    # A built-in CID font rather than a shipped .ttf: the report is Traditional
    # Chinese, and a PDF whose font cannot draw the characters produces a page
    # of black boxes rather than an error.
    font = "MSung-Light"
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(font))
    except Exception:                                        # noqa: BLE001
        font = "Helvetica"

    def style(size, leading, space_before=0, bold_gap=0):
        return ParagraphStyle(
            f"s{size}-{space_before}", fontName=font, fontSize=size,
            leading=leading, alignment=TA_LEFT, spaceBefore=space_before,
            spaceAfter=bold_gap, wordWrap="CJK")

    styles = {
        "h1": style(19, 29, 0, 4),
        "h2": style(14, 22, 16, 4),
        "h3": style(12, 19, 10, 3),
        "p": style(10, 18, 0, 8),
        "meta": style(9, 15, 0, 10),
        "note": style(9, 16, 4, 8),
    }

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm,
                            bottomMargin=20 * mm, leftMargin=20 * mm,
                            rightMargin=20 * mm,
                            title=(rep.get("sections") or {}).get("title") or "report")
    flow = []
    for kind, payload in _blocks(rep):
        if kind == "ul":
            flow.append(ListFlowable(
                [ListItem(Paragraph(_esc(i), styles["p"])) for i in payload],
                bulletType="bullet", start="•", leftIndent=12))
            flow.append(Spacer(1, 6))
        elif payload:
            flow.append(Paragraph(_esc(str(payload)), styles.get(kind, styles["p"])))
    doc.build(flow)
    return buf.getvalue()


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace("\n", "<br/>"))
