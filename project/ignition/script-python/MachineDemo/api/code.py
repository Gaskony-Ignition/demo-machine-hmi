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

ROBOT = ["Robot/State", "Robot/J1_deg", "Robot/J2_deg", "Robot/J3_deg",
         "Robot/J4_deg", "Robot/Lift_mm", "Robot/GripperClosed",
         "Robot/Vacuum_kPa", "Robot/CycleCount", "Robot/Fault",
         "Robot/FaultText"]

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

_PLAN = None


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

	groups = [("line", LINE), ("robot", ROBOT), ("pallet", pallet),
	          ("conv", CONV), ("safety", SAFETY), ("faults", FAULTS),
	          ("zones", zones)]
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


def state():
	"""The whole cell in one dict, in the shape the 3D page is written against.

	Shape is FROZEN. Adding keys is safe; renaming, reordering the pallet list
	or changing a type is not - the page reads j1..j4 and lift straight into a
	scene graph and a null there stops the animation rather than logging.
	"""
	paths, o = _plan()
	v = P.read(paths)

	line = v[o["line"]:o["line"] + len(LINE)]
	rb = v[o["robot"]:o["robot"] + len(ROBOT)]
	cv = v[o["conv"]:o["conv"] + len(CONV)]
	sf = v[o["safety"]:o["safety"] + len(SAFETY)]
	fl = v[o["faults"]:o["faults"] + len(FAULTS)]
	pl = v[o["pallet"]:o["pallet"] + len(o["_pallet"])]
	zn = v[o["zones"]:o["zones"] + len(o["_zones"])]

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
