"""
MachineDemo.setup - stand the whole cell up on a gateway, from the project.

Importing the project is the entire install. The three things the cell needs
that a project export cannot carry - its tag provider, its database connection
and its alarm journal - are gateway CONFIG resources, and 8.3's system.config
creates all three from here, live, with no file to place, no config scan and no
restart.

All three are the demo's OWN, named for it and shared with nothing. A demo that
borrows the gateway's general purpose connection has its alarm history
interleaved with every other project's, in a table whose retention belongs to
somebody else.

An existing gateway is UPGRADED by the same call. The robot arrived as a
folder of loose tags and is now a UDT instance; run() converts it in place with
system.tag.configure, keeping every tag path, and touches nothing outside this
demo's own provider.

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

# ---------------------------------------------------------------------------
# The demo's OWN database connection and OWN alarm journal.
#
# Every demo owns its resources. Pointing the journal at a gateway's general
# purpose connection and filtering the alarm screens by source only LOOKS like
# isolation: the rows still interleave with every other project's in one
# alarm_events table, and the retention belongs to somebody else. A cleanup on
# the gateway this was built on found 169,320 rows in one shared table and had
# to audit them per provider before it could safely delete any of them.
#
# Owning it costs nothing here because the connection is SQLite - a FILE beside
# the gateway. There is no server to reach, no credential to hold and no config
# scan to remember, so the demo still answers the customer's "and no database
# connections" with a yes rather than an apology.

DB = "MachineDemoDB"
DB_FILE = "machine-hmi-demo.db"

# journal_mode=WAL is not a tuning knob: the journal writes while a Perspective
# session reads the same file for the alarm table, and rollback-journal SQLite
# blocks the reader for the length of every write. busy_timeout then covers the
# one case WAL does not - two writers - by waiting rather than failing.
#
# `${data}` is expanded by Ignition, not by us, and resolves to the gateway's
# data directory on every platform, so the same string is right on Windows, on
# Linux and inside the container image.
DB_URL = ("jdbc:sqlite:${data}/%s?journal_mode=WAL&busy_timeout=30000"
          % DB_FILE)

# Ignition's own defaults for a new connection, with one change: poolMaxActive
# 8 -> 4. Eight pooled connections onto one SQLite file is eight threads
# contending for one write lock, and a demo has no business inventing a pool.
# There is no `password` key because there is no password - `username` is empty
# and the file is opened, not logged into - so the encrypt()-then-
# createEmbeddedSecretConfig() dance does not apply and must not be faked.
DB_CONFIG = {
	"connectURL": DB_URL,
	"connectionProps": "",
	"connectionResetParams": "",
	"defaultTransactionLevel": "DEFAULT",
	"driver": "SQLite",
	"evictionRate": -1,
	"evictionTests": 3,
	"evictionTime": 1800000,
	"failoverMode": "STANDARD",
	"failoverProfile": "",
	"includeSchemaInTableName": False,
	"poolInitSize": 0,
	"poolMaxActive": 4,
	"poolMaxIdle": 8,
	"poolMaxWait": 5000,
	"poolMinIdle": 0,
	"slowQueryLogThreshold": 60000,
	"testOnBorrow": True,
	"testOnReturn": False,
	"testWhileIdle": False,
	"translator": "SQLITE",
	"username": "",
	"validationQuery": "SELECT 1",
	"validationSleepTime": 10000,
}

# Ignition's own default table names, in a connection that holds nothing else.
# That is the whole point: alone in this file, alarm_events is this demo's
# alarm history and nobody else's, and it can be deleted by deleting a file.
JOURNAL = PROVIDER
JOURNAL_TABLE = "alarm_events"
JOURNAL_DATA_TABLE = "alarm_event_data"

# minPriority Diagnostic, not Low: the demo's injectable faults are the show,
# and a journal that silently drops the quiet ones is a screen full of nothing
# with no error anywhere. storeShelvedEvents so that shelving on the Alarms
# page still leaves a record of what was shelved.
JOURNAL_CONFIG = {
	"profile": {"queryOnly": False, "type": "DATASOURCE"},
	"settings": {
		"advanced": {
			"dataTableName": JOURNAL_DATA_TABLE,
			"tableName": JOURNAL_TABLE,
			"useStoreAndForward": True,
		},
		"dataFilters": {"pathFilterName": "", "pathOrSourceFilterName": "",
		                "sourceFilterName": ""},
		"datasource": DB,
		"eventData": {"dynamicAssociatedData": True, "dynamicConfig": True,
		              "staticAssociatedData": True, "staticConfig": False},
		"events": {"minPriority": "Diagnostic",
		           "storeFromEnabledChange": False,
		           "storeShelvedEvents": True},
		"pruning": {"age": 1, "ageUnits": "YEAR", "enabled": False},
	},
}


# One tag from each end of the tree and several from the middle. Reading all of
# them is how "the tags are there" is told apart from "the first folder wrote
# and then it failed", which is what a half-configured provider looks like and
# reports no error anywhere.
PROBE_TAGS = ["Config/CaseW_mm", "Line/SimEnabled", "Safety/GuardsClosed",
              "Robot/J1_deg", "Robot/LiftTarget_mm", "Robot/JogUp",
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


def _config(res):
	"""A resource's config as a plain dict.

	getConfig() hands back live wrapper objects; the round trip through JSON is
	what makes them ordinary Python to read and compare.
	"""
	return system.util.jsonDecode(system.util.jsonEncode(res.getConfig()))


def _names(typeId):
	"""Every config resource of a type on this gateway, by name.

	Used only to turn "it did not answer" into a sentence naming what this
	gateway does have, which is almost always the answer and is invisible from
	inside the project otherwise.
	"""
	from java.lang import Throwable as JThrowable
	try:
		return sorted([unicode(r.getName()) for r in
		               system.config.getResources(moduleId="ignition",
		                                          typeId=typeId)])
	except (JThrowable, Exception):
		return []


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
	return True, u"%d tags in %d top-level nodes readable in [%s]" % (
		c["tags"], c["folders"], PROVIDER)


def _bad(qualities):
	"""The quality codes system.tag.configure hands back that are NOT good.

	configure does not raise when it half-writes: it answers one quality per
	node it was given, and a tree whose Robot node came back Bad because its
	UDT definition was not there yet looks, from the return value nobody reads,
	exactly like a tree that wrote. Read them.
	"""
	out = []
	for q in (qualities or []):
		try:
			if q.isGood():
				continue
		except:
			pass
		try:
			text = unicode(q)
		except:
			text = u"?"
		if not text.startswith(u"Good"):
			out.append(text)
	return out


def _writeTypes():
	"""Put the UDT definitions in [<provider>]_types_.

	The base path is the _types_ folder itself and the node is an ordinary
	dict with tagType "UdtType" - the members are the same AtomicTag dicts a
	folder would hold, alarms included. This has to happen BEFORE the provider
	root is written, because the Robot node in that tree is an INSTANCE and an
	instance with no definition to resolve is refused.
	"""
	defs = MachineDemo.tagdata.types()
	q = system.tag.configure(u"[%s]_types_" % PROVIDER, defs, u"o")
	bad = _bad(q)
	if bad:
		raise Exception(u"UDT definitions refused: %s" % u", ".join(bad))
	return len(defs)


def _tagsFix():
	"""Write the cell's UDT definitions and its tags into the provider.

	collisionPolicy "o" - overwrite. The tree is generated from the project and
	the project is its only source, so a rerun should put the gateway back to
	the shipped design rather than merge with whatever is there. Every value is
	simulated twice a second anyway, so nothing of anyone's is lost.

	Overwrite is also what UPGRADES a gateway that already has this demo. On
	those, `Robot` is a plain folder of nineteen tags. Writing a UdtInstance
	over it with "o" converts it in place: same path, same member names, and
	the members that are no longer part of the definition are dropped rather
	than left behind. There is no delete step, no restart, and nothing outside
	this provider is touched - measured on the live gateway, not assumed.
	"""
	from java.lang import Thread as JThread
	last = None
	# A provider created seconds ago is registered but not necessarily
	# accepting writes yet, and the failure is a bare throwable rather than
	# anything that says "try again". Three goes over four seconds; on a
	# provider that was already there the first one succeeds.
	for _attempt in range(3):
		try:
			nTypes = _writeTypes()
			replaced = _clearStaleRobot()
			folders = MachineDemo.tagdata.tags()
			q = system.tag.configure(u"[%s]" % PROVIDER, folders, u"o")
			bad = _bad(q)
			if bad:
				raise Exception(u"provider refused: %s" % u", ".join(bad))
			_settle()
			c = MachineDemo.tagdata.counts()
			said = (u"wrote %d UDT definition(s) and %d tags with %d alarm "
			        u"definitions into [%s]"
			        % (nTypes, c["tags"], c["alarms"], PROVIDER))
			if replaced:
				said = u"%s, %s" % (said, replaced)
			return said
		except:
			import traceback
			last = traceback.format_exc().strip().split("\n")[-1]
			JThread.sleep(2000)
	raise Exception(u"could not write tags into [%s]: %s" % (PROVIDER, last))


def _robotCarriesValues():
	"""Do the robot's member tags actually hold a value?

	The one question that separates a working UDT instance from the broken one
	below, and it is not answerable from the configuration - only from a read.
	"""
	from java.lang import Throwable as JThrowable
	try:
		q = system.tag.readBlocking([P.tag("Robot/J1_deg")])[0]
		return bool(q.quality.isGood())
	except (JThrowable, Exception):
		return False


def _settle(seconds=6):
	"""Wait for the robot's members to start carrying values after a write.

	A tag tree comes back from system.tag.configure before its memory tags
	have their initial value, so the row underneath a successful fix would
	otherwise report the tags missing about the tags it had just written.
	"""
	from java.lang import Thread as JThread
	for _i in range(int(seconds * 2)):
		if _robotCarriesValues():
			return True
		JThread.sleep(500)
	return False


def _clearStaleRobot():
	"""Delete whatever is standing where the Robot INSTANCE goes, if it must.

	This is the whole upgrade path, and it is here because of a failure that
	reports success. system.tag.configure with collision policy "o" will write
	a UdtInstance straight over an existing FOLDER of the same name. It answers
	Good. Afterwards the node browses as a UdtInstance, getConfiguration
	returns all nineteen inherited members with their engineering ranges and
	their alarms, and `?cmd=check` is green - and every one of those members
	sits at Uncertain_InitialValue for ever and answers Bad_Unsupported to
	every write. The tag tree is perfect and the machine is dead, with nothing
	in any log. Measured on this gateway, 02/09/2026.

	Deleting the node first and creating the instance fresh gives members that
	read Good straight away. Overwriting an instance that is already HEALTHY is
	fine - also measured - so this deletes only when it has to: once on a
	gateway being upgraded, and never again.
	"""
	kind = _nodeType("Robot")
	if kind is None:
		return None
	if kind == u"UdtInstance" and _robotCarriesValues():
		return None
	from java.lang import Thread as JThread
	system.tag.deleteTags([P.tag("Robot")])
	JThread.sleep(500)
	if kind == u"UdtInstance":
		return u"replaced a Robot instance whose members carried no value"
	return u"replaced the old Robot %s with an instance of '%s'" % (
		kind.lower() if kind else u"node", MachineDemo.tagdata.ROBOT_TYPE)


# ---------------------------------------------------------------------------
# the robot UDT
# ---------------------------------------------------------------------------


def _nodeType(path):
	"""The tagType at a provider path, or None if there is nothing there."""
	from java.lang import Throwable as JThrowable
	try:
		cfg = system.tag.getConfiguration(P.tag(path), False)
	except (JThrowable, Exception):
		return None
	for node in cfg:
		try:
			return unicode(node.get("tagType"))
		except (JThrowable, Exception):
			return None
	return None


def _udtCheck():
	"""The definition exists AND the robot is an instance of it.

	Two questions again, and they fail apart. A gateway that was set up before
	the robot became a UDT has the definition (this fix wrote it) and a plain
	FOLDER at Robot, which reads identically on every screen - the difference
	is invisible everywhere except here and in the Designer.
	"""
	typeName = MachineDemo.tagdata.ROBOT_TYPE
	typePath = u"_types_/%s" % typeName
	if _nodeType(typePath) != u"UdtType":
		return False, u"no UDT definition at [%s]%s" % (PROVIDER, typePath)
	from java.lang import Throwable as JThrowable
	try:
		members = [unicode(t.get("name")) for t in
		           system.tag.getConfiguration(P.tag(typePath), True)[0]
		           .get("tags")]
	except (JThrowable, Exception):
		members = []
	want = [unicode(m["name"]) for m in MachineDemo.tagdata._robotMembers()]
	missing = [m for m in want if m not in members]
	if missing:
		return False, (u"'%s' is missing member(s): %s"
		               % (typeName, u", ".join(missing)))
	kind = _nodeType("Robot")
	if kind != u"UdtInstance":
		return False, (u"[%s]Robot is a %s, not an instance of '%s'"
		               % (PROVIDER, kind or u"nothing", typeName))
	# Being an instance is not enough. An instance written over a folder is an
	# instance in every way except that its members never carry a value, so
	# this row asks the only question that tells them apart.
	if not _robotCarriesValues():
		return False, (u"[%s]Robot is an instance of '%s' but its members "
		               u"carry no value - it was written over the old folder "
		               u"instead of replacing it. Fix this row."
		               % (PROVIDER, typeName))
	return True, (u"'%s' defines %d members and [%s]Robot is a live instance "
	              u"of it" % (typeName, len(members), PROVIDER))


# ---------------------------------------------------------------------------
# the machine's geometry
# ---------------------------------------------------------------------------


def _configPaths():
	return [p for p in MachineDemo.tagdata.paths() if p.startswith("Config/")]


def _configCheck():
	"""Every geometry tag readable, with the values a reader can sanity-check.

	The detail line quotes the case and the pallet on purpose: "15 tags exist"
	and "15 tags exist and the case is 300 x 250 x 220" are different amounts
	of proof, and the second one costs nothing.
	"""
	paths = _configPaths()
	if not paths:
		return False, u"the project carries no Config tags"
	vals = P.read(paths)
	missing = [p for p, v in zip(paths, vals) if v is None]
	if missing:
		return False, u"missing or bad quality: %s" % u", ".join(missing)
	got = dict(zip(paths, vals))
	return True, (u"%d geometry tags in [%s]Config - case %sx%sx%s mm, pallet "
	              u"%sx%s mm, %s cases x %s layers"
	              % (len(paths), PROVIDER,
	                 got.get("Config/CaseW_mm"), got.get("Config/CaseD_mm"),
	                 got.get("Config/CaseH_mm"), got.get("Config/PalletW_mm"),
	                 got.get("Config/PalletD_mm"),
	                 got.get("Config/CasesPerLayer"),
	                 got.get("Config/Layers")))


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
# the demo's own database connection
# ---------------------------------------------------------------------------


def _databaseCheck():
	"""The connection exists AND answers.

	Two questions, because they fail apart. The resource can be there while the
	pool has not started - a connection created seconds ago is registered
	before it has opened the file - and a query is the only thing that tells
	the difference.
	"""
	if _resource("database-connection", DB) is None:
		have = _names("database-connection")
		return False, (u"connection '%s' does not exist. This gateway has: %s"
		               % (DB, u", ".join(have) if have else u"(none)"))
	from java.lang import Throwable as JThrowable
	try:
		system.db.runScalarQuery("SELECT 1", DB)
	except (JThrowable, Exception):
		return False, (u"connection '%s' exists but did not answer 'SELECT 1'"
		               % DB)
	return True, u"'%s' answering - SQLite at %s" % (DB, DB_URL)


def _databaseFix():
	"""Make the demo's own SQLite connection.

	Nothing to fill in: no host, no port, no credential. The driver creates the
	file on first use if it is not there.
	"""
	if _resource("database-connection", DB) is None:
		have = _names("database-driver")
		if "SQLite" not in have:
			raise Exception(
				u"this gateway has no 'SQLite' JDBC driver (it has: %s). "
				u"SQLite ships with Ignition, so a gateway without it has had "
				u"it removed." % (u", ".join(have) if have else u"none"))
	what = _upsert("database-connection", DB, DB_CONFIG,
	               "Machine HMI Demo's own database - a SQLite file beside "
	               "the gateway, holding this demo's alarm journal and "
	               "nothing else")

	# Creating the RESOURCE and having a live pooled CONNECTION are not the
	# same moment, and the gap is long enough that the row underneath this one
	# would otherwise say "created" and "did not answer" about the same
	# connection in the same second.
	from java.lang import Thread as JThread
	for _attempt in range(15):
		ok, _detail = _databaseCheck()
		if ok:
			return u"connection '%s' %s at %s" % (DB, what, DB_URL)
		JThread.sleep(1000)
	return (u"connection '%s' %s but is not answering yet - check the row "
	        u"below in a moment" % (DB, what))


# ---------------------------------------------------------------------------
# the demo's own alarm journal
# ---------------------------------------------------------------------------


def _journalCheck():
	"""The profile exists and writes to THIS demo's connection.

	Pointing at the wrong datasource is the failure worth naming. A journal
	profile writing somewhere else does not error: the alarm page just shows a
	history that is somebody else's, or none at all, and nothing anywhere says
	why.
	"""
	res = _resource("alarm-journal", JOURNAL)
	if res is None:
		have = _names("alarm-journal")
		return False, (u"alarm journal profile '%s' does not exist. This "
		               u"gateway has: %s"
		               % (JOURNAL, u", ".join(have) if have else u"(none)"))
	from java.lang import Throwable as JThrowable
	try:
		ds = _config(res)["settings"]["datasource"]
	except (JThrowable, Exception):
		ds = None
	if ds != DB:
		return False, (u"profile '%s' writes to '%s', not this demo's '%s'"
		               % (JOURNAL, ds, DB))
	return True, u"profile '%s' writes %s on '%s'" % (JOURNAL, JOURNAL_TABLE,
	                                                  DB)


def _journalFix():
	what = _upsert("alarm-journal", JOURNAL, JOURNAL_CONFIG,
	               "Machine HMI Demo's own alarm journal - writes the standard "
	               "alarm_events / alarm_event_data tables into this demo's "
	               "own connection, sharing them with nothing")
	return u"alarm journal profile '%s' %s, pointed at '%s'" % (JOURNAL, what,
	                                                            DB)


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
	           "Line/Mode": "Auto", "Safety/GuardsClosed": True,
	           "Robot/JogUp": False, "Robot/JogDown": False}
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
		 "%d tags across the machine's geometry, the line, the safety "
		 "circuit, the robot, both pallet stations, the conveyors, eight line "
		 "zones and five injectable faults - written into the provider from "
		 "the copy the project carries, %d UDT definition(s) first."
		 % (c["tags"], c["udts"])),
		("udt", "Robot UDT", _udtCheck, _tagsFix,
		 "The robot is an instance of the '%s' type under [%s]_types_, not a "
		 "folder of %d loose tags - so a second arm is a second instance and "
		 "the alarm on Robot/Fault is defined once. Every member path is "
		 "unchanged: a gateway set up before this row existed is converted in "
		 "place, without a restart."
		 % (MachineDemo.tagdata.ROBOT_TYPE, PROVIDER,
		    len(MachineDemo.tagdata._robotMembers()))),
		("config", "Machine geometry", _configCheck, _tagsFix,
		 "%d tags under [%s]Config holding the case, the pallet, the conveyor "
		 "and where the two build stations sit. The 3D page and the screens "
		 "read them, so the next machine is a handful of tag values rather "
		 "than a source edit." % (len(_configPaths()), PROVIDER)),
		("alarms", "Alarm definitions", _alarmsCheck, _tagsFix,
		 "%d alarms on the fault tags, the safety booleans and the robot. "
		 "They travel with the tags; this row is separate because a tree that "
		 "wrote its values and dropped its alarms looks perfect and raises "
		 "nothing. The robot's is defined on the UDT and inherited by the "
		 "instance, which is why it still reads at Robot/Fault."
		 % c["alarms"]),
		("database", "Database connection", _databaseCheck, _databaseFix,
		 "This demo's own connection, named %s - SQLite, so it is a file "
		 "beside the gateway with no server to reach, no credential and no "
		 "config scan. It exists so the alarm journal below has somewhere of "
		 "its own to write." % DB),
		("journal", "Alarm journal", _journalCheck, _journalFix,
		 "A journal profile named %s writing %s into %s and sharing it with "
		 "nothing. Filtering a shared journal by source only looks like "
		 "isolation - the rows still interleave with every other project's, "
		 "and the retention belongs to someone else."
		 % (JOURNAL, JOURNAL_TABLE, DB)),
		("simulation", "Cell simulation", _simCheck, _simFix,
		 "The palletiser actually running a pattern - pick, traverse, place, "
		 "retract - at real machine speed. It is what makes every screen and "
		 "the 3D cell live."),
	]


def items():
	return _items()


FIXABLE = ["tagProvider", "tags", "udt", "config", "alarms", "database",
           "journal", "simulation"]


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

