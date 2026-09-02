"""
MachineDemo.tagdata - the cell's tag tree, as data.

A project export carries project resources and nothing else, so tags have to
travel some other way. Carrying them HERE means they travel inside the project
and MachineDemo.setup writes them into the provider with system.tag.configure:
importing the project is the entire install, with no second file to find and no
Designer step.

The tree is built by the small helpers below rather than pasted in as JSON,
because the alarm definitions are the part a reader needs to be able to check
and a 100 kB JSON string literal is not checkable.

Alarm design, deliberately:

* The five Faults/* tags and Robot/Fault alarm on Equality-true.
* The four Safety/* booleans alarm on Equality-FALSE - "guards closed" going
  false is the alarm, and writing it that way keeps the tag reading the way an
  electrician would name the circuit.
* On-delays are ZERO on every digital and 2 s on the one analog. Alarm
  on-delays are counted in REAL seconds by the alarm engine, and the simulator
  can be run at 8x, so any on-delay long enough to be interesting is an alarm a
  sped-up demo would never raise.
"""

P = MachineDemo.plant


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------


def _folder(name, tags):
	return {"name": name, "tagType": "Folder", "tags": tags}


def _atomic(name, dataType, value, extra=None):
	t = {"name": name, "tagType": "AtomicTag", "valueSource": "memory",
	     "dataType": dataType, "value": value}
	if extra:
		t.update(extra)
	return t


def _bool(name, value, alarms=None):
	extra = {"alarms": alarms} if alarms else None
	return _atomic(name, "Boolean", bool(value), extra)


def _str(name, value):
	return _atomic(name, "String", value)


def _int(name, value, engHigh=None):
	extra = {"formatString": "#,##0"}
	if engHigh is not None:
		extra["engLow"] = 0.0
		extra["engHigh"] = float(engHigh)
	return _atomic(name, "Int4", int(value), extra)


def _float(name, value, unit=None, lo=0.0, hi=100.0, fmt="#,##0.0",
           alarms=None):
	extra = {"engLow": float(lo), "engHigh": float(hi), "formatString": fmt}
	if unit:
		extra["engUnit"] = unit
	if alarms:
		extra["alarms"] = alarms
	return _atomic(name, "Float8", float(value), extra)


def _digital(name, display, priority, notes, setpoint=True):
	"""An alarm that fires when a boolean equals `setpoint`.

	No on-delay: see the module docstring. A digital fault on a machine is true
	the instant the PLC says so, and an operator who has to wait for it stops
	trusting the screen.
	"""
	return {"name": name, "mode": "Equality", "priority": priority,
	        "displayPath": display, "ackMode": "Manual", "notes": notes,
	        "setpointA": bool(setpoint)}


def _below(name, display, priority, notes, setpoint, deadband, onDelay=2):
	return {"name": name, "mode": "BelowValue", "priority": priority,
	        "displayPath": display, "ackMode": "Manual", "notes": notes,
	        "setpointA": float(setpoint), "deadband": float(deadband),
	        "timeOnDelaySeconds": onDelay}


# ---------------------------------------------------------------------------
# the tree
# ---------------------------------------------------------------------------


def _line():
	return _folder("Line", [
		_bool("Running", True),
		_str("Mode", "Auto"),
		_float("CasesPerMin", 0.0, "cases/min", 0.0, 30.0, "#,##0.0"),
		_float("CycleTime_s", P.CYCLE_S, "s", 0.0, 40.0, "#,##0.00"),
		_int("CasesTotal", 0),
		_bool("SimEnabled", True),
		_float("SimSpeed", 1.0, "x", 0.25, 10.0, "#,##0.00"),
		_int("ShiftTarget", 1800),
	])


def _safety():
	return _folder("Safety", [
		_bool("EStopOK", True, [_digital(
			"E-Stop Circuit Open",
			"Palletiser / Safety / E-Stop Circuit Open", "Critical",
			"An emergency stop has been pressed. Every drive in the cell is "
			"off. Find and release the button that was hit, then reset the "
			"safety relay at the main panel before anything will start.",
			setpoint=False)]),
		_bool("GuardsClosed", True, [_digital(
			"Guard Circuit Open",
			"Palletiser / Safety / Guard Circuit Open", "Critical",
			"A guard door or light curtain in the robot cell is open. Robot "
			"motion is held and the infeed has stopped. Clear the cell, close "
			"the guard and reset from the operator station - the robot will "
			"not resume on its own.",
			setpoint=False)]),
		_bool("AirPressureOK", True, [_digital(
			"Air Pressure Low",
			"Palletiser / Utilities / Air Pressure Low", "High",
			"Compressed air has fallen below the working threshold. The "
			"vacuum gripper cannot hold a full case set at this pressure. "
			"Check the plant air supply and the cell's filter-regulator.",
			setpoint=False)]),
		_bool("InterfacesOK", True, [_digital(
			"Machine Interface Fault",
			"Palletiser / Interfaces / Downstream Interface Fault", "Medium",
			"A handshake with an adjacent machine has failed - usually the "
			"stretch wrapper refusing a pallet. The cell keeps building but "
			"finished pallets will back up.",
			setpoint=False)]),
		_float("AirPressure_kPa", 620.0, "kPa", 0.0, 800.0, "#,##0", [_below(
			"Air Pressure Below Working",
			"Palletiser / Utilities / Air Pressure Below Working", "High",
			"Cell air pressure under 550 kPa. Below this the gripper's vacuum "
			"generator will not reach hold vacuum and cases can be dropped in "
			"transit.",
			550.0, 20.0)]),
	])


def _robot():
	return _folder("Robot", [
		_str("State", "Idle"),
		_float("J1_deg", 0.0, "deg", -170.0, 170.0, "#,##0.0"),
		_float("J2_deg", 20.0, "deg", -60.0, 90.0, "#,##0.0"),
		_float("J3_deg", -50.0, "deg", -140.0, 40.0, "#,##0.0"),
		_float("J4_deg", 0.0, "deg", -180.0, 180.0, "#,##0.0"),
		_float("Lift_mm", 620.0, "mm", 0.0, 1200.0, "#,##0"),
		_bool("GripperClosed", False),
		_float("Vacuum_kPa", 0.0, "kPa", -80.0, 0.0, "#,##0.0"),
		# Hold-to-run jog on the lift axis. Momentary bits: the HMI sets one
		# while a finger is on the button and the SIMULATOR owns the motion,
		# the same split a real machine has between the panel and the PLC. A
		# screen that moved the axis itself would keep moving it after the
		# interlock dropped, which is the whole reason machines are not built
		# that way.
		_bool("JogUp", False),
		_bool("JogDown", False),
		_float("LiftTarget_mm", 620.0, "mm", 0.0, 1200.0, "#,##0"),
		_bool("MotorsOn", True),
		_bool("Homed", True),
		_bool("Ready", True),
		_bool("Healthy", True),
		_int("CycleCount", 0),
		_float("CycleTime_s", P.CYCLE_S, "s", 0.0, 40.0, "#,##0.00"),
		_bool("Fault", False, [_digital(
			"Robot Fault",
			"Palletiser / Robot 1 / Robot Fault", "High",
			"The robot controller has faulted and stopped mid-pattern. Read "
			"Robot/FaultText for the controller's own message, clear the "
			"cause, then reset and re-home before restarting the pattern - a "
			"robot that faulted while carrying may still be holding cases.")]),
		_str("FaultText", ""),
	])


def _station(n):
	return _folder("Station%d" % n, [
		_bool("Present", True),
		_int("CasesPlaced", 0, P.CASES_PER_PALLET),
		_int("Layer", 0, P.LAYERS_PER_PALLET),
		_bool("Complete", False),
		_str("PatternName", P.PATTERN_NAME),
	])


def _pallet():
	return _folder("Pallet", [_station(n) for n in P.STATIONS])


def _conveyor():
	return _folder("Conveyor", [
		_bool("C1_Run", True),
		_bool("C2_Run", True),
		_bool("C3_Run", False),
		_float("C1_Speed_mpm", 18.0, "m/min", 0.0, 30.0, "#,##0.0"),
		_float("C2_Speed_mpm", 14.0, "m/min", 0.0, 30.0, "#,##0.0"),
		_float("C3_Speed_mpm", 0.0, "m/min", 0.0, 30.0, "#,##0.0"),
		_bool("PE_Infeed", False),
		_bool("PE_Carton", False),
		_bool("PE_Length1", False),
		_bool("PE_Length2", False),
		_bool("PE_InPos1", False),
		_bool("PE_InPos2", False),
		_bool("PE_Clear", True),
		_bool("Gate1_Up", False),
		_bool("Gate2_Up", False),
		_bool("Clamp_Extended", True),
		_str("LastBarcode", ""),
		_bool("ScanOK", True),
	])


def _zones():
	return _folder("Zones", [
		_folder(zid, [
			_str("Name", P.ZONE_NAME[zid]),
			_str("State", "Idle"),
			_bool("Running", False),
			_bool("Fault", False),
		]) for zid in P.ZONE_IDS
	])


def _faults():
	return _folder("Faults", [
		_bool("WrapperFilmFeed", False, [_digital(
			"Wrapper Film Feed Fault",
			"Palletiser / Wrapper / Film Feed Fault", "Medium",
			"The stretch wrapper has lost film feed and will not accept a "
			"pallet. Completed pallets stop discharging; the cell keeps "
			"building on the other station and will stop when both are full. "
			"Reload the film roll and reset the wrapper.")]),
		_bool("ConveyorJam", False, [_digital(
			"Infeed Carton Jam",
			"Palletiser / Infeed / Carton Jam", "High",
			"A carton is jammed on the infeed conveyor - the blocked "
			"photo-eye is what raised this. C1 has stopped and the robot will "
			"starve within a cycle. Clear the carton and restart the "
			"conveyor; check for a crushed case before running product on.")]),
		_bool("VacuumLow", False, [_digital(
			"Gripper Vacuum Low",
			"Palletiser / Robot 1 / Gripper Vacuum Low", "High",
			"Vacuum at the gripper has fallen below the hold threshold with "
			"cases picked. The robot has faulted rather than drop the set. "
			"Check the vacuum generator, the filter and the suction cups for "
			"a torn seal or a leaking case.")]),
		_bool("GuardOpen", False, [_digital(
			"Guard Door Open",
			"Palletiser / Safety / Guard Door Open", "Critical",
			"A cell guard door has been opened. This is a safety stop, not a "
			"pause: motors are off and the robot holds position. Nobody "
			"enters the cell without the key transfer interlock. Close the "
			"guard and reset at the operator station.")]),
		_bool("RobotAxisFault", False, [_digital(
			"Robot Axis Following Error",
			"Palletiser / Robot 1 / Axis Following Error", "High",
			"The robot controller has reported a following error on an axis "
			"and dropped motor power. Usually a mechanical obstruction, an "
			"overload from a jammed case, or a servo that needs attention. "
			"Reset at the pendant and re-home before running the pattern "
			"again.")]),
	])


def tags():
	"""The demo's top-level folders, as system.tag.configure() expects them."""
	return [_line(), _safety(), _robot(), _pallet(), _conveyor(), _zones(),
	        _faults()]


# ---------------------------------------------------------------------------
# counts, derived rather than remembered
# ---------------------------------------------------------------------------
# Every sentence in the project that says how big this cell is reads these.
# A count typed into prose is a count that is wrong the next time a tag moves.


def _walk(nodes):
	for n in nodes:
		if n.get("tagType") == "Folder":
			for sub in _walk(n.get("tags") or []):
				yield sub
		else:
			yield n


def counts():
	atoms = list(_walk(tags()))
	alarms = 0
	for a in atoms:
		alarms += len(a.get("alarms") or [])
	return {"tags": len(atoms), "alarms": alarms,
	        "folders": len(tags())}


def paths():
	"""Every atomic tag path in the tree, provider-relative, in tree order.

	MachineDemo.setup uses it to prove the whole tree landed rather than just
	the first folder, which is what a half-written provider looks like.
	"""
	out = []

	def walk(nodes, prefix):
		for n in nodes:
			name = n.get("name")
			full = ("%s/%s" % (prefix, name)) if prefix else name
			if n.get("tagType") == "Folder":
				walk(n.get("tags") or [], full)
			else:
				out.append(full)

	walk(tags(), "")
	return out
