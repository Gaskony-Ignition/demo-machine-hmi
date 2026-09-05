# Third-party 3D for Perspective — the AXONE-IO 3D Engine

*Evaluated 04/09/2026 against the question this demo exists to answer: can a
machine builder show an articulated machine, moving, in Perspective, driven by
tags.*

## The short answer

**It does not run on Ignition 8.3.** Installed on the test gateway on
05/09/2026, certificate trusted and licence accepted through the supported
Config → Modules flow, the ModuleManager refuses it outright:

```
W [ModuleInstance] Module "3D Engine" requires Ignition 8.1.0 (b0)
  and is not compatible with Ignition 8.3.8 (b2026071409)
```

`module.xml` declares `<requiredignitionversion>8.1.0</requiredignitionversion>`
and the artefact was built **09/08/2022**. Version 1.0.1's own documentation
still shows an `Ignition-windows-x86-64-8.1.16` install path, so the newer
release is an 8.1 build too. The module is 8.1-only and there is no 8.3 build.

**And even on 8.1 it could not animate a machine.** It is a BIM/AEC model
viewer — a packaging of the xeokit SDK — and its entire per-entity API is
appearance and camera. There is no property, method or event in the shipped
code that sets an entity's position, rotation or matrix.

Either finding alone closes the question. That is not a criticism of the
module: it is very good at the thing it is for, which is a different thing.

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

## Three things a buyer should raise first

The third is decisive on its own. The first two would still need answering
before an install could be considered on any version.

1. **The documented download is broken and 1.0.1 is not obtainable.** The doc
   page's own link 404s. The vendor's module index builds a *different* path
   and offers **1.0.0 only**.
2. **The signing certificate expired on 08/11/2024.** The artefact is properly
   signed — a real Sectigo-chained commercial code-signing cert (subject
   `Axone-io`, issuer `Sectigo Public Code Signing CA R36`, thumbprint
   `5fbe8d5f…dd6a9c`), so no unsigned-module mode was needed and our rule was
   satisfied. **8.3.8 accepted it**: the install showed the certificate as
   CA-signed, and trusting it took the ordinary commissioning step. The expiry
   is not a blocker to installation. It is still a sign of a dormant product,
   which the 8.1-only build confirms.
3. **The build is three years old and 8.1-only.** This is the finding that
   actually decides it — see the short answer above.

## Where it would genuinely earn its place

Around the machine, not as the machine.

A plant room, a building shell, a conveyor hall — a **static** context model
with real entity metadata, an IFC containment tree, parts recolouring on alarm,
annotation bullets bound to tags, and a NavCube to fly the camera. That is a
good demo and this module is a reasonable way to build it. It is simply not
this demo.

That remains unverified, and on 8.3 it cannot be verified: the module never
reaches the point of loading a file. It would need an 8.1 gateway to try.

## The model pipeline — built, proved, then removed

The module needs XKT and this project has no CAD file: the cell is boxes and
cylinders in JavaScript, which is the point. So a pipeline was written that
runs the real page and reads the scene graph it just built:

```
page.html (live)  ->  scene.json  ->  cell.gltf + cell.metamodel.json
                              ->  xeokit-convert  ->  cell.xkt
```

It worked end to end and offline. Measured 04/09/2026: 396 meshes read from the
live scene (331 boxes, 64 cylinders, 1 plane), 33 unique geometries after
dedup, a 36 KB glTF buffer, and a 98.9 KB XKT carrying 396 drawable objects and
404 metaobjects in 7 assemblies. The metamodel stated the kinematic chain as
containment — `cell > Robot > Base > Carriage > Shoulder > Elbow > Wrist` — which
is the tree a BIM viewer would show.

**The exporter and its artefacts were deleted on 05/09/2026**, once the module
was proved not to run on 8.3. They existed only to feed it. The code is in this
repo's history if the question ever reopens.

Two limits were known before it was removed. It exported **one frame** — glTF
can carry animation and the writer emitted none, because the destination cannot
play it. And `xeokit-convert` reported `Converted metaobjects: 0` even though
the file grew by the expected 5.5 KB when the metamodel was passed, with its
`triangles` counter also reading 0 on a model with 1374 vertices; the statistics
looked unreliable rather than the metamodel being rejected. That was never
settled, and on 8.3 it cannot be.

## Recommendation

**Keep the WebDev + three.js page.** It does the one thing that matters here
and the module cannot do at all, it costs nothing, it needs no licence, no
conversion toolchain and no model file, and it already runs air-gapped with the
library vendored.

If a static plant context is ever wanted alongside the machine, the first
question for the vendor is whether an **8.3 build exists at all**. Until one
does, there is nothing to evaluate — followed by price, the missing 1.0.1
download, and the expired signing certificate.

**The comparison page was not built.** It was the point of the exercise and it
cannot be done: with the module refusing to load, a page using its component
would render nothing on this gateway. What the exercise did produce is the
model pipeline below, which is independently useful and works offline.

For where our own 3D should go next, see
[3D-AS-PERSPECTIVE.md](3D-AS-PERSPECTIVE.md): the honest gap is that our parts
list is JavaScript, and the answer to that is a scene document or a Perspective
component module of our own — not a viewer built for buildings.
