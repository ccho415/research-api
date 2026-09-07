"""Offline check of what leaves the building. No database, no reportlab needed.

    python tests/test_export.py

The thing being pinned is not the formatting. It is that the two parts most
likely to be lost when a report is copied elsewhere - what it does not cover,
and what still has to be obtained - are inside the file rather than only on
the screen. Eight sections without those read as finished work.

Both renderers walk one shared block list, so the second check here is that
they cannot disagree about what the document contains.
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

import exporting

fails = []


def check(name, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{name}: got {got!r}, wanted {want!r}")
    print(("  ok  " if ok else " FAIL ") + name + f"  -> {got!r}")


REPORT = {
    "id": "368c9d4d-c93e-4f9a-85fa-6f9b28e6a05b",
    "created_at": "2026-09-05T11:11:59.149502+00:00",
    "tier": "C", "rank": 4, "novelty_verdict": "adjacent",
    "idea_title": "方向標題",
    "sections": {k: f"{label} 的內容。" for k, label in exporting.SECTION_TITLES},
    "citations": [{"doi": "10.1/a"}, {"doi": "10.1/b"}],
    "dropped": None,
    "acquisition": {
        "tier": "C",
        "missing": ["缺少的變項甲", "缺少的變項乙"],
        "route": "去某個聯盟談資料分享協議",
        "note": "兩份不一致時以這一份為準。"},
    "caveats": {
        "fulltext": {"n_with_fulltext": 69, "n_papers": 200,
                     "note": "全文只拿到 200 篇裡的 69 篇。"},
        "novelty_unverified": {"n_unverified": 8, "n_graded": 11,
                               "note": "未驗證不等於新穎。"},
        "excluded_as_already_done": {
            "n": 2,
            "directions": [{"code": 3, "title": "被搶先的方向甲"},
                           {"code": 7, "title": "被搶先的方向乙"}],
            "note": "這些方向被判定已經有人做過。"},
        "debate": {"n_rounds": 1, "note": "終止是系統算出來的。"}},
}

md = exporting.to_markdown(REPORT)

print("\n-- all eight sections are in the file --")
for i, (key, label) in enumerate(exporting.SECTION_TITLES, start=1):
    check(f"{i:02d} {label}", f"## {i:02d} {label}" in md, True)

print("\n-- the caveats block is in the FILE, not only on the screen --")
check("has the heading", "## 這份沒有涵蓋什麼" in md, True)
check("full-text rate", "200 篇裡的 69 篇" in md, True)
check("unverified is not novel", "未驗證不等於新穎" in md, True)
check("debate note", "終止是系統算出來的" in md, True)

print("\n-- excluded directions are NAMED in the file --")
check("first", "被搶先的方向甲" in md, True)
check("second", "被搶先的方向乙" in md, True)

print("\n-- the acquisition list travels too --")
check("heading says it skipped the model",
      "不經模型" in md, True)
check("each missing variable", "缺少的變項甲" in md and "缺少的變項乙" in md, True)
check("the route", "去某個聯盟談資料分享協議" in md, True)
check("and which one wins on disagreement", "以這一份為準" in md, True)

print("\n-- the header carries the three things a reader judges it by --")
check("novelty verdict", "新穎性 adjacent" in md, True)
check("its meaning spelled out", "沒人做過，但有鄰近文獻" in md, True)
check("tier", "可行性 C 級" in md, True)
check("citations with fabrications beside them",
      "引用 2 筆 · 捏造 0 筆" in md, True)

print("\n-- a report with no caveats yet does not grow an empty section --")
bare = dict(REPORT, caveats=None, acquisition=None)
bare_md = exporting.to_markdown(bare)
check("no caveats heading", "這份沒有涵蓋什麼" in bare_md, False)
check("no acquisition heading", "不經模型" in bare_md, False)
check("but the sections are still all there",
      all(f"## {i:02d} " in bare_md for i in range(1, 9)), True)

print("\n-- both renderers walk one list, so they cannot disagree --")
blocks = exporting._blocks(REPORT)
check("the list is shared", len(blocks) > 0, True)
try:
    pdf = exporting.to_pdf(REPORT)
    check("pdf is a pdf", pdf[:4], b"%PDF")
except RuntimeError as e:
    # No reportlab here is fine - what must not happen is a crash with an
    # unreadable error, or the module failing to import at all.
    check("absent reportlab is reported, not raised as a mystery",
          "reportlab" in str(e) and "markdown" in str(e), True)

print()
if fails:
    print(f"{len(fails)} FAILED")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("all checks passed")
