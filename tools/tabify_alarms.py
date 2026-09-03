#!/usr/bin/env python3
"""Make Machine/Alarms a two-tab page: live alarms, and the journal.

WHY

Stacked, the two tables starve each other. Measured on the live page at
1443x541 - a real reviewer's window - the standing-alarms panel got 121px and
rendered TWO rows including the header, while the journal below held a fixed
330px basis. Nineteen unacknowledged alarms existed and not one of them could
be drawn. At 1920x1080 the same page is fine, which is exactly how this kind of
defect survives review.

Tabs give each table the whole body at every window size, and the tab strip
says which one you are looking at, so the shouty panel titles stop earning
their 31px.

A tab container with COMPONENT children binds a pane to its tab by
position.tabIndex and by NOTHING else - not order, not name. Omit it and every
tab past the first renders completely blank, with no error anywhere.

Idempotent. Run:  python3 tools/tabify_alarms.py
"""

import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
VIEW_DIR = os.path.join(HERE, os.pardir, "project",
                        "com.inductiveautomation.perspective", "views", "Machine", "Alarms")
VIEW = os.path.join(VIEW_DIR, "view.json")

INK, DIM, LINE, PANEL, ACCENT = "#dde4e9", "#8b98a3", "#2c343d", "#1d232a", "#6cc4e8"


def find(node, name):
    if node.get("meta", {}).get("name") == name:
        return node
    for c in node.get("children", []):
        hit = find(c, name)
        if hit:
            return hit
    return None


v = json.load(open(VIEW))
body = find(v["root"], "Body")
first_run = body["type"] != "ia.container.tab"
live, hist = find(body, "Live"), find(body, "Hist")

# Each pane fills its tab. The card border and radius were chrome for two
# stacked cards; inside a tab they are a box drawn around the whole screen.
for pane, idx in ((live, 0), (hist, 1)):
    pane["position"] = {"tabIndex": idx}
    st = pane.setdefault("props", {}).setdefault("style", {})
    for k in ("border", "borderRadius"):
        st.pop(k, None)
    st["height"] = "100%"
    st["minHeight"] = "0px"

body["type"] = "ia.container.tab"
# The component writes an IDENTICAL inline `flex: 0 1 <n>px` on every tab,
# sized to the widest one and not to each label - so a longer label is clipped
# with no ellipsis and no warning. "LIVE ALARMS" wanted 103px inside 94px and
# lost its S. Keep the labels one word, and keep the padding modest so the
# content box has slack. Both words here are the project's own vocabulary:
# the pane headers already say STANDING ALARMS and ALARM JOURNAL.
body["props"] = {
    "tabs": [{"text": "STANDING"}, {"text": "JOURNAL"}],
    "currentTabIndex": 0,
    # props.style alone leaves the tab strip stock grey - the strip, the tabs
    # and the content pane each take their own style object.
    "menuStyle": {"backgroundColor": PANEL, "borderBottom": "1px solid " + LINE},
    "tabStyle": {
        "inactive": {"color": DIM, "backgroundColor": "transparent", "fontWeight": 700,
                     "fontSize": "11px", "letterSpacing": "1.3px", "padding": "0 14px"},
        "active": {"color": "#cfeafa", "backgroundColor": "#152f3b", "fontWeight": 700,
                   "fontSize": "11px", "letterSpacing": "1.3px", "padding": "0 14px",
                   "borderBottom": "2px solid " + ACCENT},
    },
    "contentStyle": {"backgroundColor": "#171b20", "minHeight": "0px", "height": "100%"},
    "style": {"minHeight": "0px", "minWidth": "0px"},
}

# The journal defaulted to the last 8 hours and opened on "No results found":
# the demo's own most recent alarm was 10.5 hours old. A demo screen that is
# empty when you walk up to it is a defect whatever the query says.
j = find(v["root"], "Journal")
j["props"]["dateRange"] = {"realtime": {"interval": 24, "unit": "hours"}}
h = find(hist, "Hint")
if h is not None:
    h["props"]["text"] = "last 24 hours"

# Every standing row rendered on a blue that reads as a selection highlight,
# while the view's own rowStyles said transparent. The cause is a merge order,
# not a typo: the alarm status table applies a per-PRIORITY default background
# (a blue severity ramp - critical rgb(46,94,170), high rgb(80,122,191), medium
# rgb(113,152,214)) ON TOP of the state's base style. This view set
# backgroundColor on each state's `base` only, and left the `priorities`
# entries setting colour and weight alone - so the component's ramp won every
# time. Measured on the live page, 03/09/2026.
#
# Setting backgroundColor explicitly on every priority entry is what actually
# turns it off. Renaming the state keys (clearUnacked -> clearedUnacked) was
# tried first and changed nothing, which is how the merge order was found.
status = find(v["root"], "Status")
for state in status["props"].get("rowStyles", {}).values():
    for pri in state.get("priorities", {}).values():
        pri["backgroundColor"] = "transparent"

json.dump(v, open(VIEW, "w"), indent=2)
print("structural move: %s" % ("done" if first_run else "already tabbed, props refreshed"))
rp = os.path.join(VIEW_DIR, "resource.json")
r = json.load(open(rp))
r["attributes"]["lastModification"] = {"actor": "external",
    "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
r.pop("lastModificationSignature", None)
json.dump(r, open(rp, "w"), indent=2)
print("Alarms is now a two-tab page (journal window widened to 24h)")
