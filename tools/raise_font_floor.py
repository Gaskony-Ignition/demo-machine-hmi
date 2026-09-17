#!/usr/bin/env python3
"""WCAG 2.1 AA, Stage 4: no text below 11px anywhere in the project - CSS is
fixed by hand in stylesheet.css, this script does the other half, every
inline `props.style.fontSize` in every view. Idempotent: a size already
>= 11px is left exactly alone, so re-running after a hand edit changes
nothing.

Flat floor, not a proportional rescale: a label at 9px becomes 11px, not
9 * (11/9)px, because the failing sizes were themselves the fitted answer to
a fixed width (see fit_overview.py, fit_manual.py) - scaling every sibling
by the same factor would just move the shortfall onto whichever one had the
least spare room, not remove it.

Run:  python3 tools/raise_font_floor.py
"""
import datetime
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
VIEWS = os.path.join(HERE, os.pardir, "project",
                     "com.inductiveautomation.perspective", "views", "Machine")

FLOOR = 11.0
SIZE_RE = re.compile(r"^(-?[0-9.]+)(px)$")


def raise_size(node, changed):
    props = node.get("props")
    if isinstance(props, dict):
        style = props.get("style")
        if isinstance(style, dict):
            fs = style.get("fontSize")
            if isinstance(fs, str):
                m = SIZE_RE.match(fs.strip())
                if m and float(m.group(1)) < FLOOR:
                    style["fontSize"] = "%gpx" % FLOOR
                    changed[0] += 1
    for child in node.get("children", []):
        raise_size(child, changed)


def stamp(view_dir):
    path = os.path.join(view_dir, "resource.json")
    r = json.load(open(path))
    lm = r.setdefault("attributes", {}).setdefault("lastModification", {})
    lm["actor"] = "external"
    lm["timestamp"] = (datetime.datetime.now(datetime.timezone.utc)
                       .strftime("%Y-%m-%dT%H:%M:%SZ"))
    r.pop("lastModificationSignature", None)
    lm.pop("lastModificationSignature", None)
    json.dump(r, open(path, "w"), indent=2)


def main():
    total = 0
    for name in sorted(os.listdir(VIEWS)):
        view_dir = os.path.join(VIEWS, name)
        view_file = os.path.join(view_dir, "view.json")
        if not os.path.isfile(view_file):
            continue
        before = open(view_file, encoding="utf-8").read()
        view = json.loads(before)
        changed = [0]
        raise_size(view["root"], changed)
        if changed[0]:
            after = json.dumps(view, indent=2)
            open(view_file, "w", encoding="utf-8").write(after)
            stamp(view_dir)
            total += changed[0]
            print("  %-10s %d size(s) raised to %gpx" % (name, changed[0], FLOOR))
        else:
            print("  %-10s already >= %gpx" % (name, FLOOR))
    print("%d font size(s) raised" % total)


if __name__ == "__main__":
    main()
