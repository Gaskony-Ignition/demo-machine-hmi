#!/usr/bin/env python3
"""Call the two alarm views what everyone else calls them: Active and Historical.

The tabs said STANDING and JOURNAL. "Standing" is accurate - the alarm status
table holds alarms that are active OR cleared-but-not-yet-acknowledged, and
"standing" covers both - but it is not the word an operator arrives with.
Active and Historical are the pair every alarm system uses.

The word was in four user-visible places, and changing one of them would have
left the page arguing with itself:

  the tab labels                     STANDING / JOURNAL
  the pane headings                  "Standing alarms - active, or cleared..."
  the Overview alarm chip            "0 ACTIVE / 22 STANDING"
  the Overview alarm bar subtitle    "22 standing - 0 active - 3 unacknowledged"

The two Overview readouts counted the right things under the old vocabulary:
the second number is every row the status table holds, not the unacknowledged
subset. Under the new one that is "total", so they say total.

Nothing about WHAT is counted changes - only what it is called.

Idempotent. Run:  python3 tools/rename_alarm_tabs.py
"""

import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir))
VIEWS = os.path.join(ROOT, "project", "com.inductiveautomation.perspective",
                     "views", "Machine")


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


# --- Alarms: the tabs and the two pane headings ------------------------------
alarms_dir = os.path.join(VIEWS, "Alarms")
alarms_file = os.path.join(alarms_dir, "view.json")
alarms = json.load(open(alarms_file))

body = find(alarms["root"], "Body")
body["props"]["tabs"] = [{"text": "ACTIVE"}, {"text": "HISTORICAL"}]

# The tab component sizes every tab the SAME - it writes an identical
# `flex: 0 1 96px` inline on each one, sized once rather than per label - so a
# longer label is simply cut, with no ellipsis and no warning. Measured:
# HISTORICAL needs 78px of text room and the 96px tab gives 67. That is what
# forced the previous labels to be one short word each.
#
# The class lets the stylesheet widen them. It has to win against an INLINE
# flex, so that rule is one of the few places !important is genuinely required.
style = body["props"].setdefault("style", {})
classes = [c for c in style.get("classes", "").split() if c]
if "alm-tabs" not in classes:
    classes.append("alm-tabs")
    style["classes"] = " ".join(classes)

live, hist = body["children"][0], body["children"][1]
find(live, "H")["props"]["text"] = (
    u"Active alarms — and those cleared but not yet acknowledged")
find(hist, "H")["props"]["text"] = u"Historical — the alarm journal"

json.dump(alarms, open(alarms_file, "w"), indent=2)
stamp(alarms_dir)

# --- Overview: the chip and the alarm bar subtitle ---------------------------
# Both are inside script/expression strings, so they are edited as text. The
# replacements are exact and asserted, because a silent no-op here leaves the
# Overview saying STANDING under a tab that says ACTIVE.
overview_dir = os.path.join(VIEWS, "Overview")
overview_file = os.path.join(overview_dir, "view.json")
raw = open(overview_file, encoding="utf-8").read()

swaps = [
    (u'+ \\" STANDING\\"', u'+ \\" TOTAL\\"'),
    (u'\\"sub\\": \\"0 standing - 0 unacknowledged\\"',
     u'\\"sub\\": \\"0 alarms - 0 unacknowledged\\"'),
    (u'%d standing - %d active - %d unacknowledged',
     u'%d alarms - %d active - %d unacknowledged'),
]
for old, new in swaps:
    if new in raw and old not in raw:
        continue                      # already applied
    if raw.count(old) != 1:
        raise SystemExit("Overview: expected exactly one %r, found %d"
                         % (old, raw.count(old)))
    raw = raw.replace(old, new)

open(overview_file, "w", encoding="utf-8").write(raw)
stamp(overview_dir)

print("tabs are ACTIVE / HISTORICAL; Overview no longer says STANDING")
