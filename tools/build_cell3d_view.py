#!/usr/bin/env python3
"""Build Machine/Cell3D - the 3D palletising cell as a genuinely embeddable
Perspective view.

The view is a header plus an ia.display.iframe pointed at the WebDev-served
3D page. This generator adds four view params so the same view can be
dropped into any screen as an Embedded View, aimed at a chosen camera, with
its own title bar switched off:

    camera  string   default "overview"          which 3D camera the page starts on
    hud     boolean  default true                 overlay cards + camera buttons
    header  boolean  default true                 this view's OWN header row
    theme   string   default {session.props.theme} which colour set the page renders in

The iframe's props.src is bound to an expression that appends
?camera=<camera>&hud=<1|0>&theme=<theme> to the same relative WebDev path
used before - never an absolute URL, so the view keeps working on any
host/port. With no params overridden (the plain page route uses this view
with defaults) the rendered src is exactly what it always was, plus the
params the page already treats as its defaults - see docs/CONTRACT.md's
page-URL-params section, which the T+Q package implements on the page side.

`theme`'s DEFAULT is bound to {session.props.theme} rather than a literal
string, so an embed with nothing overridden follows the Perspective session's
own theme; passing a literal string in an Embedded View's param override still
wins, same as camera/hud/header.

Cell2D's builder (tools/build_cell2d_view.py) finds this view's "Header" node
by name and deep-copies it wholesale, including whatever propConfig sits on
it - Cell2D declares no view params of its own, so a binding on the "Header"
node itself would carry over an expression referencing a param that view has
never heard of. To keep that copy working unmodified, the header#-visibility
switch lives on a WRAPPER ("HeaderSlot") that Cell2D's find()/copy never
reaches - the "Header" node it grabs stays exactly as innocent as before.

Binding a view param into an expression is a KNOWN silent-failure mode (see
knowledge/perspective-bindings.md and the "view params can fail silently"
note): the binding can render with every literal correct and the parameter
value simply missing, with no error anywhere. There is no way to avoid that
risk here (the whole point is a runtime-supplied camera/hud/header), so this
generator's caller MUST verify the rendered `src` attribute in the live DOM
before calling the work done - do not trust the JSON alone.

Run: python3 tools/build_cell3d_view.py
"""

import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, os.pardir, "project",
                   "com.inductiveautomation.perspective", "views",
                   "Machine", "Cell3D")

COL_BG = "#171b20"
WEBDEV_PATH = "/system/webdev/Machine_HMI_Demo/cell3d"


def expr_binding(expression):
    return {"type": "expr", "config": {"expression": expression}}


def bind(node, prop_path, expression):
    node.setdefault("propConfig", {})[prop_path] = {
        "binding": expr_binding(expression)
    }
    return node


# --- header (kept byte-for-byte identical to what Cell2D expects to find) ---
# t1/t2 text, the RobotState badge and the Overview button are unchanged from
# before params existed - Cell2D's set_text() calls still land on the same
# two names, and the copied node still carries the Overview button's own
# event config (the one place a missing "scope" key would 500 the project).
header = {
    "type": "ia.container.flex",
    "meta": {"name": "Header"},
    "position": {"shrink": 0},
    "props": {
        "direction": "row",
        "alignItems": "center",
        "style": {
            "backgroundColor": "#1d232a",
            "borderBottom": "1px solid #2c343d",
            "padding": "9px 16px",
            "gap": "14px",
        },
    },
    "children": [
        {
            "type": "ia.container.flex",
            "meta": {"name": "Title"},
            "position": {"grow": 1},
            "props": {"direction": "column", "style": {"gap": "1px"}},
            "children": [
                {
                    "type": "ia.display.label",
                    "meta": {"name": "t1"},
                    "props": {
                        "text": "Zone 2 · Robot Cell 2 — Live 3D",
                        "style": {
                            "fontSize": "16px",
                            "color": "#f2f6f8",
                            "fontWeight": "bold",
                        },
                    },
                    "position": {"shrink": 0},
                },
                {
                    "type": "ia.display.label",
                    "meta": {"name": "t2"},
                    "props": {
                        "text": "Model driven by the same [MachineDemo] tags as every other screen",
                        "style": {
                            "fontSize": "11.5px",
                            "color": "#8b98a3",
                            "fontWeight": "normal",
                        },
                    },
                    "position": {"shrink": 0},
                },
            ],
        },
        {
            "type": "ia.display.label",
            "meta": {"name": "RobotState"},
            "position": {"shrink": 0},
            "props": {
                "text": "",
                "style": {
                    "fontSize": "11px",
                    "fontWeight": "bold",
                    "letterSpacing": ".06em",
                    "textTransform": "uppercase",
                    "borderRadius": "4px",
                    "padding": "3px 9px",
                    "backgroundColor": "#14313e",
                    "color": "#6cc4e8",
                    "border": "1px solid #1e546c",
                },
            },
            "propConfig": {
                "props.text": {
                    "binding": {
                        "type": "tag",
                        "config": {
                            "mode": "direct",
                            "tagPath": "[MachineDemo]Robot/State",
                        },
                    }
                }
            },
        },
        {
            "type": "ia.input.button",
            "meta": {"name": "BackToOverview"},
            "position": {"shrink": 0},
            "props": {
                "text": "Overview",
                "style": {
                    "backgroundColor": "#262e36",
                    "color": "#cdd6dd",
                    "border": "1px solid #38424c",
                    "borderRadius": "7px",
                    "fontWeight": "bold",
                    "fontSize": "12.5px",
                    "minHeight": "38px",
                    "padding": "0 16px",
                    # This is the only button in the project that fixes
                    # minHeight rather than growing to fit its content, and
                    # ia.input.button renders as display:flex with
                    # align-items:normal - its inner content wrapper (a fixed
                    # 25px) then sits at the TOP of the 38px box instead of
                    # centred, riding the label 5.5px high. Every other
                    # button has min-height 0 and centres by construction, so
                    # only this one needs the explicit override. Measured on
                    # /cell3d at 1366x768, 02/09/2026.
                    "alignItems": "center",
                },
            },
            "events": {
                "component": {
                    "onActionPerformed": {
                        "type": "script",
                        "scope": "G",
                        "config": {"script": "\tsystem.perspective.navigate(page='/')\n"},
                    }
                }
            },
        },
    ],
}

# The wrapper is the ONLY place the header param is consulted. It is a plain
# pass-through flex container: unstyled, single child, "shrink": 0 so a
# column-direction parent never stretches it - the header keeps its natural
# height when shown and disappears (and gives its space back to the iframe)
# when the header param is false.
header_slot = {
    "type": "ia.container.flex",
    "meta": {"name": "HeaderSlot"},
    "position": {"shrink": 0},
    "props": {"direction": "column"},
    "children": [header],
}
bind(header_slot, "meta.visible", "{view.params.header}")

# --- the embeddable 3D panel --------------------------------------------------
# The relative WebDev path never changes; only the query string does, built
# entirely from view params so the SAME view produces a different URL per
# embed. if() rather than a numeric cast keeps the "1"/"0" the page's own
# ?hud= parsing already expects (see docs/CONTRACT.md).
cell_iframe = {
    "type": "ia.display.iframe",
    "meta": {"name": "Cell3D"},
    "position": {"grow": 1, "basis": "0px"},
    "props": {
        "src": WEBDEV_PATH,
        "style": {
            "height": "100%",
            "width": "100%",
            "border": "none",
            "minHeight": "0",
        },
    },
}
bind(
    cell_iframe,
    "props.src",
    '"' + WEBDEV_PATH + '?camera=" + {view.params.camera}'
    ' + "&hud=" + if({view.params.hud}, "1", "0")'
    ' + "&theme=" + {view.params.theme}',
)

view = {
    "custom": {},
    "params": {
        "camera": "overview",
        "hud": True,
        "header": True,
        # Static fallback only - never what actually resolves when nothing
        # overrides the param. The binding below is what makes this follow
        # the session by default; this literal only matters if that binding
        # itself somehow fails to evaluate.
        "theme": "dark-cool",
    },
    # A view's declared params are just default values unless each one is ALSO
    # marked paramDirection "input" here - the Designer does this invisibly
    # when a param is added through its Params editor, but a hand-authored
    # view.json has to say it explicitly, or the value an embedder passes in
    # never reaches view.params: it silently stays on its own default with no
    # error anywhere (see the popup-params gotcha in perspective-bindings.md,
    # and reference-perspective-popup-params-and-table-events.md - the same
    # trap, at the view-embedding boundary instead of openPopup).
    "propConfig": {
        "params.camera": {"paramDirection": "input", "persistent": True},
        "params.hud": {"paramDirection": "input", "persistent": True},
        "params.header": {"paramDirection": "input", "persistent": True},
        # theme carries a BINDING as well as paramDirection: input. The
        # binding is what makes an unembedded/no-override view follow
        # {session.props.theme} - a param with only a static default would
        # sit on "dark-cool" forever even as the session theme changed. An
        # Embedded View's own param override still wins over this binding,
        # same as it wins over camera/hud/header's static defaults.
        "params.theme": {
            "paramDirection": "input",
            "persistent": True,
            "binding": expr_binding("{session.props.theme}"),
        },
    },
    "props": {"defaultSize": {"width": 1366, "height": 768}},
    "root": {
        "type": "ia.container.flex",
        "meta": {"name": "Page"},
        "props": {
            "direction": "column",
            "style": {
                "height": "100%",
                "overflow": "hidden",
                "minHeight": "0",
                "backgroundColor": COL_BG,
            },
        },
        "children": [header_slot, cell_iframe],
    },
}

resource = {
    "scope": "G",
    "version": 1,
    "restricted": False,
    "overridable": True,
    "files": ["view.json"],
    # A timestamp that does not move makes the scan skip the resource on
    # every rebuild after the first - the file changes and the gateway never
    # notices. No lastModificationSignature key - its presence, even stale,
    # makes the scan treat the resource as already-known and skip it too.
    "attributes": {
        "lastModification": {
            "actor": "external",
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
                                 .strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    },
}

os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "view.json"), "w") as f:
    json.dump(view, f, indent=2)
with open(os.path.join(OUT, "resource.json"), "w") as f:
    json.dump(resource, f, indent=2)

print("wrote %s" % OUT)
