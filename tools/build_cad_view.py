#!/usr/bin/env python3
"""Build Machine/CadModel - the customer's own CAD on a Perspective screen.

The page itself is the WebDev resource `cadview`, which draws every STL in the
project's `cad` resource folder with orbit/zoom/pan/pick. This view is only the
Perspective wrapper: the project's standard header, and an iframe.

The header is DEEP-COPIED from Machine/Cell3D rather than rebuilt, so the three
full-bleed model screens cannot drift apart - same heights, same fonts, same
Back button, same event shape. The Geometry toggle is dropped: it edits the
palletising cell's [MachineDemo]Config tags, which have nothing to do with an
arbitrary customer model.

Cell3D must be generated first (tools/build_cell3d_view.py) - this reads it.

Run: python3 tools/build_cad_view.py
"""

import copy
import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
VIEWS = os.path.join(HERE, os.pardir, "project",
                     "com.inductiveautomation.perspective", "views", "Machine")
SRC = os.path.join(VIEWS, "Cell3D", "view.json")
OUT = os.path.join(VIEWS, "CadModel")

COL_BG = "var(--md-bg, #171b20)"

# Same reasoning as build_cell3d_view.py: the project name is not knowable at
# build time, so the binding asks the session for it.
WEBDEV_PROJECT = 'runScript("system.project.getProjectName()")'
WEBDEV_RES = "cadview"

TITLE = "Zone 2 · Robot Cell 2 — CAD model"
SUBTITLE = "Any STL dropped in the project's cad resource folder - the customer's own geometry, not ours"


def find(node, name):
    if node.get("meta", {}).get("name") == name:
        return node
    for child in node.get("children", []):
        hit = find(child, name)
        if hit:
            return hit
    return None


def drop(node, name):
    """Remove a named child anywhere below `node`. Quiet if it is not there."""
    kids = node.get("children")
    if kids is None:
        return False
    for i, child in enumerate(kids):
        if child.get("meta", {}).get("name") == name:
            del kids[i]
            return True
        if drop(child, name):
            return True
    return False


src = json.load(open(SRC))
header_slot = copy.deepcopy(find(src["root"], "HeaderSlot"))
if header_slot is None:
    raise SystemExit("Cell3D has no HeaderSlot - run build_cell3d_view.py first")

# HeaderSlot's own visibility is bound to Cell3D's `header` param, which this
# view does not declare. A binding on a param that does not exist evaluates to
# null and the header disappears - silently. This view is always its own page,
# so the switch is simply removed rather than reproduced.
header_slot.pop("propConfig", None)

drop(header_slot, "GeomToggle")
find(header_slot, "t1")["props"]["text"] = TITLE
find(header_slot, "t2")["props"]["text"] = SUBTITLE
# RobotState reads the cell's own tags; a CAD model has none.
drop(header_slot, "RobotState")

cad_iframe = {
    "type": "ia.display.iframe",
    "meta": {"name": "CadModel"},
    "position": {"grow": 1, "basis": "0px"},
    "props": {
        "src": "",
        "style": {"height": "100%", "width": "100%",
                  "border": "none", "minHeight": "0"},
    },
    "propConfig": {
        "props.src": {
            "binding": {
                "type": "expr",
                "config": {"expression": '"/system/webdev/" + ' + WEBDEV_PROJECT
                                         + ' + "/' + WEBDEV_RES + '"'},
            }
        }
    },
}

view = {
    "custom": {},
    "params": {},
    "propConfig": {},
    "props": {"defaultSize": {"width": 1366, "height": 768}},
    "root": {
        "type": "ia.container.flex",
        "meta": {"name": "Page"},
        "props": {
            "direction": "column",
            "style": {"height": "100%", "overflow": "hidden",
                      "minHeight": "0", "backgroundColor": COL_BG},
        },
        "children": [
            header_slot,
            {
                "type": "ia.container.flex",
                "meta": {"name": "Body"},
                "position": {"grow": 1, "shrink": 1, "basis": "0px"},
                "props": {"direction": "row", "style": {"minHeight": "0px"}},
                "children": [cad_iframe],
            },
        ],
    },
}

resource = {
    "scope": "G",
    "version": 1,
    "restricted": False,
    "overridable": True,
    "files": ["view.json"],
    # A stale timestamp makes the scan skip the resource silently, and a
    # lastModificationSignature key does the same even when it is wrong.
    "attributes": {
        "lastModification": {
            "actor": "external",
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
                                 .strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    },
}

os.makedirs(OUT, exist_ok=True)
json.dump(view, open(os.path.join(OUT, "view.json"), "w"), indent=2)
json.dump(resource, open(os.path.join(OUT, "resource.json"), "w"), indent=2)
print("wrote %s" % OUT)
