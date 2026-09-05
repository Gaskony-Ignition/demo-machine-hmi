# The cell's parts list, read from where a person can edit it.
#
# Option A: the 3D page's geometry is a DOCUMENT, not a function. The document
# lives in the custom properties of the Machine/Scene view, so it is edited in
# the Designer's property editor with its tree, its add-row buttons and its
# binding dialog - rather than in a tag's JSON editor, which is honest but not
# friendly, or in JavaScript, which is what this replaces.
#
# Those custom props are also, deliberately, the prop schema a Perspective
# component would take. Nothing built against them is thrown away if the
# component gets built.

import os
import system
from java.lang import System

VIEW = "Machine/Scene"

# The five props the document is spread across. Spread rather than nested so a
# binding path reads custom.parts[3].size[0] - which is what the component's
# props.parts[3].size[0] would be.
KEYS = ["units", "consts", "data", "materials", "parts"]


def _candidates():
	# Same resolution the lib route uses to serve the vendored three.js: the
	# gateway's install directory is not something a project resource can
	# assume, so try the properties that name it and fall back to the path the
	# stock Docker image uses.
	project = system.util.getProjectName()
	rel = os.path.join("data", "projects", project,
	                   "com.inductiveautomation.perspective", "views",
	                   os.path.join(*VIEW.split("/")), "view.json")
	roots = []
	for prop in ("user.dir", "ignition.installdir", "catalina.base"):
		v = System.getProperty(prop)
		if v:
			roots.append(v)
			roots.append(os.path.join(v, ".."))
	roots.append("/usr/local/bin/ignition")
	out = []
	for r in roots:
		p = os.path.normpath(os.path.join(r, rel))
		if p not in out:
			out.append(p)
	return out


def document():
	"""The scene document, or a dict saying why there isn't one.

	Never raises. The 3D page falls back to its built-in geometry if this
	cannot be read, and a page that renders the cell it has always rendered is
	a better failure than a page that renders nothing.
	"""
	tried = []
	for path in _candidates():
		tried.append(path)
		if not os.path.exists(path):
			continue
		try:
			f = open(path, "r")
			try:
				view = system.util.jsonDecode(f.read())
			finally:
				f.close()
		except Exception, exc:
			return {"ok": False, "error": "could not read %s: %s" % (path, exc),
			        "tried": tried}
		custom = view.get("custom") or {}
		missing = [k for k in KEYS if k not in custom]
		if missing:
			return {"ok": False,
			        "error": "%s has no custom.%s" % (VIEW, ", custom.".join(missing)),
			        "path": path}
		doc = {}
		for k in KEYS:
			doc[k] = custom[k]
		return {"ok": True, "view": VIEW, "path": path, "scene": doc,
		        "parts": len(doc["parts"]), "materials": len(doc["materials"])}
	return {"ok": False,
	        "error": "%s/view.json was not found on this gateway" % VIEW,
	        "tried": tried}
