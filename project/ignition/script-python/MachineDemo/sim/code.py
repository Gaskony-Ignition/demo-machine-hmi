"""
MachineDemo.sim - the palletising cell, simulated.

The point of this module is that the cell RUNS rather than jitters. A robot
that randomises its joint angles looks like noise the moment you put a 3D model
on it; this one walks a real pick-and-place cycle and the pose at any instant
is an eased interpolation between the two task-space points either side of it.
Cases land on the pallet because the arm put them there, the layer count
follows from the cases, the photo-eyes make and break as cartons actually pass
them, and the infeed buffer drains if the conveyor stops.

The wrist travels UP, ACROSS and DOWN, never on a diagonal: it lifts clear of
the tallest stack before J1 turns, holds that height for the whole swing, and
only descends once J1 is parked over the slot. That is what a real cell does
and it is not a detail - a diagonal is geometrically valid at both ends and
takes the forearm straight through the pallet in the middle.

Time. `Line/SimSpeed` multiplies how fast MACHINE time runs against the wall
clock. It does not make the machine faster: the nominal cycle stays 12.6
machine-seconds and the reported cases/min stays ~14.3 at any speed, so the
numbers on screen remain the numbers a real cell of this size would show. The
tick integrates against measured elapsed real time, not against tick count, so
a late or missed timer tick costs smoothness and nothing else.

State. The sub-cycle state - which phase, how far into it, what is staged on
the infeed - has nowhere to live in the tag contract, so it lives in a
module-level dict. That dict is rebuilt from the tags whenever the module is
reloaded (which is what a project scan does), so a deploy in the middle of a
demo resumes the pallet where it was rather than starting it again.

Faults are read from the tags every tick rather than held in here, so toggling
[MachineDemo]Faults/ConveyorJam in the Designer drives the cell exactly the way
the presenter route does.
"""

import math
import random

from java.lang import System as JSystem

P = MachineDemo.plant
LOG = system.util.getLogger("MachineDemo.sim")


# ---------------------------------------------------------------------------
# geometry and inverse kinematics
# ---------------------------------------------------------------------------
# The joints are SOLVED, not chosen. The cell is described in metres in the
# world frame - where the conveyor is, where the two pallets are, how tall a
# case is - and the arm is asked to put its wrist there; J2, J3 and the lift
# fall out of a two-link IK solve. Picking joint angles by eye is what put the
# gripper 330 mm through the floor in the first cut of this module: angles that
# look plausible in a tag browser are not a machine that can reach anything.
#
# World frame: robot base at the origin, Y up, metres.
#   J1 rotates the base about Y:      J1 = atan2(-Z, X), planar radius r = |XZ|
#   the carriage rides the column at  y = BASE_Y + Lift_mm/1000
#   J2 is the upper arm from horizontal, positive up
#   J3 is the forearm relative to the upper arm, positive up
#   so the wrist lands at            r = L1*cos(J2) + L2*cos(J2+J3)
#                                    y = carriageY + L1*sin(J2) + L2*sin(J2+J3)
#   J4 spins the gripper about Y to lay the case to the interlock pattern.

L1 = 1.35            # shoulder to elbow, m
L2 = 1.15            # elbow to wrist, m
BASE_Y = 0.34        # carriage height at Lift_mm = 0
LIFT_MAX_MM = 1200.0
D_MIN = 0.20         # the solve is never asked for anything outside
D_MAX = 2.45         # these, whatever the pattern asks for

# The carriage tracks the wrist from CARRIAGE_ABOVE metres above it, which is
# what keeps D short as the stack grows: a lift that never moves has to solve
# every layer with reach alone and runs out of arm on layer four.
CARRIAGE_ABOVE = 0.30

# A pose here is TASK space - (J1 deg, planar radius m, wrist height m, J4 deg)
# - and it is task space that gets interpolated through the cycle. Interpolating
# joint ANGLES between two solved poses does not travel between the two points;
# it travels along whatever curve the linkage happens to trace, which on a long
# swing dips the wrist through the conveyor halfway across.

def _task(x, z, wristY, j4=0.0):
	"""A world point (X, Z, wrist height) as (J1, radius, wristY, J4)."""
	return (math.degrees(math.atan2(-z, x)), math.hypot(x, z), wristY, j4)


# Where the cell's three places are, in metres.
INFEED_XZ = (1.62, 0.10)          # pick point off the infeed conveyor
STATION_XZ = {1: (-1.45, -1.65), 2: (-1.45, 1.65)}
HOME_XZ = (1.10, 0.0)

CONVEYOR_TOP_M = 0.90
CASE_H_M = 0.22
WRIST_TO_CASE_TOP_M = 0.125       # gripper depth: wrist above the case it holds

# Wrist height to lift a case off the conveyor.
#
# The two numbers in the spec disagree by 45 mm: its components - conveyor top
# 0.90, case 0.22, and the 0.125 gripper depth its PLACE formula uses - come to
# 1.245, but it states 1.29. Taking the stated number rather than the
# derivation, because the error directions are not equal: 1.29 floats the case
# 45 mm above the belt, which nobody can see, and 1.245 would put it 45 mm
# THROUGH the belt if the page's gripper is drawn deeper than 0.125. Change the
# one constant if the page says otherwise.
PICK_WRIST_Y = 1.29
_PICK_WRIST_Y_DERIVED = CONVEYOR_TOP_M + CASE_H_M + WRIST_TO_CASE_TOP_M

PALLET_DECK_M = 0.16              # top of the pallet, where layer 0 sits
HOME_WRIST_Y = 1.35

# How far above the tallest stack the wrist travels while it is swinging.
SAFE_CLEAR_M = 0.35

# Where this pick's three cases go within the layer, as (J1 offset degrees,
# radius offset m) around the station centre. Polar rather than Cartesian
# deliberately: an offset along X and Z can push the planar radius past the
# arm's reach at the far corner, and a slot the robot cannot reach is a demo
# that stops on case 34 with no explanation.
SLOT_POLAR = [(-5.5, -0.24), (5.5, -0.24), (-5.5, 0.16), (5.5, 0.16)]


def _solve(r, wristY):
	"""(J2, J3, Lift_mm) putting the wrist at planar radius r, height wristY.

	Elbow-down branch, which is the one a palletiser uses: the forearm comes
	down onto the stack rather than up over it, so the elbow never has to clear
	the case it is carrying.
	"""
	lift = _clamp((wristY - (BASE_Y - CARRIAGE_ABOVE)) * 1000.0, 0.0,
	              LIFT_MAX_MM)
	carriageY = BASE_Y + lift / 1000.0
	dx = r
	dy = wristY - carriageY
	d = _clamp(math.hypot(dx, dy), D_MIN, D_MAX)
	c3 = _clamp((d * d - L1 * L1 - L2 * L2) / (2.0 * L1 * L2), -1.0, 1.0)
	j3 = -math.degrees(math.acos(c3))
	c2 = _clamp((d * d + L1 * L1 - L2 * L2) / (2.0 * d * L1), -1.0, 1.0)
	j2 = math.degrees(math.atan2(dy, dx) + math.acos(c2))
	return _clamp(j2, -60.0, 90.0), _clamp(j3, -140.0, 40.0), lift


HOME = _task(HOME_XZ[0], HOME_XZ[1], HOME_WRIST_Y)
PICK_LOW = _task(INFEED_XZ[0], INFEED_XZ[1], PICK_WRIST_Y)


def _stackTopM(s):
	"""The top of the TALLER of the two stacks, in metres.

	Both stations, not just the one being built: the arm swings across the
	cell, and a safe height worked out from the target pallet alone is not safe
	over the other one when that is the full pallet waiting for the wrapper.
	A part-built layer counts as a whole one - the cases in it are already at
	full height.
	"""
	top = PALLET_DECK_M
	for n in P.STATIONS:
		c = s["st"][n]["cases"]
		layers = (c + P.CASES_PER_LAYER - 1) // P.CASES_PER_LAYER
		top = max(top, PALLET_DECK_M + layers * CASE_H_M)
	return top


def _safeWristY(s, layer):
	"""Travel height for this cycle: clear of both stacks and of the conveyor.

	Floored at the pick height so that on an empty pallet the arm still travels
	high enough to clear the infeed and the pallet rails rather than skimming
	them, which is what the bare stack-plus-clearance figure would give.
	"""
	top = max(_stackTopM(s), PALLET_DECK_M + (layer + 1) * CASE_H_M)
	return max(PICK_WRIST_Y, top + SAFE_CLEAR_M)

# The cycle, as (name, machine-seconds at nominal, the state the robot reports).
# They sum to P.CYCLE_S, and a jittered cycle scales all eight together.
#
# UP, ACROSS, DOWN - never a diagonal. Every swing (Approach, Traverse) happens
# at the safe height and changes nothing but J1; every height change (Descend,
# Lift, Lower, Retract) happens with J1 already parked at its target. The
# straight interpolation this replaced was geometrically valid at both ends and
# put the forearm through the middle of the pallet stack in between, which on a
# close-up camera is the first thing a palletiser builder sees.
PHASES = [
	("Approach", 1.6, "Picking"),    # swing back over to the infeed, up high
	("Descend", 1.2, "Picking"),     # straight down onto the case set
	("Grip", 1.0, "Picking"),        # cups seal, vacuum pulls
	("Lift", 1.3, "Picking"),        # straight up to safe height
	("Traverse", 3.0, "Placing"),    # swing to the pallet, height held
	("Lower", 1.8, "Placing"),       # straight down onto the layer
	("Release", 0.8, "Placing"),     # vacuum breaks, cases are set
	("Retract", 1.9, "Placing"),     # straight up, clear of the stack
]

# Hold-to-run jog on the lift axis. 120 mm/s of MACHINE time: fast enough to
# cross the column in ten seconds, slow enough that a finger on a button can
# stop it where it means to.
JOG_RATE_MM_S = 120.0

# The axis follows its command with a short lag, so the Manual screen's
# commanded and actual readouts are two different numbers during a move -
# which is what makes showing both of them worth the space.
JOG_LAG_S = 0.25

# A momentary bit that stays set is the failure a customer WILL ask about: a
# browser tab closes mid-jog and the axis runs to the limit on its own. Counted
# in REAL seconds, not machine seconds - a tab closing is a wall-clock event,
# and counting machine time would make the watchdog four times twitchier at 4x.
JOG_WATCHDOG_S = 30.0

HOLD_VACUUM_KPA = -66.0
LOW_VACUUM_KPA = -17.0

# The infeed runs 8% FASTER than the robot consumes, so the accumulation
# conveyor rides full and backs up - which is what an infeed does when the
# palletiser is the bottleneck, and it is the bottleneck by design.
#
# Matching the two rates exactly instead looked right on paper and was wrong on
# the gateway: the buffer grazed zero between cycles, so the robot took a
# single idle tick roughly every third cycle and Line/Running flickered false
# for half a second. A machine that micro-stops for no reason is the first
# thing a machine builder notices.
CARTON_PITCH_S = (P.CYCLE_S / float(P.CASES_PER_PICK)) * 0.92

# Two picks' worth of accumulation. It is also the fuse on a jam: with the
# infeed stopped the robot works the buffer down and starves about 25 machine-
# seconds later, so the fault has a visible cause and then a visible effect
# rather than both at once.
BUFFER_MAX = 2 * P.CASES_PER_PICK

DISCHARGE_LIFT_S = 3.0     # pallet leaves the station
DISCHARGE_TOTAL_S = 8.0    # a fresh pallet is in place


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------

_S = None


def _blank():
	# The lift the arm actually holds at HOME, solved rather than typed, so the
	# jog axis starts from where the column really is.
	homeLift = _solve(HOME[1], HOME[2])[2]
	return {
		"t": JSystem.currentTimeMillis(),
		"ticks": 0,
		"phase": 0,
		"pf": 0.0,
		"cycleTime": P.CYCLE_S,
		"pose": list(HOME),
		"from": list(HOME),
		"idle": True,
		"safeY": PICK_WRIST_Y,
		"homing": 0.0,
		"wasBlocked": False,
		"active": 1,
		"slot": 0,
		"layer": 0,
		"buf": 2 * P.CASES_PER_PICK,
		"carton": 0.0,
		"barcode": 0,
		"lastBarcode": "",
		"scanOK": True,
		"cpm": 0.0,
		"casesTotal": 0,
		"cycleCount": 0,
		"zclock": 0.0,
		"named": False,
		"jogLift": homeLift,
		"jogTarget": homeLift,
		"jogHeld": 0.0,
		"guardWasHeld": False,
		"st": dict((n, {"present": True, "cases": 0, "complete": False,
		                "disch": 0.0}) for n in P.STATIONS),
	}


def _state():
	"""The live sim state, rebuilt from the tags the first time it is asked.

	Rehydration is what makes a project scan mid-demo survivable: the module
	globals are gone, but the pallet, the totals and the cycle count are tags,
	so the cell picks up where it stopped rather than starting the pallet over.
	"""
	global _S
	if _S is not None:
		return _S
	s = _blank()
	try:
		want = {"casesTotal": "Line/CasesTotal",
		        "cycleCount": "Robot/CycleCount",
		        "lift": "Robot/Lift_mm",
		        "liftTarget": "Robot/LiftTarget_mm",
		        "barcode": "Conveyor/LastBarcode"}
		for n in P.STATIONS:
			want["p%d" % n] = "Pallet/Station%d/Present" % n
			want["c%d" % n] = "Pallet/Station%d/CasesPlaced" % n
			want["k%d" % n] = "Pallet/Station%d/Complete" % n
		v = P.readDict(want)
		s["casesTotal"] = int(v.get("casesTotal") or 0)
		s["cycleCount"] = int(v.get("cycleCount") or 0)
		if v.get("lift") is not None:
			s["jogLift"] = float(v.get("lift"))
			s["jogTarget"] = float(v.get("liftTarget") or v.get("lift"))
		bc = v.get("barcode") or ""
		if bc.startswith("T") and bc[1:].isdigit():
			s["barcode"] = int(bc[1:])
			s["lastBarcode"] = bc
		for n in P.STATIONS:
			st = s["st"][n]
			if v.get("p%d" % n) is not None:
				st["present"] = bool(v.get("p%d" % n))
			st["cases"] = min(P.CASES_PER_PALLET, int(v.get("c%d" % n) or 0))
			st["complete"] = bool(v.get("k%d" % n))
			if st["cases"] >= P.CASES_PER_PALLET:
				st["complete"] = True
		for n in P.STATIONS:
			if s["st"][n]["present"] and not s["st"][n]["complete"]:
				s["active"] = n
				break
	except:
		import traceback
		LOG.warn("could not rehydrate from tags, starting clean: %s"
		         % traceback.format_exc())
	_S = s
	return _S


def ticks():
	"""How many times the timer has driven this module since it last loaded."""
	return 0 if _S is None else _S.get("ticks", 0)


def info():
	"""What the simulator is doing right now, for ?cmd=status."""
	s = _state()
	j1, radius, wristY, j4 = s["pose"]
	j2, j3, lift = _solve(radius, wristY)
	carriageY = BASE_Y + lift / 1000.0
	return {
		"wristY_m": round(wristY, 3),
		"safeY_m": round(s.get("safeY") or PICK_WRIST_Y, 3),
		"stackTop_m": round(_stackTopM(s), 3),
		"radius_m": round(radius, 3),
		"solveD_m": round(math.hypot(radius, wristY - carriageY), 3),
		"carriageY_m": round(carriageY, 3),
		"ticks": s["ticks"],
		"phase": PHASES[s["phase"]][0] if not s["idle"] else "Waiting",
		"activeStation": s["active"],
		"slot": s["slot"],
		"layer": s["layer"],
		"infeedBuffer": s["buf"],
		"cycleTime": round(s["cycleTime"], 2),
		"casesTotal": s["casesTotal"],
		"cycleCount": s["cycleCount"],
	}


def clearInternals():
	"""Drop the sub-cycle state so the next tick rebuilds it from the tags.

	Used by ?cmd=reset: the tags are the record, this dict is only how far
	through a cycle the arm was, and after a reset that is not worth keeping.
	"""
	global _S
	_S = None


# ---------------------------------------------------------------------------
# small maths
# ---------------------------------------------------------------------------


def _smooth(x):
	"""Ease in and out. Constant-velocity joints read as a machine that has no
	acceleration limits, which is the one thing every real robot has."""
	if x <= 0.0:
		return 0.0
	if x >= 1.0:
		return 1.0
	return x * x * (3.0 - 2.0 * x)


def _lerp(a, b, t):
	return [a[i] + (b[i] - a[i]) * t for i in range(len(a))]


def _clamp(v, lo, hi):
	return lo if v < lo else (hi if v > hi else v)


def _placePose(station, slot, layer, safeY=None):
	"""Where the wrist has to be over this slot on the pallet.

	`safeY` None means the placement height itself: layer L sits on top of L
	completed layers, so the case bottom is at PALLET_DECK_M + L*CASE_H_M and
	the wrist rides one case plus the gripper above that. Pass a height instead
	and it is the same J1 and radius at that height, which is what makes the
	descent vertical.
	"""
	x, z = STATION_XZ.get(station, STATION_XZ[1])
	centre = _task(x, z, 0.0)
	dj1, dr = SLOT_POLAR[slot % P.SLOTS_PER_LAYER]
	if safeY is None:
		wristY = (PALLET_DECK_M + layer * CASE_H_M + CASE_H_M
		          + WRIST_TO_CASE_TOP_M)
	else:
		wristY = safeY
	j4 = 90.0 if (layer % 2) else 0.0    # every second layer interlocks
	return (centre[0] + dj1, centre[1] + dr, wristY, j4)


def _target(s, phase):
	"""Where the WRIST is going by the end of this phase.

	Read it down the list and the profile is the whole story: the two swings
	end at the safe height, the four vertical legs end with J1 unchanged.
	"""
	name = PHASES[phase][0]
	safeY = s.get("safeY") or PICK_WRIST_Y
	if name == "Approach":
		# The empty-gripper swing back. It travels at the HIGHER of where it
		# starts and where it is going, so that a cycle which began after the
		# stack grew a layer - or on the other station, whose pallet is empty -
		# is still a level swing and not a shallow descent across the cell.
		# Costs nothing: the Descend leg takes the whole height off anyway.
		return _task(INFEED_XZ[0], INFEED_XZ[1],
		             max(safeY, s["from"][2] if s.get("from") else safeY))
	if name == "Lift":
		return _task(INFEED_XZ[0], INFEED_XZ[1], safeY)
	if name in ("Descend", "Grip"):
		return PICK_LOW
	if name in ("Traverse", "Retract"):
		return _placePose(s["active"], s["slot"], s["layer"], safeY)
	if name in ("Lower", "Release"):
		return _placePose(s["active"], s["slot"], s["layer"], None)
	return HOME


def _phaseSeconds(s, phase):
	return PHASES[phase][1] * (s["cycleTime"] / P.CYCLE_S)


# ---------------------------------------------------------------------------
# the tick
# ---------------------------------------------------------------------------


def tick():
	"""One simulation step. Never raises - a tick that fails logs and the next
	one carries on, because a gateway timer that throws stops being scheduled
	in some configurations and a dead demo is worse than a rough one."""
	try:
		_tick()
	except:
		import traceback
		LOG.warn("tick failed: %s" % traceback.format_exc())


def _tick():
	s = _state()

	now = JSystem.currentTimeMillis()
	dtr = (now - s["t"]) / 1000.0
	s["t"] = now
	if dtr <= 0.0:
		dtr = 0.5
	if dtr > 2.0:
		# The cell was paused, the gateway was busy, or the module just
		# reloaded. Cap it: integrating a ten second gap teleports the arm.
		dtr = 2.0

	# Everything the tick needs to read, in ONE round trip: the controls, the
	# five faults, the two jog bits and the guard circuit.
	ctl = P.readDict({
		"enabled": "Line/SimEnabled",
		"speed": "Line/SimSpeed",
		"mode": "Line/Mode",
		"jogUp": "Robot/JogUp",
		"jogDown": "Robot/JogDown",
		"guards": "Safety/GuardsClosed",
	})
	f = dict(zip(P.FAULTS, P.read(["Faults/%s" % n for n in P.FAULTS])))
	for k in f:
		f[k] = bool(f[k])

	if ctl.get("enabled") is None:
		# The provider is not there yet. Setup has not been run.
		return

	speed = _clamp(float(ctl.get("speed") or 1.0), 0.1, 20.0)
	dt = dtr * speed
	s["ticks"] += 1
	s["zclock"] += dt

	# The guard circuit is an INPUT, not something this module owns. It goes
	# false when the GuardOpen fault is injected, and it also goes false when
	# anyone writes it false - a test, an operator screen, a Designer session.
	# Either way the cell is held. Driving it purely from the injected fault
	# would mean a gateway that reported guards open and kept running.
	held = f["GuardOpen"] or (ctl.get("guards") is False)
	robotFault = f["RobotAxisFault"] or f["VacuumLow"]
	blocked = held or robotFault

	if not ctl.get("enabled"):
		# Manual, or the simulation switched off. The auto cycle stops; the
		# lift axis does NOT, because manual jog is the whole point of the mode
		# and an operator jogging an axis is not the cell running a pattern.
		_jog(s, dt, dtr, ctl, blocked, False, None)
		_writeStopped(s, f, blocked, robotFault, held)
		return

	state = _motion(s, dt, f, blocked, robotFault, held)
	_material(s, dt, f, held)
	_stations(s, dt, f)
	_write(s, dt, dtr, f, ctl, state, blocked, robotFault, held)


def _motion(s, dt, f, blocked, robotFault, held):
	"""Advance the arm, and say what state the robot is in."""
	if blocked:
		s["wasBlocked"] = True
		return "Fault" if robotFault else "Held"

	if s["wasBlocked"]:
		# Coming back from a stop is not instant on a real cell: the robot
		# re-homes before it will run the pattern again. It is also the only
		# time the contract's "Homing" state is honest.
		s["wasBlocked"] = False
		s["homing"] = 2.5
		s["idle"] = True
		s["phase"] = 0
		s["pf"] = 0.0
		s["from"] = list(s["pose"])

	if s["homing"] > 0.0:
		s["homing"] -= dt
		s["pose"] = _lerp(s["pose"], HOME, min(1.0, dt / 1.2))
		return "Homing"

	if s["idle"]:
		s["pose"] = _lerp(s["pose"], HOME, min(1.0, dt / 1.5))
		if _startCycle(s, f):
			return PHASES[0][2]
		return "Idle"

	s["pf"] += dt
	guard = 0
	while s["pf"] >= _phaseSeconds(s, s["phase"]) and guard < 20:
		guard += 1
		s["pf"] -= _phaseSeconds(s, s["phase"])
		s["pose"] = list(_target(s, s["phase"]))
		_endPhase(s)
		s["phase"] += 1
		if s["phase"] >= len(PHASES):
			s["phase"] = 0
			s["cycleCount"] += 1
			if not _startCycle(s, f):
				s["idle"] = True
				s["pf"] = 0.0
				return "Idle"
		s["from"] = list(s["pose"])

	dur = _phaseSeconds(s, s["phase"])
	frac = _clamp(s["pf"] / dur, 0.0, 1.0) if dur > 0 else 1.0
	s["pose"] = _lerp(s["from"], _target(s, s["phase"]), _smooth(frac))
	s["frac"] = frac
	return PHASES[s["phase"]][2]


def _endPhase(s):
	"""Side effects that happen exactly at a phase boundary."""
	name = PHASES[s["phase"]][0]
	if name != "Release":
		return
	# The cases are on the pallet the instant the gripper lets go, so this is
	# where the pallet count moves - not at the end of the cycle, which would
	# show the arm already halfway home before the pallet changed.
	st = s["st"][s["active"]]
	st["cases"] = min(P.CASES_PER_PALLET, st["cases"] + P.CASES_PER_PICK)
	s["casesTotal"] += P.CASES_PER_PICK
	if st["cases"] >= P.CASES_PER_PALLET:
		st["complete"] = True

	# Raise the travel height NOW, for the retract that follows, to whatever
	# the next cycle will need. The stack is one layer taller than it was when
	# this cycle worked its height out, and doing it here means the extra rise
	# happens on the vertical retract leg instead of part-way through the swing
	# back - the arm goes up and then across, rather than climbing as it goes.
	nextLayer = min(P.LAYERS_PER_PALLET - 1,
	                st["cases"] // P.CASES_PER_LAYER)
	s["safeY"] = max(s["safeY"], _safeWristY(s, nextLayer))


def _availableStation(s):
	"""The station the robot can build on, preferring the one it is on.

	When a pallet completes the robot moves to the other station immediately -
	that is the whole reason a cell has two - and only stops when neither is
	available, which is exactly what the wrapper fault engineers.
	"""
	order = [s["active"]] + [n for n in P.STATIONS if n != s["active"]]
	for n in order:
		st = s["st"][n]
		if st["present"] and not st["complete"]:
			return n
	return None


def _startCycle(s, f):
	"""Begin a pick, if there is product staged and a pallet to build on."""
	if s["buf"] < P.CASES_PER_PICK:
		return False
	n = _availableStation(s)
	if n is None:
		return False
	s["active"] = n
	st = s["st"][n]
	s["layer"] = min(P.LAYERS_PER_PALLET - 1,
	                 st["cases"] // P.CASES_PER_LAYER)
	s["slot"] = (st["cases"] % P.CASES_PER_LAYER) // P.CASES_PER_PICK
	# Worked out ONCE per cycle, not per tick: it depends on the stacks, and a
	# travel height that moved under the arm halfway through a swing would jerk
	# the wrist every time a case landed.
	s["safeY"] = _safeWristY(s, s["layer"])
	s["buf"] -= P.CASES_PER_PICK
	s["idle"] = False
	s["phase"] = 0
	s["pf"] = 0.0
	s["from"] = list(s["pose"])
	# Real cycles are not identical. A few percent of scatter is what makes the
	# cases/min readout move the way an operator expects it to.
	s["cycleTime"] = P.CYCLE_S * (0.97 + 0.09 * random.random())
	return True


def _material(s, dt, f, held):
	"""Cartons arriving on the infeed, and the photo-eyes they break."""
	s["c1"] = (not f["ConveyorJam"]) and (not held)
	s["c2"] = not held
	if not s["c1"]:
		return
	s["carton"] += dt
	guard = 0
	while s["carton"] >= CARTON_PITCH_S and guard < 20:
		guard += 1
		s["carton"] -= CARTON_PITCH_S
		s["buf"] = min(BUFFER_MAX, s["buf"] + 1)
		s["barcode"] += 1
		s["lastBarcode"] = "T%05d" % s["barcode"]
		# One no-read in every 37 cartons. It is not a fault - it is the thing
		# an operator sees often enough to know what the ScanOK lamp means.
		s["scanOK"] = (s["barcode"] % 37) != 0


def _inPosition(s):
	"""The two 'case set squared up under the gripper' eyes at the pick station.

	They are staging sensors, not a buffer gauge. A set is present until the
	robot lifts it, then both go dark until the next set has indexed in - so
	they blink once a cycle, which is what makes them worth putting on a
	screen, and they stay dark when the infeed has nothing to send.
	"""
	if s["buf"] < P.CASES_PER_PICK or s["idle"]:
		return False, False
	name = PHASES[s["phase"]][0]
	# Dark from the moment the set is lifted until the next one has indexed
	# in behind it - the lift and the swing away.
	if name in ("Lift", "Traverse"):
		return False, False
	return True, name != "Grip"


def _eyes(s, f):
	"""The seven photo-eyes, as the cartons and the arm actually leave them."""
	pos1, pos2 = _inPosition(s)
	if f["ConveyorJam"]:
		# A jam IS a blocked eye. Latching them is the diagnosis an operator
		# reads off the panel to find where the carton stopped.
		return {"PE_Infeed": True, "PE_Carton": True, "PE_Length1": True,
		        "PE_Length2": False, "PE_Clear": False,
		        "PE_InPos1": pos1, "PE_InPos2": pos2}
	u = s["carton"] / CARTON_PITCH_S
	carton = 0.18 <= u < 0.46
	len1 = 0.32 <= u < 0.60
	len2 = 0.40 <= u < 0.68
	return {
		"PE_Infeed": u < 0.26,
		"PE_Carton": carton,
		"PE_Length1": len1,
		"PE_Length2": len2,
		"PE_Clear": not (carton or len1 or len2),
		"PE_InPos1": pos1,
		"PE_InPos2": pos2,
	}


def _stations(s, dt, f):
	"""Discharge a finished pallet, and put an empty one in its place.

	Blocked by WrapperFilmFeed on purpose: a completed pallet with nowhere to
	go is the most common real reason a palletiser stops, and it stops the cell
	slowly - one station, then the other - which is far more interesting to
	watch than a fault that stops everything at once.
	"""
	for n in P.STATIONS:
		st = s["st"][n]
		if not st["complete"]:
			st["disch"] = 0.0
			continue
		if f["WrapperFilmFeed"]:
			continue
		st["disch"] += dt
		if st["disch"] >= DISCHARGE_TOTAL_S:
			st["present"] = True
			st["cases"] = 0
			st["complete"] = False
			st["disch"] = 0.0
		elif st["disch"] >= DISCHARGE_LIFT_S:
			st["present"] = False


def _discharging(s, n):
	st = s["st"][n]
	return st["complete"] and st["disch"] > 0.0


def _grip(s, state, f):
	"""Gripper and vacuum, which follow the phase rather than the other way."""
	if f["VacuumLow"]:
		return True, LOW_VACUUM_KPA + random.uniform(-1.5, 1.5)
	if state not in ("Picking", "Placing"):
		return False, 0.0
	name = PHASES[s["phase"]][0]
	frac = s.get("frac", 0.0)
	if name in ("Approach", "Descend"):
		return False, 0.0
	if name == "Grip":
		return frac > 0.35, HOLD_VACUUM_KPA * min(1.0, frac / 0.8)
	if name == "Release":
		return frac < 0.4, HOLD_VACUUM_KPA * (1.0 - min(1.0, frac / 0.6))
	if name == "Retract":
		return False, 0.0
	return True, HOLD_VACUUM_KPA + random.uniform(-1.8, 1.8)


def _jog(s, dt, dtr, ctl, blocked, autoRunning, solvedLift):
	"""Hold-to-run jog on the lift axis. Returns (Lift_mm, LiftTarget_mm).

	The HMI sets a momentary bit; the motion happens HERE. That split is the
	point of the exercise - a screen that moved the axis itself would carry on
	moving it after the interlock dropped, after the operator let go, and after
	the browser tab closed.

	Four independent reasons not to move, and each one is checked here even
	though the screen already greys the button out. The panel disabling a
	button and the controller refusing the motion are not the same safeguard,
	and a machine builder will ask which one you have.
	"""
	up = bool(ctl.get("jogUp"))
	down = bool(ctl.get("jogDown"))

	# The watchdog runs FIRST and runs in every mode, including auto: a bit
	# stuck on is worth clearing whether or not anything would have moved.
	if up or down:
		s["jogHeld"] += dtr
	else:
		s["jogHeld"] = 0.0
	if s["jogHeld"] > JOG_WATCHDOG_S:
		P.write({"Robot/JogUp": False, "Robot/JogDown": False})
		LOG.warn("jog watchdog: a jog bit was held for more than %.0f s and "
		         "has been cleared - the session that set it is gone"
		         % JOG_WATCHDOG_S)
		s["jogHeld"] = 0.0
		up = down = False

	if autoRunning:
		# The auto cycle owns the axis. The jog bits are ignored, and the
		# manual position tracks the cycle so that a drop into manual starts
		# from where the column actually is rather than where it was last
		# jogged to, minutes ago.
		s["jogLift"] = solvedLift
		s["jogTarget"] = solvedLift
		return solvedLift, solvedLift

	if up and down:
		# A real controller treats both directions commanded at once as a
		# fault condition, not a race to be resolved. Neither bit is cleared:
		# it is the panel's mistake to fix, and clearing it would hide it.
		direction = 0
	elif blocked:
		direction = 0
	elif up:
		direction = 1
	elif down:
		direction = -1
	else:
		direction = 0

	target = s["jogTarget"]
	if direction:
		target = _clamp(target + direction * JOG_RATE_MM_S * dt,
		                0.0, LIFT_MAX_MM)
	lift = s["jogLift"]
	lift = lift + (target - lift) * min(1.0, dt / JOG_LAG_S)
	s["jogTarget"] = target
	s["jogLift"] = lift
	return lift, target


def _zoneRow(state, running, fault):
	if fault:
		return "Fault"
	if state == "held":
		return "Held"
	return "Running" if running else "Idle"


def _writeStopped(s, f, blocked, robotFault, held):
	"""The auto cycle is off - Manual, or SimEnabled false.

	It says so honestly rather than leaving stale values, and it still
	publishes the lift axis, the motor contactor and the fault, because in
	Manual all three are live: the operator is jogging, and the interlocks that
	stop them jogging have to read correctly on the same screen.
	"""
	state = "Fault" if robotFault else ("Held" if held else "Idle")
	paths = ["Line/Running", "Line/CasesPerMin", "Robot/State",
	         "Robot/Lift_mm", "Robot/LiftTarget_mm",
	         "Robot/MotorsOn", "Robot/Ready", "Robot/Fault",
	         "Conveyor/C1_Run", "Conveyor/C2_Run", "Conveyor/C3_Run",
	         "Conveyor/C1_Speed_mpm", "Conveyor/C2_Speed_mpm",
	         "Conveyor/C3_Speed_mpm"]
	vals = [False, 0.0, state,
	        round(s["jogLift"], 0), round(s["jogTarget"], 0),
	        (not blocked), False, bool(robotFault),
	        False, False, False, 0.0, 0.0, 0.0]
	paths, vals = _guardWrite(s, f, held, paths, vals)
	for zid in P.ZONE_IDS:
		paths += ["Zones/%s/State" % zid, "Zones/%s/Running" % zid]
		vals += ["Idle", False]
	P.writePaths(paths, vals)


def _guardWrite(s, f, held, paths, vals):
	"""Drive Safety/GuardsClosed only when this module has something to say.

	It is a field input - a guard switch - so the simulator forces it FALSE
	while the GuardOpen fault stands, and forces it back TRUE once on the
	transition out. In between it leaves the tag alone, which is what lets a
	test (or an operator screen) write it false and have that mean something
	instead of being overwritten 500 ms later.
	"""
	if f["GuardOpen"]:
		s["guardWasHeld"] = True
		paths.append("Safety/GuardsClosed")
		vals.append(False)
	elif s.get("guardWasHeld"):
		s["guardWasHeld"] = False
		paths.append("Safety/GuardsClosed")
		vals.append(True)
	return paths, vals


def _write(s, dt, dtr, f, ctl, state, blocked, robotFault, held):
	"""Everything the cell is, written in one round trip."""
	# Task space in, joints out. The interpolation above moved the WRIST; this
	# is the only place joint angles exist, so the angles the 3D page receives
	# are by construction a pose the arm can actually hold.
	j1, radius, wristY, j4 = s["pose"]
	j2, j3, solvedLift = _solve(radius, wristY)
	grip, vac = _grip(s, state, f)
	eyes = _eyes(s, f)

	producing = state in ("Picking", "Placing")
	inst = (P.CASES_PER_PICK * 60.0 / s["cycleTime"]) if producing else 0.0
	# Eight machine-seconds of memory: long enough that the readout does not
	# flicker between phases, short enough that a jam shows inside a cycle.
	s["cpm"] += (inst - s["cpm"]) * min(1.0, dt / 8.0)

	air = 620.0 + 6.0 * math.sin(s["zclock"] / 11.0) + random.uniform(-3.0, 3.0)
	airOK = air >= 550.0

	d1 = _discharging(s, 1)
	d2 = _discharging(s, 2)
	c3 = d1 or d2

	faultText = ""
	if f["RobotAxisFault"]:
		faultText = P.ROBOT_FAULT_TEXT["RobotAxisFault"]
	elif f["VacuumLow"]:
		faultText = P.ROBOT_FAULT_TEXT["VacuumLow"]

	paths = [
		"Line/Running", "Line/CasesPerMin", "Line/CycleTime_s",
		"Line/CasesTotal",
		"Robot/State", "Robot/J1_deg", "Robot/J2_deg", "Robot/J3_deg",
		"Robot/J4_deg", "Robot/Lift_mm", "Robot/GripperClosed",
		"Robot/Vacuum_kPa", "Robot/MotorsOn", "Robot/Homed", "Robot/Ready",
		"Robot/Healthy", "Robot/CycleCount", "Robot/CycleTime_s",
		"Robot/Fault", "Robot/FaultText",
		"Robot/LiftTarget_mm",
		"Safety/EStopOK", "Safety/AirPressureOK",
		"Safety/InterfacesOK", "Safety/AirPressure_kPa",
		"Conveyor/C1_Run", "Conveyor/C2_Run", "Conveyor/C3_Run",
		"Conveyor/C1_Speed_mpm", "Conveyor/C2_Speed_mpm",
		"Conveyor/C3_Speed_mpm",
		"Conveyor/Gate1_Up", "Conveyor/Gate2_Up", "Conveyor/Clamp_Extended",
		"Conveyor/LastBarcode", "Conveyor/ScanOK",
	]
	# Running means PRODUCING. A cell that is held, faulted, starved of cartons
	# or has nowhere left to put a pallet is stopped, and saying so is the
	# whole point of the lamp - "not faulted" is a different question and
	# Safety/ already answers it.
	running = (not blocked) and (not s["idle"])

	# Who owns the lift. While the cycle runs it is the cycle's, and the jog
	# bits are ignored; the moment the cell goes idle - starved, both pallets
	# full, held - the operator can jog it, which is exactly when they would
	# want to.
	lift, liftTarget = _jog(s, dt, dtr, ctl, blocked, running, solvedLift)

	vals = [
		bool(running), round(s["cpm"], 1), round(s["cycleTime"], 2),
		int(s["casesTotal"]),
		state, round(j1, 1), round(j2, 1), round(j3, 1),
		round(j4, 1), round(lift, 0), bool(grip),
		round(vac, 1), (not blocked), (not robotFault),
		(not blocked) and s["homing"] <= 0.0,
		(not robotFault) and airOK, int(s["cycleCount"]),
		round(s["cycleTime"], 2),
		bool(robotFault), faultText,
		round(liftTarget, 0),
		True, bool(airOK), (not f["WrapperFilmFeed"]),
		round(air, 0),
		bool(s.get("c1")), bool(s.get("c2")), bool(c3),
		round(18.0 + random.uniform(-0.4, 0.4), 1) if s.get("c1") else 0.0,
		round(14.0 + random.uniform(-0.3, 0.3), 1) if s.get("c2") else 0.0,
		round(9.0 + random.uniform(-0.2, 0.2), 1) if c3 else 0.0,
		bool(d1), bool(d2),
		bool(s["st"][s["active"]]["present"] and not _discharging(s, s["active"])),
		s["lastBarcode"], bool(s["scanOK"]),
	]

	paths, vals = _guardWrite(s, f, held, paths, vals)

	for key in ("PE_Infeed", "PE_Carton", "PE_Length1", "PE_Length2",
	            "PE_InPos1", "PE_InPos2", "PE_Clear"):
		paths.append("Conveyor/%s" % key)
		vals.append(bool(eyes[key]))

	for n in P.STATIONS:
		st = s["st"][n]
		paths += ["Pallet/Station%d/Present" % n,
		          "Pallet/Station%d/CasesPlaced" % n,
		          "Pallet/Station%d/Layer" % n,
		          "Pallet/Station%d/Complete" % n]
		vals += [bool(st["present"]), int(st["cases"]),
		         int(min(P.LAYERS_PER_PALLET,
		                 st["cases"] // P.CASES_PER_LAYER)),
		         bool(st["complete"])]

	# The other three robot cells on the line. They are not modelled - only
	# Robot 1 has a 3D model to drive - but a zone overview where three of the
	# eight rows never change is a zone overview nobody believes.
	zst = "held" if held else ""
	zone = {}
	zone["Z1"] = (state in ("Picking", "Placing"), robotFault)
	for i, zid in enumerate(("Z2", "Z3", "Z4")):
		o = (s["zclock"] + (i + 1) * 4.1) % P.CYCLE_S
		zone[zid] = ((not held) and o < 9.6, False)
	zone["Z5"] = ((not held) and not f["WrapperFilmFeed"], f["WrapperFilmFeed"])
	zone["Z6"] = (not held, False)
	zone["Z7"] = (bool(c3), False)
	zone["Z8"] = (bool(s.get("c1")), f["ConveyorJam"])

	if not s["named"]:
		for zid in P.ZONE_IDS:
			paths.append("Zones/%s/Name" % zid)
			vals.append(P.ZONE_NAME[zid])
		s["named"] = True

	for zid in P.ZONE_IDS:
		running, fault = zone[zid]
		paths += ["Zones/%s/State" % zid, "Zones/%s/Running" % zid,
		          "Zones/%s/Fault" % zid]
		vals += [_zoneRow(zst, running, fault), bool(running), bool(fault)]

	P.writePaths(paths, vals)
