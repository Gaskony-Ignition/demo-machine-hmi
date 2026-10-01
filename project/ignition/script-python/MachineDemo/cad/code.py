# CAD models for the CAD page: the built-in one in the project's `cad` WebDev
# resource, and the ones uploaded from the screen.
#
# Uploads live OUTSIDE the project, in <gateway data dir>/machine-demo-cad/
# <model>/, so a new model shows the moment it is written - no project scan, no
# resource.json to keep in step, and nothing that a project import or export
# carries. One folder per model:
#
#   *.stl        an STL model: one part per file, part name = file name
#   model.step   a STEP model: the parts come from its assembly tree, in the
#                browser (occt-import-js), so the gateway never parses it
#   meta.json    what was uploaded, when, as what
#
# Writes come only from the Perspective session (the CAD Models popup). The
# WebDev `cad` route reads; it never writes, like every other route here.

import os
import re
import shutil
import system
from java.lang import Throwable as JThrowable

LOG = system.util.getLogger("MachineDemo.cad")

FOLDER = "machine-demo-cad"
# safeName strips a leading _, so no upload can take this name
BUILTIN = "_builtin"
BUILTIN_LABEL = "UR5 sample (built-in)"

MAX_UPLOAD = 50 * 1024 * 1024
# A zip is checked against what it UNPACKS to, not what it weighs: a few KB of
# zip can inflate to gigabytes.
MAX_UNZIPPED = 200 * 1024 * 1024
MAX_PARTS = 500
NAME_MAX = 48

STEP_FILE = "model.step"
META = "meta.json"


def root():
	"""<data dir>/machine-demo-cad, created on first use."""
	try:
		from com.inductiveautomation.ignition.gateway import IgnitionGateway
		data = IgnitionGateway.get().getSystemManager().getDataDir().getAbsolutePath()
	except (JThrowable, Exception):
		from java.lang import System
		data = os.path.join(System.getProperty("user.dir"), "data")
	d = os.path.join(unicode(data), FOLDER)
	if not os.path.isdir(d):
		os.makedirs(d)
	return d


def safeName(text):
	"""A model or part name that is only ever one path segment.

	Letters, digits, - and _; anything else becomes _. A leading dot or
	separator is stripped, so '..', '.hidden' and '/etc' cannot survive.
	"""
	base = unicode(text or u"")
	base = re.split(r"[\\/]", base)[-1]
	stem, ext = os.path.splitext(base)
	if ext.lower() in (".stl", ".zip", ".step", ".stp"):
		base = stem
	base = re.sub(r"[^A-Za-z0-9_-]+", "_", base)
	base = re.sub(r"_+", "_", base).strip("_-")
	return base[:NAME_MAX]


def _modelDir(name, mustExist=True):
	if not name or safeName(name) != name:
		raise ValueError("not a valid model name: %r" % name)
	r = root()
	d = os.path.join(r, name)
	# belt and braces: safeName already allows one segment only
	if os.path.dirname(os.path.realpath(d)) != os.path.realpath(r):
		raise ValueError("model path escapes the CAD folder")
	if mustExist and not os.path.isdir(d):
		raise ValueError("no such model: %s" % name)
	return d


def _readMeta(d):
	try:
		return system.util.jsonDecode(system.file.readFileAsString(
			os.path.join(d, META), "UTF-8")) or {}
	except:
		return {}


def models():
	"""Every uploaded model, newest first."""
	out = []
	r = root()
	for name in os.listdir(r):
		d = os.path.join(r, name)
		if not os.path.isdir(d) or safeName(name) != name:
			continue
		files = os.listdir(d)
		meta = _readMeta(d)
		if STEP_FILE in files:
			kind = "step"
			parts = meta.get("parts")
		else:
			kind = "stl"
			parts = len([f for f in files if f.lower().endswith(".stl")])
		out.append({"name": name, "kind": kind, "parts": parts,
		            "source": meta.get("source", u""),
		            "uploaded": meta.get("uploaded", u""),
		            "mtime": os.path.getmtime(d)})
	out.sort(key=lambda m: -m["mtime"])
	return out


def options(rev=None):
	"""Dropdown options for the CAD page. `rev` only forces a re-evaluation."""
	opts = [{"value": BUILTIN, "label": BUILTIN_LABEL}]
	for m in models():
		opts.append({"value": m["name"],
		             "label": u"%s  (%s)" % (m["name"], m["kind"].upper())})
	return opts


def uploadedOptions(rev=None):
	return [o for o in options(rev) if o["value"] != BUILTIN]


def files(name):
	"""(kind, [file stems]) of one uploaded model, for the cad route."""
	d = _modelDir(name)
	fs = os.listdir(d)
	if STEP_FILE in fs:
		return "step", [STEP_FILE[:-5]]
	return "stl", sorted([f[:-4] for f in fs if f.lower().endswith(".stl")])


def filePath(name, stem):
	"""Path of one file of an uploaded model, or None. Never leaves the folder."""
	d = _modelDir(name)
	for f in os.listdir(d):
		low = f.lower()
		if (low.endswith(".stl") or low == STEP_FILE) and \
				os.path.splitext(f)[0] == stem:
			return os.path.join(d, f)
	return None


# ---------------------------------------------------------------------------
# upload
# ---------------------------------------------------------------------------


def _isBinarySTL(data):
	"""84-byte header + 50 bytes a triangle, exactly. Everything else is not."""
	n = len(data)
	if n < 84:
		return False
	from java.nio import ByteBuffer, ByteOrder
	count = ByteBuffer.wrap(data, 80, 4).order(ByteOrder.LITTLE_ENDIAN).getInt() & 0xFFFFFFFF
	return 84 + count * 50 == n


def _isStep(data):
	from java.lang import String as JString
	head = unicode(JString(data, 0, min(len(data), 200), "ISO-8859-1")).lstrip()
	return head.startswith(u"ISO-10303-21")


def _write(path, data):
	from java.io import FileOutputStream
	out = FileOutputStream(path)
	try:
		out.write(data)
	finally:
		out.close()


def _unzipSTLs(data):
	"""[(part name, bytes)] from a zip of STLs. Entry paths are never used.

	Each part is named from the entry's BASENAME, run through safeName, so an
	entry called ../../etc/x.stl lands as x.stl inside the model folder - there
	is no path in the zip that can write outside it.
	"""
	from java.io import ByteArrayInputStream, ByteArrayOutputStream
	from java.util.zip import ZipInputStream
	from jarray import zeros
	zin = ZipInputStream(ByteArrayInputStream(data))
	parts, seen, total = [], set(), 0
	buf = zeros(65536, "b")
	try:
		while True:
			e = zin.getNextEntry()
			if e is None:
				break
			ename = unicode(e.getName())
			base = re.split(r"[\\/]", ename)[-1]
			if e.isDirectory() or not base.lower().endswith(".stl") \
					or ename.startswith("__MACOSX") or base.startswith("."):
				continue
			bout = ByteArrayOutputStream()
			while True:
				n = zin.read(buf)
				if n < 0:
					break
				total += n
				if total > MAX_UNZIPPED:
					raise ValueError("the zip unpacks to more than %d MB"
					                 % (MAX_UNZIPPED // (1024 * 1024)))
				bout.write(buf, 0, n)
			body = bout.toByteArray()
			if not _isBinarySTL(body):
				raise ValueError("%s is not a binary STL (ASCII STL is not read)"
				                 % base)
			name = safeName(base) or "part"
			stem, i = name, 2
			while name.lower() in seen:
				name = "%s_%d" % (stem, i)
				i += 1
			seen.add(name.lower())
			parts.append((name, body))
			if len(parts) > MAX_PARTS:
				raise ValueError("more than %d STL files in the zip" % MAX_PARTS)
	finally:
		zin.close()
	if not parts:
		raise ValueError("no .stl files in the zip")
	return parts


def save(filename, data, name=None):
	"""Store one upload as a model. Returns {"name", "kind", "parts", "replaced"}.

	`filename` decides the kind (.stl, .zip, .step/.stp); `name` defaults to it.
	An existing model of the same name is replaced - re-uploading an updated
	export is the normal case. The new model is written to a temporary folder
	and swapped in, so a failed upload never leaves half a model behind.
	"""
	size = len(data)
	if size == 0:
		raise ValueError("the file is empty")
	if size > MAX_UPLOAD:
		raise ValueError("the file is %.1f MB; the limit is %d MB"
		                 % (size / 1048576.0, MAX_UPLOAD // 1048576))
	ext = os.path.splitext(unicode(filename or u""))[1].lower()
	model = safeName(name) or safeName(filename)
	if not model:
		raise ValueError("give the model a name")

	if ext == ".stl":
		if not _isBinarySTL(data):
			raise ValueError("not a binary STL (ASCII STL is not read)")
		kind, items = "stl", [(model, data)]
	elif ext == ".zip":
		kind, items = "stl", _unzipSTLs(data)
	elif ext in (".step", ".stp"):
		if not _isStep(data):
			raise ValueError("not a STEP file (no ISO-10303-21 header)")
		kind, items = "step", [(STEP_FILE[:-5], data)]
	else:
		raise ValueError("only .stl, .zip of .stl, .step and .stp are accepted")

	r = root()
	final = _modelDir(model, mustExist=False)
	tmp = os.path.join(r, ".upload-%s" % model)
	if os.path.isdir(tmp):
		shutil.rmtree(tmp)
	os.makedirs(tmp)
	try:
		for stem, body in items:
			_write(os.path.join(tmp, stem + (".step" if kind == "step" else ".stl")),
			       body)
		meta = {"kind": kind, "source": unicode(filename),
		        "bytes": size,
		        "parts": len(items) if kind == "stl" else None,
		        "uploaded": system.date.format(system.date.now(),
		                                       "yyyy-MM-dd HH:mm:ss")}
		system.file.writeFile(os.path.join(tmp, META),
		                      system.util.jsonEncode(meta))
		replaced = os.path.isdir(final)
		if replaced:
			shutil.rmtree(final)
		os.rename(tmp, final)
	except:
		if os.path.isdir(tmp):
			shutil.rmtree(tmp)
		raise
	LOG.info("CAD model %s %s from %s (%s, %d part file(s))"
	         % (model, "replaced" if replaced else "stored", filename, kind,
	            len(items)))
	return {"name": model, "kind": kind, "parts": len(items),
	        "replaced": replaced}


def delete(name):
	"""Remove one uploaded model. The built-in model is not deletable here."""
	if name == BUILTIN:
		raise ValueError("the built-in model is part of the project")
	d = _modelDir(name)
	shutil.rmtree(d)
	LOG.info("CAD model %s deleted" % name)
	return True


# ---------------------------------------------------------------------------
# alarms linked to parts
# ---------------------------------------------------------------------------


def alarms():
	"""Standing alarms on this demo's provider that name a CAD part.

	The page decides which of them belong to the model it is showing; only it
	knows a STEP model's part names, because only it parses the file.
	"""
	key = MachineDemo.tagdata.CAD_PART
	try:
		events = system.alarm.queryStatus(
			source=["prov:%s:/tag:*" % MachineDemo.plant.PROVIDER])
	except (JThrowable, Exception):
		import traceback
		LOG.warn("queryStatus failed: %s" % traceback.format_exc())
		return []
	out = []
	for e in events:
		try:
			part = e.get(key)
		except:
			part = None
		if not part:
			continue
		f = MachineDemo.plant._field
		state = f(e, lambda x: unicode(x.getState()), u"")
		out.append({
			"part": unicode(part),
			"name": f(e, lambda x: unicode(x.getName()), u"Alarm"),
			"label": f(e, lambda x: unicode(x.get("displayPath") or u""), u""),
			"priority": f(e, lambda x: unicode(x.getPriority()), u""),
			"state": state,
			"active": state.lower().startswith("active"),
			"acked": f(e, lambda x: bool(x.isAcked()), True),
			"time": f(e, lambda x: system.date.format(
				x.get("eventTime"), "HH:mm:ss"), u""),
			"ts": f(e, lambda x: x.get("eventTime").getTime(), 0),
		})
	out.sort(key=lambda a: (not a["active"], a["acked"], -a["ts"]))
	return out
