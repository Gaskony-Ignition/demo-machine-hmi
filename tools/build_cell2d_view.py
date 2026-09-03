#!/usr/bin/env python3
"""Build Machine/Cell2D - the SAME robot, using only stock Perspective components.

This exists to answer one question honestly: how far can you get without any
JavaScript at all? Everything here is a component you can drag out of the
Designer palette, and every moving part is an ordinary tag binding.

The trick is that Perspective puts `props.style` straight onto the component as
an inline CSS style, and CSS `transform` composes down the DOM tree. So a
container rotated by J2, holding a container rotated by J3, is a two-link arm -
the same parent/child relationship the three.js version uses, expressed in the
only nesting Perspective gives you.

Run:  python3 tools/build_cell2d_view.py
"""

import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, os.pardir, "project",
                   "com.inductiveautomation.perspective", "views",
                   "Machine", "Cell2D")

PROVIDER = "MachineDemo"


def T(path):
    """An Ignition expression tag reference: {[MachineDemo]Robot/J2_deg}."""
    return "{[" + PROVIDER + "]" + path + "}"

# --- palette, kept to the same values the 3D page uses -----------------------
COL = {
    "bg":      "#171b20",
    "floor":   "#22282f",
    "grid":    "#2b323a",
    "steel":   "#7d8894",
    "steelHi": "#98a4b1",
    "arm":     "#c8ced5",
    "arm2":    "#aab3bd",
    "joint":   "#5a646f",
    "case":    "#b98a4e",
    "caseAlt": "#a8793f",
    "pallet":  "#8a6b41",
    "ink":     "#e6ebf0",
    "dim":     "#8b98a3",
    "run":     "#5fd08a",
}

# Side elevation, 110 px per metre. The sim's link lengths are 1.35 m and
# 1.15 m (docs/CONTRACT.md) - keep these two in step with it or the arm will
# reach somewhere the 3D view does not.
PX_PER_M = 110.0
L1 = int(1.35 * PX_PER_M)   # 148
L2 = int(1.15 * PX_PER_M)   # 126

SHOULDER_X = 210
SHOULDER_Y = 190
FLOOR_Y = 430
BODY_H = 550


def coord(name, x, y, w, h, style=None, children=None, mode="fixed"):
    node = {
        "type": "ia.container.coord",
        "version": 0,
        "meta": {"name": name},
        "position": {"x": x, "y": y, "width": w, "height": h},
        "props": {"mode": mode},
        "children": children or [],
    }
    if style:
        node["props"]["style"] = style
    return node


def block(name, x, y, w, h, style):
    """A plain filled rectangle. A flex container with nothing in it is the
    cheapest stock component that paints a box."""
    return {
        "type": "ia.container.flex",
        "version": 0,
        "meta": {"name": name},
        "position": {"x": x, "y": y, "width": w, "height": h},
        "props": {"style": style},
    }


def label(name, x, y, w, h, text, style):
    return {
        "type": "ia.display.label",
        "version": 0,
        "meta": {"name": name},
        "position": {"x": x, "y": y, "width": w, "height": h},
        "props": {"text": text, "style": style},
    }


def expr_binding(expression):
    return {"type": "expr", "config": {"expression": expression}}


def bind(node, prop_path, expression):
    node.setdefault("propConfig", {})[prop_path] = {
        "binding": expr_binding(expression)
    }
    return node


# --- the arm -----------------------------------------------------------------
# Upper arm: rotates about its own left edge, which sits exactly on the
# shoulder pivot. CSS rotates clockwise with Y pointing down the screen, and
# the sim's J2 is counter-clockwise with Y up, so the sign is flipped.
gripper = block("Gripper", L2 - 12, -7, 26, 34, {
    "backgroundColor": COL["joint"],
    "borderRadius": "3px",
})

held_case = block("HeldCase", L2 - 16, 28, 32, 26, {
    "backgroundColor": COL["case"],
    "border": "1px solid #8d6836",
    "borderRadius": "2px",
})
bind(held_case, "meta.visible", T("Robot/GripperClosed"))

fore_arm = coord("ForeArm", L1 - 14, 2, L2, 22, style={
    "backgroundColor": COL["arm2"],
    "borderRadius": "11px",
    "overflow": "visible",
    "transformOrigin": "11px 11px",
}, children=[
    block("ElbowPin", 2, 5, 12, 12, {
        "backgroundColor": COL["joint"], "borderRadius": "50%"}),
    gripper,
    held_case,
])
bind(fore_arm, "props.style.transform",
     'stringFormat("rotate(%.2fdeg)", 0 - ' + T("Robot/J3_deg") + ')')

upper_arm = coord("UpperArm", SHOULDER_X, SHOULDER_Y, L1, 26, style={
    "backgroundColor": COL["arm"],
    "borderRadius": "13px",
    "overflow": "visible",
    "transformOrigin": "13px 13px",
}, children=[
    block("ShoulderPin", 5, 7, 16, 16, {
        "backgroundColor": COL["joint"], "borderRadius": "50%"}),
    fore_arm,
])
# Lift_mm 0..2000 raises the whole assembly. Same expression drives both parts
# of the transform, so the carriage and the shoulder can never disagree.
bind(upper_arm, "props.style.transform",
     'stringFormat("translateY(%.1fpx) rotate(%.2fdeg)", (2000 - '
     + T("Robot/Lift_mm") + ') / 2000.0 * 200 - 100, 0 - '
     + T("Robot/J2_deg") + ')')

# The carriage block that visibly rides the column with the arm.
carriage = block("Carriage", SHOULDER_X - 26, SHOULDER_Y - 8, 34, 42, {
    "backgroundColor": COL["steelHi"],
    "borderRadius": "4px",
})
bind(carriage, "props.style.transform",
     'stringFormat("translateY(%.1fpx)", (2000 - ' + T("Robot/Lift_mm")
     + ') / 2000.0 * 200 - 100)')


# --- pallet ------------------------------------------------------------------
# A side elevation shows one face of the stack: 4 across, 5 high. Each visible
# block therefore stands for 3 of the 12 cases in a layer.
PALLET_X = 600
PALLET_TOP = FLOOR_Y - 30
CASE_W, CASE_H = 44, 26

pallet_children = []
for row in range(5):
    for col in range(4):
        idx = row * 4 + col
        pallet_children.append(bind(
            block("Case_%d_%d" % (row, col),
                  PALLET_X + col * (CASE_W + 3),
                  PALLET_TOP - (row + 1) * (CASE_H + 3),
                  CASE_W, CASE_H,
                  {"backgroundColor": COL["case"] if row % 2 == 0 else COL["caseAlt"],
                   "border": "1px solid #8d6836", "borderRadius": "2px"}),
            "meta.visible",
            T("Pallet/Station1/CasesPlaced") + " > " + str(idx * 3)))


# --- assembly ----------------------------------------------------------------
children = [
    # cell floor and column
    block("Floor", 0, FLOOR_Y, 1024, 6, {"backgroundColor": COL["steel"]}),
    block("FloorFill", 0, FLOOR_Y + 6, 1024, BODY_H - FLOOR_Y - 6, {"backgroundColor": COL["floor"]}),
    block("Column", SHOULDER_X - 30, 90, 42, FLOOR_Y - 90,
          {"backgroundColor": COL["steel"], "borderRadius": "4px"}),
    block("ColumnCap", SHOULDER_X - 36, 78, 54, 14,
          {"backgroundColor": COL["steelHi"], "borderRadius": "3px"}),
    block("Base", SHOULDER_X - 60, FLOOR_Y - 22, 102, 22,
          {"backgroundColor": COL["steelHi"], "borderRadius": "3px"}),

    # conveyor stub, so the scene reads as a cell rather than an arm on a stick
    block("ConvDeck", 700, 302, 300, 12, {"backgroundColor": COL["steel"]}),
    block("ConvLeg1", 730, 314, 10, FLOOR_Y - 314, {"backgroundColor": COL["grid"]}),
    block("ConvLeg2", 960, 314, 10, FLOOR_Y - 314, {"backgroundColor": COL["grid"]}),

    # pallet deck
    block("PalletDeck", PALLET_X - 8, FLOOR_Y - 30, 4 * (CASE_W + 3) + 12, 30,
          {"backgroundColor": COL["pallet"], "borderRadius": "2px"}),

    carriage,
    upper_arm,
]
children += pallet_children

# A live readout of the three values driving the picture, so the claim "these
# are ordinary tag bindings" is checkable on the screen itself.
state = label("State", 24, BODY_H - 34, 460, 22, "",
              {"color": COL["run"], "fontSize": "13px"})
bind(state, "props.text",
     '"Robot: " + ' + T("Robot/State")
     + ' + "   J2 " + stringFormat("%.1f", ' + T("Robot/J2_deg")
     + ') + "  J3 " + stringFormat("%.1f", ' + T("Robot/J3_deg")
     + ') + "  Lift " + stringFormat("%.0f", ' + T("Robot/Lift_mm")
     + ') + " mm"')
children.append(state)

# The header is LIFTED FROM Cell3D rather than re-authored. The two cell pages
# are siblings and should stay identical above the fold; copying the node also
# inherits the Overview button's event config, which is the one place a missing
# "scope" key takes the whole project down with an HTTP 500.
import copy

CELL3D = os.path.join(HERE, os.pardir, "project",
                      "com.inductiveautomation.perspective", "views",
                      "Machine", "Cell3D", "view.json")


def find(node, name):
    if node.get("meta", {}).get("name") == name:
        return node
    for child in node.get("children", []):
        hit = find(child, name)
        if hit:
            return hit
    return None


def set_text(node, name, text):
    node = find(node, name)
    if node is None:
        raise SystemExit("Cell3D header has no %r - the layout changed" % name)
    node["props"]["text"] = text


header = copy.deepcopy(find(json.load(open(CELL3D))["root"], "Header"))
if header is None:
    raise SystemExit("Cell3D has no Header to copy")
# The geometry-panel toggle is Cell3D's alone: this view has no panel for it.
header["children"] = [c for c in header["children"]
                      if c.get("meta", {}).get("name") != "GeomToggle"]
set_text(header, "t1", u"Zone 2 \u00b7 Robot Cell 2 \u2014 Stock components")
set_text(header, "t2", "The same robot, the same tags, built entirely in the "
                       "Designer with no JavaScript")

body = {
    "type": "ia.container.coord",
    "version": 0,
    "meta": {"name": "Cell"},
    "position": {"grow": 1, "shrink": 1, "basis": "0px"},
    "props": {"mode": "fixed",
              "style": {"backgroundColor": COL["bg"], "overflow": "hidden",
                        "minHeight": "0px"}},
    "children": children,
}

view = {
    "custom": {},
    "params": {},
    "props": {"defaultSize": {"width": 1024, "height": 600}},
    "root": {
        "type": "ia.container.flex",
        "version": 0,
        "meta": {"name": "Page"},
        "props": {"direction": "column",
                  "style": {"height": "100%", "overflow": "hidden",
                            "minHeight": "0", "backgroundColor": COL["bg"]}},
        "children": [header, body],
    },
}

resource = {
    "scope": "G",
    "version": 1,
    "restricted": False,
    "overridable": True,
    "files": ["view.json"],
    # A timestamp that does not move makes the scan skip the resource on every
    # rebuild after the first - the file changes and the gateway never notices.
    "attributes": {"lastModification": {
        "actor": "external",
        "timestamp": datetime.datetime.now(datetime.timezone.utc)
                             .strftime("%Y-%m-%dT%H:%M:%SZ")}},
}

os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "view.json"), "w") as f:
    json.dump(view, f, indent=2)
with open(os.path.join(OUT, "resource.json"), "w") as f:
    json.dump(resource, f, indent=2)

print("wrote %s (%d components)" % (OUT, len(children)))
