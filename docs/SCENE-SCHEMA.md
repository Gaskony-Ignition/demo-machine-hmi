# The scene document

*Option A from [3D-AS-PERSPECTIVE.md](3D-AS-PERSPECTIVE.md): the cell's parts
list as **data** instead of as a function. Started 05/09/2026.*

This is also the **prop schema for Option B**. A Perspective component whose
`props.scene` is this document is the same renderer with a different host, so
nothing written against this format is thrown away if the component gets built.

## Why the format looks like this

Three things the page already does had to survive the move to data, and each
one forced a piece of the schema:

| What the page does | What the schema needs |
| --- | --- |
| Nests six groups so one tag sets one rotation | `parent`, and a `joint` that names an axis and a tag |
| Sizes the conveyor and the cases from Config tags | values that are **expressions**, not just numbers |
| Generates 24 rollers, 60 pallet cases, 6 photo-eyes in loops | `repeat`, with the loop index visible to expressions |

A flat list of literal boxes would have expressed none of them. A parts list
that cannot express the machine it replaces is not a parts list.

## Shape

```json
{
  "units": "m",
  "consts": { "UPPER": 1.35, "FORE": 1.15 },
  "materials": {
    "arm": { "color": "0xe8a33d", "metalness": 0.35, "roughness": 0.5 }
  },
  "parts": [
    { "name": "Robot", "type": "group" },
    { "name": "Base", "type": "group", "parent": "Robot", "at": [0, 0.3, 0],
      "joint": { "axis": "y", "tag": "Robot/J1_deg", "unit": "deg" } },
    { "name": "column", "type": "box", "parent": "Base",
      "size": [0.3, 2.35, 0.3], "at": [0, 1.175, 0], "material": "column" }
  ]
}
```

### Parts

Every part has a `name` (unique) and a `type`. `parent` names another part;
omitted, the part is added to the scene root. Order does not matter — the tree
is resolved by name after the whole list is read, so a part may name a parent
that appears below it.

| `type` | Extra fields |
| --- | --- |
| `group` | none — it exists to be a transform |
| `box` | `size: [w, h, d]` |
| `cylinder` | `radiusTop`, `radiusBottom`, `height`, `segments` (default 20) |
| `plane` | `size: [w, h]` |

Common optional fields: `at: [x, y, z]` (default origin), `rotate: [x, y, z]`
in **radians** for a fixed orientation, `material` (a key of `materials`),
`shadow: {"cast": false, "receive": false}` (both default true), and `visible`
(default true).

### Joints — the one thing that makes it a machine

```json
"joint": { "axis": "z", "tag": "Robot/J2_deg", "unit": "deg" }
```

Sets exactly one rotation on this part from a live value, replacing nothing
else. `axis` is `x`, `y` or `z`; `unit` is `deg` (default) or `rad`. A
`joint` with `"kind": "translate"` moves along the axis instead, in metres,
which is how the carriage lift works.

One joint per part, deliberately. Two rotations on one node is how a chain
becomes unreadable; nest another group instead, which is what a real axis is.

### Two value bags, not one

`Config/` reaches the raw tag values. `Geometry/` reaches what the **gateway
derives and publishes** — the pattern's `rows` and `cols`, `casesPerPick`.

That split matters. The gripper head has to be as long as one pick, and a pick
is a column of the layer, so its size depends on the rows in the pattern — which
come from an algorithm that finds the factor pair of `CasesPerLayer` closest to
square. The document reads the published answer instead of recomputing it,
because a second implementation is a second chance to disagree.

### Values are expressions

Anywhere a number is expected, three forms are accepted:

| Form | Meaning |
| --- | --- |
| `1.35` | a literal, in the document's units |
| `"UPPER"` | a name from `consts`, or a `repeat` index in scope |
| `"Config/ConvLength_mm"` | a config value; a path ending `_mm` is **divided by 1000** |
| `["*", "UPPER", 0.5]` | an expression |

Expressions are prefix arrays, evaluated by a ~40-line walker with **no
`eval`**: `+ - * / neg min max abs floor ceil round sqrt atan2 hypot`. `+ - * /`
take any number of arguments.

The `_mm` rule is not a special case bolted on — every dimension tag in this
project is named in millimetres and the page works in metres, so the conversion
belongs in one place rather than in every part that mentions one.

An unresolvable name is a **hard error**, reported with the part that used it.
A silently-zero dimension is a box you cannot see, which is the worst way for
this to fail.

### Repeat

Two forms. A **count**:

```json
{ "name": "guide", "type": "cylinder", "parent": "Base",
  "repeat": { "count": 2, "as": "i" },
  "at": [["+", -0.18, ["*", "i", 0.36]], 1.175, 0.09] }
```

and a walk over a table in the document's `data` block:

```json
"data": { "fenceRuns": [ { "x1": -3.1, "z1": -2.75, "x2": 2.6, "z2": -2.75 } ] }

{ "name": "fenceRun", "type": "group", "repeat": { "over": "fenceRuns", "as": "r" },
  "at": ["r.x1", 0, "r.z1"] }
```

`count` is itself an expression, so a conveyor's roller count can come from its
length. `as` names the index (`0 .. count-1`) or the row; a row's fields are
reached with a dot. Instances get their index appended to the name
(`guide.0`, `guide.1`) so they stay addressable.

**Children of a repeated part repeat with it**, once per instance, with the
parent's loop variable still in scope. That is what makes a fence run carry its
own posts and a pallet station its own case grid, without the child having to
know how many parents there are.

### `let` — naming a value once

```json
{ "name": "fenceRun", "type": "group",
  "repeat": { "over": "fenceRuns", "as": "r" },
  "let": { "len": ["hypot", ["-", "r.x2", "r.x1"], ["-", "r.z2", "r.z1"]] },
  "at": ["r.x1", 0, "r.z1"] }
```

`let` adds names to the part's scope, visible to the rest of that part **and to
its children**. A fence panel, its rail and its posts all need the run's length;
without `let` each would recompute the same `hypot`, and the three would drift
apart the first time one was edited.

Names are evaluated in order, so a later one may use an earlier one.

## What it deliberately does not do

- **No conditionals and no functions.** The pallet's interlocked layer pattern
  and the factor-pair grid maths stay in code. They are an algorithm, not a
  parts list, and a JSON dialect that grows an `if` has become a bad
  programming language.
- **No animation.** Joints are bound to live values; there are no keyframes.
- **No materials beyond the standard PBR set** already used by the page.

## Status

| Piece | State |
| --- | --- |
| Schema | this document |
| `src/cell3d/scene.json` | 45 parts, 18 materials |
| `src/cell3d/scene-render.js` | ~320 lines, no `eval` |
| Parity gate | **passing**, stable over repeated runs, negative-tested |
| Every part of the cell | **done** — except the pallet case stacks, deliberately |
| The `Machine/Scene` view and the route that serves it | **done** — `admin?cmd=scene` |
| Page switched over to the renderer | not started |
| Where the document lives | **a view's custom props** (Nigel, 05/09/2026) |
| Page switched over to the renderer | not yet — the document is proved, not wired in |

### What the gate proves

`tools/verify/scene_parity.js` loads the real page, lets it build its own scene
with the vendored three.js, then builds the document in the same context and
compares the two trees node for node — geometry parameters, transforms,
material colour and finish, and both shadow flags.

```
hand-coded nodes: 56   document nodes: 56
photo-eyes: page has 6, document builds 6
  ok   6 of 6 beams own their material
subtree ConveyorFrame: identical across 32 nodes (excluding animated axes)
  ok   24 rollers are actually spinning
subtree Station1: identical across 17 nodes
  ok   180 further nodes on the page are the case stacks
subtree Station2: identical across 17 nodes
  ok   180 further nodes on the page are the case stacks
PARITY: identical across 56 nodes
```

The conveyor frame is what proves the **Config-path** half of the schema: its
rails, legs and roller count all come from `Config/convLength_mm` and its two
siblings, resolved from the same state the page uses and divided by 1000 by the
`_mm` rule. Nothing in the static structure exercised that.

A gate that cannot fail is worth nothing, so it was negative-tested: changing
the upper arm's height from 0.24 to 0.25 in the document — a 10 mm lie —
produces `PARITY: 1 of 56 nodes differ` and exit 1.

It also drives the joints two ways, because a tree comparison alone would pass
if **both** scenes sat at zero:

- with the live tag values off `admin?cmd=state`, and
- one joint at a time with a distinctive value, asserting the named axis takes
  it **and the other two do not move**. `J4` reads 0.0 for most of the cycle, so
  without this the wrist binding would have been carried by a test that never
  moved it.

Run it with:

```bash
NODE_PATH=/Home-Claude/ignition-claude-toolkit/plugins/ignition/skills/verify-view/tool/node_modules \
  node tools/verify/scene_parity.js
```

The static structure moved first because it is the part with the kinematic
chain in it: if the schema could not express a six-group arm whose joints are
tags, nothing else about it would matter. The config-driven parts are more code
but less risk — they are already parameterised, just in JavaScript.

### Where the document lives

The `Machine/Scene` view. The document is spread across five custom props —
`units`, `consts`, `data`, `materials`, `parts` — rather than nested under one,
so a binding path reads `custom.parts[3].size[0]`, which is exactly what the
Option B component's `props.parts[3].size[0]` would be.

`tools/build_scene_view.py` generates the view from `src/cell3d/scene.json`, and
`--extract` goes the other way. The readable file is the source and the view is
generated, for the same reason `webdev_page.py` splits the 3D page: a `view.json`
with a 45-part document inlined is not reviewable in git. The same rule applies —
edit in the Designer, extract before committing.

`MachineDemo.scene.document()` reads the deployed view off disk, resolving the
gateway's install directory the way the `lib` route already does to serve the
vendored three.js. It never raises: if the document cannot be read it says why,
and the page keeps its built-in geometry, because a page rendering the cell it
has always rendered is a better failure than a page rendering nothing.

**The gate tests the document the gateway SERVES**, not the repo file — and
reports drift between the two. Testing the file alone would have proved the
renderer and nothing about the plumbing: a view that failed to deploy, or custom
props edited in the Designer and never extracted, would both have passed.
Editing the deployed view's `upperArm` as if someone had typed it in the property
editor produces both a `DRIFT` line and `PARITY: 1 of 55 nodes differ`.

The drift comparison is canonical, not textual: Jython's `jsonDecode` returns an
unordered map, so the served key order differs on every read. Array order is
preserved, because that one is real — it is the child order in the scene graph.

A Document tag would have been cheaper and was rejected: those custom props
*are* the Option B component's props, so building against them rehearses the
real answer instead of building plumbing that gets thrown away. Editing the
machine in the property editor is also the thing a customer can be shown.

### Excluding a property is only safe if something else asserts it

Three properties are excluded from the comparison because they are **state**,
not structure — and each one is then asserted another way, because an exclusion
with nothing behind it is just a blind spot:

| Excluded | Asserted instead |
| --- | --- |
| roller spin | 24 rollers are actually turning |
| photo-eye beam colour and opacity | the page shows more than one opacity, so the pulse is alive; each beam owns its material, so one blocked eye cannot recolour the rest |
| held-case and carton visibility | the document builds all 12 hidden, so a fresh page shows no product that is not there |
| carton position on the belt | the pool is evenly pitched at 0.3 m on one level — where a carton *is* is state, where the pool *sits* is structure |

The last one was found the hard way. Comparing held-case visibility made the
gate **depend on where the arm was when it ran** — the same code passed or
failed depending on whether the gripper was carrying. A flaky gate is worse than
no gate, because it teaches you to re-run it until it goes green.

### What stays in code, and why

The pallet **case stacks** are not in the document and are not going to be.
Their layout is `layerLayout()`: an interlocked pattern that alternates case
orientation layer by layer, on a grid derived from `CasesPerLayer` as the factor
pair closest to square. The page's own comment says the simulator's `_layout()`
is that loop in Jython and *change one, change both*. Expressing it in JSON
would make that three places, and would need conditionals and a modulo the
schema deliberately does not have.

So the station's **structure** is data — deck, bearers, slats, feet, guide
rails, all sized from the pallet tags — and the stack that sits on it stays an
algorithm. The gate holds that line honestly: it compares the 17 structural
nodes exactly and then asserts the remaining 180 are the case stacks and
nothing else, so a part quietly dropped from the document cannot hide in the
tail. Dropping one of the five deck slats gives `subtree Station1 #8 MISMATCH`
and exit 1.

### `ownMaterial`

Materials are shared by name — which is what you want for sixty identical
cartons and exactly what you do not want for six photo-eye beams, because each
beam's colour is its own tag and one shared material turns them all red
together. `"ownMaterial": true` gives each instance its own copy. It is the same
reason the page clones materials before highlighting a faulted group, and the
gate asserts it: *6 of 6 beams own their material*.

### Two things the work has already settled

**`repeat.count` cannot see the part's own `let`.** It is evaluated in the
enclosing scope, before the part's names exist. That is not a limitation to work
around: a count that depends on the part is nearly always a property of its
*parent* — how many posts this run of guarding carries — and belongs there.

**Animation is not structure.** The page spins the rollers and pulses the
photo-eye beams' opacity; neither is more part of the document than a joint
angle is. The gate excludes both and then asserts each is still happening — 24
rollers turning, beam opacity showing more than one value — because a belt that
had stopped, or a pulse that had died, would otherwise pass in silence.

**Lights and the grid helper are not parts.** They are scene furniture. A parts
list describing the lighting rig would be a parts list that had stopped being
about the machine.
