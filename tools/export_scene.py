#!/usr/bin/env python3
"""Write the 3D cell out as glTF, so it can leave three.js.

WHY THIS EXISTS

This project's cell is built PROCEDURALLY in src/cell3d/page.html - boxes and
cylinders in JavaScript. There is no CAD file, no .obj, no model on disk. That
is a deliberate strength (the machine's dimensions are fifteen tags and the
scene rebuilds itself when they change) and it is the one thing that makes the
cell hard to hand to anything else.

Any third-party 3D component wants a model file. AXONE-IO's 3D Engine wants
XKT, converted from glTF by xeokit-convert - see docs/3D-ALTERNATIVES.md. So
the route out is: run the real page, read the scene graph it just built, and
write the geometry from that. The exported model is therefore the SAME cell the
demo shows, at whatever geometry the Config tags currently hold, rather than a
second copy of the machine that would immediately drift.

    node _scene.js scene.json          (in the verify-view tool dir)
    python3 tools/export_scene.py scene.json cell.gltf

It writes a METAMODEL beside the glTF (cell.metamodel.json). Without one,
xeokit-convert reports "Converted metaobjects: 0" and the model has no
containment tree and no per-entity metadata - which is most of what a BIM
viewer is FOR. Pass it through:

    xeokit-convert -s cell.gltf -m cell.metamodel.json -o cell.xkt

WHAT IT DOES NOT DO

It exports one FRAME. glTF can carry animation and this writer does not emit
any, because the consumer it was written for cannot play it: the module exposes
no transform API at all (colorize/visible/xrayed/selected/highlighted, and
camera). A moving arm does not survive the trip, and that is a property of the
destination, not of this exporter.

Node names come from the group ancestry in page.html - Robot/Shoulder/Elbow and
so on - because entity ids are how anything downstream addresses a part.
"""
import base64
import json
import math
import struct
import sys


def box(w, h, d):
	"""Positions, normals and indices for a box centred on the origin."""
	x, y, z = w / 2.0, h / 2.0, d / 2.0
	faces = [
		((0, 0, 1), [(-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)]),
		((0, 0, -1), [(x, -y, -z), (-x, -y, -z), (-x, y, -z), (x, y, -z)]),
		((1, 0, 0), [(x, -y, z), (x, -y, -z), (x, y, -z), (x, y, z)]),
		((-1, 0, 0), [(-x, -y, -z), (-x, -y, z), (-x, y, z), (-x, y, -z)]),
		((0, 1, 0), [(-x, y, z), (x, y, z), (x, y, -z), (-x, y, -z)]),
		((0, -1, 0), [(-x, -y, -z), (x, -y, -z), (x, -y, z), (-x, -y, z)]),
	]
	pos, nrm, idx = [], [], []
	for n, quad in faces:
		base = len(pos)
		for v in quad:
			pos.append(v)
			nrm.append(n)
		idx += [base, base + 1, base + 2, base, base + 2, base + 3]
	return pos, nrm, idx


def cyl(rt, rb, h, seg):
	"""A cylinder about Y, centred on the origin - three.js CylinderGeometry."""
	seg = max(3, int(seg or 12))
	y0, y1 = -h / 2.0, h / 2.0
	pos, nrm, idx = [], [], []
	for i in range(seg):
		a0 = 2 * math.pi * i / seg
		a1 = 2 * math.pi * (i + 1) / seg
		for (a, r, y) in ((a0, rb, y0), (a1, rb, y0), (a1, rt, y1), (a0, rt, y1)):
			pos.append((math.cos(a) * r, y, math.sin(a) * r))
		# Side normal: the slope matters when the radii differ (a cone).
		slope = (rb - rt) / h if h else 0.0
		for a in (a0, a1, a1, a0):
			n = (math.cos(a), slope, math.sin(a))
			ln = math.sqrt(sum(c * c for c in n)) or 1.0
			nrm.append(tuple(c / ln for c in n))
		b = len(pos) - 4
		idx += [b, b + 1, b + 2, b, b + 2, b + 3]
	for (y, ny, r, wind) in ((y1, 1.0, rt, True), (y0, -1.0, rb, False)):
		if r <= 0:
			continue
		c = len(pos)
		pos.append((0.0, y, 0.0))
		nrm.append((0.0, ny, 0.0))
		for i in range(seg):
			a = 2 * math.pi * i / seg
			pos.append((math.cos(a) * r, y, math.sin(a) * r))
			nrm.append((0.0, ny, 0.0))
		for i in range(seg):
			p, q = c + 1 + i, c + 1 + (i + 1) % seg
			idx += [c, p, q] if wind else [c, q, p]
	return pos, nrm, idx


def main(src, out):
	scene = json.load(open(src))
	parts = scene["parts"]

	buf = bytearray()
	views, accessors, meshes, nodes, materials = [], [], [], [], []
	geom_cache, mat_cache = {}, {}

	def pad4():
		while len(buf) % 4:
			buf.append(0)

	def add_view(data, target):
		pad4()
		off = len(buf)
		buf.extend(data)
		views.append({"buffer": 0, "byteOffset": off,
		              "byteLength": len(data), "target": target})
		return len(views) - 1

	def add_geom(kind, pr):
		key = (kind, json.dumps(pr, sort_keys=True))
		if key in geom_cache:
			return geom_cache[key]
		if kind == "box":
			pos, nrm, idx = box(pr.get("width", 1), pr.get("height", 1), pr.get("depth", 1))
		elif kind == "cyl":
			pos, nrm, idx = cyl(pr.get("radiusTop", 1), pr.get("radiusBottom", 1),
			                    pr.get("height", 1), pr.get("radialSegments", 12))
		else:
			pos, nrm, idx = box(pr.get("width", 1), 0.001, pr.get("height", 1))
		pv = add_view(struct.pack("<%df" % (len(pos) * 3), *[c for v in pos for c in v]), 34962)
		nv = add_view(struct.pack("<%df" % (len(nrm) * 3), *[c for v in nrm for c in v]), 34962)
		iv = add_view(struct.pack("<%dH" % len(idx), *idx), 34963)
		mins = [min(v[i] for v in pos) for i in range(3)]
		maxs = [max(v[i] for v in pos) for i in range(3)]
		accessors.append({"bufferView": pv, "componentType": 5126, "count": len(pos),
		                  "type": "VEC3", "min": mins, "max": maxs})
		accessors.append({"bufferView": nv, "componentType": 5126, "count": len(nrm),
		                  "type": "VEC3"})
		accessors.append({"bufferView": iv, "componentType": 5123, "count": len(idx),
		                  "type": "SCALAR"})
		geom_cache[key] = (len(accessors) - 3, len(accessors) - 2, len(accessors) - 1)
		return geom_cache[key]

	def add_material(hexs):
		if hexs in mat_cache:
			return mat_cache[hexs]
		r, g, b = (int(hexs[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
		materials.append({"name": "m_" + hexs,
		                  "pbrMetallicRoughness": {"baseColorFactor": [r, g, b, 1.0],
		                                           "metallicFactor": 0.1,
		                                           "roughnessFactor": 0.8}})
		mat_cache[hexs] = len(materials) - 1
		return mat_cache[hexs]

	seen = {}
	for part in parts:
		p, n, i = add_geom(part["kind"], part.get("params") or {})
		m = add_material(part.get("colour") or "cccccc")
		meshes.append({"primitives": [{"attributes": {"POSITION": p, "NORMAL": n},
		                               "indices": i, "material": m}]})
		# Entity ids must be unique - two rollers share a group path.
		name = part.get("name") or "part"
		seen[name] = seen.get(name, 0) + 1
		if seen[name] > 1:
			name = "%s_%d" % (name, seen[name])
		nodes.append({"name": name, "matrix": part["matrix"], "mesh": len(meshes) - 1})

	pad4()
	gltf = {
		"asset": {"version": "2.0", "generator": "machine-hmi-demo/tools/export_scene.py"},
		"scene": 0,
		"scenes": [{"nodes": list(range(len(nodes)))}],
		"nodes": nodes, "meshes": meshes, "materials": materials,
		"accessors": accessors, "bufferViews": views,
		"buffers": [{"byteLength": len(buf),
		             "uri": "data:application/octet-stream;base64,"
		                    + base64.b64encode(bytes(buf)).decode("ascii")}],
	}
	with open(out, "w") as f:
		json.dump(gltf, f)

	# The metamodel: what each entity IS, and what contains it. Built from the
	# same group ancestry the node names came from, so the tree a viewer shows
	# is the tree page.html actually builds - Robot > Carriage > Shoulder >
	# Elbow > Wrist > Gripper is the kinematic chain, stated as containment.
	metas = [{"id": "cell", "name": "Palletising Cell", "type": "IfcProject",
	          "parent": None}]
	seen_groups = set()
	for n in nodes:
		segs = n["name"].split("/")
		for i in range(len(segs) - 1):
			gid = "/".join(segs[:i + 1])
			if gid in seen_groups:
				continue
			seen_groups.add(gid)
			metas.append({"id": gid, "name": segs[i], "type": "IfcElementAssembly",
			              "parent": "/".join(segs[:i]) if i else "cell"})
		parent = "/".join(segs[:-1]) if len(segs) > 1 else "cell"
		metas.append({"id": n["name"], "name": segs[-1], "type": "IfcBuildingElementProxy",
		              "parent": parent})
	meta_path = out.rsplit(".", 1)[0] + ".metamodel.json"
	with open(meta_path, "w") as f:
		json.dump({"metaObjects": metas}, f, indent=1)

	print("parts      %d" % len(parts))
	print("geometries %d unique (deduplicated)" % len(geom_cache))
	print("materials  %d" % len(materials))
	print("buffer     %d KB" % (len(buf) // 1024))
	print("metaobjects %d (%d assemblies)" % (len(metas), len(seen_groups)))
	print("wrote      %s" % out)
	print("wrote      %s" % meta_path)


if __name__ == "__main__":
	main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "cell.gltf")
