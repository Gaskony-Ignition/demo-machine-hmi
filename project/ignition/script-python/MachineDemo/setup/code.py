"""
MachineDemo.setup - stand the whole cell up on a gateway, from the project.

Importing the project is the entire install. The one thing the cell needs that
a project export cannot carry - the tag provider - is a gateway CONFIG
resource, and 8.3's system.config creates it from here, live, with no file to
place, no config scan and no restart.

    MachineDemo.setup.check()          # report on every item, change nothing
    MachineDemo.setup.run()            # create whatever is missing
    MachineDemo.setup.fix("tags")      # just one item

and the same three from a terminal:

    curl ".../system/webdev/Machine_HMI_Demo/admin?cmd=check"
    curl ".../system/webdev/Machine_HMI_Demo/admin?cmd=setup"
    curl ".../system/webdev/Machine_HMI_Demo/admin?cmd=fix&name=tags"

EVERY CHECK IS INDEPENDENT AND NONE OF THEM STOPS AT THE FIRST FAILURE.
"The provider exists but the tags are missing", "the tags are there but the
alarms are not" and "everything is there but nothing is moving" need three
different actions, and they look identical if you only ever see the first
error.
"""

P = MachineDemo.plant

PROVIDER = P.PROVIDER
LOG = system.util.getLogger("MachineDemo.setup")


# The tag provider config, the same JSON the resource has on disk at
# data/config/resources/core/ignition/tag-provider/<name>/config.json. It lives
# HERE and nowhere else: a second copy as a file, for anyone who would rather
# scan it in, is a definition that goes stale on one side without saying so.
TAG_PROVIDER_CONFIG = {
	"profile": {
		"allowBackfill": False,
		"enableTagReferenceStore": True,
		"type": "STANDARD",
	},
	"settings": {
		"defaultDatasourceName": None,
		"editPermissions": {"securityLevels": [], "type": "AllOf"},
		"readOnly": False,
		"readPermissions": {"securityLevels": [], "type": "AllOf"},
		"valuePersistence": "Database",
		"writePermissions": {"securityLevels": [], "type": "AllOf"},
	},
}

# One tag from each end of the tree and several from the middle. Reading all of
# them is how "the tags are there" is told apart from "the first folder wrote
# and then it failed", which is what a half-configured provider looks like and
# reports no error anywhere.
PROBE_TAGS = ["Line/SimEnabled", "Safety/GuardsClosed", "Robot/J1_deg",
              "Pallet/Station2/CasesPlaced", "Conveyor/PE_Clear",
              "Zones/Z8/Name", "Faults/RobotAxisFault"]

# The tags that must be carrying alarm definitions, and how many each.
ALARM_TAGS = (["Safety/EStopOK", "Safety/GuardsClosed",
               "Safety/AirPressureOK", "Safety/InterfacesOK",
               "Safety/AirPressure_kPa", "Robot/Fault"]
              + ["Faults/%s" % n for n in
                 ["WrapperFilmFeed", "ConveyorJam", "VacuumLow", "GuardOpen",
                  "RobotAxisFault"]])


def _resource(typeId, name):
	"""A config resource, or None.

	getResource RAISES when the resource is missing rather than returning None,
	and it raises a java.lang.Throwable - which in Jython is NOT an Exception,
	so a plain `except Exception` walks straight past it and the caller gets a
	stack trace instead of an answer.
	"""
	from java.lang import Throwable as JThrowable
	try:
		return system.config.getResource(moduleId="ignition", typeId=typeId,
		                                 name=name)
	except (JThrowable, Exception):
		return None


def _upsert(typeId, name, config, description):
	"""Create it, or replace it if it is already there.

	`replace` needs the CURRENT signature - it is optimistic concurrency, and
	without it the call is refused rather than applied.
	"""
	existing = _resource(typeId, name)
	if existing is None:
		system.config.create(moduleId="ignition", typeId=typeId, name=name,
		                     config=config, description=description,
		                     actor="MachineDemo.setup")
		return "created"
	system.config.replace(moduleId="ignition", typeId=typeId, name=name,
	                      config=config, signature=existing.getSignature(),
	                      actor="MachineDemo.setup")
	return "updated"


# ---------------------------------------------------------------------------
# tag provider
# ---------------------------------------------------------------------------


def _providerCheck():
	if _resource("tag-provider", PROVIDER) is None:
		return False, u"tag provider '%s' does not exist" % PROVIDER
	return True, u"tag provider '%s' exists" % PROVIDER


def _providerFix():
	what = _upsert("tag-provider", PROVIDER, TAG_PROVIDER_CONFIG,
	               "Palletising cell demo tag provider - the cell's folders "
	               "live at the provider root")
	return u"tag provider '%s' %s" % (PROVIDER, what)


# ---------------------------------------------------------------------------
# tags
# ---------------------------------------------------------------------------


def _tagsCheck():
	from java.lang import Throwable as JThrowable
	try:
		qvs = system.tag.readBlocking([P.tag(p) for p in PROBE_TAGS])
	except (JThrowable, Exception):
		return False, u"the tag provider did not answer"
	bad = []
	for path, q in zip(PROBE_TAGS, qvs):
		try:
			good = q.quality.isGood()
		except:
			good = False
		if not good:
			bad.append(path)
	if bad:
		return False, u"missing or bad quality: %s" % u", ".join(bad)
	c = MachineDemo.tagdata.counts()
	return True, u"%d tags in %d folders readable in [%s]" % (
		c["tags"], c["folders"], PROVIDER)


def _tagsFix():
	"""Write the cell's tags into the provider.

	collisionPolicy "o" - overwrite. The tree is generated from the project and
	the project is its only source, so a rerun should put the gateway back to
	the shipped design rather than merge with whatever is there. Every value is
	simulated twice a second anyway, so nothing of anyone's is lost.
	"""
	from java.lang import Thread as JThread
	folders = MachineDemo.tagdata.tags()
	last = None
	# A provider created seconds ago is registered but not necessarily
	# accepting writes yet, and the failure is a bare throwable rather than
	# anything that says "try again". Three goes over four seconds; on a
	# provider that was already there the first one succeeds.
	for _attempt in range(3):
		try:
			system.tag.configure(u"[%s]" % PROVIDER, folders, u"o")
			c = MachineDemo.tagdata.counts()
			return u"wrote %d tags and %d alarm definitions into [%s]" % (
				c["tags"], c["alarms"], PROVIDER)
		except:
			import traceback
			last = traceback.format_exc().strip().split("\n")[-1]
			JThread.sleep(2000)
	raise Exception(u"could not write tags into [%s]: %s" % (PROVIDER, last))


# ---------------------------------------------------------------------------
# alarms
# ---------------------------------------------------------------------------


def _alarmsOn(path):
	from java.lang import Throwable as JThrowable
	try:
		cfg = system.tag.getConfiguration(P.tag(path), False)
	except (JThrowable, Exception):
		return []
	out = []
	for node in cfg:
		for a in (node.get("alarms") or []):
			try:
				out.append(unicode(a.get("name")))
			except:
				out.append(u"?")
	return out


def _alarmsCheck():
	"""The alarms are the demo, so prove they landed on the TAGS.

	A tag tree that wrote its values but dropped its alarm definitions reads
	perfectly on every screen and raises nothing, ever. That failure has no
	other symptom.
	"""
	missing = [p for p in ALARM_TAGS if not _alarmsOn(p)]
	if missing:
		return False, u"no alarm definition on: %s" % u", ".join(missing)
	total = sum(len(_alarmsOn(p)) for p in ALARM_TAGS)
	return True, u"%d alarm definitions on %d tags" % (total, len(ALARM_TAGS))


# ---------------------------------------------------------------------------
# the simulation
# ---------------------------------------------------------------------------


def _simCheck():
	"""Is the cell actually running?

	The timer script is a project resource, so it is always THERE. What this
	asks is whether it has TICKED - and the only answer that cannot be faked is
	watching the arm move: read three joints, wait, read them again. A tick
	counter in the simulator's own module would be cheaper, but it is only
	visible if this code and the timer happen to share a script manager, and
	"the sim is running" is not a question worth a maybe.
	"""
	from java.lang import Thread as JThread
	v = P.readDict({"enabled": "Line/SimEnabled", "speed": "Line/SimSpeed",
	                "state": "Robot/State"})
	if v.get("enabled") is None:
		return False, u"the simulation tags are not readable - write the tags first"
	if not v.get("enabled"):
		return False, u"the simulation is switched off (Line/SimEnabled)"

	probe = ["Robot/J1_deg", "Robot/J2_deg", "Robot/Lift_mm",
	         "Robot/Vacuum_kPa", "Safety/AirPressure_kPa"]
	before = P.read(probe)
	JThread.sleep(1400)
	after = P.read(probe)
	if before == after:
		return False, (u"the simulation is enabled but nothing moved in 1.4 s "
		               u"- check the CellSim gateway timer script is enabled, "
		               u"and that the robot is not held or faulted")
	return True, u"running at %sx, robot %s" % (
		v.get("speed"), v.get("state") or u"?")


def _simFix():
	mapping = {"Line/SimEnabled": True, "Line/SimSpeed": 1.0,
	           "Line/Mode": "Auto"}
	for n in P.FAULTS:
		mapping["Faults/%s" % n] = False
	P.write(mapping)
	MachineDemo.sim.clearInternals()
	return u"simulation enabled at 1x with every fault cleared"


# ---------------------------------------------------------------------------
# the items
# ---------------------------------------------------------------------------
# (key, title, check, fix, why). check returns (ok, detail); fix returns a
# one-line account of what it did, or raises.

def _items():
	c = MachineDemo.tagdata.counts()
	return [
		("tagProvider", "Tag provider", _providerCheck, _providerFix,
		 "A standard provider named %s, created live through system.config - "
		 "no file to place and no config scan to remember." % PROVIDER),
		("tags", "Cell tags", _tagsCheck, _tagsFix,
		 "%d tags across the line, the safety circuit, the robot, both pallet "
		 "stations, the conveyors, eight line zones and five injectable "
		 "faults - written into the provider from the copy the project "
		 "carries." % c["tags"]),
		("alarms", "Alarm definitions", _alarmsCheck, _tagsFix,
		 "%d alarms on the fault tags, the safety booleans and the robot. "
		 "They travel with the tags; this row is separate because a tree that "
		 "wrote its values and dropped its alarms looks perfect and raises "
		 "nothing." % c["alarms"]),
		("simulation", "Cell simulation", _simCheck, _simFix,
		 "The palletiser actually running a pattern - pick, traverse, place, "
		 "retract - at real machine speed. It is what makes every screen and "
		 "the 3D cell live."),
	]


def items():
	return _items()


FIXABLE = ["tagProvider", "tags", "alarms", "simulation"]


def check():
	"""Every item's state, in install order. Changes nothing.

	Returns {"items": [...], "ok": bool, "version": ...} where each item is
	{key, title, ok, detail, fixable, why} - one row of a Setup screen per
	item.
	"""
	rows = []
	for key, title, checkFn, fixFn, why in _items():
		try:
			ok, detail = checkFn()
		except:
			import traceback
			ok = False
			detail = traceback.format_exc().strip().split("\n")[-1]
			LOG.warn("check %s failed: %s" % (key, traceback.format_exc()))
		rows.append({"key": key, "title": title, "ok": bool(ok),
		             "detail": detail, "fixable": fixFn is not None,
		             "why": why})
	c = MachineDemo.tagdata.counts()
	return {"items": rows,
	        "ok": all(r["ok"] for r in rows),
	        "version": P.VERSION,
	        "provider": PROVIDER,
	        "cell": u"%s - %s" % (P.CELL_OWNER, P.CELL_NAME),
	        "counts": c}


def fix(key):
	"""Create one item. Returns a one-line account, or raises."""
	for k, _title, _checkFn, fixFn, _why in _items():
		if k != key:
			continue
		if fixFn is None:
			raise ValueError("%s cannot be created from the project" % key)
		return fixFn()
	raise ValueError("no such setup item: %s (try one of %s)"
	                 % (key, ", ".join(FIXABLE)))


def run():
	"""Create everything that is missing, in order, and report.

	Safe to run twice: every fix is an upsert or a no-op. Ordered as the
	dependencies run - the provider before the tags that go in it, the tags
	before the simulation that writes them - and a step that fails is recorded
	and the next one still runs, because "the provider failed" must not hide
	"and so did four other things".
	"""
	done, failed = [], []
	for key, _title, checkFn, fixFn, _why in _items():
		if fixFn is None:
			continue
		try:
			ok, _detail = checkFn()
		except:
			ok = False
		if ok:
			continue
		try:
			said = fix(key)
			if said not in done:
				done.append(said)
		except:
			import traceback
			failed.append("%s: %s"
			              % (key,
			                 traceback.format_exc().strip().split("\n")[-1]))
			LOG.warn("setup step %s failed: %s"
			         % (key, traceback.format_exc()))

	state = check()
	state["changed"] = done
	if failed:
		state["errors"] = failed
	LOG.info("setup run: %d changed, %d failed, ok=%s"
	         % (len(done), len(failed), state["ok"]))
	return state
