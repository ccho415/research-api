"""The paradigm packs and field modules, read from disk and recorded in the database.

Two layers, answering different questions. A paradigm pack says what has to be
true for a claim to hold; a field module says which checklist a reviewer will
actually hold up. A pack alone produces critique that is correct and generic -
the kind that warns an EEG study about data leakage when its real problem is
that nobody removed eye-blink artifacts.

Disk is the source. `skill_prompt` is the record of what was in force, which is
a different thing: the deployed files change with every release, and a report
read six months later has to say which judgement was applied to it without
re-running anything. `project.domain_frame` stores the key and version, and
those rows are never rewritten.
"""

import hashlib
import os
import re

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packs")

PARADIGMS = os.path.join(ROOT, "paradigms")
FIELDS = os.path.join(ROOT, "fields")
ROUTING = os.path.join(ROOT, "routing.md")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def summarise(text, name):
    """Enough to route on, and no more.

    Routing needs to know what a pack is for; it does not need the pack. Sending
    all thirteen in full would be a hundred and thirty kilobytes of prompt to
    answer three questions, and on this model the thinking budget comes out of
    the same allowance as the reply.
    """
    head = None
    first = None
    fields = None
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("# ") and head is None:
            head = s[2:].strip()
            continue
        if s.startswith("**Fields:**") and fields is None:
            fields = s.replace("**Fields:**", "").strip()
            continue
        if head and first is None and not s.startswith(("#", "---", "|", "**Fields:")):
            first = s
    return {"key": name, "title": head or name,
            "summary": (first or "")[:400], "fields": (fields or "")[:300]}


def all_packs():
    """Every pack and module on disk, keyed the way the database stores them."""
    out = []
    for folder, prefix in ((PARADIGMS, "paradigm"), (FIELDS, "field")):
        if not os.path.isdir(folder):
            continue
        for fn in sorted(os.listdir(folder)):
            if not fn.endswith(".md"):
                continue
            name = fn[:-3]
            text = _read(os.path.join(folder, fn))
            out.append({"key": f"{prefix}:{name}", "kind": prefix, "name": name,
                        "content": text,
                        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
    if os.path.exists(ROUTING):
        text = _read(ROUTING)
        out.append({"key": "routing", "kind": "routing", "name": "routing",
                    "content": text,
                    "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
    return out


def routing_menu():
    """What the router chooses between: summaries only, never the full packs."""
    packs, fields = [], []
    for p in all_packs():
        if p["kind"] == "paradigm":
            packs.append(summarise(p["content"], p["name"]))
        elif p["kind"] == "field":
            fields.append(summarise(p["content"], p["name"]))
    return {"paradigms": packs, "fields": fields}


def routing_rules():
    """The three questions and the rule that forces a second pack.

    Kept as the skill's own text rather than paraphrased here, because the rule
    that matters - a second answer to Q2 forces a second pack - is the one the
    validation caught being skipped, and a paraphrase is where it would go
    missing again.
    """
    return _read(ROUTING) if os.path.exists(ROUTING) else ""
