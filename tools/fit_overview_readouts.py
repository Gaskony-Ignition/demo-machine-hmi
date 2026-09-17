#!/usr/bin/env python3
"""WCAG 2.1 AA (axe scrollable-region-focusable): a handful of Overview's
single-line caption/readout rows (the "Line mimic" strap, the conveyor
direction arrows, a zone header, the BARCODE/CASES-MIN/SHIFT readouts) are
plain `ia.container.flex` wrapping one label each with no explicit overflow
- Perspective still writes `overflow: auto` on them by default, and the
label's own rendered line height is 1-3px taller than the row's basis,
making each a "scrollable" box with nothing inside to scroll to or focus.
Not a real scrollable region (confirmed live - none of them show a
scrollbar or ever clip text); give each an explicit tabIndex, the same
answer as the header's User block and Manual's Who row.

Matched by the leaf label's own text, since these rows are not generated
and the pattern repeats identically per zone without being one component
cloned from a template. `--` prefix labels use a zone number instead of a
literal for the ones that read the same in every zone.

Run:  python3 tools/fit_overview_readouts.py
"""
import datetime
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
VIEW = os.path.join(HERE, os.pardir, "project",
                    "com.inductiveautomation.perspective", "views",
                    "Machine", "Overview")
VIEW_FILE = os.path.join(VIEW, "view.json")

MARKERS = [
    "Line mimic",
    "▶",            # conveyor direction arrow
    "BARCODE",
    "CASES / MIN",
    "SHIFT",
]
ZONE_HEADER = re.compile(r"^Zone \d+ —")


def is_marker(text):
    if text in MARKERS:
        return True
    return bool(text and ZONE_HEADER.match(text))


def fix(node, parent, changed):
    if node.get("type") == "ia.display.label" and is_marker(node.get("props", {}).get("text", "")):
        if parent is not None and "tabIndex" not in parent.get("meta", {}):
            parent.setdefault("meta", {})["tabIndex"] = 0
            changed[0] += 1
    for child in node.get("children", []):
        fix(child, node, changed)


def stamp():
    path = os.path.join(VIEW, "resource.json")
    r = json.load(open(path))
    lm = r.setdefault("attributes", {}).setdefault("lastModification", {})
    lm["actor"] = "external"
    lm["timestamp"] = (datetime.datetime.now(datetime.timezone.utc)
                       .strftime("%Y-%m-%dT%H:%M:%SZ"))
    r.pop("lastModificationSignature", None)
    lm.pop("lastModificationSignature", None)
    json.dump(r, open(path, "w"), indent=2)


def main():
    view = json.load(open(VIEW_FILE))
    changed = [0]
    fix(view["root"], None, changed)
    if changed[0]:
        json.dump(view, open(VIEW_FILE, "w"), indent=2)
        stamp()
        print("%d readout row(s) made reachable" % changed[0])
    else:
        print("already done")


if __name__ == "__main__":
    main()
