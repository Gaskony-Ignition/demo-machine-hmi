#!/usr/bin/env python3
"""Bake a URDF kinematic chain into the STL vertex data, once, offline.

The CAD viewer is deliberately dumb: it draws every STL in the resource folder
at that file's own coordinates. That is the right contract, because it is what a
CAD user gets when they export the parts of an assembly - they come out sharing
the assembly's origin and arrive already fitted together.

The ros-industrial UR5 meshes are not like that. They are modelled per LINK, in
each link's own frame, and the assembly lives in a URDF the viewer never sees -
so dropped in raw they stack on top of each other at the origin. Correct
behaviour, useless sample.

This applies each link's world transform (the joint chain at zero angles, then
the mesh's own origin inside the link) to the vertices and writes the STL back
out in assembly coordinates. Run once; the shipped meshes are the output.

    python3 tools/bake_stl_assembly.py <src-dir> <dest-dir>

Numbers are from ur_description/urdf, ur5. Two frames per link and both matter:
the joint, and the mesh's own pose inside that link.
"""
import math
import os
import struct
import sys

H = math.pi / 2
PI = math.pi

# (stl name, joint xyz, joint rpy, mesh xyz, mesh rpy)
CHAIN = [
    ("base",     (0, 0, 0),                  (0, 0, PI),   (0, 0, 0),       (0, 0, PI)),
    ("shoulder", (0, 0, 0.089159),           (0, 0, 0),    (0, 0, 0),       (0, 0, PI)),
    ("upperarm", (0, 0, 0),                  (H, 0, 0),    (0, 0, 0.13585), (H, 0, -H)),
    ("forearm",  (-0.425, 0, 0),             (0, 0, 0),    (0, 0, 0.0165),  (H, 0, -H)),
    ("wrist1",   (-0.39225, 0, 0.10915),     (0, 0, 0),    (0, 0, -0.093),  (H, 0, 0)),
    ("wrist2",   (0, -0.09465, 0),           (H, 0, 0),    (0, 0, -0.095),  (0, 0, 0)),
    ("wrist3",   (0, 0.0823, 0),             (H, PI, PI),  (0, 0, -0.0818), (H, 0, 0)),
]


def rpy(r, p, y):
    """URDF fixed-axis roll-pitch-yaw -> R = Rz(y) . Ry(p) . Rx(r)."""
    cr, sr, cp, sp, cy, sy = (math.cos(r), math.sin(r), math.cos(p),
                              math.sin(p), math.cos(y), math.sin(y))
    return [
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp,     cp * sr,                cp * cr],
    ]


def mul(a, b):
    """4x4 as (R, t) pairs."""
    ra, ta = a
    rb, tb = b
    r = [[sum(ra[i][k] * rb[k][j] for k in range(3)) for j in range(3)]
         for i in range(3)]
    t = [ta[i] + sum(ra[i][k] * tb[k] for k in range(3)) for i in range(3)]
    return (r, t)


def read_stl(path):
    with open(path, "rb") as fh:
        data = fh.read()
    n = struct.unpack("<I", data[80:84])[0]
    if 84 + n * 50 != len(data):
        raise SystemExit("%s: not a binary STL (or truncated)" % path)
    return n, data


def write_stl(path, tris):
    with open(path, "wb") as fh:
        fh.write(b"Baked into assembly coordinates by bake_stl_assembly.py".ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(tris)))
        for verts in tris:
            fh.write(struct.pack("<3f", 0.0, 0.0, 0.0))   # normals are recomputed
            for v in verts:                                # in the browser anyway
                fh.write(struct.pack("<3f", *v))
            fh.write(b"\0\0")


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    src, dest = sys.argv[1], sys.argv[2]
    os.makedirs(dest, exist_ok=True)

    world = ([[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0.0, 0.0, 0.0])
    for name, jxyz, jrpy, mxyz, mrpy in CHAIN:
        world = mul(world, (rpy(*jrpy), list(jxyz)))
        mesh_tf = mul(world, (rpy(*mrpy), list(mxyz)))
        R, t = mesh_tf

        n, data = read_stl(os.path.join(src, "%s.stl" % name))
        tris = []
        for i in range(n):
            o = 84 + i * 50
            verts = []
            for v in range(3):
                q = o + 12 + v * 12
                x, y, z = struct.unpack("<3f", data[q:q + 12])
                verts.append((
                    R[0][0] * x + R[0][1] * y + R[0][2] * z + t[0],
                    R[1][0] * x + R[1][1] * y + R[1][2] * z + t[1],
                    R[2][0] * x + R[2][1] * y + R[2][2] * z + t[2],
                ))
            tris.append(verts)
        write_stl(os.path.join(dest, "%s.stl" % name), tris)
        print("%-10s %5d triangles -> assembly coordinates" % (name, n))


if __name__ == "__main__":
    main()
