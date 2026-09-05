#!/usr/bin/env python3
"""Generate the Machine/Scene view from src/cell3d/scene.json.

WHY THIS EXISTS

Option A's whole point is that the cell's parts list is data a person can edit
in the Designer's property editor. That means the document has to live in a
view's custom props. It also has to live in git as something reviewable, and a
view.json with a 45-part document inlined is neither.

So the readable file stays the source and this writes the view. The direction is
one-way on purpose: edit scene.json, run this, deploy. If someone edits the
document in the Designer instead - which is the point of putting it there - pull
the view back and run `extract`, exactly the rule webdev_page.py imposes on the
3D page for the same reason.

USE

    python3 tools/build_scene_view.py           scene.json -> the view
    python3 tools/build_scene_view.py --extract the view   -> scene.json
"""

import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir))
DOC = os.path.join(ROOT, "src", "cell3d", "scene.json")
VIEW_DIR = os.path.join(ROOT, "project", "com.inductiveautomation.perspective",
                        "views", "Machine", "Scene")
VIEW = os.path.join(VIEW_DIR, "view.json")
RESOURCE = os.path.join(VIEW_DIR, "resource.json")

# The document is spread across five custom props rather than nested under one,
# so a binding path reads custom.parts[3].size[0] - which is also what the
# Option B component's props.parts[3].size[0] would be.
KEYS = ["units", "consts", "data", "materials", "parts"]


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def build():
    with open(DOC, encoding="utf-8") as f:
        doc = json.load(f)
    missing = [k for k in KEYS if k not in doc]
    if missing:
        sys.exit("scene.json has no %s" % ", ".join(missing))

    view = {
        "custom": {k: doc[k] for k in KEYS},
        "params": {},
        "props": {},
        "root": {
            "type": "ia.container.flex",
            "version": 0,
            "meta": {"name": "root"},
            "props": {"direction": "column"},
            "children": [{
                "type": "ia.display.markdown",
                "version": 0,
                "meta": {"name": "Note"},
                "position": {"grow": 1},
                "props": {"source":
                          "### The cell, as data\n\n"
                          "This view renders nothing. It holds the palletising "
                          "cell's parts list in its **custom properties**, "
                          "where it can be edited with the property editor and "
                          "bound with the binding dialog.\n\n"
                          "`custom.parts` is the machine. Every size and "
                          "position is a number, a named constant, or a tag "
                          "path such as `Config/convLength_mm`.\n\n"
                          "The 3D page reads this through `admin?cmd=scene`."}
            }]
        }
    }
    os.makedirs(VIEW_DIR, exist_ok=True)
    with open(VIEW, "w", encoding="utf-8") as f:
        json.dump(view, f, indent=2)
        f.write("\n")
    with open(RESOURCE, "w", encoding="utf-8") as f:
        json.dump({
            "scope": "G", "version": 1, "restricted": False,
            "overridable": True, "files": ["view.json"],
            "attributes": {"lastModification": {"actor": "external",
                                                "timestamp": now()}}
        }, f, indent=2)
        f.write("\n")
    print("built  %s  (%d parts, %d materials)"
          % (os.path.relpath(VIEW, ROOT), len(doc["parts"]), len(doc["materials"])))


def extract():
    with open(VIEW, encoding="utf-8") as f:
        view = json.load(f)
    custom = view.get("custom") or {}
    missing = [k for k in KEYS if k not in custom]
    if missing:
        sys.exit("the view's custom props have no %s" % ", ".join(missing))
    with open(DOC, "w", encoding="utf-8") as f:
        json.dump({k: custom[k] for k in KEYS}, f, indent=2)
        f.write("\n")
    print("extracted  %s  (%d parts)" % (os.path.relpath(DOC, ROOT),
                                         len(custom["parts"])))


if __name__ == "__main__":
    extract() if "--extract" in sys.argv[1:] else build()
