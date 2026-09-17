#!/usr/bin/env python3
"""WCAG 2.1 AA 2.1.1 (axe scrollable-region-focusable): a flex container that
can scroll (`overflow`/`overflowY`/`overflowX`: auto|scroll) needs to be
reachable by keyboard itself, in case what is inside it is not (a status
rail of plain labels, say) - `meta.tabIndex: 0` puts the region itself in the
tab order, and Tab/PageUp/PageDown then scroll it exactly as a mouse wheel
would. Idempotent: a region already carrying tabIndex is left alone.

Run:  python3 tools/add_scroll_tabindex.py
"""
import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
VIEWS = os.path.join(HERE, os.pardir, "project",
                     "com.inductiveautomation.perspective", "views", "Machine")

SCROLLS = ("auto", "scroll")


def fix(node, changed):
    style = node.get("props", {}).get("style", {})
    scrolls = any(style.get(k) in SCROLLS for k in
                  ("overflow", "overflowY", "overflowX"))
    if scrolls and "tabIndex" not in node.get("meta", {}):
        node.setdefault("meta", {})["tabIndex"] = 0
        changed[0] += 1
    for child in node.get("children", []):
        fix(child, changed)


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
        fix(view["root"], changed)
        if changed[0]:
            after = json.dumps(view, indent=2)
            open(view_file, "w", encoding="utf-8").write(after)
            stamp(view_dir)
            total += changed[0]
            print("  %-10s %d scrollable region(s) made reachable" % (name, changed[0]))
        else:
            print("  %-10s already reachable" % name)
    print("%d scrollable region(s) fixed" % total)


if __name__ == "__main__":
    main()
