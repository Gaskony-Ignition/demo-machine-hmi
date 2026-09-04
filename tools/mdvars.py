#!/usr/bin/env python3
"""Hoist every literal colour in the views into a variable, so the light
themes can be offered without touching the dark ones.

WHY THIS EXISTS

`tools/themeify.py` mapped 568 colours onto the theme's `--neutral-N` tokens
and stopped there, because its regex only matches a prop whose WHOLE value is
a hex string. That left 849 more: inside `if(...)` expression bindings, inside
`1px solid #2c343d` shorthands, inside `repeating-linear-gradient(...)`, inside
alarm-table `rowStyles`, and inside Jython script transforms. Those are the
ones that made a light theme unusable - not the accents, but the SURFACES:
a card left at a literal #1d232a while its text followed a token to near-black
measures 1.06:1.

THE SHAPE, AND WHY IT IS THIS SHAPE

Every literal becomes `var(--md-NAME, #originalhex)`, and every `--md-NAME` is
defined so that **in a dark theme it computes to exactly the literal it
replaced**. Not approximately - exactly, by construction, and provably:

    --md-line: rgb(from var(--neutral-40, #2c343d)
        calc(44 + clamp(0, (r - 110) / 46, 1) * (r - 44))
        calc(52 + clamp(0, (r - 110) / 46, 1) * (g - 52))
        calc(61 + clamp(0, (r - 110) / 46, 1) * (b - 61)));

Read the clamp as a POLARITY: 0 when the theme is dark, 1 when it is light.
`--neutral-40` is #5E5E5E / #4D5358 / #565151 in the three dark themes (red
channel 77-94) and #BDBDBD / #A2A9B0 / #ADA8A8 in the three light ones (162-189).
The clamp saturates at 0 below 110 and at 1 above 156, so every dark theme
gives exactly 0 and every light theme exactly 1 - no rounding, no drift, no
theme-specific rule.

At polarity 0 the expression is the literal, character for character. At
polarity 1 it is `r g b` - the theme's own token, tint and all, so light-cool
gets the cool grey and light-warm the warm one. The two ends are what the
project needs and the middle never happens.

That is what makes this safe to ship: the reason light themes were never
offered is that adopting the theme tokens outright would have restyled the
three dark themes that are already in use. Pinning the dark end to the literal
removes that objection instead of arguing about it.

The four semantic accents cannot come from the neutral ramp - a green that
turned grey in a light theme would be a defect - so they use the same
mechanism with `--neutral-10` as the polarity source and a hand-picked light
value at the far end. Ignition's own `--success` / `--error` / `--warning` /
`--info` do flip correctly, and were rejected: adopting them changes the dark
themes (`--success` is #0AA648, the project's running green is #46d07c), which
is the one thing this change may not do.

Three properties worth keeping in mind:

  * NO THEME AT ALL still works. `var(--neutral-40, #2c343d)` falls back to
    the literal, whose red channel is 44, which clamps the polarity to 0,
    which yields the literal. The whole table degrades to today's colours.
  * NO RELATIVE-COLOUR SUPPORT still works. The `@supports` guard leaves the
    plain literal in place on a browser too old for `rgb(from ...)`.
  * The 568 references themeify.py already made are LEFT ALONE. Rewriting
    them would move them from the theme token back to the literal, which is
    a dark-theme change. They converge with this table under a light theme
    anyway, because both ends resolve to the same `--neutral-N`.

A colour computed this way serialises as `color(srgb 0.27 0.81 0.48)`, not
`rgb(70, 208, 124)`. It is the same colour; a checker that reads channels as
0-255 will report near-black. Both verify scripts in tools/verify/ parse it.

Idempotent, and it owns the generated block in stylesheet.css. Run:

    python3 tools/mdvars.py
"""

import datetime
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(HERE, os.pardir, "project",
                    "com.inductiveautomation.perspective")
VIEWS = os.path.join(PROJ, "views", "Machine")
SHEET_DIR = os.path.join(PROJ, "stylesheet")

# --- the polarity term, per neutral rung -------------------------------------
#
# Measured red channel of --neutral-N across the six stock themes:
#
#   rung   dark / dark-cool / dark-warm      light / light-cool / light-warm
#   10       22    18    23                    250   242   247
#   20       50    33    39                    244   221   229
#   30       81    52    60                    216   193   202
#   40       94    77    86                    189   162   173
#   50      118   105   115                    161   135   143
#   60      161   135   143                    118   105   115
#   70      189   162   173                     94    77    86
#   80      216   193   202                     81    52    60
#   90      244   221   229                     50    33    39
#  100      250   242   247                     22    18    23
#
# Rungs 10-50 are dark-low/light-high; 60-100 invert. Each expression is 0
# across the whole dark column and 1 across the whole light column, with the
# transition sitting in the gap between them. The 50/60 pair is the tight one
# - the ramp's middle rungs are only 17 points apart - so those two thresholds
# are placed exactly on the measured edges.
POLARITY = {
    10:  "clamp(0, (r - 100) / 56, 1)",
    20:  "clamp(0, (r - 100) / 56, 1)",
    30:  "clamp(0, (r - 100) / 56, 1)",
    40:  "clamp(0, (r - 110) / 46, 1)",
    50:  "clamp(0, (r - 118) / 17, 1)",
    60:  "clamp(0, (135 - r) / 17, 1)",
    70:  "clamp(0, (162 - r) / 52, 1)",
    80:  "clamp(0, (193 - r) / 100, 1)",
    90:  "clamp(0, (221 - r) / 100, 1)",
    100: "clamp(0, (242 - r) / 100, 1)",
}

# --- the table ---------------------------------------------------------------
#
# (dark hex, variable name, rung or light hex, what it is)
#
# An int is a NEUTRAL: the light end is the theme's own --neutral-<rung>, so
# it follows whichever light theme is loaded.
# A hex is a SEMANTIC: the light end is that value, chosen for contrast on a
# light ground and measured (see the sweep numbers in add_theme_picker.py).
# None means the colour is the same in both - cardboard is cardboard.
NEUTRAL = [
    ("#12171c", "bg-deep",     10, "the darkest ground, behind everything"),
    ("#171b20", "bg",          10, "page background"),
    ("#1d232a", "panel",       20, "panel"),
    ("#20262d", "card",        20, "zone card"),
    ("#22282f", "floor",       20, "mimic floor"),
    ("#232a31", "inset",       30, "inset / conveyor belt stripe"),
    ("#252c34", "face",        30, "button face, untinted"),
    ("#262e36", "well",        30, "track, well, lamp OFF"),
    ("#28313a", "block",       30, "nested block"),
    ("#2b323a", "grid",        30, "mimic grid line"),
    ("#2c343d", "line",        40, "the hairline border, 181 of them"),
    ("#38424c", "line-soft",   40, "border, Cell3D panels"),
    ("#39434b", "gate-off",    40, "gate lamp, down"),
    ("#39434c", "edge",        40, "zone card border / belt stripe"),
    ("#3a434b", "beam-off",    40, "photo-eye beam, clear"),
    ("#3b4650", "rule",        40, "divider on Overview"),
    ("#4a5560", "clamp-off",   50, "clamp lamp, retracted"),
    ("#5a646f", "joint",       50, "Cell2D arm joint"),
    ("#74808a", "ink-dim",     60, "dim text - captions, inactive counts"),
    ("#7d8894", "steel",       60, "Cell2D structure"),
    ("#8b98a3", "ink-quiet",   60, "secondary text"),
    ("#98a4b1", "steel-hi",    70, "Cell2D structure, lit face"),
    ("#aab3bd", "arm-2",       70, "Cell2D forearm"),
    ("#b7c2ca", "ink-soft",    80, "text on a tinted card"),
    ("#c8ced5", "arm",         80, "Cell2D upper arm"),
    ("#cdd6dd", "ink-mid",     80, "readout text"),
    ("#cfd8df", "ink-body",    80, "body text"),
    ("#d5dde3", "ink-strong",  90, "emphasised text"),
    ("#dde4e9", "ink",         90, "primary text"),
    ("#e6ebf0", "ink-cool",    90, "Cell2D primary text"),
    ("#e6eef4", "ink-bright",  90, "primary text, brightest"),
    ("#f2f6f8", "ink-max",    100, "maximum contrast text"),
]

SEMANTIC = [
    # running / OK green
    ("#46d07c", "run",          "#0e7038", "running, OK, beam made"),
    ("#5fd08a", "run-soft",     "#0d7d3e", "running, Cell2D readout"),
    ("#7ee2d2", "teal",         "#0a6b62", "throughput readout"),
    ("#bff0d2", "run-ink",      "#10502c", "text on a green button"),
    ("#2c7a4a", "run-line",     None,      "green button border"),
    ("#1c3b2a", "run-bg",       "#d8f0e2", "green button face"),
    ("#16261d", "run-bg-2",     "#e3f5ea", "green banner"),
    # fault red
    ("#f0565e", "fault",        "#c01a20", "fault, stopped, not OK"),
    ("#c2444c", "fault-line",   "#9e1a20", "fault card border"),
    ("#ff8d92", "fault-ink",    "#b3121a", "fault headline"),
    ("#e59aa0", "fault-ink-2",  "#a3363c", "fault detail"),
    ("#ffb3b6", "fault-ink-3",  "#8c1a20", "text on a red button"),
    ("#7a2a2f", "fault-edge",   None,      "red button border"),
    ("#4a3338", "fault-edge-2", "#d4b9bd", "faulted zone card border"),
    ("#3a1d21", "fault-bg",     "#f7dcde", "red button face"),
    ("#2e1a1d", "fault-bg-2",   "#f9e4e5", "faulted zone card"),
    # warning amber
    ("#eebf5e", "warn",         "#8f5c05", "warning, unacknowledged, gate up"),
    ("#f4dda2", "warn-ink",     "#6b4a05", "text on an amber button"),
    ("#7d6427", "warn-line",    None,      "amber button border"),
    ("#7a5b2e", "pallet",       None,      "pallet block in the mimic"),
    ("#3a301a", "warn-bg",      "#f6e9c9", "amber button face"),
    ("#2b2418", "warn-bg-2",    "#f8f0dc", "amber banner"),
    # info blue
    ("#6cc4e8", "info",         "#0d6f96", "info, selection, the active tab"),
    ("#9fdcf5", "info-ink",     "#0b5f81", "active toggle text"),
    ("#cfeafa", "info-ink-2",   "#0a4f6b", "text on a blue button"),
    ("#1e546c", "info-line",    None,      "blue button border"),
    ("#152f3b", "info-bg",      "#d6ecf7", "blue button face, active nav tab"),
    ("#14313e", "info-bg-2",    "#e0f0f9", "blue readout panel"),
    # the product. A carton is brown in every theme.
    ("#b98a4e", "case",         None,      "carton, lit face"),
    ("#a8793f", "case-alt",     None,      "carton, shaded face"),
    ("#8a6b41", "pallet-deck",  None,      "pallet deck"),
    ("#8d6836", "case-line",    None,      "carton outline"),
]

# Declared here but applied BY NAME - by a rule in stylesheet.css, or by SPOT
# below - rather than by substituting a literal. Both entries are dim text on
# a mid-grey surface, which is the one pairing Ignition's ramp does not carry
# into a light theme: --neutral-60 on --neutral-30 is 4.5:1 in the dark themes
# and 2.9:1 in light-cool and light-warm.
#
#   arrow      keeps whatever --neutral-60 gives it in the dark (it is one of
#              themeify.py's 568 already) and darkens the light end.
#   tab-quiet  is #b7c2ca, NOT the #8b98a3 it was first given. That was tuned
#              against dark-cool, whose toolbar is #343a3f: 4.3:1. The plain
#              dark theme puts the same tab on #515151, where #8b98a3 is
#              2.69:1 - so the first fix for this tab was itself theme-
#              specific, and only measuring all six themes found it.
BY_HAND = [
    ("#74808a", "arrow",     (60, "#4D5358"), "conveyor arrow on the mimic floor"),
    ("#b7c2ca", "tab-quiet", "#4D5358",       "inactive alarm-table toolbar tab"),
]

TABLE = NEUTRAL + SEMANTIC + BY_HAND
# Only the first two groups are reached by substituting a literal.
BY_HEX = {h: n for h, n, _, _ in NEUTRAL + SEMANTIC}

# Colours that have to move in a light theme and cannot be reached by hex,
# because they are already a var() and the literal is gone. Matched on the
# component's TEXT, which is what identifies these three - their component
# names are "A", "A" and "Flow".
#
# The three conveyor-direction arrows are --neutral-60 text sitting on the
# mimic floor, which is --neutral-30. That pairing is 4.5:1 in the dark themes
# and 2.94:1 in light-cool and light-warm: Ignition's ramp is not symmetric,
# and rungs 30 and 60 sit closer together at the light end than the dark.
# --md-arrow keeps exactly the dark value they have and darkens the light one.
SPOT = [("Overview", "\u25b6", "color", "var(--md-arrow, #74808a)")]

BEGIN = "/* === md colour table - generated by tools/mdvars.py, do not hand-edit"
END = "/* === end of the md colour table === */"


def channels(hexv):
    h = hexv.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def definition(hexv, spec):
    """The rgb(from ...) form: the literal at polarity 0, `spec` at 1."""
    if isinstance(spec, int):
        origin = "var(--neutral-%d, %s)" % (spec, hexv)
        t = POLARITY[spec]
        near = [str(c) for c in channels(hexv)]
        far = ["r", "g", "b"]
    elif isinstance(spec, tuple):
        rung, light = spec
        origin = "var(--neutral-%d, %s)" % (rung, hexv)
        t = POLARITY[rung]
        near = ["r", "g", "b"]
        far = [str(c) for c in channels(light)]
    else:
        origin = "var(--neutral-10, #171b20)"
        t = POLARITY[10]
        near = [str(c) for c in channels(hexv)]
        far = [str(c) for c in channels(spec)]
    return "rgb(from %s %s)" % (origin, " ".join(
        "calc(%s + %s * (%s - %s))" % (near[i], t, far[i], near[i])
        for i in range(3)))


def block():
    out = [BEGIN, "   Every value below is the ORIGINAL literal in a dark theme and the",
           "   theme's own colour in a light one - see the header of mdvars.py for",
           "   why that is provable rather than hoped for. === */",
           ":root {"]
    for group, title in ((NEUTRAL, "neutrals - the light end is the theme's own --neutral-N"),
                         (SEMANTIC, "semantics - the light end is a measured value"),
                         (BY_HAND, "applied by name, not by substituting a literal")):
        out.append("\t/* %s */" % title)
        for hexv, name, spec, what in group:
            base = ("var(--neutral-%d, %s);" % (spec[0], hexv)
                    if isinstance(spec, tuple) else hexv + ";")
            out.append("\t--md-%-18s %-9s /* %s */" % (name + ":", base, what))
    out.append("}")
    out.append("")
    out.append("/* Everything above is the dark value. Everything below makes it follow")
    out.append("   the theme, and is skipped whole on a browser without relative colour")
    out.append("   syntax - which leaves the project exactly as it renders today. */")
    out.append("@supports (color: rgb(from white r g b)) {")
    out.append("\t:root {")
    for hexv, name, spec, _what in TABLE:
        if spec is None:
            continue
        out.append("\t\t--md-%s: %s;" % (name, definition(hexv, spec)))
    out.append("\t}")
    out.append("}")
    out.append(END)
    return "\n".join(out)


# --- rewriting --------------------------------------------------------------
# A hex that is ALREADY the fallback of a var() is left alone: those are
# themeify.py's 568, and moving them would change the dark themes.
GUARD = re.compile(r'var\(\s*--[A-Za-z0-9-]+\s*,\s*#[0-9a-fA-F]{6}\s*\)')
HEX = re.compile(r'#[0-9a-fA-F]{6}\b')


def substitute(text):
    kept = []

    def hide(m):
        kept.append(m.group(0))
        return "\x00%d\x00" % (len(kept) - 1)

    text = GUARD.sub(hide, text)
    n = [0]
    missing = {}

    def swap(m):
        hexv = m.group(0).lower()
        name = BY_HEX.get(hexv)
        if not name:
            missing[hexv] = missing.get(hexv, 0) + 1
            return m.group(0)
        n[0] += 1
        return "var(--md-%s, %s)" % (name, hexv)

    text = HEX.sub(swap, text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], text)
    return text, n[0], missing


def spot(node, marker, prop, value, n):
    """Set one style prop on every component whose text is `marker`."""
    if isinstance(node, dict):
        props = node.get("props")
        if isinstance(props, dict) and props.get("text") == marker:
            style = props.setdefault("style", {})
            if style.get(prop) != value:
                style[prop] = value
                n[0] += 1
        for v in node.values():
            spot(v, marker, prop, value, n)
    elif isinstance(node, list):
        for v in node:
            spot(v, marker, prop, value, n)


def stamp(res_dir):
    path = os.path.join(res_dir, "resource.json")
    r = json.load(open(path))
    mod = r.setdefault("attributes", {}).setdefault("lastModification", {})
    mod["actor"] = "external"
    mod["timestamp"] = datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    r.pop("lastModificationSignature", None)
    mod.pop("lastModificationSignature", None)
    json.dump(r, open(path, "w"), indent=2)


def main():
    total = 0
    unknown = {}
    for name in sorted(os.listdir(VIEWS)):
        view_dir = os.path.join(VIEWS, name)
        view_file = os.path.join(view_dir, "view.json")
        if not os.path.isfile(view_file):
            continue
        raw = open(view_file, encoding="utf-8").read()
        out, n, missing = substitute(raw)
        for k, v in missing.items():
            unknown[k] = unknown.get(k, 0) + v
        spots = [0]
        for view, marker, prop, value in SPOT:
            if view == name:
                view_json = json.loads(out)
                spot(view_json, marker, prop, value, spots)
                if spots[0]:
                    out = json.dumps(view_json, indent=2)
        if out != raw:
            open(view_file, "w", encoding="utf-8").write(out)
            stamp(view_dir)
            total += n + spots[0]
            print("  %-10s %4d literals -> variables%s"
                  % (name, n, ", %d named" % spots[0] if spots[0] else ""))
        else:
            print("  %-10s already done" % name)

    sheet = os.path.join(SHEET_DIR, "stylesheet.css")
    css = open(sheet, encoding="utf-8").read()
    fresh = block()
    if BEGIN in css:
        head, rest = css.split(BEGIN, 1)
        tail = rest.split(END, 1)[1]
        new = head + fresh + tail
    else:
        # After the :root block that opens the file, before the first rule.
        marker = "\n}\n"
        i = css.index(marker) + len(marker)
        new = css[:i] + "\n" + fresh + "\n" + css[i:]
    if new != css:
        open(sheet, "w", encoding="utf-8").write(new)
        stamp(SHEET_DIR)
        print("  stylesheet %d variables" % len([t for t in TABLE]))

    print("%d literals now follow the theme" % total)
    if unknown:
        print("NOT in the table - add them or they stay literal:")
        for h, c in sorted(unknown.items(), key=lambda kv: -kv[1]):
            print("   %s x%d" % (h, c))


if __name__ == "__main__":
    main()
