# The CAD viewer — showing a customer's own 3D model

A machine builder has CAD. This page puts it on a Perspective screen and lets an
operator turn it around, without a third-party module, a licence or an internet
connection.

It is deliberately **not** the palletising cell page. That one is a machine
that moves, driven by tags. This one just shows a model and lets you look at it.

It has its own tab — **CAD** — on the project's nav bar, and its own page route
`/cad`. Directly, it is:

    http://<gateway>/system/webdev/<project>/cadview

## Putting your own model in

1. Copy the `.stl` files into the project at
   `com.inductiveautomation.webdev/resources/cad/`
2. Add each filename to `files[]` in that folder's `resource.json` — a file on
   disk that is not listed there is skipped by the scan, silently, for good.
3. Config → Platform → Projects → **Scan File System**
4. Open the page. Whatever STLs are in the folder are the model; there is no
   list to maintain in the code.

To put it on a screen of your own, drop an `ia.display.iframe` into a
Perspective view with that URL as its `src` — and build the URL the way
`Machine/CadModel` does, so it keeps working when the project is called
something else:

    "/system/webdev/" + runScript("system.project.getProjectName()") + "/cadview"

A literal project name in that `src` is the one mistake that turns this page
into `HTTP ERROR 404 Project "..." not found` on somebody else's gateway.

The filename becomes the part name shown when someone clicks it.

## What the format costs you

- **Binary STL only.** ASCII STL is not parsed. Most CAD exports binary by
  default; check the export dialog.
- **One file per part you want to select.** A single STL of a whole assembly is
  one pickable lump — STL carries no names, no colours and no structure. This is
  a property of the format, not of the viewer.
- **Where the parts land is a CAD export choice.** Parts exported from one
  assembly share that assembly's origin and arrive already fitted together.
  Parts exported individually each sit at their own origin and stack up on top
  of one another.
- **STEP is not loadable directly.** It needs conversion — `occt-import-js`
  (OpenCASCADE compiled to WASM, MIT) can read STEP in the browser and would
  keep the assembly tree, which removes the per-part export discipline above.
  Not done here.

## Three things that cost time, all of which fail silently

- **WebDev corrupts binary if you return it as `response`.** It encodes the
  byte array as text: a 28,984-byte STL arrived as 39,156 bytes of mojibake,
  with no error anywhere. Write to
  `request['servletResponse'].getOutputStream()` and return `None`. Verified
  byte-identical by md5 afterwards.
- **Ignore the STL's own face normals** — `computeVertexNormals()` instead.
  Exporters write them inconsistently and an inverted set renders as a perfect
  black silhouette, which reads as a lighting or material bug and is neither.
- **A CAD mesh has two frames, not one**: where the part pivots, and where the
  mesh sits inside that part. Using only the first measures correct in the scene
  graph and still draws the assembly as loose pieces floating beside itself.

three.js r150+ removed the non-module `examples/js` loaders, so there is no
`STLLoader` or `OrbitControls` to vendor for the r160 UMD build this project
uses. Both are written out in the page instead — binary STL is 50 bytes per
triangle, and the orbit camera is about fifty lines. That also keeps the page
dependency-free, which is the condition the panel it targets actually runs in.

## The sample meshes

The seven UR5 meshes shipped in `resources/cad/` are from
**[ros-industrial/universal_robot](https://github.com/ros-industrial/universal_robot)**,
`ur_description`, and are licensed **BSD-3-Clause**. Authors: Wim Meeussen,
Kelsey Hawkins, Mathias Ludtke, Felix Messmer.

They are there so the page has something to show out of the box. Delete them and
drop your own in; nothing in the code refers to them by name.

**If you take more meshes from that package, check the licence first.** The
UR20, UR30, UR8 Long, UR15 and UR18 meshes are **not** BSD — they are covered by
Universal Robots A/S' own Terms and Conditions for Use of Graphical
Documentation. UR5 and UR10 are BSD.
