#!/usr/bin/env python3
"""Make the top bar survive a 1024x600 panel.

Titles is the only flex item in the header with shrink:1, so every pixel the
header is short comes out of it and nothing else. Six nav tabs pushed it past
the point where that was survivable and the line name rendered as "Pa".

Three changes, applied to every view that has the nav bar:

  1. The title drops "- Overview". The active tab already says which page you
     are on, so the suffix was costing 135px to repeat something on screen.
  2. Titles gets a floor (minWidth + a real basis) so it can never collapse
     to nothing again, whatever else lands in the header later.
  3. Title, subtitle and tabs get style classes so the project stylesheet can
     shed the subtitle and tighten the tabs below 1320px. The subtitle's inline
     `display: block` is removed - an inline style beats a class, and the only
     way to win that from CSS is !important, which is worth avoiding when you
     own the JSON and can simply not set it.

Idempotent. Run:  python3 tools/fit_header.py
"""

import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
VIEWS = os.path.join(HERE, os.pardir, "project",
                     "com.inductiveautomation.perspective", "views", "Machine")

TITLE_WAS = u"Palletising Line 1 — Overview"
TITLE_NOW = u"Palletising Line 1"


def find(node, name):
    if node.get("meta", {}).get("name") == name:
        return node
    for child in node.get("children", []):
        hit = find(child, name)
        if hit:
            return hit
    return None


def add_class(node, cls):
    style = node.setdefault("props", {}).setdefault("style", {})
    have = [c for c in style.get("classes", "").split() if c]
    if cls not in have:
        have.append(cls)
    style["classes"] = " ".join(have)


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


touched = []
for name in sorted(os.listdir(VIEWS)):
    view_dir = os.path.join(VIEWS, name)
    view_file = os.path.join(view_dir, "view.json")
    if not os.path.isfile(view_file):
        continue

    view = json.load(open(view_file))
    nav = find(view["root"], "Nav")
    if nav is None:
        continue

    titles = find(view["root"], "Titles")
    t = find(view["root"], "T")
    s = find(view["root"], "S")

    # 1. the title no longer repeats the active tab
    if t is not None and t["props"].get("text", "").endswith(u"— Overview"):
        t["props"]["text"] = TITLE_NOW

    # 2. a floor, so a future seventh tab cannot collapse it again
    if titles is not None:
        titles["props"]["style"]["minWidth"] = "132px"
        titles["position"]["basis"] = "132px"

    # 3. classes for the responsive rules
    if t is not None:
        add_class(t, "hdr-title")
        t["props"]["style"].pop("fontSize", None)   # the class owns the size now
    if s is not None:
        add_class(s, "hdr-sub")
        s["props"]["style"].pop("display", None)    # or the class cannot hide it
    for tab in nav.get("children", []):
        add_class(tab, "nav-tab")

    # The chips and the user block also give ground below 1320px. Their inline
    # font sizes and padding have to come out or the class cannot win.
    bar = find(view["root"], "TopBar")
    if bar is not None:
        add_class(bar, "hdr-bar")
        bar["props"]["style"].pop("gap", None)
        bar["props"]["style"].pop("padding", None)

    chips = find(view["root"], "Chips")
    for chip in (chips or {}).get("children", []):
        add_class(chip, "hdr-chip")
        chip["props"]["style"].pop("fontSize", None)
        chip["props"]["style"].pop("padding", None)
        chip["props"]["style"].pop("letterSpacing", None)
    # Separate classes, not an adjacent-sibling selector: Perspective is free
    # to wrap each label in its own div, and "+" would then match nothing.
    for who, cls in (("Name", "hdr-user"), ("Role", "hdr-user-sub")):
        el = find(view["root"], who)
        if el is not None:
            add_class(el, cls)
            el["props"]["style"].pop("fontSize", None)

    json.dump(view, open(view_file, "w"), indent=2)
    stamp(view_dir)
    touched.append(name)

print("header fitted in: %s" % (", ".join(touched) or "nothing"))
