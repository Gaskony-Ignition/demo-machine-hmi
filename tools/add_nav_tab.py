#!/usr/bin/env python3
"""Add the 2D CELL tab to every view that carries the nav bar.

Idempotent: run it twice and nothing changes. The tab is cloned from N_3DCELL
in the same view rather than written from scratch, so it inherits that view's
styling and - more importantly - the exact event shape. A nav action with a
missing "scope" key returns HTTP 500 on EVERY page of the project while the
scan still reports success, so the safe move is never to hand-author one.

Run:  python3 tools/add_nav_tab.py
"""

import copy
import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
VIEWS = os.path.join(HERE, os.pardir, "project",
                     "com.inductiveautomation.perspective", "views", "Machine")

NEW_NAME = "N_CELL2D"
NEW_TEXT = "2D CELL"
NEW_PAGE = "/cell2d"
AFTER = "N_3DCELL"

# The nav marks the current page by colour. Each view therefore needs to know
# which of its tabs is the active one.
ACTIVE = {"backgroundColor": "var(--md-info-bg, #152f3b)",
          "border": "1px solid var(--md-info, #6cc4e8)",
          "color": "var(--md-info-ink-2, #cfeafa)"}
INACTIVE = {"backgroundColor": "transparent",
            "border": "1px solid var(--md-line, #2c343d)",
            "color": "var(--md-ink-quiet, #8b98a3)"}


def find(node, name):
    if node.get("meta", {}).get("name") == name:
        return node
    for child in node.get("children", []):
        hit = find(child, name)
        if hit:
            return hit
    return None


def stamp(view_dir):
    path = os.path.join(view_dir, "resource.json")
    r = json.load(open(path))
    r.setdefault("attributes", {}).setdefault("lastModification", {})
    r["attributes"]["lastModification"]["actor"] = "external"
    r["attributes"]["lastModification"]["timestamp"] = (
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    # A stale content-hash makes the scan silently skip the resource.
    r.pop("lastModificationSignature", None)
    r["attributes"]["lastModification"].pop("lastModificationSignature", None)
    json.dump(r, open(path, "w"), indent=2)


changed = []
for name in sorted(os.listdir(VIEWS)):
    view_dir = os.path.join(VIEWS, name)
    view_file = os.path.join(view_dir, "view.json")
    if not os.path.isfile(view_file):
        continue

    view = json.load(open(view_file))
    nav = find(view["root"], "Nav")
    if nav is None:
        print("%-10s no nav bar - skipped" % name)
        continue
    if find(nav, NEW_NAME):
        print("%-10s already has %s" % (name, NEW_NAME))
        continue

    src = find(nav, AFTER)
    if src is None:
        raise SystemExit("%s has a nav but no %s to clone" % (name, AFTER))

    tab = copy.deepcopy(src)
    tab["meta"]["name"] = NEW_NAME
    tab["props"]["text"] = NEW_TEXT
    tab["events"]["dom"]["onClick"]["config"]["page"] = NEW_PAGE
    tab["props"]["style"].update(INACTIVE)

    nav["children"].insert(nav["children"].index(src) + 1, tab)
    json.dump(view, open(view_file, "w"), indent=2)
    stamp(view_dir)
    changed.append(name)
    print("%-10s added %s after %s" % (name, NEW_NAME, AFTER))

print("\nchanged: %s" % (", ".join(changed) or "nothing"))
