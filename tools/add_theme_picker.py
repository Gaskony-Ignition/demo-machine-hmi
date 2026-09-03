#!/usr/bin/env python3
"""Put the theme choice in the operator's hands, on every page.

WHY IT IS WORTH HAVING

The session already carried a theme - `session.props.theme` feeds the Cell3D
view param, which feeds the 3D page's `?theme=`, which picks one of six
palettes. All of that plumbing existed and nothing could change the value
without editing the project. This adds the control.

The six names are Ignition's own stock themes, and the 3D page's palettes are
named to match, so one setting moves both: Perspective's components and the
WebGL cell change together instead of drifting apart.

TWO PLACES, ON PURPOSE

  Header dropdown - on every page, for the person driving a demonstration who
                    wants to change it without leaving the screen they are on.
                    Hidden below 1120px: the header already sheds its subtitle,
                    then its padding, then its font sizes at that width, and on
                    a 10in panel an operator does not pick themes.

  Setup page row  - six buttons beside the simulation-speed row, which is the
                    same idiom and is reachable at any width. This is the one
                    that still works on the panel.

The dropdown writes `session.props.theme` through a bidirectional binding.
`bidirectional` goes INSIDE `config`; at binding level it is accepted and
silently never writes back, which looks exactly like a dropdown that does not
work.

Idempotent. Run:  python3 tools/add_theme_picker.py
"""

import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
VIEWS = os.path.join(HERE, os.pardir, "project",
                     "com.inductiveautomation.perspective", "views", "Machine")

# Ignition ships six stock themes and the 3D page has a palette for each. Only
# the three DARK ones are offered, and that is a measured decision, not taste.
#
# The chrome follows the theme now (tools/themeify.py mapped 569 neutral
# colours onto the theme's surface-relative tokens), and on a light theme that
# part works. What does not is everything else:
#
#   * ~1200 more colours are produced INSIDE expressions and scripts rather
#     than sitting in props.style, so they are literal hex chosen for a dark
#     ground and no substitution reaches them.
#   * The semantic accents - running green #46d07c, fault red #f0565e,
#     warning amber #eebf5e, info blue #6cc4e8 - are built for a dark
#     background. Measured on a light theme they come out at contrast ratios
#     of 1.31 to 1.49 against the surface behind them; 4.5 is the readable
#     bar and 3.0 is the floor for large text. The alarm page alone had 106
#     labels under 3.0.
#
# Ignition's own --success/--warning/--error tokens DO flip correctly and are
# the right target for those, but adopting them also restyles the dark themes,
# which is a separate decision.
#
# So: three themes that are verified legible, rather than six of which half
# are not. Every one of these visibly changes the whole project - Perspective
# chrome, stock components, and the 3D cell together.
THEMES = [("dark", "Dark"), ("dark-cool", "Dark cool"),
          ("dark-warm", "Dark warm")]


def find(node, name):
    if node.get("meta", {}).get("name") == name:
        return node
    for child in node.get("children", []) or []:
        hit = find(child, name)
        if hit:
            return hit
    return None


def stamp(view_dir):
    path = os.path.join(view_dir, "resource.json")
    r = json.load(open(path))
    mod = r.setdefault("attributes", {}).setdefault("lastModification", {})
    mod["actor"] = "external"
    mod["timestamp"] = datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    r.pop("lastModificationSignature", None)
    mod.pop("lastModificationSignature", None)
    json.dump(r, open(path, "w"), indent=2)


def dropdown():
    return {
        "type": "ia.input.dropdown",
        "version": 0,
        "meta": {"name": "Theme"},
        "position": {"grow": 0, "shrink": 0, "basis": "138px"},
        "props": {
            "options": [{"value": v, "label": l} for v, l in THEMES],
            "placeholder": "Theme",
            "style": {"classes": "hdr-theme", "minWidth": "0px"},
        },
        "propConfig": {
            "props.value": {
                "binding": {
                    "type": "property",
                    # bidirectional INSIDE config, or the dropdown reads the
                    # session theme and never writes one back.
                    "config": {"path": "session.props.theme",
                               "bidirectional": True},
                }
            }
        },
    }


def button(value, label):
    return {
        "type": "ia.input.button",
        "version": 0,
        "meta": {"name": "T_" + value.replace("-", "_")},
        "position": {"grow": 1, "shrink": 1, "basis": "0px"},
        "props": {
            "text": label,
            "style": {"fontSize": "11.5px", "fontWeight": 700,
                      "letterSpacing": "0.4px", "borderRadius": "6px",
                      "border": "1px solid #2c343d",
                      "backgroundColor": "#252c34", "color": "#cfd8df",
                      "padding": "0px", "minWidth": "0px",
                      "alignItems": "center", "whiteSpace": "nowrap"},
        },
        "events": {
            "dom": {
                "onClick": {
                    "type": "script",
                    "config": {
                        "script": "\tself.session.props.theme = %r\n" % str(value)
                    },
                    "scope": "G",
                }
            }
        },
    }


# --- 1. the header dropdown, on every view that has the nav bar --------------
touched = []
for name in sorted(os.listdir(VIEWS)):
    view_dir = os.path.join(VIEWS, name)
    view_file = os.path.join(view_dir, "view.json")
    if not os.path.isfile(view_file):
        continue
    view = json.load(open(view_file))
    bar = find(view["root"], "TopBar")
    if bar is None or find(view["root"], "Nav") is None:
        continue
    if find(bar, "Theme") is None:
        # Between the nav tabs and the user block: it belongs with the other
        # session-level controls, not among the page links.
        names = [c["meta"]["name"] for c in bar["children"]]
        bar["children"].insert(names.index("User") if "User" in names
                               else len(names), dropdown())
    json.dump(view, open(view_file, "w"), indent=2)
    stamp(view_dir)
    touched.append(name)

# --- 2. the Setup page row ---------------------------------------------------
setup_dir = os.path.join(VIEWS, "Setup")
setup_file = os.path.join(setup_dir, "view.json")
setup = json.load(open(setup_file))

speed = find(setup["root"], "Speed")
if speed is None:
    raise SystemExit("Setup has no Speed panel to sit beside")
body = find(speed, "Body")

if find(body, "Themes") is None:
    # The panel was sized for exactly what it held. Six more buttons on two
    # rows need 68px, and a caption 20px.
    speed["position"]["basis"] = "262px"
    body["children"].append({
        "type": "ia.container.flex", "version": 0,
        "meta": {"name": "ThemeK"},
        "position": {"grow": 0, "shrink": 0, "basis": "22px"},
        "props": {"style": {"minWidth": "0px", "minHeight": "0px"}},
        "children": [{
            "type": "ia.display.label", "version": 0, "meta": {"name": "K"},
            "position": {"grow": 1, "shrink": 1, "basis": "auto"},
            "props": {"text": "Theme — Perspective and the 3D cell together",
                      "style": {"fontSize": "10px", "color": "#74808a",
                                "letterSpacing": "0.6px",
                                "whiteSpace": "nowrap", "overflow": "hidden",
                                "textOverflow": "ellipsis"}},
        }],
    })
    for row, pairs in (("Themes", THEMES),):
        body["children"].append({
            "type": "ia.container.flex", "version": 0,
            "meta": {"name": row},
            "position": {"grow": 0, "shrink": 0, "basis": "34px"},
            "props": {"direction": "row",
                      "style": {"gap": "6px", "padding": "0 10px 6px",
                                "minWidth": "0px", "minHeight": "0px"}},
            "children": [button(v, l) for v, l in pairs],
        })

json.dump(setup, open(setup_file, "w"), indent=2)
stamp(setup_dir)

print("theme dropdown in the header of: %s" % ", ".join(touched))
print("theme buttons added to the Setup page")
