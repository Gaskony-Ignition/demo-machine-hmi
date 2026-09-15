#!/usr/bin/env python3
"""Make the project's own chrome follow the gateway theme.

THE PROBLEM

session.props.theme already drove two things: Perspective's stock components,
and the 3D page (which has six palettes of its own keyed to the same names).
It did NOT drive this project's hand-styled chrome, because every panel,
border and label in the views carried a literal hex colour. Switching to a
light theme therefore produced a page that was dark everywhere except the
dropdown that switched it - measurably worse than not offering the choice.

THE MECHANISM

Perspective does not mark the DOM with the theme name. It swaps the whole
theme stylesheet, and that stylesheet defines the tokens. So the chrome cannot
be keyed on the theme - it has to be *expressed in* the theme's tokens.

The token set is surface-relative, not an absolute lightness ramp, which is
what makes this work at all:

    --neutral-10   #161616 in dark themes,  #FAFAFA in light   (the page)
    --neutral-100  #FAFAFA in dark themes,  #161616 in light   (max contrast)

So neutral-10 always means "the surface the page sits on" and neutral-90
always means "text that reads on it", whichever way round the theme is. A
colour written as var(--neutral-20) is correct in all six themes without a
single media query or theme-specific rule.

WHAT IS MAPPED, AND WHAT IS NOT

Only the NEUTRALS. Every semantic colour stays exactly as it is: running
green, fault red, warning amber, info blue, the case and pallet browns, and
the tinted button faces. Those mean something, and a green that turned grey
in a light theme would be a bug, not a feature. That is the whole reason this
is a table and not a search-and-replace of everything that looks like a hex
value.

Fallbacks are kept on every var() - `var(--neutral-20, #1d232a)` - so the
project still renders correctly if it is ever opened somewhere the tokens are
not defined.

Idempotent. Run:  python3 tools/themeify.py
"""

import datetime
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
VIEWS = os.path.join(HERE, os.pardir, "project",
                     "com.inductiveautomation.perspective", "views", "Machine")

# demo hex -> theme token. Roles, in surface order:
#
#   10  the page itself          20  a panel on it      30  a well inside one
#   40  a divider or an off lamp 60  dim text           80  secondary text
#   90  primary text
MAP = {
    # --- surfaces ---
    "#12171c": "--neutral-10",   # the darkest ground, behind everything
    "#171b20": "--neutral-10",   # page background
    "#1d232a": "--neutral-20",   # panel
    "#20262d": "--neutral-20",   # card
    "#22282f": "--neutral-20",   # mimic floor
    "#232a31": "--neutral-30",   # inset
    "#252c34": "--neutral-30",   # button face, untinted
    "#262e36": "--neutral-30",   # track / well
    "#28313a": "--neutral-30",   # nested block
    "#2b323a": "--neutral-30",   # grid line block
    # --- lines, borders, and lamps that are OFF ---
    "#2c343d": "--neutral-40",
    "#39434b": "--neutral-40",
    "#3a434b": "--neutral-40",
    "#3b4650": "--neutral-40",
    "#4a5560": "--neutral-50",
    "#5a646f": "--neutral-50",
    # --- text, dim to bright ---
    "#74808a": "--neutral-60",
    "#7d8894": "--neutral-60",
    "#8b98a3": "--neutral-60",
    "#98a4b1": "--neutral-70",
    "#aab3bd": "--neutral-70",
    "#b7c2ca": "--neutral-80",
    "#c8ced5": "--neutral-80",
    "#cdd6dd": "--neutral-80",
    "#cfd8df": "--neutral-80",
    "#d5dde3": "--neutral-90",
    "#dde4e9": "--neutral-90",
    "#e6eef4": "--neutral-90",
    "#f2f6f8": "--neutral-100",
}

# Named here so the intent is on the record rather than implied by absence.
KEEP = {
    "#46d07c", "#5fd08a", "#7ee2d2", "#bff0d2", "#2c7a4a", "#1c3b2a",   # running
    "#f0565e", "#ff8d92", "#e59aa0", "#ffb3b6", "#7a2a2f", "#3a1d21", "#4a3338",
    "#eebf5e", "#f4dda2", "#7d6427", "#7a5b2e", "#3a301a",              # warning
    "#6cc4e8", "#cfeafa", "#152f3b", "#1e546c", "#14313e",              # info
    "#b98a4e", "#a8793f", "#8a6b41",                                    # cases
}

TOKEN = re.compile(r'"(#[0-9a-fA-F]{6})"')


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


unknown = {}
total = 0
for name in sorted(os.listdir(VIEWS)):
    view_dir = os.path.join(VIEWS, name)
    view_file = os.path.join(view_dir, "view.json")
    if not os.path.isfile(view_file):
        continue
    raw = open(view_file, encoding="utf-8").read()

    n = [0]

    def swap(m):
        hexv = m.group(1).lower()
        if hexv in MAP:
            n[0] += 1
            return '"var(%s, %s)"' % (MAP[hexv], hexv)
        if hexv not in KEEP:
            unknown[hexv] = unknown.get(hexv, 0) + 1
        return m.group(0)

    out = TOKEN.sub(swap, raw)
    if n[0]:
        open(view_file, "w", encoding="utf-8").write(out)
        stamp(view_dir)
        total += n[0]
        print("  %-10s %3d colours -> theme tokens" % (name, n[0]))

print("%d neutral colours now follow the theme" % total)
if unknown:
    print("NOT mapped and NOT in the keep list - check these are deliberate:")
    for h, c in sorted(unknown.items(), key=lambda kv: -kv[1]):
        print("   %s x%d" % (h, c))
