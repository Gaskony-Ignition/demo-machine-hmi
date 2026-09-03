#!/usr/bin/env python3
"""Bind the pallet capacity on Overview and Manual to the Config tags.

Both screens said "of 60 cases" and "/60 ... /5" as literals. With the
pattern now a pair of tags that the simulator and the 3D page follow, a
literal 60 is a number that is wrong the moment somebody changes them - the
one kind of defect a machine builder spots immediately, because it is the
screen contradicting the machine.

Run: python3 tools/bind_capacity.py
"""
import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
VIEWS = os.path.join(HERE, os.pardir, "project",
                     "com.inductiveautomation.perspective", "views", "Machine")

CAP = "toStr({[MachineDemo]Config/CasesPerLayer} * {[MachineDemo]Config/Layers})"
LAY = "toStr({[MachineDemo]Config/Layers})"

EDITS = {
    "Overview": [('"of 60 cases"', '"of " + ' + CAP + ' + " cases"')],
    "Manual": [('"/60   layer "', '"/" + ' + CAP + ' + "   layer "'),
               ('"/5"', '"/" + ' + LAY)],
}


def walk(node, fn):
    fn(node)
    for c in node.get("children", []) or []:
        walk(c, fn)


def stamp(view_dir):
    path = os.path.join(view_dir, "resource.json")
    r = json.load(open(path))
    mod = r.setdefault("attributes", {}).setdefault("lastModification", {})
    mod["actor"] = "external"
    mod["timestamp"] = datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    r.pop("lastModificationSignature", None)
    json.dump(r, open(path, "w"), indent=2)


for name, edits in EDITS.items():
    vdir = os.path.join(VIEWS, name)
    vfile = os.path.join(vdir, "view.json")
    view = json.load(open(vfile))
    hits = [0] * len(edits)

    def fix(node):
        for key, pc in (node.get("propConfig") or {}).items():
            b = pc.get("binding") or {}
            if b.get("type") != "expr":
                continue
            e = b["config"].get("expression", "")
            for i, (old, new) in enumerate(edits):
                if old in e:
                    e = e.replace(old, new)
                    hits[i] += 1
            b["config"]["expression"] = e

    walk(view["root"], fix)
    for (old, new), n in zip(edits, hits):
        print("%s: %s -> %d binding(s)" % (name, old, n))
    json.dump(view, open(vfile, "w"), indent=2)
    stamp(vdir)
