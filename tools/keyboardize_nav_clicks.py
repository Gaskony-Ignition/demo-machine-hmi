#!/usr/bin/env python3
"""WCAG 2.1 AA 2.1.1: every `nav`-type onClick in the project becomes
reachable by Tab and fires on Enter/Space, not just the shared nav bar
`tools/add_nav_tab.py` clones. Overview's mimic zones and zone-card arrows
navigate to Manual/Alarms the same way but are hand-authored, not generated
- this script is their equivalent of "fix the generator": walk every
view.json, and for every `events.dom.onClick` of type `nav` with no
`meta.tabIndex` yet, add the same tabIndex + onKeyDown pattern
`add_nav_tab.py` uses. Idempotent - a component already carrying tabIndex
is left alone, so this is also safe to run after add_nav_tab.py, or on a
view neither script has touched.

Run:  python3 tools/keyboardize_nav_clicks.py
"""
import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
VIEWS = os.path.join(HERE, os.pardir, "project",
                     "com.inductiveautomation.perspective", "views", "Machine")


def keyboard_nav(component, page):
    component.setdefault("meta", {})["tabIndex"] = 0
    dom = component.setdefault("events", {}).setdefault("dom", {})
    dom["onKeyDown"] = {
        "type": "script", "scope": "G",
        "config": {"script": (
            "\tif event.key in ('Enter', ' '):\n"
            "\t\tsystem.perspective.navigate(page='%s')" % page
        )},
    }


def already_fixed(node):
    if "tabIndex" not in node.get("meta", {}):
        return False
    kd = node.get("events", {}).get("dom", {}).get("onKeyDown", {})
    # scope "C" is last build's bug (silent "Client Action 'script' not
    # registered" - never actually reaches the client): not fixed.
    return kd.get("scope") == "G"


def fix(node, changed):
    onclick = node.get("events", {}).get("dom", {}).get("onClick")
    if (isinstance(onclick, dict) and onclick.get("type") == "nav"
            and not already_fixed(node)):
        page = onclick.get("config", {}).get("page")
        if page:
            keyboard_nav(node, page)
            changed[0] += 1
    for child in node.get("children", []):
        fix(child, changed)


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


def main():
    total = 0
    for name in sorted(os.listdir(VIEWS)):
        view_dir = os.path.join(VIEWS, name)
        view_file = os.path.join(view_dir, "view.json")
        if not os.path.isfile(view_file):
            continue
        before = open(view_file, encoding="utf-8").read()
        view = json.loads(before)
        changed = [0]
        fix(view["root"], changed)
        if changed[0]:
            after = json.dumps(view, indent=2)
            open(view_file, "w", encoding="utf-8").write(after)
            stamp(view_dir)
            total += changed[0]
            print("  %-10s %d nav click(s) made reachable" % (name, changed[0]))
        else:
            print("  %-10s already reachable" % name)
    print("%d nav click(s) fixed" % total)


if __name__ == "__main__":
    main()
