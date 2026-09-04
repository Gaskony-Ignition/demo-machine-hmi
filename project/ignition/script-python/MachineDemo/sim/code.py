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

Geometry is read the same way. The fifteen Config/* tags - case, pallet,
pattern, conveyor, where the two stations sit - are read every tick alongside
the controls, and everything the cycle needs that depends on them (the layer
pitch, the placement heights, where each pick goes on the pallet, how many
cases a pick is, the safe travel height, whether the arm can reach any of it)
is derived from them in _geometry() and cached until a value changes. So a
tag written in the Designer changes the MACHINE within a tick, not just the
picture: the 3D page rebuilds from the same tags, and the two agree because
they are both reading the one set of numbers. There is no second copy.
"""

import math
import random

from java.lang import System as JSystem
from java.util import Calendar

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


# The two places that do NOT move with the Config tags, in metres. The infeed
# conveyor's pick end is fixed beside the robot - the page draws the conveyor
# growing away from it when ConvLength changes - and home is home.
INFEED_XZ = (1.62, 0.10)          # pick point off the infeed conveyor
HOME_XZ = (1.10, 0.0)
HOME_WRIST_Y = 1.35

# Three offsets that are the 3D page's, read off how it draws the parts, so the
# arm puts a case exactly where the page shows one:
#   a case on the infeed rides ROLLER_TOP_M above the conveyor's top-of-belt
#   height (the rollers), layer 0 sits DECK_TOP_M above the pallet's deck
#   height (the deck boards), and the case the gripper holds has its top
#   WRIST_TO_CASE_TOP_M below the wrist (0.14 plate drop + 0.09 case drop).
# The gripper depth used to be 0.125 here while the page drew 0.23, so every
# placed case was set 105 mm INTO the layer below it and every pick reached
# 60 mm through the belt. Measured off the page's own numbers, 03/09/2026.
ROLLER_TOP_M = 0.045
DECK_TOP_M = 0.02
WRIST_TO_CASE_TOP_M = 0.23
CASE_INSET = 0.94                 # the page draws the pattern 6% inside its span

# How far above the tallest stack the wrist travels while it is swinging.
SAFE_CLEAR_M = 0.35

# Where the cartons stand on the infeed, and where the photo-eyes look.
#
# The accumulation queue is ONE model shared with the 3D page: cartons stop at
# a line 0.35 m from the near end of the belt and back up behind each other at
# a pitch of one case depth plus a 50 mm gap. The page draws that queue; this
# module decides which eyes it covers. Both sides have to use the same three
# numbers or a beam goes green with a carton sitting in it, which is the one
# thing a photo-eye must never do on a screen a fitter is reading.
#
# EYE_OFFSETS is each eye's distance from the stop line, in metres, positive
# upstream. Four of the six are measured from the FAR end of the belt, so they
# move when ConvLength does - hence a function of the length rather than a
# table of constants.
QUEUE_STOP_GAP_M = 0.35           # stop line, back from the near end
QUEUE_GAP_M = 0.05                # between one carton and the next


def _eyeOffsets(convLen):
	return {
		"PE_InPos2": -0.10,
		"PE_InPos1": 0.25,
		"PE_Carton": convLen - 3.45,
		"PE_Length2": convLen - 2.65,
		"PE_Length1": convLen - 2.05,
		"PE_Infeed": convLen - 0.70,
	}


# A placement is judged reached if the solved wrist lands within this of where
# it was asked to go. The arm's joints and column are clamped in _solve(), so
# anything further out than this is a slot the machine cannot build.
REACH_TOL_M = 0.05

# Everything else about the cell - the case, the pallet, the pattern, the
# conveyor height, where the stations sit - is the Config tags, derived into
# one dict by _geometry() and cached here until a tag changes. Nothing below
# this line reads a case height or a station position from anywhere else.
_G = None
_G_KEY = None


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


def _forward(j2, j3, lift):
	"""Where the wrist actually is for a solved (J2, J3, Lift): (radius, y).

	_solve() clamps every joint and the column to its travel, so its answer is
	not always the point it was asked for. Running that answer forward is how
	the reach report tells a slot the arm can build from one it cannot.
	"""
	a = math.radians(j2)
	b = math.radians(j2 + j3)
	r = L1 * math.cos(a) + L2 * math.cos(b)
	y = BASE_Y + lift / 1000.0 + L1 * math.sin(a) + L2 * math.sin(b)
	return r, y


HOME = _task(HOME_XZ[0], HOME_XZ[1], HOME_WRIST_Y)


# ---------------------------------------------------------------------------
# geometry, derived from the Config tags
# ---------------------------------------------------------------------------


def _grid(count):
	"""(rows, cols) for one layer of `count` cases - the SAME rule the 3D page
	uses, so the arm and the picture agree on where case n is.

	The factor pair closest to square, the larger factor along X (the wider
	pallet dimension). A count that will not factor - a prime - becomes one
	row of `count`, which tiles; anything that is not a positive number falls
	back to the 4 x 3 the demo shipped with, as the page does.
	"""
	try:
		count = int(count)
	except:
		count = 0
	if count <= 0:
		return 3, 4
	a = 1
	d = 1
	while d * d <= count:
		if count % d == 0:
			a = d
		d += 1
	return a, count // a


def _layout(g, rot):
	"""Station-local (x, z) of every case in a layer, in the order the page
	fills them: column by column, so that one pick - one column - is `rows`
	cases standing in a line. Odd layers are the same grid with the case
	turned, which is what interlocks the stack."""
	cw = g["caseD"] if rot else g["caseW"]
	cd = g["caseW"] if rot else g["caseD"]
	rows, cols = g["rows"], g["cols"]
	spanX = cols * cw
	spanZ = rows * cd
	out = []
	for q in range(cols):
		for r in range(rows):
			out.append(((-spanX / 2.0 + cw * (q + 0.5)) * CASE_INSET,
			            (-spanZ / 2.0 + cd * (r + 0.5)) * CASE_INSET))
	return out


def _geometry(raw):
	"""Everything the cycle needs, from the fifteen Config values.

	`raw` is {response key: int} - the same keys ?cmd=state publishes - with a
	default already filled in for any tag that did not read. Distances come in
	as whole millimetres and leave as metres, because the solve is in metres.
	"""
	mm = lambda k: raw[k] / 1000.0
	g = {
		"raw": dict(raw),
		"caseW": mm("caseW_mm"), "caseD": mm("caseD_mm"),
		"caseH": mm("caseH_mm"),
		"palletW": mm("palletW_mm"), "palletD": mm("palletD_mm"),
		"perLayer": max(1, int(raw["casesPerLayer"])),
		"layers": max(1, int(raw["layers"])),
		"convY": mm("convHeight_mm"),
		"stations": {1: (mm("station1X_mm"), mm("station1Z_mm")),
		             2: (mm("station2X_mm"), mm("station2Z_mm"))},
	}
	g["rows"], g["cols"] = _grid(g["perLayer"])
	# A pick is one column of the pattern: the case set squared up on the
	# infeed is the row of cases the gripper takes across in one go. With the
	# default 4 x 3 that is three, which is what it always was.
	g["pick"] = g["rows"]
	g["perPallet"] = g["perLayer"] * g["layers"]
	# Layer 0's case bottoms, and the wrist height that lifts a case set off
	# the infeed. Both derived, both matching the page to the millimetre.
	g["deck"] = mm("palletH_mm") + DECK_TOP_M
	g["pickWristY"] = g["convY"] + g["caseH"] + ROLLER_TOP_M + WRIST_TO_CASE_TOP_M
	g["pickLow"] = _task(INFEED_XZ[0], INFEED_XZ[1], g["pickWristY"])
	# Where each pick lands: the centroid of the cases it places, per layer
	# parity, in station-local metres. Column-major layout means a full column
	# has a centroid on the column's centreline; a short last column (a count
	# that does not divide) is simply whatever cases are left.
	slots = {}
	for parity in (0, 1):
		lay = _layout(g, parity == 1)
		cents = []
		for k in range(0, len(lay), g["pick"]):
			grp = lay[k:k + g["pick"]]
			cents.append((sum(c[0] for c in grp) / len(grp),
			              sum(c[1] for c in grp) / len(grp)))
		slots[parity] = cents
	g["slots"] = slots
	g["picksPerLayer"] = len(slots[0])
	g["pattern"] = "%d x %d interlock" % (g["layers"], g["perLayer"])
	# The infeed runs 8% faster than the robot consumes a column - see the
	# CARTON_PITCH note further down for why exactly-matched rates were wrong.
	g["cartonPitch"] = (P.CYCLE_S / float(g["pick"])) * 0.92
	g["bufferMax"] = 2 * g["pick"]
	g["reach"] = _reach(g)
	return g


def _reach(g):
	"""Can this arm build this pattern on these pallets? Asked of the solver.

	Every slot of every layer on both stations, plus the pick, is solved and
	run forward again; a wrist that lands more than REACH_TOL_M from where it
	was sent is a case the machine would set down in the wrong place - or, at
	the far corner of a big pallet, in mid-air. This is the number the
	geometry panel and ?cmd=state report, so a presenter who types a 2 m
	pallet finds out from the screen and not from the arm.
	"""
	bad = []
	worst = 0.0

	def check(where, pose):
		j1, r, y, j4 = pose
		j2, j3, lift = _solve(r, y)
		r2, y2 = _forward(j2, j3, lift)
		err = math.hypot(r - r2, y - y2)
		if err > REACH_TOL_M:
			bad.append("%s (%.0f mm short)" % (where, err * 1000.0))
		return err

	worst = max(worst, check("infeed pick", g["pickLow"]))
	for n in sorted(g["stations"].keys()):
		for layer in range(g["layers"]):
			for slot in range(g["picksPerLayer"]):
				pose = _placePoseG(g, n, slot, layer, None)
				worst = max(worst, check("station %d layer %d slot %d"
				                         % (n, layer + 1, slot + 1), pose))
	# The travel height over the finished stack: a pallet the arm can build
	# but cannot then clear is a pallet it collides with on the last retract.
	top = g["deck"] + g["layers"] * g["caseH"] + SAFE_CLEAR_M
	for n in sorted(g["stations"].keys()):
		x, z = g["stations"][n]
		worst = max(worst, check("clearing station %d" % n, _task(x, z, top)))
	if bad:
		note = "%d of %d placements beyond reach - first: %s" % (
			len(bad), 1 + 2 * g["layers"] * g["picksPerLayer"] + 2, bad[0])
	else:
		note = "every placement within reach (worst %.0f mm)" % (worst * 1000.0)
	return {"ok": not bad, "unreachable": len(bad), "worst_mm":
	        int(round(worst * 1000.0)), "note": note, "detail": bad[:8]}


def _rawFromRead(values):
	"""{key: int} from what the Config tags read back, defaults filling any
	tag that is missing or will not convert - a machine with a hole in its
	geometry is not a machine, so the hole is filled and the tag fixed later
	by setup rather than the cycle stopping."""
	raw = {}
	for (path, key, default), v in zip(P.GEOMETRY, values):
		try:
			raw[key] = int(v) if v is not None else int(default)
		except:
			raw[key] = int(default)
	return raw


def _geo(values=None):
	"""The current derived geometry. Pass the fifteen freshly read Config
	values from the tick; with none it reads them itself, which is what
	rehydration and ?cmd=status do. Rebuilt only when a value changes."""
	global _G, _G_KEY
	if values is None:
		if _G is not None:
			return _G
		values = P.read([c[0] for c in P.GEOMETRY])
	raw = _rawFromRead(values)
	key = tuple(raw[c[1]] for c in P.GEOMETRY)
	if key != _G_KEY:
		old = _G
		_G = _geometry(raw)
		_G_KEY = key
		if old is not None:
			changed = [c[1] for c in P.GEOMETRY
			           if old["raw"][c[1]] != raw[c[1]]]
			LOG.info("geometry changed (%s): %s, %d cases a pallet, %d a "
			         "pick; %s" % (", ".join(changed), _G["pattern"],
			                        _G["perPallet"], _G["pick"],
			                        _G["reach"]["note"]))
			if not _G["reach"]["ok"]:
				LOG.warn("geometry: %s" % _G["reach"]["note"])
			if _S is not None:
				_onGeometryChange(_S, _G)
	return _G


def _onGeometryChange(s, g):
	"""Bring the running cycle onto the new machine.

	The pallet counts are kept - the cases are on the pallet - and clamped to
	the new capacity, so a smaller pattern on a full station completes it and
	the wrapper takes it away. Layer and slot are re-derived from the count,
	the travel height from the new stack, and the next _target() call glides
	the arm from wherever it is to the new place. Names are re-written so the
	stations report the new pattern.
	"""
	for n in P.STATIONS:
		st = s["st"][n]
		st["cases"] = min(g["perPallet"], st["cases"])
		if st["cases"] >= g["perPallet"]:
			st["complete"] = True
	st = s["st"][s["active"]]
	s["layer"] = min(g["layers"] - 1, st["cases"] // g["perLayer"])
	s["slot"] = (st["cases"] % g["perLayer"]) // g["pick"]
	s["buf"] = min(g["bufferMax"], s["buf"])
	s["safeY"] = _safeWristY(s, s["layer"])
	s["named"] = False


def infeedInfo():
	"""The accumulation queue, for the 3D page: how many cartons are standing
	on the belt and the most it holds. The page draws this many, at the pitch
	in QUEUE_GAP_M, which is the same queue _eyes() blocks its beams with."""
	s = _state()
	g = _geo()
	return {"queue": int(s["buf"] + _staged(s)), "max": int(g["bufferMax"]),
	        "pitch_mm": int(round((g["caseD"] + QUEUE_GAP_M) * 1000.0)),
	        "stopGap_mm": int(round(QUEUE_STOP_GAP_M * 1000.0))}


def geometryInfo():
	"""The derived machine, for ?cmd=state and the geometry panel: additive,
	small, and cached - the poll pays nothing for it until a tag changes."""
	g = _geo()
	return {
		"pattern": g["pattern"],
		"rows": g["rows"], "cols": g["cols"],
		"casesPerPick": g["pick"],
		"picksPerLayer": g["picksPerLayer"],
		"casesPerPallet": g["perPallet"],
		"pickWristY_mm": int(round(g["pickWristY"] * 1000.0)),
		"stackTop_mm": int(round((g["deck"] + g["layers"] * g["caseH"]) * 1000.0)),
		"reach": g["reach"],
	}


def _stackTopM(s):
	"""The top of the TALLER of the two stacks, in metres.

	Both stations, not just the one being built: the arm swings across the
	cell, and a safe height worked out from the target pallet alone is not safe
	over the other one when that is the full pallet waiting for the wrapper.
	A part-built layer counts as a whole one - the cases in it are already at
	full height.
	"""
	g = _geo()
	top = g["deck"]
	for n in P.STATIONS:
		c = s["st"][n]["cases"]
		layers = (c + g["perLayer"] - 1) // g["perLayer"]
		top = max(top, g["deck"] + layers * g["caseH"])
	return top


def _safeWristY(s, layer):
	"""Travel height for this cycle: clear of both stacks and of the conveyor.

	Floored at the pick height so that on an empty pallet the arm still travels
	high enough to clear the infeed and the pallet rails rather than skimming
	them, which is what the bare stack-plus-clearance figure would give.
	"""
	g = _geo()
	top = max(_stackTopM(s), g["deck"] + (layer + 1) * g["caseH"])
	return max(g["pickWristY"], top + SAFE_CLEAR_M)

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
# Both the pitch and the buffer depend on how many cases a pick is, which is
# the pattern's, so they live on the derived geometry: g["cartonPitch"] and
# g["bufferMax"] (two picks' worth of accumulation - also the fuse on a jam:
# with the infeed stopped the robot works the buffer down and starves about
# 25 machine-seconds later, so the fault has a visible cause and then a
# visible effect rather than both at once).

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
		"safeY": _geo()["pickWristY"],
		"homing": 0.0,
		"wasBlocked": False,
		"active": 1,
		"slot": 0,
		"layer": 0,
		"buf": _geo()["bufferMax"],
		"carton": 0.0,
		"barcode": 0,
		"lastBarcode": "",
		"scanOK": True,
		"cpm": 0.0,
		"casesTotal": 0,
		"shiftIndex": -1,
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
		        "shiftIndex": "Line/ShiftIndex",
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
		s["shiftIndex"] = int(v.get("shiftIndex", -1) if v.get("shiftIndex") is not None else -1)
		s["cycleCount"] = int(v.get("cycleCount") or 0)
		if v.get("lift") is not None:
			s["jogLift"] = float(v.get("lift"))
			s["jogTarget"] = float(v.get("liftTarget") or v.get("lift"))
		bc = v.get("barcode") or ""
		if bc.startswith("T") and bc[1:].isdigit():
			s["barcode"] = int(bc[1:])
			s["lastBarcode"] = bc
		perPallet = _geo()["perPallet"]
		for n in P.STATIONS:
			st = s["st"][n]
			if v.get("p%d" % n) is not None:
				st["present"] = bool(v.get("p%d" % n))
			st["cases"] = min(perPallet, int(v.get("c%d" % n) or 0))
			st["complete"] = bool(v.get("k%d" % n))
			if st["cases"] >= perPallet:
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
		"safeY_m": round(s.get("safeY") or _geo()["pickWristY"], 3),
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
		"infeedStaged": _staged(s),
		"infeedOnBelt": s["buf"] + _staged(s),
		"cycleTime": round(s["cycleTime"], 2),
		"casesTotal": s["casesTotal"],
		"cycleCount": s["cycleCount"],
		"geometry": geometryInfo(),
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
	completed layers, so the case bottom is at deck + L*caseH and the wrist
	rides one case plus the gripper above that. Pass a height instead and it
	is the same J1 and radius at that height, which is what makes the descent
	vertical.
	"""
	return _placePoseG(_geo(), station, slot, layer, safeY)


def _placePoseG(g, station, slot, layer, safeY):
	"""_placePose against an explicit geometry - the reach report solves a
	geometry that is not (yet) the live one."""
	x, z = g["stations"].get(station, g["stations"][1])
	dx, dz = g["slots"][layer % 2][slot % g["picksPerLayer"]]
	if safeY is None:
		wristY = g["deck"] + layer * g["caseH"] + g["caseH"] + WRIST_TO_CASE_TOP_M
	else:
		wristY = safeY
	j4 = 90.0 if (layer % 2) else 0.0    # every second layer interlocks
	return _task(x + dx, z + dz, wristY, j4)


def _target(s, phase):
	"""Where the WRIST is going by the end of this phase.

	Read it down the list and the profile is the whole story: the two swings
	end at the safe height, the four vertical legs end with J1 unchanged.
	"""
	name = PHASES[phase][0]
	g = _geo()
	safeY = s.get("safeY") or g["pickWristY"]
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
		return g["pickLow"]
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


def _shiftIndex(now):
	"""Which 8-hour shift a moment falls in: 0 from 00:00, 1 from 08:00,
	2 from 16:00, and a different number tomorrow.

	Derived from the clock rather than counted, so a gateway that was off
	overnight comes back on the right shift instead of resuming yesterday's.

	Calendar, not arithmetic on the epoch: dividing currentTimeMillis by
	86400000 gives UTC days and a UTC hour, which on a +09:30 gateway would put
	the shift boundaries at 09:30, 17:30 and 01:30 local. Calendar.getInstance()
	uses the gateway's own zone, so the boundaries land where an operator would
	expect them.
	"""
	cal = Calendar.getInstance()
	cal.setTimeInMillis(now)
	day = cal.get(Calendar.YEAR) * 366 + cal.get(Calendar.DAY_OF_YEAR)
	return int(day * 3 + cal.get(Calendar.HOUR_OF_DAY) // 8)


def _rollShift(s, now):
	"""Zero the shift total when the shift changes.

	Without this the count only ever goes up: it is rehydrated from its tag on
	every scan and incremented on every pick, so a demo gateway left running
	reaches "12162 / 1800" against an 1800-case shift target - 676% of a target,
	on the headline throughput readout of the Overview. The label says SHIFT and
	it has to mean it.

	ShiftIndex of -1 means no shift was ever recorded against this total - the
	state of a gateway upgrading from a build that had no shift model. Whatever
	the total says there, it is not this shift's, so it is zeroed too. On a
	genuinely fresh install the total is already 0 and that costs nothing.
	"""
	idx = _shiftIndex(now)
	if s["shiftIndex"] == idx:
		return
	if s["casesTotal"]:
		LOG.info("shift %d -> %d: cases this shift reset from %d"
		         % (s["shiftIndex"], idx, s["casesTotal"]))
	s["casesTotal"] = 0
	s["shiftIndex"] = idx


def _tick():
	s = _state()

	now = JSystem.currentTimeMillis()
	_rollShift(s, now)
	dtr = (now - s["t"]) / 1000.0
	s["t"] = now
	if dtr <= 0.0:
		dtr = 0.5
	if dtr > 2.0:
		# The cell was paused, the gateway was busy, or the module just
		# reloaded. Cap it: integrating a ten second gap teleports the arm.
		dtr = 2.0

	# Everything the tick needs to read, in ONE round trip: the controls, the
	# two jog bits, the guard circuit and the fifteen geometry tags.
	want = {
		"enabled": "Line/SimEnabled",
		"speed": "Line/SimSpeed",
		"mode": "Line/Mode",
		"jogUp": "Robot/JogUp",
		"jogDown": "Robot/JogDown",
		"guards": "Safety/GuardsClosed",
	}
	for path, key, default in P.GEOMETRY:
		want[key] = path
	ctl = P.readDict(want)
	f = dict(zip(P.FAULTS, P.read(["Faults/%s" % n for n in P.FAULTS])))
	for k in f:
		f[k] = bool(f[k])

	if ctl.get("enabled") is None:
		# The provider is not there yet. Setup has not been run.
		return

	# The machine's shape, this tick. Cached until a value changes, and a
	# change re-derives the pattern and re-aims the cycle before anything
	# below moves.
	g = _geo([ctl.get(key) for path, key, default in P.GEOMETRY])

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
		# The cases this cycle reserved were never picked, so they are still on
		# the belt and must go back to the buffer. Without this a fault silently
		# ate a pick's worth of product every time it was injected: debited at
		# _startCycle, never placed, never returned.
		s["buf"] = min(_geo()["bufferMax"], s["buf"] + _staged(s))
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


def _staged(s):
	"""Cases the running cycle has reserved that are STILL on the conveyor.

	_startCycle debits the buffer the moment it commits, because it has to know
	it has product before it will move. But the cases do not leave the belt until
	the cups seal, which is Approach + Descend + a third of Grip - about 3.1 s
	later. Publishing the buffer alone told the 3D page to delete the cartons at
	cycle start, so the arm descended onto an empty belt and the staging eyes
	went clear with boxes still sitting in them.

	Derived from the phase rather than stored, so it cannot drift out of step
	with the arm it describes.
	"""
	if s["idle"]:
		return 0
	name = PHASES[s["phase"]][0]
	if name in ("Approach", "Descend"):
		return _geo()["pick"]
	if name == "Grip":
		# The same 0.35 the vacuum seals at: the instant the cups take the cases
		# is the instant they stop being on the conveyor. Both read it from here.
		return 0 if s.get("frac", 0.0) > 0.35 else _geo()["pick"]
	return 0


def _endPhase(s):
	"""Side effects that happen exactly at a phase boundary."""
	name = PHASES[s["phase"]][0]
	if name != "Release":
		return
	# The cases are on the pallet the instant the gripper lets go, so this is
	# where the pallet count moves - not at the end of the cycle, which would
	# show the arm already halfway home before the pallet changed.
	g = _geo()
	st = s["st"][s["active"]]
	placed = min(g["pick"], g["perPallet"] - st["cases"])
	st["cases"] = min(g["perPallet"], st["cases"] + g["pick"])
	s["casesTotal"] += max(0, placed)
	if st["cases"] >= g["perPallet"]:
		st["complete"] = True

	# Raise the travel height NOW, for the retract that follows, to whatever
	# the next cycle will need. The stack is one layer taller than it was when
	# this cycle worked its height out, and doing it here means the extra rise
	# happens on the vertical retract leg instead of part-way through the swing
	# back - the arm goes up and then across, rather than climbing as it goes.
	nextLayer = min(g["layers"] - 1, st["cases"] // g["perLayer"])
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
	g = _geo()
	if s["buf"] < g["pick"]:
		return False
	n = _availableStation(s)
	if n is None:
		return False
	s["active"] = n
	st = s["st"][n]
	s["layer"] = min(g["layers"] - 1, st["cases"] // g["perLayer"])
	s["slot"] = (st["cases"] % g["perLayer"]) // g["pick"]
	# Worked out ONCE per cycle, not per tick: it depends on the stacks, and a
	# travel height that moved under the arm halfway through a swing would jerk
	# the wrist every time a case landed.
	s["safeY"] = _safeWristY(s, s["layer"])
	s["buf"] -= g["pick"]
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
	g = _geo()
	s["carton"] += dt
	guard = 0
	while s["carton"] >= g["cartonPitch"] and guard < 20:
		guard += 1
		s["carton"] -= g["cartonPitch"]
		# bufferMax is how many cases the accumulation zone HOLDS, so cases the
		# robot has reserved but not yet lifted take up room in it. Capping on
		# the logical buffer alone let the belt draw eight cartons in a zone
		# stated to hold six. The barcode still advances either way: the scanner
		# is at the upstream end, ahead of the zone that is full.
		if s["buf"] < g["bufferMax"] - _staged(s):
			s["buf"] += 1
		s["barcode"] += 1
		s["lastBarcode"] = "T%05d" % s["barcode"]
		# One no-read in every 37 cartons. It is not a fault - it is the thing
		# an operator sees often enough to know what the ScanOK lamp means.
		s["scanOK"] = (s["barcode"] % 37) != 0


def _covered(g, buf, offset):
	"""Is there a carton standing on this point of the belt?

	The queue holds `buf` cartons from the stop line back, each one caseD long
	on a caseD + gap pitch. An eye is blocked when its offset falls inside one
	of them. This is geometry, not a phase: the beam is red because a box is
	in front of it, which is what the lamp claims.
	"""
	pitch = g["caseD"] + QUEUE_GAP_M
	# Half a case, plus half the gap between two of them. A beam has width and
	# a carton has flaps, and without the tolerance an eye sited exactly on the
	# join between two boxes - PE_Carton is, on the default belt, by 25 mm -
	# reads clear for ever with product standing on it.
	half = g["caseD"] / 2.0 + QUEUE_GAP_M / 2.0
	for i in range(int(buf)):
		if abs(offset - i * pitch) <= half:
			return True
	return False


def _eyes(s, f):
	"""The six photo-eyes, blocked by the cartons that are actually standing
	on the belt, plus the derived PE_Clear.

	This used to be a phase model - each eye made and broke on a fraction of
	the carton pitch, which looked convincing on a belt drawn with gaps
	between the cartons and became visibly wrong the moment the 3D page drew
	the queue accumulating: beams reading CLEAR with a carton sitting in
	them. The eyes are geometry now, off the same queue the page draws.
	"""
	g = _geo()
	# Cases reserved by a cycle that has not lifted them yet are still physically
	# in the beams, so the eyes count them - the same number the page draws.
	buf = s["buf"] + _staged(s)
	if f["ConveyorJam"]:
		# A jam IS a blocked eye, and it latches: which eyes are made is the
		# diagnosis an operator reads off the panel to find where the carton
		# stopped, so it must not keep moving with the queue behind it.
		return {"PE_Infeed": True, "PE_Carton": True, "PE_Length1": True,
		        "PE_Length2": False, "PE_Clear": False,
		        "PE_InPos1": buf >= 1, "PE_InPos2": buf >= 1}
	off = _eyeOffsets(g["raw"]["convLength_mm"] / 1000.0)
	eyes = {}
	for key, d in off.items():
		eyes[key] = _covered(g, buf, d)
	# The three along the run are what "clear" means - the two staging eyes at
	# the pick point are made whenever a set is waiting, which is most of the
	# time, and folding them in would make PE_Clear permanently false.
	eyes["PE_Clear"] = not (eyes["PE_Carton"] or eyes["PE_Length1"]
	                        or eyes["PE_Length2"])
	return eyes


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

	g = _geo()
	producing = state in ("Picking", "Placing")
	inst = (g["pick"] * 60.0 / s["cycleTime"]) if producing else 0.0
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
		"Line/CasesTotal", "Line/ShiftIndex",
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
		int(s["casesTotal"]), int(s["shiftIndex"]),
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
		         int(min(g["layers"], st["cases"] // g["perLayer"])),
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
		# Once after a reload, and again whenever the geometry changes: the
		# zone names, and the pattern each station is building - which is the
		# Config tags' pattern, not a string typed at install.
		for zid in P.ZONE_IDS:
			paths.append("Zones/%s/Name" % zid)
			vals.append(P.ZONE_NAME[zid])
		for n in P.STATIONS:
			paths.append("Pallet/Station%d/PatternName" % n)
			vals.append(g["pattern"])
		s["named"] = True

	for zid in P.ZONE_IDS:
		running, fault = zone[zid]
		paths += ["Zones/%s/State" % zid, "Zones/%s/Running" % zid,
		          "Zones/%s/Fault" % zid]
		vals += [_zoneRow(zst, running, fault), bool(running), bool(fault)]

	P.writePaths(paths, vals)
