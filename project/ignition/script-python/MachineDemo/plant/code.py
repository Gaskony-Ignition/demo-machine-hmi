"""
MachineDemo.plant - the cell's names, paths, constants and tag helpers.

One palletising cell, four robot zones, two pallet build stations. Everything
in the project that needs to know the provider name, a tag path, the machine's
geometry or its cycle budget reads it from here, so those facts appear once.

The provider name appears in exactly one place - PROVIDER - because a demo that
spells it out in forty bindings is a demo that cannot be renamed.
"""

VERSION = "1.7.2"

PROVIDER = "MachineDemo"

CELL_NAME = "Palletising Cell 1"
CELL_OWNER = "ACME Machine Works"
CELL_SUBTITLE = "Robotic case palletiser, two build stations"

LOG = system.util.getLogger("MachineDemo.plant")


def tag(path):
	"""A tag path in this demo's provider."""
	return "[%s]%s" % (PROVIDER, path)


# ---------------------------------------------------------------------------
# the machine
# ---------------------------------------------------------------------------
# These are the numbers the simulator, the setup notes and the screens all have
# to agree about. The pattern is 3 cases per pick, 4 picks to a layer, 5 layers
# to a pallet - so a nominal 12.6 s cycle is 14.3 cases a minute, which is what
# a mid-size case palletiser actually does.

CASES_PER_PICK = 3
SLOTS_PER_LAYER = 4
CASES_PER_LAYER = CASES_PER_PICK * SLOTS_PER_LAYER      # 12
LAYERS_PER_PALLET = 5
CASES_PER_PALLET = CASES_PER_LAYER * LAYERS_PER_PALLET  # 60

PATTERN_NAME = "5 x 12 interlock"

# Nominal pick-and-place cycle, in MACHINE seconds. SimSpeed is a multiplier on
# how fast machine time runs against the wall clock; it does not make the
# machine faster, so the reported cycle time and cases/min stay honest at any
# speed.
CYCLE_S = 12.6

# The cell's physical geometry - arm links, where the conveyor and the pallets
# are, how tall a case is - lives in MachineDemo.sim and only there, because it
# is only ever used by the IK solve. Two copies of a case height is how a
# palletiser comes to stack layers the arm cannot reach.

STATIONS = [1, 2]

ZONE_META = [
	("Z1", "Robot 1"),
	("Z2", "Robot 2"),
	("Z3", "Robot 3"),
	("Z4", "Robot 4"),
	("Z5", "Wrapper"),
	("Z6", "Shuttle"),
	("Z7", "Pallet Outfeed"),
	("Z8", "Tray Conveyors"),
]
ZONE_IDS = [z[0] for z in ZONE_META]
ZONE_NAME = dict(ZONE_META)

# The five faults a presenter can inject, in the order they read on a control
# strip: the two that stop the machine, then the two that stop the product,
# then the one that stops the pallet leaving.
FAULTS = ["GuardOpen", "RobotAxisFault", "VacuumLow", "ConveyorJam",
          "WrapperFilmFeed"]

FAULT_LABEL = {
	"GuardOpen": "Guard door open",
	"RobotAxisFault": "Robot axis following error",
	"VacuumLow": "Gripper vacuum low",
	"ConveyorJam": "Infeed carton jam",
	"WrapperFilmFeed": "Wrapper film feed fault",
}

# What each fault does to the cell. This is the demo's script, and it is here
# rather than buried in the simulator so a presenter can read it.
FAULT_EFFECT = {
	"GuardOpen": "Drops the guard circuit: motors off, robot HELD in place, "
	             "infeed and transfer conveyors stop.",
	"RobotAxisFault": "Robot faults on J3 and freezes. Motors off, the pallet "
	                  "stops building.",
	"VacuumLow": "Gripper vacuum collapses mid-carry. The robot faults rather "
	             "than drop the cases.",
	"ConveyorJam": "Carton jams on the infeed: C1 stops, the photo-eye stays "
	               "blocked and the robot starves.",
	"WrapperFilmFeed": "Wrapper cannot take a finished pallet, so completed "
	                   "pallets stop discharging. The cell keeps running on "
	                   "the other station until both are full.",
}

ROBOT_FAULT_TEXT = {
	"RobotAxisFault": "J3 servo following error - reset required at the pendant",
	"VacuumLow": "Gripper vacuum below hold threshold - cases at risk",
}


# ---------------------------------------------------------------------------
# tag reads and writes
# ---------------------------------------------------------------------------
# Every screen and every route reads through these, so a read is always one
# round trip and a bad-quality tag is always None rather than an exception that
# blanks a whole panel.


def read(paths):
	"""Read many tags at once, as plain Python values. Bad quality -> None."""
	full = [tag(p) for p in paths]
	try:
		qvs = system.tag.readBlocking(full)
	except:
		import traceback
		LOG.warn("read failed: %s" % traceback.format_exc())
		return [None] * len(paths)
	out = []
	for q in qvs:
		try:
			out.append(q.value if q.quality.isGood() else None)
		except:
			out.append(None)
	return out


def readOne(path, default=None):
	v = read([path])[0]
	return default if v is None else v


def readDict(mapping):
	"""{key: tagpath} -> {key: value}. One round trip."""
	keys = list(mapping.keys())
	vals = read([mapping[k] for k in keys])
	return dict(zip(keys, vals))


def write(mapping):
	"""{tagpath: value} -> written in one call. Never raises."""
	if not mapping:
		return 0
	keys = list(mapping.keys())
	try:
		system.tag.writeBlocking([tag(k) for k in keys],
		                         [mapping[k] for k in keys])
		return len(keys)
	except:
		import traceback
		LOG.warn("write failed: %s" % traceback.format_exc())
		return 0


def writePaths(paths, values):
	"""Parallel lists, for the simulator's hot path - no dict churn per tick."""
	if not paths:
		return 0
	try:
		system.tag.writeBlocking([tag(p) for p in paths], values)
		return len(paths)
	except:
		import traceback
		LOG.warn("write failed: %s" % traceback.format_exc())
		return 0


# ---------------------------------------------------------------------------
# alarms
# ---------------------------------------------------------------------------


def liveAlarms():
	"""This demo's standing alarms, newest first, as plain dicts.

	`source` is not optional and it is not a wildcard on the provider alone:
	queryStatus wants prov:<provider>:/tag:* - prov:<provider>:* silently
	matches nothing. Without the filter this counts every alarm on the gateway,
	which on a shared demo box is somebody else's plant.
	"""
	try:
		events = system.alarm.queryStatus(
			source=["prov:%s:/tag:*" % PROVIDER])
	except:
		import traceback
		LOG.warn("queryStatus failed: %s" % traceback.format_exc())
		return []
	out = []
	for e in events:
		out.append({
			"label": _field(e, lambda x: unicode(x.get("displayPath") or u""),
			                u""),
			"name": _field(e, lambda x: unicode(x.getName()), u"Alarm"),
			"priority": _field(e, lambda x: unicode(x.getPriority()), u""),
			"state": _field(e, lambda x: unicode(x.getState()), u""),
			"active": _field(e, lambda x: unicode(x.getState()).lower()
			                 .startswith("active"), False),
			"acked": _field(e, lambda x: bool(x.isAcked()), True),
			"source": _field(e, lambda x: unicode(x.getSource()), u""),
			"time": _field(e, lambda x: system.date.format(
				x.get("eventTime"), "HH:mm:ss"), u""),
		})
	out.sort(key=lambda a: (not a["active"], a["acked"], a["label"]))
	return out


def _field(event, fn, default):
	"""One accessor on one AlarmEvent, or the default.

	Each accessor is guarded SEPARATELY and not the row as a whole. Guarding
	the row means one accessor this gateway's build does not have - isActive()
	was the one - silently drops the entire alarm, and an alarm list that comes
	back EMPTY when eleven alarms are standing is the worst possible way to
	fail. Whether an event is active is read off its state string for the same
	reason: the string is on every 8.x build.
	"""
	try:
		return fn(event)
	except:
		return default


def alarmCounts():
	"""How many are active, and how many of those are unacknowledged."""
	active = 0
	unacked = 0
	for a in liveAlarms():
		if a["active"]:
			active += 1
			if not a["acked"]:
				unacked += 1
	return {"active": active, "unacked": unacked}
