#!/usr/bin/env python3
"""Only an intentional list, table or text pane may scroll.

WHAT WAS WRONG

Perspective writes `overflow: auto` on every flex container that does not set
its own overflow, so a row whose label line box is 1px taller than the row
draws a scroll bar on Windows. Headless Chromium hides scroll bars, so every
"no page scroll" check passed while the operator saw bars in the panel
headers, the sign-in block and the CASES / MIN tile. Worse, at 1366x640 the
Overview rail, Manual's side columns and both Setup columns were simply taller
than the window and scrolled as whole columns, controls and all.

WHAT CHANGES

  Panel headers   Every 31px `Head` row: overflow hidden. Each holds labels
                  only; what overflows is the H label's own bottom border,
                  which sits under the Head's identical border.
  Overview        The rail no longer scrolls. CASES / MIN, SHIFT and the
                  START/STOP LINE buttons stay put; the eight zone cards go in
                  a `Zones` list that scrolls only on a short window. The
                  CASES / MIN tile gets the height its labels need, and SHIFT
                  twice the width of the rate, so a five-digit count fits.
  Manual          At 1366x640 the eight panels need ~1700px of column height
                  and three columns hold ~1400. Below 820px of window height
                  THIS USER MAY moves to a popup and MESSAGES to the Alarms
                  page (it is the same live alarm list), each behind a footer
                  button that only shows then. Above that both stay inline.
                  The columns stop scrolling; the pallet station list scrolls
                  on a short window, as a list.
  Setup           Two columns become three: install + gateway reply, then
                  simulation speed + running order, then the fault buttons.
                  The columns stop scrolling; the running-order steps and the
                  raw JSON reply are the only things that may.

tools/verify/scrollbar_sweep.js is the check, at 1366x640, 1600x900 and
1920x1080, popups included. Idempotent. Run:  python3 tools/fit_scrollbars.py
"""

import copy
import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
VIEWS = os.path.join(HERE, os.pardir, "project",
                     "com.inductiveautomation.perspective", "views", "Machine")
# The 820px switch for md-tall-only / md-short-only lives in the project
# stylesheet, as @media rules; the sweep's POPUPS entry knows it too.


def at(node, path):
    for name in path.split("/"):
        node = next((c for c in node.get("children", []) if c["meta"]["name"] == name), None)
        if node is None:
            return None
    return node


def style(node):
    return node.setdefault("props", {}).setdefault("style", {})


def no_scroll(node):
    s = style(node)
    for k in ("overflowY", "overflowX"):
        s.pop(k, None)
    s["overflow"] = "hidden"
    node.get("meta", {}).pop("tabIndex", None)


def add_class(node, cls):
    s = style(node)
    have = s.get("classes", "").split()
    if cls not in have:
        s["classes"] = " ".join(have + [cls])


def heads(node):
    if node.get("type") == "ia.container.flex" and node["meta"]["name"] == "Head":
        style(node)["overflow"] = "hidden"
    for c in node.get("children", []):
        heads(c)


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


def overview(root):
    rail = at(root, "Body/Rail")
    no_scroll(rail)
    style(rail).pop("paddingRight", None)
    cards = [c for c in rail["children"] if c["meta"]["name"].startswith("CardZ")]
    if cards:
        zones = {
            "type": "ia.container.flex",
            "meta": {"name": "Zones", "tabIndex": 0},
            "props": {"direction": "column", "style": {
                "gap": "7px", "overflowY": "auto", "overflowX": "hidden",
                "minWidth": "0px", "minHeight": "0px"}},
            "position": {"grow": 1, "shrink": 1, "basis": "0px"},
            "children": cards,
        }
        rail["children"] = [c for c in rail["children"] if c not in cards] + [zones]
    rate = at(rail, "Rate")
    rate["position"]["basis"] = "50px"
    no_scroll(rate)
    for side, grow in (("A", 1), ("B", 2)):
        col = at(rate, side)
        col["position"]["grow"] = grow
        at(col, "K")["position"]["basis"] = "14px"


def popup_button(name, text, script):
    return {
        "type": "ia.input.button",
        "meta": {"name": name},
        "props": {"text": text, "style": {
            "fontSize": "11px", "fontWeight": 700, "letterSpacing": "0.5px",
            "borderRadius": "6px", "border": "1px solid var(--md-line, #2c343d)",
            "backgroundColor": "transparent", "color": "var(--neutral-80, #b7c2ca)",
            "padding": "0 12px", "whiteSpace": "nowrap", "height": "28px",
            "classes": "md-short-only"}},
        "position": {"grow": 0, "shrink": 0, "basis": "auto"},
        "events": {"component": {"onActionPerformed": {
            "type": "script", "scope": "G", "config": {"script": script}}}},
    }


ACCESS_POPUP = (
    "\tsystem.perspective.openPopup('manualAccess', 'Machine/ManualAccess',"
    " title='This user may', modal=True,\n"
    "\t\tparams={'mayOperate': self.view.custom.mayOperate},\n"
    "\t\tshowCloseIcon=True, draggable=False, resizable=False,\n"
    "\t\tviewportBound=True, position={'width': 360, 'height': 230})\n")
OPEN_ALARMS = "\tsystem.perspective.navigate(page='/alarms')\n"


def manual(root):
    for col in ("Left", "Mid", "Right"):
        no_scroll(at(root, "Body/" + col))
    add_class(at(root, "Body/Left/Access"), "md-tall-only")
    add_class(at(root, "Body/Mid/Messages"), "md-tall-only")
    st = at(root, "Body/Right/Stations")
    st["position"].update({"grow": 1, "shrink": 1, "basis": "0px"})
    foot = at(root, "Footer")
    names = [c["meta"]["name"] for c in foot["children"]]
    i = names.index("S")
    for name, text, script in (("Messages", "OPEN ALARMS", OPEN_ALARMS),
                               ("Access", "THIS USER MAY", ACCESS_POPUP)):
        if name in names:
            foot["children"][names.index(name)] = popup_button(name, text, script)
        else:
            foot["children"].insert(i, popup_button(name, text, script))
            names.insert(i, name)
            i += 1
    return copy.deepcopy(at(root, "Body/Left/Access/Body"))


def access_popup(body):
    # The panel's own body, reading the role from a param instead of the
    # Manual view's custom prop. The popup is modal, so the role cannot change
    # under it while it is open.
    text = json.dumps(body).replace("view.custom.mayOperate", "view.params.mayOperate")
    body = json.loads(text)
    no_scroll(body)
    body["position"] = {"grow": 1, "shrink": 1, "basis": "0px"}
    return {
        "custom": {},
        "params": {"mayOperate": False},
        "propConfig": {"params.mayOperate": {"paramDirection": "input", "persistent": True}},
        "props": {"defaultSize": {"width": 360, "height": 250}},
        "root": {
            "type": "ia.container.flex",
            "meta": {"name": "root"},
            "props": {"direction": "column", "style": {
                "overflow": "hidden", "backgroundColor": "var(--md-panel, #1d232a)"}},
            "children": [body],
        },
    }


def setup(root):
    body = at(root, "Body")
    left, right = at(body, "Left"), at(body, "Right")
    no_scroll(left)
    no_scroll(right)
    at(left, "Status")["position"].update({"grow": 1, "shrink": 1, "basis": "0px"})
    at(left, "Status/Body/RawBox")["position"].update({"grow": 1, "shrink": 1, "basis": "60px"})
    at(right, "Faults")["position"]["grow"] = 1
    if at(body, "Side") is None:
        presenter = at(left, "Presenter")
        speed = at(right, "Speed")
        left["children"].remove(presenter)
        right["children"].remove(speed)
        presenter["position"].update({"grow": 1, "shrink": 1, "basis": "0px"})
        side = {
            "type": "ia.container.flex",
            "meta": {"name": "Side"},
            "props": {"direction": "column", "style": copy.deepcopy(style(right))},
            "position": {"grow": 0, "shrink": 0, "basis": "320px"},
            "children": [speed, presenter],
        }
        body["children"].insert(body["children"].index(right), side)
    # 320 leaves the four install buttons room for RESET DEMO on one line.
    at(body, "Side")["position"]["basis"] = "320px"
    # A step is as tall as its wrapped text. A fixed 48px drew a bar inside
    # any step whose note wraps to three lines at this width.
    for step in at(body, "Side/Presenter/Body")["children"]:
        step["position"].update({"grow": 0, "shrink": 0, "basis": "auto"})


def main():
    done = []
    for name in sorted(os.listdir(VIEWS)):
        view_dir = os.path.join(VIEWS, name)
        view_file = os.path.join(view_dir, "view.json")
        if not os.path.isfile(view_file):
            continue
        view = json.load(open(view_file))
        before = json.dumps(view, sort_keys=True)
        heads(view["root"])
        if name == "Overview":
            overview(view["root"])
        elif name == "Setup":
            setup(view["root"])
        elif name == "Manual":
            popup = access_popup(manual(view["root"]))
            pdir = os.path.join(VIEWS, "ManualAccess")
            pfile = os.path.join(pdir, "view.json")
            old = json.load(open(pfile)) if os.path.isfile(pfile) else None
            if old != popup:
                os.makedirs(pdir, exist_ok=True)
                json.dump(popup, open(pfile, "w"), indent=2)
                rfile = os.path.join(pdir, "resource.json")
                if not os.path.isfile(rfile):
                    json.dump({"scope": "G", "version": 1, "restricted": False,
                               "overridable": True, "files": ["view.json"],
                               "attributes": {"lastModification": {}}},
                              open(rfile, "w"), indent=2)
                stamp(pdir)
                done.append("ManualAccess")
        if json.dumps(view, sort_keys=True) != before:
            json.dump(view, open(view_file, "w"), indent=2)
            stamp(view_dir)
            done.append(name)
    print("scroll bars fitted in: %s" % (", ".join(done) or "nothing"))


if __name__ == "__main__":
    main()
