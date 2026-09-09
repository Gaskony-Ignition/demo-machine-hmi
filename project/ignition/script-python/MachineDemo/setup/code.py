"""
MachineDemo.setup - stand the whole cell up on a gateway, from the project.

Importing the project is the entire install. The things the cell needs that a
project export cannot carry - its tag provider, and on a gateway that can have
one, a database connection and an alarm journal - are gateway CONFIG
resources, and 8.3's system.config creates them from here, live, with no file
to place, no config scan and no restart.

This demo argues for Ignition Edge Panel on a machine builder's small,
single-panel machines, and Edge Panel has NO database connectivity at all - it
is not merely discouraged, the module that provides it (SQL Bridge) is absent
from the Edge build. So setup asks the gateway what it can actually do
(_hasDatabaseModule, below) before it tries anything database-shaped:

  - a gateway WITH SQL Bridge gets exactly what this demo always gave it - its
    own SQLite connection and a DATASOURCE alarm journal writing into it.
  - a gateway WITHOUT it (Edge Panel) gets no connection attempt at all, and
    the alarm journal is configured as a LOCAL profile instead - Edge's own
    internal alarm history, no datasource, no database anywhere. Alarms are
    still journalled and the Alarms screen still has history to show; only
    the *mechanism* changes.

Both are the demo's OWN, named for it and shared with nothing. A demo that
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
JOURNAL_NAME_TAG = "Line/JournalName"
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

# The no-database journal. Same dataFilters/eventData/events/pruning as
# JOURNAL_CONFIG above - same alarms, same priority floor, same retention -
# minus the two things only a database can back: "advanced" (the table
# names) and "datasource". Confirmed against a live gateway, 03/09/2026: a
# real system.config.create with exactly this shape for typeId "alarm-journal"
# is accepted and reads back byte-for-byte unchanged - no extra fields get
# filled in, none of these get dropped.
JOURNAL_CONFIG_LOCAL = {
	"profile": {"type": "LOCAL"},
	"settings": {
		"dataFilters": {"pathFilterName": "", "pathOrSourceFilterName": "",
		                "sourceFilterName": ""},
		"eventData": {"dynamicAssociatedData": True, "dynamicConfig": True,
		              "staticAssociatedData": True, "staticConfig": False},
		"events": {"minPriority": "Diagnostic",
		           "storeFromEnabledChange": False,
		           "storeShelvedEvents": True},
		"pruning": {"age": 1, "ageUnits": "YEAR", "enabled": False},
	},
}


# Test-only override for _hasDatabaseModule(), below. None (the shipped
# value) means "ask the gateway for real". True/False forces the answer so
# the no-database branch can be driven and its consequences proven
# deterministically on a gateway that DOES have SQL Bridge - which is the
# only kind of gateway this was ever tested against. Never leave this at
# anything but None outside of a scratch diagnostic session; nothing in this
# module sets it.
_FORCE_NO_DB = None


def _hasDatabaseModule():
	"""Can this gateway create a database connection at all?

	The positive, structural answer, not a license flag and not a guess:
	whether ('ignition', 'database-connection') is among the resource types
	system.config.getResourceTypes() knows about. That type - and
	'database-driver' and 'database-translator' alongside it - is registered
	by the SQL Bridge gateway module (com.inductiveautomation...sqlbridge),
	which also backs every system.db.* call. Ignition Edge Panel does not
	ship SQL Bridge at all: it is not disabled by license, the module is
	simply absent from the Edge build, so the type is never registered there
	and this answers False with nothing to catch.

	Measured on THIS (STANDARD) gateway, 03/09/2026: getResourceTypes()
	returns 57 (module, type) pairs, including ('ignition',
	'database-connection'), ('ignition', 'database-driver') and ('ignition',
	'database-translator'); the installed-module list
	(ModuleManager.getModuleInfoAsJson()) independently confirms SQL Bridge
	itself is ACTIVE. ('ignition', 'alarm-journal') is ALSO in that list
	regardless - it is registered by the gateway core, not SQL Bridge,
	because its LOCAL flavour (JOURNAL_CONFIG_LOCAL, above) needs no database
	and was proven live on this same gateway: system.config.create with
	profile.type "LOCAL" was accepted and read back unchanged, with no
	datasource anywhere in it.

	This project has never run against a real Edge Panel gateway - proving
	Edge itself lacks SQL Bridge is out of scope here, and is the documented,
	reasoned answer rather than a measured one. _FORCE_NO_DB is what lets the
	no-database branch be exercised and its results proven anyway, on this
	standard gateway, without guessing at what setup would do on one.
	"""
	if _FORCE_NO_DB is not None:
		return not _FORCE_NO_DB
	from java.lang import Throwable as JThrowable
	try:
		return ("ignition", "database-connection") in system.config.getResourceTypes()
	except (JThrowable, Exception):
		# getResourceTypes() itself is not documented anywhere we have handy,
		# so if some future gateway build does not carry it, do not risk a
		# write from inside what must stay a read-only check - default to
		# "no database" rather than assume a capability nothing confirmed.
		LOG.warn("could not determine database capability - "
		         "assuming none (see _hasDatabaseModule)")
		return False


def _isEdgeGateway():
	"""Is this an Ignition Edge gateway?

	The same structural question as _hasDatabaseModule, asked of a type only
	Edge registers: ('ignition', 'edge-system-properties'), which backs the
	Config -> Ignition Edge page. Measured on a real Edge 8.3.8 gateway
	09/09/2026 - 55 resource types, including 'edge-system-properties' and
	'edge-sync-settings', and NOT 'database-connection'.

	'alarm-journal' is registered on Edge too, so the journal cannot be
	detected the way the database is - the type is there and the CREATE is
	what gets refused, with java.lang.UnsupportedOperationException("Cannot
	create Alarm Journal on Edge").
	"""
	from java.lang import Throwable as JThrowable
	try:
		return ("ignition", "edge-system-properties") in \
		       system.config.getResourceTypes()
	except (JThrowable, Exception):
		return False


def journalName():
	"""The alarm journal this gateway actually keeps history in.

	Edge has exactly one, made by the platform (EdgeJournal, unless a site
	renamed it) and unremovable; everywhere else it is this demo's own,
	named for it. The Alarms screen binds its table to this rather than to a
	constant, because a journal table pointed at a profile that does not
	exist shows an empty history and no error.
	"""
	if not _isEdgeGateway():
		return JOURNAL
	have = _names("alarm-journal")
	if JOURNAL in have:
		return JOURNAL
	return have[0] if have else JOURNAL


# One tag from each end of the tree and several from the middle. Reading all of
# them is how "the tags are there" is told apart from "the first folder wrote
# and then it failed", which is what a half-configured provider looks like and
# reports no error anywhere.
# Kept as the sample the STATUS reply shows when it wants a handful of
# representative tags. The tag CHECK no longer uses it - it reads every path
# the design declares, for the reason in _tagsCheck.
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
	"""The provider exists AND is running.

	The config resource existing is not enough. Edge permits exactly one
	realtime provider, and a second one written through system.config is
	accepted as a resource and then refused at startup - "Unable to start
	provider: 'MachineDemo', an Edge Gateway Provider is already registered"
	in the log, nothing raised at the caller. This row read green while all
	113 tags failed with Bad_NotFound underneath it, which is the one thing
	it exists to prevent. Browsing is what tells them apart.
	"""
	if _resource("tag-provider", PROVIDER) is None:
		if _isEdgeGateway():
			return False, (u"tag provider '%s' does not exist. Edge keeps "
			               u"exactly ONE realtime provider and will not "
			               u"start a second - name it '%s' under Config -> "
			               u"Ignition Edge -> Tag Provider (this gateway "
			               u"has: %s)"
			               % (PROVIDER, PROVIDER,
			                  u", ".join(_names("tag-provider"))))
		return False, u"tag provider '%s' does not exist" % PROVIDER
	from java.lang import Throwable as JThrowable
	try:
		system.tag.browse("[%s]" % PROVIDER)
	except (JThrowable, Exception):
		return False, (u"tag provider '%s' is configured but not running - "
		               u"on Edge that means a second provider was written "
		               u"and refused at startup; rename Edge's own provider "
		               u"to '%s' instead" % (PROVIDER, PROVIDER))
	return True, u"tag provider '%s' exists and is running" % PROVIDER


def _providerFix():
	if _isEdgeGateway() and _resource("tag-provider", PROVIDER) is None:
		# Writing one here would be accepted and then never started, leaving
		# the row green and every tag write failing underneath it.
		return (u"not created - Edge permits one realtime provider. Set "
		        u"Config -> Ignition Edge -> Tag Provider to '%s' and save; "
		        u"the rename is live, no restart." % PROVIDER)
	what = _upsert("tag-provider", PROVIDER, TAG_PROVIDER_CONFIG,
	               "Palletising cell demo tag provider - the cell's folders "
	               "live at the provider root")
	return u"tag provider '%s' %s" % (PROVIDER, what)


# ---------------------------------------------------------------------------
# tags
# ---------------------------------------------------------------------------


def _tagsCheck():
	"""Prove every tag in the design is actually in the provider.

	This used to probe ten hand-picked tags and then report
	MachineDemo.tagdata.counts() - the count from the PROJECT - as though it
	were the gateway's. Two things followed, and both bit:

	  * A tag added to the design was invisible to the check unless someone
	    also remembered to add it to the probe list. Line/ShiftIndex was added,
	    the check stayed green, RUN SETUP reported "changed: []", and the tag
	    was never created. The sim wrote to a path that did not exist - which
	    Ignition drops in silence - so the value never persisted and every
	    gateway restart reset the shift total it was supposed to be keeping.
	  * The number in the message was the design's, not the gateway's. It read
	    "113 tags readable in [MachineDemo]" against a provider holding 112.
	    A check that counts the thing it is checking AGAINST cannot fail.

	So: read every path the design declares, and report how many came back.
	That is what tagdata.paths() was written for - its own docstring says the
	setup uses it to prove the whole tree landed - it had simply never been
	wired up here.
	"""
	from java.lang import Throwable as JThrowable
	paths = MachineDemo.tagdata.paths()
	try:
		qvs = system.tag.readBlocking([P.tag(p) for p in paths])
	except (JThrowable, Exception):
		return False, u"the tag provider did not answer"
	bad = []
	for path, q in zip(paths, qvs):
		try:
			good = q.quality.isGood()
		except:
			good = False
		if not good:
			bad.append(path)
	if bad:
		# Name a few rather than all of them - a provider that is missing
		# everything would otherwise fill the page.
		shown = u", ".join(bad[:6])
		if len(bad) > 6:
			shown = u"%s and %d more" % (shown, len(bad) - 6)
		return False, u"%d of %d tags missing or bad quality: %s" % (
			len(bad), len(paths), shown)
	c = MachineDemo.tagdata.counts()
	return True, u"all %d tags in %d top-level nodes readable in [%s]" % (
		len(paths), c["folders"], PROVIDER)


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
	"""The connection exists AND answers - or this edition cannot have one.

	Three questions, in order, because they fail apart. First: can this
	gateway have a database connection at all (_hasDatabaseModule) - on an
	edition that cannot, this row reports green and "not applicable" rather
	than red "missing", because there is nothing to be missing. Only on a
	gateway that CAN have one do the other two apply: the resource can be
	there while the pool has not started - a connection created seconds ago
	is registered before it has opened the file - and a query is the only
	thing that tells the difference.
	"""
	if not _hasDatabaseModule():
		return True, (u"not applicable on this edition - no SQL Bridge "
		              u"module, so no database connection is possible here. "
		              u"The alarm journal below uses Edge's own local "
		              u"profile instead.")
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
	"""Make the demo's own SQLite connection - or skip it cleanly.

	Nothing to fill in on a gateway that can have one: no host, no port, no
	credential. The driver creates the file on first use if it is not there.

	On a gateway with no SQL Bridge module, there is nothing this CAN create -
	system.config would refuse a database-connection resource type it never
	registered - so this is a clean, reported no-op rather than an attempt
	that fails. _databaseCheck already reports that row green, so run() never
	calls this in that case; it stays safe to call directly all the same.
	"""
	if not _hasDatabaseModule():
		return (u"skipped - this edition has no SQL Bridge module, so no "
		        u"database connection is possible; nothing to create")
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
	"""The profile exists and is the right FLAVOUR for this edition.

	Two different questions depending on what the gateway can do. With a
	database: does the profile write to THIS demo's connection - pointing at
	the wrong datasource is the failure worth naming, because a journal
	profile writing somewhere else does not error, the alarm page just shows
	a history that is somebody else's, or none at all, and nothing anywhere
	says why. Without one: is the profile the LOCAL flavour Edge provides -
	a profile left over from a database this edition no longer has (or never
	had) journals nothing, silently, the same way.
	"""
	if _isEdgeGateway():
		if not _names("alarm-journal"):
			return False, u"this Edge gateway has no alarm journal at all"
		ok, why = _journalTagCheck()
		if not ok:
			return False, why
		return True, (u"'%s' is Edge's own journal - Edge keeps exactly one "
		              u"and will not accept a second, so this demo uses it "
		              u"rather than creating its own, and %s carries the name"
		              % (journalName(), JOURNAL_NAME_TAG))

	res = _resource("alarm-journal", JOURNAL)
	if res is None:
		have = _names("alarm-journal")
		return False, (u"alarm journal profile '%s' does not exist. This "
		               u"gateway has: %s"
		               % (JOURNAL, u", ".join(have) if have else u"(none)"))
	from java.lang import Throwable as JThrowable
	try:
		cfg = _config(res)
		flavour = cfg["profile"]["type"]
	except (JThrowable, Exception):
		flavour = None

	if not _hasDatabaseModule():
		if flavour != u"LOCAL":
			return False, (u"profile '%s' is a '%s' journal, not the LOCAL "
			               u"one this edition needs - no database is "
			               u"available to a 'DATASOURCE' profile here"
			               % (JOURNAL, flavour))
		return True, (u"profile '%s' is Edge's own LOCAL journal - no "
		              u"database, alarms still journalled internally"
		              % JOURNAL)

	if flavour != u"DATASOURCE":
		return False, (u"profile '%s' is a '%s' journal, not 'DATASOURCE' - "
		               u"this gateway can have a database and should be "
		               u"using it" % (JOURNAL, flavour))
	try:
		ds = cfg["settings"]["datasource"]
	except (JThrowable, Exception):
		ds = None
	if ds != DB:
		return False, (u"profile '%s' writes to '%s', not this demo's '%s'"
		               % (JOURNAL, ds, DB))
	ok, why = _journalTagCheck()
	if not ok:
		return False, why
	return True, u"profile '%s' writes %s on '%s'" % (JOURNAL, JOURNAL_TABLE,
	                                                  DB)


def _journalTagCheck():
	"""The Alarms screen's journal-name tag agrees with this gateway.

	The screen binds its journal table to this tag, so a stale value is an
	empty history with nothing anywhere saying why.
	"""
	want = journalName()
	qv = system.tag.readBlocking(["[%s]%s" % (PROVIDER, JOURNAL_NAME_TAG)])[0]
	have = unicode(qv.value) if qv.quality.isGood() else None
	if have != want:
		return False, (u"%s reads '%s', not '%s' - the Alarms screen binds "
		               u"its journal table to it" % (JOURNAL_NAME_TAG,
		                                             have, want))
	return True, u""


def _journalFix():
	"""Upsert the alarm journal profile in the flavour this edition needs.

	Same resource name either way (JOURNAL == the provider name) - only the
	config differs, and _upsert doesn't care that a DATASOURCE profile is
	being replaced by a LOCAL one or vice versa, it just needs the current
	signature to replace against.
	"""
	_journalTagFix()
	if _isEdgeGateway():
		# system.config.create for typeId "alarm-journal" throws
		# java.lang.UnsupportedOperationException("Cannot create Alarm Journal
		# on Edge") - measured 09/09/2026. There is nothing to create.
		return u"alarm journal '%s' is Edge's own and already exists - " \
		       u"nothing created, %s written" % (journalName(),
		                                         JOURNAL_NAME_TAG)
	if not _hasDatabaseModule():
		what = _upsert("alarm-journal", JOURNAL, JOURNAL_CONFIG_LOCAL,
		               "Machine HMI Demo's own alarm journal - this edition "
		               "has no database, so this is Edge's own LOCAL "
		               "profile: alarms are still journalled, internally, "
		               "with no datasource anywhere")
		return u"alarm journal profile '%s' %s as a LOCAL (no-database) " \
		       u"journal" % (JOURNAL, what)
	what = _upsert("alarm-journal", JOURNAL, JOURNAL_CONFIG,
	               "Machine HMI Demo's own alarm journal - writes the standard "
	               "alarm_events / alarm_event_data tables into this demo's "
	               "own connection, sharing them with nothing")
	return u"alarm journal profile '%s' %s, pointed at '%s'" % (JOURNAL, what,
	                                                            DB)


def _journalTagFix():
	system.tag.writeBlocking(["[%s]%s" % (PROVIDER, JOURNAL_NAME_TAG)],
	                         [journalName()])


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
		 "its own to write. On an edition with no SQL Bridge module (Edge "
		 "Panel - the reason this demo exists) this row is not applicable: "
		 "no connection is attempted, and it still reports green." % DB),
		("journal", "Alarm journal", _journalCheck, _journalFix,
		 "A journal profile named %s, sharing its history with nothing. On "
		 "this gateway it writes %s into %s; filtering a shared journal by "
		 "source only looks like isolation - the rows still interleave with "
		 "every other project's, and the retention belongs to someone else. "
		 "On an edition with no database (Edge Panel) this is instead a "
		 "LOCAL profile - Edge's own internal journal, alarms still kept, "
		 "no datasource anywhere."
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
