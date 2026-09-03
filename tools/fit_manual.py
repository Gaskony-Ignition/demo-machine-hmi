#!/usr/bin/env python3
"""Stop the lift readouts wrapping over their own labels.

WHAT WAS WRONG

On the 10" panel the Lift card's POSITION and TARGET columns are 68px wide.
"1200.0 mm" set in 26px monospace needs 94px. Neither label had
`white-space: nowrap` - the MOTION readout beside them does - so the value
wrapped onto a second line, became a 64px-tall span inside a 32px box, and
bled upwards straight over the word POSITION.

Measured at 1024x600: value span 64px in a 32px box, 26px of horizontal
overflow, 14px of vertical overlap with the caption. At 1443x541 the same
columns are 278px wide, nothing wraps, and the card is fine - which is why
this only ever showed up on the panel size the demo argues for.

TWO CHANGES

1. nowrap on both value labels, so a value can never again grow the box it
   sits in. On its own this converts the overlap into a clip, which is less
   wrong but still wrong.

2. Below 1120px the MOTION readout goes, and the two numbers take the row.

   There is no font size that fits "2000.0 mm" into a 68px column and is
   still a readout - measured, it needs 141px at 26px and 76px even at 14px.
   The column is 68px because Manual is three columns wide and the two outer
   ones are FIXED at 330px and 340px, so on a 1024 panel they take 670px and
   the controls in the middle get 292px to share between three readouts.

   So on the panel the row drops to two: POSITION and TARGET take 139px each
   and set at 24px, where the widest reading measures 130px. MOTION is the
   one that can go - an operator holding a jog button does not need a label
   telling them the axis is jogging, and during a seek the target readout
   already says where it is going. FLAGGED FOR REVIEW: this is a judgement
   about what a 10" panel can carry, not a measurement.

3. MOTION's column is a fixed 128px and "JOGGING DOWN" measures 132px at
   15px, so it was clipped by 4px at EVERY window size - only while jogging
   down, which is why it survived. 136px now.

Idempotent. Run:  python3 tools/fit_manual.py
"""

import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
VIEW = os.path.join(HERE, os.pardir, "project",
                    "com.inductiveautomation.perspective", "views",
                    "Machine", "Manual")


def find(node, name):
    if node.get("meta", {}).get("name") == name:
        return node
    for child in node.get("children", []) or []:
        hit = find(child, name)
        if hit:
            return hit
    return None


view_file = os.path.join(VIEW, "view.json")
view = json.load(open(view_file))

vals = find(view["root"], "Vals")
if vals is None:
    raise SystemExit("Manual has no Vals row - the layout changed")

# MOTION was 4px narrower than its own longest word at every window size.
jog = find(vals, "JogInd")
jog["position"]["basis"] = "136px"
style = jog.setdefault("props", {}).setdefault("style", {})
classes = [c for c in style.get("classes", "").split() if c]
if "jog-ind" not in classes:
    classes.append("jog-ind")
style["classes"] = " ".join(classes)

touched = []
for column in ("Pos", "Tgt"):
    value = find(find(vals, column), "V")
    style = value["props"]["style"]
    style["whiteSpace"] = "nowrap"
    classes = [c for c in style.get("classes", "").split() if c]
    if "lift-val" not in classes:
        classes.append("lift-val")
    style["classes"] = " ".join(classes)
    touched.append(column)

json.dump(view, open(view_file, "w"), indent=2)

res_file = os.path.join(VIEW, "resource.json")
res = json.load(open(res_file))
mod = res.setdefault("attributes", {}).setdefault("lastModification", {})
mod["actor"] = "external"
mod["timestamp"] = datetime.datetime.now(
    datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
res.pop("lastModificationSignature", None)
mod.pop("lastModificationSignature", None)
json.dump(res, open(res_file, "w"), indent=2)

print("lift readouts fixed: %s, MOTION column widened" % ", ".join(touched))
