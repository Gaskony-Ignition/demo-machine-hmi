"""
MachineDemo.api - the state snapshot, and the presenter's controls.

`state()` is polled four times a second by the 3D cell page, so it is built the
only way that can survive that: ONE system.tag.readBlocking of a path list that
is computed once at module load, then plain indexing. No browsing, no
per-property reads, no queries. The list and the response shape are frozen -
the 3D page is written against them.

Everything else here is what a presenter needs during a live meeting: inject a
fault, clear it, change the speed, get back to steady state. The fault commands
write the Faults/* tags and nothing else, because the simulator reads those
tags every tick - so the route, the Designer and an operator screen all drive
the cell by exactly the same mechanism.
"""

from java.lang import System as JSystem

P = MachineDemo.plant
LOG = system.util.getLogger("MachineDemo.api")


# ---------------------------------------------------------------------------
# the snapshot
# ---------------------------------------------------------------------------
# Built once at module load: the cost of a poll is one round trip and a list
# index, and the ORDER below is the only thing keeping the two halves in step,
# so the reader and the writer are deliberately next to each other.

LINE = ["Line/Running", "Line/Mode", "Line/CasesPerMin", "Line/CycleTime_s",
        "Line/CasesTotal", "Line/ShiftTarget"]

# APPEND ONLY. The offsets below are positional, and the 3D page reads this
# shape - so a new tag goes on the end and nothing existing ever moves.
ROBOT = ["Robot/State", "Robot/J1_deg", "Robot/J2_deg", "Robot/J3_deg",
         "Robot/J4_deg", "Robot/Lift_mm", "Robot/GripperClosed",
         "Robot/Vacuum_kPa", "Robot/CycleCount", "Robot/Fault",
         "Robot/FaultText",
         "Robot/JogUp", "Robot/JogDown", "Robot/LiftTarget_mm"]

STATION = ["Present", "CasesPlaced", "Layer", "Complete", "PatternName"]

CONV = ["Conveyor/C1_Run", "Conveyor/C2_Run", "Conveyor/C3_Run",
        "Conveyor/PE_Infeed", "Conveyor/PE_Carton", "Conveyor/PE_Length1",
        "Conveyor/PE_Length2", "Conveyor/PE_InPos1", "Conveyor/PE_InPos2",
        "Conveyor/PE_Clear", "Conveyor/Gate1_Up", "Conveyor/Gate2_Up",
        "Conveyor/Clamp_Extended", "Conveyor/LastBarcode",
        "Conveyor/ScanOK"]

SAFETY = ["Safety/EStopOK", "Safety/GuardsClosed", "Safety/AirPressureOK",
          "Safety/InterfacesOK"]

FAULTS = ["Faults/%s" % n for n in
          ["WrapperFilmFeed", "ConveyorJam", "VacuumLow", "GuardOpen",
           "RobotAxisFault"]]

# The 3D page's geometry. Tag name -> (response key, default). The defaults
# are today's page geometry, from docs/CONTRACT.md - if a Config tag does not
# exist yet (agent A has not deployed it) or reads bad quality, the page must
# still get a complete block, never a hole.
CONFIG = [
	("Config/CaseW_mm", "caseW_mm", 300),
	("Config/CaseD_mm", "caseD_mm", 250),
	("Config/CaseH_mm", "caseH_mm", 220),
	("Config/PalletW_mm", "palletW_mm", 1200),
	("Config/PalletD_mm", "palletD_mm", 1000),
	("Config/PalletH_mm", "palletH_mm", 140),
	("Config/CasesPerLayer", "casesPerLayer", 12),
	("Config/Layers", "layers", 5),
	("Config/ConvHeight_mm", "convHeight_mm", 900),
	("Config/ConvLength_mm", "convLength_mm", 3300),
	("Config/ConvWidth_mm", "convWidth_mm", 620),
	("Config/Station1_X_mm", "station1X_mm", -1450),
	("Config/Station1_Z_mm", "station1Z_mm", -1650),
	("Config/Station2_X_mm", "station2X_mm", -1450),
	("Config/Station2_Z_mm", "station2Z_mm", 1650),
]

_PLAN = None

# Quality is judged stale after this many milliseconds with no fresh write.
# The contract calls for ">5s"; the simulator ticks every 500ms, so 5000ms is
# ten missed ticks - long enough that ordinary poll jitter or a slow gateway
# never trips it, short enough that a presenter watching the page sees the
# banner inside about a second of the sim actually stopping (the 250ms poll
# plus this margin).
STALE_AFTER_MS = 5000


def _plan():
	"""(paths, offsets), built once and cached.

	Built lazily rather than at module load: a project script module that
	touches a SIBLING module while it is itself being imported depends on the
	order the script manager happens to load them in, and that order is not
	something a project gets to choose.
	"""
	global _PLAN
	if _PLAN is not None:
		return _PLAN
	zones = []
	for z in P.ZONE_IDS:
		zones += ["Zones/%s/Name" % z, "Zones/%s/State" % z,
		          "Zones/%s/Running" % z, "Zones/%s/Fault" % z]
	pallet = []
	for n in P.STATIONS:
		pallet += ["Pallet/Station%d/%s" % (n, k) for k in STATION]

	config = [c[0] for c in CONFIG]
	groups = [("line", LINE), ("robot", ROBOT), ("pallet", pallet),
	          ("conv", CONV), ("safety", SAFETY), ("faults", FAULTS),
	          ("zones", zones), ("config", config)]
	paths = []
	off = {}
	for name, group in groups:
		off[name] = len(paths)
		paths += group
	off["_pallet"] = pallet
	off["_zones"] = zones
	_PLAN = (paths, off)
	return _PLAN


def _f(v, default=0.0):
	try:
		return round(float(v), 1)
	except:
		return default


def _i4(v):
	try:
		return int(v)
	except:
		return 0


def _b(v):
	return bool(v)


def _s(v):
	return u"" if v is None else unicode(v)


def _ci(v, default):
	"""One Config/* value as an int, or the contract default.

	Covers both holes: the tag does not exist yet (P.read() -> None) and the
	tag exists but reads something that will not convert (bad quality already
	came back as None from P.read(), so this is really just belt-and-braces).
	"""
	if v is None:
		return default
	try:
		return int(v)
	except:
		return default


def _readQ(paths):
	"""Read many tags at once, exactly like plant.read(), but keep the
	QualifiedValue instead of collapsing it straight to a value-or-None.

	plant.read() is not ours to change, and adding a second readBlocking
	call beside it would make every poll pay for two round trips instead of
	one just to see what plant.read() already saw and threw away. So this is
	a sibling of plant.read() living in api, not an edit to plant.py: same
	call shape, same "bad quality reads back None" behaviour for the values,
	but it also hands back the QualifiedValue list so the caller can look at
	quality and timestamp.
	"""
	full = [P.tag(p) for p in paths]
	try:
		qvs = system.tag.readBlocking(full)
	except:
		import traceback
		LOG.warn("read failed: %s" % traceback.format_exc())
		return [None] * len(paths), [None] * len(paths)
	vals = []
	for q in qvs:
		try:
			vals.append(q.value if q.quality.isGood() else None)
		except:
			vals.append(None)
	return vals, list(qvs)


def _quality(paths, qvs):
	"""The `quality` block for ?cmd=state - additive, alongside the frozen
	shape below, never inside it.

	Every tag in this demo is a standard/memory tag with no OPC device behind
	it (the simulator writes them directly), so `bad` - built from each
	QualifiedValue's own quality.isGood() - is the check for a tag that was
	deleted, renamed, or never created: it will almost never fire from the
	simulator merely being stopped, because writeBlocking leaves a memory
	tag's quality Good forever, changing only its timestamp.

	That is exactly the dangerous case docs/CONTRACT.md describes: a frozen
	arm position that still reads Good. So `stale` is judged separately, off
	the AGE of the NEWEST timestamp across every tag in this same read -
	directly measuring "the simulator, as a whole, has not written for more
	than 5s", the contract's own wording, rather than "one particular tag
	has not changed".

	A single representative tag was tried first and measured wrong: Robot/
	CycleCount only advances once per ~12s pick-and-place cycle, and a
	memory tag's timestamp does not move on a write that repeats the same
	value (measured on this gateway, 02/09/2026 - CycleCount alone flagged a
	healthy, moving robot "stale" for several seconds out of every cycle).
	Taking the max across the whole snapshot fixes that for free: something
	in an 8-node, ~90-tag cell (a joint angle, a photo-eye, a case count) is
	all but certain to have moved within the last tick whenever the
	simulator is genuinely running, and only truly freezes when the whole
	tree does.
	"""
	bad = []
	worst_name = u"Good"
	worst_rank = 2   # 0 Bad, 1 Uncertain, 2 Good - lower is worse
	newest = None
	for path, qv in zip(paths, qvs):
		if qv is None:
			bad.append(path)
			if worst_rank > 0:
				worst_rank = 0
				worst_name = u"Bad_Failure"
			continue
		try:
			q = qv.quality
			good = q.isGood()
		except:
			bad.append(path)
			if worst_rank > 0:
				worst_rank = 0
				worst_name = u"Bad_Failure"
			continue
		if not good:
			bad.append(path)
		rank = 2
		try:
			if q.isBad():
				rank = 0
			elif q.isUncertain():
				rank = 1
		except:
			rank = 0
		if rank < worst_rank:
			worst_rank = rank
			worst_name = unicode(q)
		try:
			if qv.timestamp is not None:
				t = qv.timestamp.getTime()
				if newest is None or t > newest:
					newest = t
		except:
			pass

	stale = True
	if newest is not None:
		age = JSystem.currentTimeMillis() - newest
		stale = age > STALE_AFTER_MS

	return {
		"ok": (not bad) and (not stale),
		"bad": bad,
		"stale": stale,
		"worst": worst_name,
	}


def state():
	"""The whole cell in one dict, in the shape the 3D page is written against.

	Shape is FROZEN. Adding keys is safe; renaming, reordering the pallet list
	or changing a type is not - the page reads j1..j4 and lift straight into a
	scene graph and a null there stops the animation rather than logging.
	"""
	paths, o = _plan()
	v, qvs = _readQ(paths)

	line = v[o["line"]:o["line"] + len(LINE)]
	rb = v[o["robot"]:o["robot"] + len(ROBOT)]
	cv = v[o["conv"]:o["conv"] + len(CONV)]
	sf = v[o["safety"]:o["safety"] + len(SAFETY)]
	fl = v[o["faults"]:o["faults"] + len(FAULTS)]
	pl = v[o["pallet"]:o["pallet"] + len(o["_pallet"])]
	zn = v[o["zones"]:o["zones"] + len(o["_zones"])]
	cf = v[o["config"]:o["config"] + len(CONFIG)]

	pallets = []
	for k in range(len(P.STATIONS)):
		b = k * len(STATION)
		pallets.append({
			"present": _b(pl[b + 0]),
			"cases": _i4(pl[b + 1]),
			"layer": _i4(pl[b + 2]),
			"complete": _b(pl[b + 3]),
			"pattern": _s(pl[b + 4]),
		})

	zones = []
	for k, zid in enumerate(P.ZONE_IDS):
		b = k * 4
		zones.append({
			"id": zid,
			"name": _s(zn[b + 0]) or P.ZONE_NAME[zid],
			"state": _s(zn[b + 1]) or u"Idle",
			"running": _b(zn[b + 2]),
			"fault": _b(zn[b + 3]),
		})

	return {
		"ok": True,
		"ts": JSystem.currentTimeMillis(),
		"line": {
			"running": _b(line[0]),
			"mode": _s(line[1]) or u"Auto",
			"cpm": _f(line[2]),
			"cycle": _f(line[3]),
			"cases": _i4(line[4]),
			"target": _i4(line[5]),
		},
		"robot": {
			"state": _s(rb[0]) or u"Idle",
			"j1": _f(rb[1]), "j2": _f(rb[2]), "j3": _f(rb[3]),
			"j4": _f(rb[4]), "lift": _f(rb[5]),
			"grip": _b(rb[6]), "vac": _f(rb[7]),
			"cycles": _i4(rb[8]),
			"fault": _b(rb[9]), "faultText": _s(rb[10]),
			# Added after the shape was frozen: additions only, so the page
			# and the screens written against the original keys are untouched.
			"jogUp": _b(rb[11]), "jogDown": _b(rb[12]),
			"liftTarget": _f(rb[13]),
		},
		"pallets": pallets,
		"conv": {
			"c1": _b(cv[0]), "c2": _b(cv[1]), "c3": _b(cv[2]),
			"pe": {"infeed": _b(cv[3]), "carton": _b(cv[4]),
			       "len1": _b(cv[5]), "len2": _b(cv[6]),
			       "inpos1": _b(cv[7]), "inpos2": _b(cv[8]),
			       "clear": _b(cv[9])},
			"gate1": _b(cv[10]), "gate2": _b(cv[11]), "clamp": _b(cv[12]),
			"barcode": _s(cv[13]), "scanOK": _b(cv[14]),
		},
		"safety": {"estop": _b(sf[0]), "guards": _b(sf[1]),
		           "air": _b(sf[2]), "interfaces": _b(sf[3])},
		"faults": {"WrapperFilmFeed": _b(fl[0]), "ConveyorJam": _b(fl[1]),
		           "VacuumLow": _b(fl[2]), "GuardOpen": _b(fl[3]),
		           "RobotAxisFault": _b(fl[4])},
		"zones": zones,
		# Additive: the 3D page's geometry. Every key is always present, even
		# when the tag underneath it does not exist yet - a missing Config tag
		# reads back None from P.read() and falls to the default beside it
		# above, not a hole in the response.
		"config": dict((key, _ci(val, default))
		               for (path, key, default), val in zip(CONFIG, cf)),
		# Additive: whether this snapshot is trustworthy - see _quality()'s
		# docstring for how "stale" is judged across the whole read.
		"quality": _quality(paths, qvs),
	}


# ---------------------------------------------------------------------------
# presenter controls
# ---------------------------------------------------------------------------


def faults():
	"""Which faults exist, what each one does, and whether it is standing.

	The effects are stated so a presenter can pick the one that makes the point
	being made rather than the one with the shortest name.
	"""
	live = dict(zip(P.FAULTS, P.read(["Faults/%s" % n for n in P.FAULTS])))
	return [{"name": n, "label": P.FAULT_LABEL[n], "effect": P.FAULT_EFFECT[n],
	         "active": bool(live.get(n))} for n in P.FAULTS]


def setFault(name, on=True):
	"""Inject or clear one fault. Returns what it did, or raises."""
	name = (name or "").strip()
	match = [n for n in P.FAULTS if n.lower() == name.lower()]
	if not match:
		raise ValueError("no such fault: '%s' - try one of %s"
		                 % (name, ", ".join(P.FAULTS)))
	n = match[0]
	P.write({"Faults/%s" % n: bool(on)})
	# Wait out one 500 ms simulator tick before returning. The route's caller -
	# a presenter's phone, or a test - reads the state that comes back with the
	# response, and without this it is the state from BEFORE the cell reacted:
	# "I injected a jam and the conveyor is still running" on the same screen
	# as the injection that stopped it.
	from java.lang import Thread as JThread
	JThread.sleep(700)
	LOG.info("%s fault %s" % ("injected" if on else "cleared", n))
	return {"fault": n, "active": bool(on), "label": P.FAULT_LABEL[n],
	        "effect": P.FAULT_EFFECT[n] if on else "cleared"}


def reset():
	"""Back to steady state: every fault cleared, the cell running again.

	It does NOT wipe the pallets or the shift total. A reset on a real cell
	clears the fault and lets the machine carry on with the pallet it was
	building, and a demo that silently threw away 40 cases every time somebody
	pressed reset would be teaching the wrong thing.
	"""
	mapping = dict(("Faults/%s" % n, False) for n in P.FAULTS)
	# Momentary bits are cleared by a reset like everything else - a reset that
	# left a jog bit set would move the axis the moment the interlocks came
	# back.
	mapping["Robot/JogUp"] = False
	mapping["Robot/JogDown"] = False
	mapping["Line/SimEnabled"] = True
	mapping["Line/Mode"] = "Auto"
	mapping["Robot/Fault"] = False
	mapping["Robot/FaultText"] = ""
	mapping["Safety/EStopOK"] = True
	mapping["Safety/GuardsClosed"] = True
	P.write(mapping)
	MachineDemo.sim.clearInternals()
	LOG.info("reset to steady state")
	return {"cleared": list(P.FAULTS), "running": True}


def setSpeed(value):
	"""Machine time as a multiple of real time. 1 is real time.

	Clamped to 0.25x..10x. Nothing above that is watchable, and the alarm
	engine counts on-delays in REAL seconds regardless of this number - which
	is why nothing in this demo's tag tree carries an on-delay long enough for
	speed to outrun it.
	"""
	try:
		v = float(value)
	except:
		raise ValueError("speed must be a number, not '%s'" % value)
	v = max(0.25, min(10.0, v))
	P.write({"Line/SimSpeed": v})
	return {"speed": v}


def setMode(value):
	"""Auto or Manual. Manual stops the pattern; the arm holds where it is."""
	m = (value or "").strip().capitalize()
	if m not in ("Auto", "Manual"):
		raise ValueError("mode must be Auto or Manual, not '%s'" % value)
	P.write({"Line/Mode": m, "Line/SimEnabled": m == "Auto"})
	return {"mode": m}


def setJog(name, on=True):
	"""Set or clear ONE momentary jog bit, and nothing else.

	It writes the tag and returns immediately - no settle delay, no motion of
	its own. That is the point: the bit is the whole of the command, the
	simulator owns the axis, and a caller that wants to know what moved reads
	?cmd=state like any other client. A route that moved the axis itself would
	prove nothing about the tags.
	"""
	key = (name or "").strip().lower()
	if key not in ("up", "down"):
		raise ValueError("jog direction must be up or down, not '%s'" % name)
	tag = "Robot/Jog%s" % ("Up" if key == "up" else "Down")
	P.write({tag: bool(on)})
	return {"tag": tag, "on": bool(on)}


def setGuards(closed):
	"""Open or close the guard circuit directly, as a guard switch would.

	Safety/GuardsClosed is an INPUT to the simulator, not something it owns, so
	this is a real interlock test and not a flag the next tick overwrites.
	"""
	P.write({"Safety/GuardsClosed": bool(closed)})
	return {"guardsClosed": bool(closed)}


def status():
	"""A one-screen account of the cell, for ?cmd=status."""
	s = state()
	return {
		"cell": P.CELL_NAME,
		"owner": P.CELL_OWNER,
		"version": P.VERSION,
		"provider": P.PROVIDER,
		"line": s["line"],
		"robot": {"state": s["robot"]["state"], "cycles": s["robot"]["cycles"],
		          "fault": s["robot"]["fault"],
		          "faultText": s["robot"]["faultText"]},
		"pallets": s["pallets"],
		"safety": s["safety"],
		"faults": faults(),
		"zones": s["zones"],
		"alarms": P.alarmCounts(),
		"sim": MachineDemo.sim.info(),
	}
