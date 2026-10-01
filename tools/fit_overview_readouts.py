#!/usr/bin/env python3
"""Stop a handful of Overview's single-line caption/readout rows (the "Line
mimic" strap, the conveyor direction arrows, a zone header, the
BARCODE/CASES-MIN/SHIFT readouts) drawing scroll bars.

They are plain `ia.container.flex` wrapping one label each with no explicit
overflow, so Perspective writes `overflow: auto` on them, and the label's own
line box is 1-3px taller than the row's basis. That is leading, not text, but
it is enough for Windows to draw a scroll bar in the row, and for axe to call
it a scrollable region (scrollable-region-focusable).

Until 1.19.2 this gave each row a tabIndex, on the belief that no bar showed.
It does on Windows; headless Chromium hides scroll bars, which is why it was
missed. The row never scrolls, so it now gets `overflow: hidden` and loses the
tab stop it no longer needs. tools/verify/scrollbar_sweep.js checks it.

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
        if parent is not None:
            style = parent.setdefault("props", {}).setdefault("style", {})
            if style.get("overflow") != "hidden" or "tabIndex" in parent.get("meta", {}):
                style["overflow"] = "hidden"
                parent.get("meta", {}).pop("tabIndex", None)
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
        print("%d readout row(s) set to overflow hidden" % changed[0])
    else:
        print("already done")


if __name__ == "__main__":
    main()
