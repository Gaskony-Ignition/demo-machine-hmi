# Third-party 3D for Perspective — the AXONE-IO 3D Engine

*Evaluated 04/09/2026 against the question this demo exists to answer: can a
machine builder show an articulated machine, moving, in Perspective, driven by
tags.*

## The short answer

**It cannot animate a machine.** It is a BIM/AEC model viewer — a packaging of
the xeokit SDK — and its entire per-entity API is appearance and camera. There
is no property, method or event in the shipped code that sets an entity's
position, rotation or matrix.

That is not a criticism of the module. It is very good at the thing it is for,
which is a different thing.

## What was actually checked

Not the marketing page. The module binary and the vendor's own live bundle.

| | Finding |
| --- | --- |
| Component props (v1.0.0) | `configuration`, `url` |
| Component props (current, from the vendor's demo gateway) | `configuration`, `url`, `navCube`, `treeView`, `viewer`, `style` |
| Per-entity mutations in the code | `colorize`, `visible`, `xrayed`, `selected`, `highlighted` |
| Scripting surface | `flyTo`, `jumpTo`, `getMetaObject`, `getSnapshot`, `getRootMetaObjects`, `loadTreeView`, `getPOV` |
| Search for `position\|rotation\|matrix\|transform\|translate\|scale\|quaternion` in the component source | **0 matches**, both versions |

The underlying xeokit version bundled here gives `Entity` a settable **`offset`**
and nothing else positional — documented for exploded-assembly effects. So even
with the full SDK surface exposed, you would have translation and **no
rotation**. A shoulder and an elbow are rotations.

## What that means for this demo

Our cell is six nested groups — base, column, shoulder, elbow, wrist, gripper —
each rotating on a joint angle at 4 Hz. That is the whole argument the demo
makes. This module can render a palletising cell that is **coloured** by tags
and cannot render one that **moves**.

Everything else it would cost:

- **Paid.** `module.xml` says `<freeModule>false</freeModule>`; the gateway
  hook implements licence-state handling with the usual trial states, and the
  component polls a licence endpoint every 60 s. Unlicensed, it skips the
  `configuration` block entirely — so colouring and annotations, the only
  tag-driven behaviour it has, are exactly what stops working. No price is
  published; the vendor asks you to contact them. (Their *git* module is free
  and open on GitHub. This one is not.)
- **A model pipeline we do not have.** It needs XKT, via `xeokit-convert`,
  from glTF/IFC/STL and friends. Our geometry is procedural — boxes and
  cylinders in code, no CAD file — so we would author a model, export it split
  into named sub-assemblies (entity IDs are how you address anything), and
  convert it. All to end up with parts we still could not move.
  `xeokit-convert` is at least free, AGPL, and runs offline.
- **A model outside Ignition.** Files live on the webserver filesystem. The
  vendor concedes it plainly: *"This solution is not conventional in Ignition.
  The files are not saved in the gateway and therefore not redundant by
  Ignition."* No better than our WebDev resource on that count, and no worse.

## Two things a buyer should raise first

Neither is a reason to dismiss the module; both need answering before an
install could be considered.

1. **The documented download is broken and 1.0.1 is not obtainable.** The doc
   page's own link 404s. The vendor's module index builds a *different* path
   and offers **1.0.0 only**.
2. **The signing certificate expired on 08/11/2024.** The artefact is properly
   signed — a real Sectigo-chained commercial code-signing cert, so no
   unsigned-module mode would be needed, and our rule is satisfied in
   principle. But the leaf expired nearly two years ago and the artefact was
   signed in 2022. Whether 8.3.8 installs that cleanly was **not tested**, and
   would not be tested on our gateway without a decision to.

## Where it would genuinely earn its place

Around the machine, not as the machine.

A plant room, a building shell, a conveyor hall — a **static** context model
with real entity metadata, an IFC containment tree, parts recolouring on alarm,
annotation bullets bound to tags, and a NavCube to fly the camera. That is a
good demo and this module is a reasonable way to build it. It is simply not
this demo.

## The model pipeline, built and proved

The module needs XKT and this project has no CAD file — the cell is boxes and
cylinders in JavaScript, which is the point. So the route out is to run the
real page and read the scene graph it just built:

```
page.html (live)  ->  _scene.js  ->  scene.json
                  ->  tools/export_scene.py  ->  cell.gltf + cell.metamodel.json
                  ->  xeokit-convert         ->  cell.xkt
```

It works, end to end and offline. Measured on 04/09/2026:

| | |
| --- | --- |
| meshes read from the live scene | 396 (331 boxes, 64 cylinders, 1 plane) |
| unique geometries after dedup | 33 |
| glTF buffer | 36 KB |
| XKT | 98.9 KB, 396 drawable objects, 33 geometries, 1374 vertices |
| metaobjects | 404, in 7 assemblies |

Exporting from the running page rather than re-modelling the cell is what
keeps it honest: the XKT is the same machine the demo shows, at whatever the
fifteen Config tags currently hold, instead of a second copy that would drift
the first time someone changed a case size.

The metamodel states the kinematic chain as containment, which is the tree a
BIM viewer would show:

```
cell > Robot > Base > Carriage > Shoulder > Elbow > Wrist
     > InfeedConveyor
```

Two honest limits. **It exports one frame** — glTF can carry animation and this
writer emits none, because the destination cannot play it. And the converter
reports `Converted metaobjects: 0` even though the file grows by the expected
5.5 KB when the metamodel is passed; its `triangles` counter also reads 0 on a
model with 1374 vertices, so the statistics look unreliable on the glTF path
rather than the metamodel being rejected. **That is not verified either way**,
and it cannot be until the module is installed and loads the file.

## Recommendation

**Keep the WebDev + three.js page.** It does the one thing that matters here
and the module cannot do at all, it costs nothing, it needs no licence, no
conversion toolchain and no model file, and it already runs air-gapped with the
library vendored.

If a static plant context is ever wanted alongside the machine, evaluate this
module again for that job — and open the conversation with the vendor on price,
the missing 1.0.1 download, and the expired signing certificate.

For where our own 3D should go next, see
[3D-AS-PERSPECTIVE.md](3D-AS-PERSPECTIVE.md): the honest gap is that our parts
list is JavaScript, and the answer to that is a scene document or a Perspective
component module of our own — not a viewer built for buildings.
