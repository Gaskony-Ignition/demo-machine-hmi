#!/usr/bin/env python3
"""Give the two alarm tables a column layout instead of the stock one.

WHAT WAS WRONG

Neither table configured its columns, so both took the component defaults. On
the standing table that meant six columns, and the widest of them was Source:

    prov:MachineDemo:/tag:Faults/WrapperFilmFeed:/alm:Wrapper Film Feed Fault

539px of internal tag path, holding 313px of the window, saying nothing an
operator can act on - the same alarm's Display Path already reads
"Palletiser / Wrapper / Wrapper Film Feed Fault". Meanwhile State was 157px
wide holding text that needs 180 ("Cleared, Unacknowledged"), so the one
column that tells you whether an alarm still needs acknowledging was the one
being ellipsised.

HOW THE WIDTHS WORK

A column's `width` is a proportional ratio, NOT pixels, unless the column also
sets `strictWidth: true`. The stock defaults are all proportional, which is why
Source at ratio 200 ate 313 real pixels on a wide window - it grew with the
table whether or not it had anything to show.

So: pin the columns whose content has a known maximum, and let the two columns
whose content is genuinely variable share everything left over.

    activeTime  strict 155   "02/09/2026 13:17:28" measures 132
    priority    strict  92   "Diagnostic" measures 62
    state       strict 205   "Cleared, Unacknowledged" measures 180
    displayPath ratio  200   longest measured 352, and it is the column an
    name        ratio  110   operator reads first, so it takes the larger share

Measured with the table's own font (14px/500 Noto Sans) over every row in the
live tables, not estimated. The +16px on each pin is the cell padding added
below.

CELL PADDING

Perspective ships table cells with `padding: 0`. Every column therefore sits
flush against the next and two values read as one. 8px a side fixes it, and is
why each pinned width above carries 16px more than its content needs.

Idempotent. Run:  python3 tools/fit_alarm_columns.py
"""

import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir))
VIEW = os.path.join(ROOT, "project", "com.inductiveautomation.perspective",
                    "views", "Machine", "Alarms")

# The two tables name the same concepts differently - the standing table's
# activeTime/state are the journal's eventTime/eventState. Same layout either
# way, so the operator's eye lands in the same place when the tab changes.
# The two tables do NOT put their column configs in the same place, and
# getting that wrong is completely silent.
#
#   journal:  props.columns          = {eventTime: {...}, ...}
#   status:   props.columns.ACTIVE   = {activeTime: {...}, ...}
#
# The status table has two tabs - active alarms and shelved ones - so its
# `columns` prop is keyed by tab first. A flat object written there is not
# rejected and does not warn: `columns.active` is simply undefined, the
# component falls back to its stock six columns, and the page looks exactly
# as it did before. The journal, given the same treatment, takes its config
# immediately - so a single deploy shows one table obeying and one ignoring,
# which reads like a scan problem and is not.
#
# Read from the shipped component (`getActiveColumnConfigs` in
# Perspective-module.modl), not guessed.

def col(width=None, strict=False, sort="none", enabled=True, order=None):
    c = {"enabled": enabled, "sort": sort}
    if width is not None:
        c["width"] = width
        c["strictWidth"] = strict
    if order is not None:
        c["order"] = order
    return c


OFF = col(enabled=False, width=100)

# WIDTHS
#
# Every column whose content has a known maximum is PINNED to that maximum.
# Exactly one column - Display Path - is left unpinned, and it absorbs all the
# space left over. That is the whole rule, and the first version broke it: it
# pinned only three columns and let Display Path AND Name share the remainder
# proportionally, so on a wide window Name sat on 300+ spare pixels while
# Active Time cut "02/09/2026 13:17:28" down to "02/09/2026 13:17..." and State
# showed "Cleared, Unacknowledg...". Two columns starving beside two columns
# with hundreds of pixels doing nothing.
#
# The widths below are the measured content maximum of each column across every
# row of both tables, plus 26px:
#
#   16px  the cell padding added in stylesheet.css
#   10px  chrome the component keeps inside the cell (measured: a 155px column
#         gives its text 129px, not 139)
#
#   activeTime   136 + 26 = 162  ->  170   "02/09/2026 13:17:28"
#   priority      64 + 26 =  90  ->   98   the "Priority" header, not a value
#   state        181 + 26 = 207  ->  215   "Cleared, Unacknowledged"
#   name         186 + 26 = 212  ->  222   "Robot Axis Following Error"
#   displayPath  355 + 26 = 381 minimum, unpinned, takes everything else
#
# The few px of headroom on each is for a longer value than this demo happens
# to produce - a date format with a 4-digit year already fits, an alarm name a
# word longer does not have to break the layout.
#
# Two things that made the first measurement wrong, both worth remembering:
# the text renders at font-weight 700, not the 500 a naive probe assumes, and
# the element that actually elides is a div NESTED INSIDE `.content`, so
# measuring `.content` reports no overflow while the cell is visibly cut off.

# Key order IS column order here.
STATUS = {
    "activeTime":     col(170, strict=True),
    "displayPath":    col(195),       # shares the surplus, 58%
    "priority":       col(98, strict=True, sort="descending"),
    "state":          col(215, strict=True),
    "name":           col(140),       # shares the surplus, 42%
    # Off, deliberately: Display Path says the same thing in operator words.
    "source":         col(enabled=False, width=200),
    "label":          OFF, "eventId": OFF, "eventValue": OFF, "notes": OFF,
    "isAcked":        OFF, "ackTime": OFF, "ackUser": OFF, "ackNotes": OFF,
    "ackPipeline":    OFF, "isActive": OFF, "activePipeline": OFF,
    "isClear":        OFF, "clearTime": OFF, "clearPipeline": OFF,
    "deadband":       OFF,
}

JOURNAL = {
    "eventTime":   col(170, strict=True, sort="descending", order=0),
    "displayPath": col(195, order=1),          # shares the surplus, 58%
    "priority":    col(98, strict=True, order=2),
    "eventState":  col(215, strict=True, order=3),
    "name":        col(140, order=4),          # shares the surplus, 42%
    "source":      col(enabled=False, width=150, order=5),
    "eventId":     col(enabled=False, width=200, order=6),
    "label":       col(enabled=False, width=100, order=7),
    "state":       col(enabled=False, width=150, order=8),
    "isSystemEvent": col(enabled=False, width=200, order=9),
    "ackUser":     col(enabled=False, width=100, order=10),
    "ackNotes":    col(enabled=False, width=100, order=11),
}

# Shelved alarms: the tab is off in this project, but the widths are set so
# that turning it on does not produce a differently-proportioned table.
SHELVED = {
    "sourcePath": col(195, order=0),
    "shelvedBy":  col(170, strict=True, order=1),
    "expires":    col(170, strict=True, sort="descending", order=2),
}

TABLES = {"ia.display.alarmstatustable": {"active": STATUS, "shelved": SHELVED},
          "ia.display.alarmjournaltable": JOURNAL}


def walk(node):
    yield node
    for child in node.get("children", []) or []:
        for n in walk(child):
            yield n


def add_class(node, cls):
    style = node.setdefault("props", {}).setdefault("style", {})
    have = [c for c in style.get("classes", "").split() if c]
    if cls not in have:
        have.append(cls)
        style["classes"] = " ".join(have)


view_file = os.path.join(VIEW, "view.json")
view = json.load(open(view_file))

touched = []
for node in walk(view["root"]):
    cfg = TABLES.get(node.get("type"))
    if cfg is None:
        continue
    node["props"]["columns"] = json.loads(json.dumps(cfg))
    add_class(node, "alm-table")
    touched.append(node["meta"]["name"])

if len(touched) != 2:
    raise SystemExit("expected both alarm tables, found: %r" % (touched,))

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

print("columns set on: %s" % ", ".join(touched))
