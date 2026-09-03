# Changing the 3D cell

*How much of this machine is data, how much is code, and what it takes to make
it represent something else.*

The summary: **the shape of the machine is 15 numbers, the numbers are tags,
and everything reads them live.** Change one and, within a tick, the
simulator is placing to the new pattern, the 3D page has rebuilt itself, and
the screens show the new capacity. No source edit, no JavaScript, no reload.

The fastest way to see it is the **Geometry** button on the 3D page.

---

## The three levels

| | What changes | What you edit | Who can do it |
| --- | --- | --- | --- |
| **1** | The machine's proportions and pattern | 15 tags in `[MachineDemo]Config` | anyone with the Designer, or the Geometry panel |
| **2** | The arrangement of parts | one function in `page.html` | anyone who can read the function |
| **3** | A different machine entirely | the same function, more of it | someone comfortable with three.js |

---

## Level 1 — the proportions are tags

`[MachineDemo]Config` holds the cell's dimensions in whole millimetres:

```text
CaseW_mm  CaseD_mm  CaseH_mm             the case being handled
PalletW_mm  PalletD_mm  PalletH_mm       the pallet it goes on
CasesPerLayer  Layers                    the pattern
ConvHeight_mm  ConvLength_mm  ConvWidth_mm    the infeed conveyor
Station1_X_mm  Station1_Z_mm             where pallet station 1 sits,
Station2_X_mm  Station2_Z_mm             measured from the robot base
```

Every one has engineering limits and a tooltip describing what it means, so
the Designer's tag editor will not let you type a 6-metre case.

### Three readers, one set of numbers

**The simulator** reads all fifteen every tick, in the same round trip as its
controls, and derives the machine from them:

- the layer grid — rows × columns is the factor pair closest to square, the
  larger along X (12 → 4 × 3, 8 → 4 × 2, 30 → 6 × 5);
- **cases a pick = one column** of that grid, so the case set squared up on
  the infeed is the column the gripper carries across;
- where every pick lands — the centroid of the cases it places, in the
  order the page fills them;
- the height of every layer, the pick height off the belt, the safe travel
  height over the tallest stack;
- and whether the arm can **reach** all of it (below).

**The 3D page** gets the same fifteen as the `config` block of `?cmd=state`
and rebuilds its geometry the moment that block changes, inside its 250 ms
poll — conveyor, stations, cases, gripper head — and names the change on
screen: *CaseH_mm 220 → 350 · 5 x 12 interlock, 60 a pallet*. The HUD shows
the derived pattern and the reach verdict.

**The screens** bind to them. Pallet capacity on Overview and Manual is
`CasesPerLayer * Layers`, not a literal 60.

### The Geometry panel

The 3D page's header has a **Geometry** button. It slides out a drawer of
fifteen Perspective numeric fields, each bound **bidirectionally** to one
Config tag, and three whole-machine presets. Closed, the drawer takes no
width at all and the model has the whole page; the button lights while it is
out:

| Preset | What it is |
| --- | --- |
| Default | 300 × 250 × 220 mm cases, 12 a layer, 5 layers, 1200 × 1000 pallet |
| Euro, tall | 350 mm cases, 8 a layer (4 × 2), 4 layers, on a 1200 × 800 Euro pallet |
| Small, dense | 200 × 200 × 150 mm cases, 30 a layer (6 × 5), 7 layers |

There is no script behind the fields. Typing 350 into CASE HEIGHT and
pressing Enter writes `Config/CaseH_mm`; the simulator re-derives on its next
tick; the page rebuilds on its next poll. The presets call
`MachineDemo.api.setGeometry()`, which does nothing a tag write could not —
it writes all fifteen at once.

This is the demonstration's argument in one gesture: the 3D model is fed by
tags exactly the way a Perspective component is, and here it is being edited
from Perspective.

### Reach

A bigger pallet, a taller stack or a station further out is a question the
arm has to answer, not the page. The simulator solves every placement of the
pattern on both stations, plus the pick and the clearance over a finished
pallet, runs each solution forward through the same kinematics, and reports
anything more than 50 mm from where it was sent:

```json
"reach": {"ok": true, "unreachable": 0, "worst_mm": 0,
          "note": "every placement within reach (worst 0 mm)", "detail": []}
```

The HUD's **Reach** row shows *OK* or *n short*; the geometry-changed
banner turns amber and carries the first offender. The default and all
three presets solve with 0 mm error. Type `Station1_X_mm = -2000` and you
will be told, by the machine, before the arm demonstrates it.

The first honest solve is also why the default stations moved from 2.2 m to
1.98 m from the robot base on 03/09/2026: the far column of a 1.2 m pallet
was 64 mm beyond a 2.5 m arm, and the previous hand-picked slot offsets had
been quietly avoiding it.

### What is *not* a tag

The robot's link lengths (1.35 m and 1.15 m), its column travel (1200 mm) and
its joint limits. They are the arm, not the job — a machine builder changes
the pattern for every customer and the arm once per model. The page draws
the same two links the simulator solves against, and the reach report is
what tells you whether *this* arm can build *this* pattern.

---

## Level 2 — the arrangement

The scene is built in `src/cell3d/page.html`. The static parts — floor, grid,
fence, the robot arm's links — are built once at the top of `main()`.
Everything whose size or place is a Config tag is built by `buildCell()`,
which is what the live rebuild calls.

Both use two helpers and almost nothing else:

```js
box(w, h, d, material, x, y, z)      // a rectangular part
cyl(rTop, rBottom, h, material, seg) // a round one
```

both in metres, both returning a three.js mesh already positioned. A conveyor
leg is one `box`. A roller is one `cyl`. Moving the fence is changing four
numbers in `FX0, FX1, FZ0, FZ1`.

The robot itself is a chain of nested groups — `baseYaw → carriage → shoulder
→ elbow → wrist → gripper` — which is the same parent/child relationship a
real arm has. Rotating `shoulder` carries everything below it, so the
kinematics are the nesting, not a matrix calculation.

**To change what a part looks like**, find it by name and change its numbers.
**To add a part**, add a `box()` or `cyl()` beside the ones around it. If its
size should follow a tag, put it in `buildCell()` and read `M`.

---

## Level 3 — a different machine

Nothing about the page is palletising-specific except the contents of
`main()` and `buildCell()`. The plumbing either side — the config fetch, the
state poll, the live rebuild, the HUD, the damping, the theme palettes, the
camera presets — is machine agnostic.

A different machine means replacing the parts list with a different one and
pointing `applyState()` at whichever tags drive it. The existing file is the
worked example: about 400 lines of the 1400 are the parts, and the rest is
the plumbing you would keep.

For where this could go next — a scene that is *data* rather than code, or
a real Perspective component — see [3D-AS-PERSPECTIVE.md](3D-AS-PERSPECTIVE.md).

---

## Where to edit it

`src/cell3d/page.html` is the source of truth in git. The gateway serves a
**WebDev Text Resource**, which is the same HTML stored as a JSON string —
readable in the Designer under Web Dev, editable there in a text editor with
a content type of `text/html`.

```bash
python3 tools/webdev_page.py build      # src/cell3d/page.html -> the resource
python3 tools/webdev_page.py extract    # the resource -> src/cell3d/page.html
```

**Run `extract` after editing in the Designer**, before committing, or the
next `build` overwrites what you typed there. That is the one rule the split
imposes.

The Perspective side is generated too: `tools/build_cell3d_view.py` writes the
Cell3D view, panel included. Rebuild it rather than editing the JSON.
