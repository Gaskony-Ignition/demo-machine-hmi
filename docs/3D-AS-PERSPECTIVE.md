# The 3D cell as Perspective

*How close the 3D view is to "programmed in Perspective with some scripting,
driven by tags", what closed the gap today, and the three ways to close the
rest.*

## What "feels like Perspective" means

A Perspective component has four properties a machine builder's engineer
relies on without naming them:

1. **Its shape and behaviour are props**, edited in the Designer, not in code.
2. **Props bind to tags** — bidirectionally where it makes sense — and the
   screen follows the tag with no script in between.
3. **Scripting is the exception**: a short Jython handler on an event, in the
   Designer, against the project library.
4. **Nothing else is needed**: no toolchain, no build, no browser knowledge.

The 3D page is judged against those four. Today's position, and where each
one stands, is below.

## Where it stands after 03/09/2026

| Property | Before today | Now |
| --- | --- | --- |
| Shape is data, not code | 15 Config tags changed the *picture*; the simulator kept its own constants | 15 Config tags change the **machine**: simulator, page and screens read the same tags live |
| Follows tags without scripting | The page polled a JSON snapshot; a tag change needed a page reload | The page **rebuilds inside its 250 ms poll** when the config block changes; the HUD shows what was derived |
| Edited from Perspective | Only from the Designer's tag browser | The **Geometry drawer** — 15 `numeric-entry-field`s with bidirectional tag bindings and three preset buttons — slides out of the 3D page itself, and the model takes the width back when it closes |
| Consistency check | None: a change silently disagreed with the arm | The simulator solves every placement and **reports reach**; the HUD and the change banner carry the verdict |
| Screens honour the change | "of 60 cases" and "/5" were literals | Bound to `CasesPerLayer * Layers` and `Layers` |

What that gives the presenter: open the 3D page, press **Geometry**, type
350 into CASE HEIGHT, press Enter. Within half a second the pallet stack is
taller, the arm is placing to the new heights, the pattern label reads the
new pattern, Overview's capacity reads the new capacity, and a banner names
the tag that changed. Press **Euro, tall** and it is a different machine —
two cases a pick, four layers, on a narrower pallet — with the arm's reach
confirmed before it moves.

That is the whole tag → screen story told with tags and Perspective
bindings. The one thing in the chain that is *not* Perspective is the
rendering of the 3D itself, which is what the watermark says.

## The gap that remains

The 3D page is a WebDev-served HTML page in an iframe. Its **parts list is
JavaScript**: to move the fence, add a conveyor or model a different machine,
someone edits `page.html` — in the Designer's Web Dev text editor, which is
more than most vendors offer, but still code, still three.js, still a
`box()` and a `cyl()` with seven numbers each.

So of the four properties, the first is true for the machine's *dimensions*
and not for its *composition*. Below are the three ways to close that, in
increasing order of effort and of how completely they close it.

## Option A — the scene as data (weeks, not months)

Keep the page, but make its parts list a **document instead of a function**.
A scene description in JSON:

```json
{"parts": [
  {"name": "conveyor", "type": "box", "size": ["Config/ConvLength_mm", 100, "Config/ConvWidth_mm"],
   "at": [2050, "Config/ConvHeight_mm", 0], "material": "steel"},
  {"name": "upperArm", "type": "box", "parent": "shoulder", "size": [1350, 240, 260],
   "at": [675, 0, 0], "material": "arm"},
  {"name": "shoulder", "type": "group", "parent": "carriage",
   "rotate": {"axis": "z", "tag": "Robot/J2_deg"}}
]}
```

Every number is a literal **or a tag path**. Every group can rotate or
translate on a tag. The page becomes a generic renderer: fetch the document,
build the tree, subscribe the bound values. Adding a conveyor is adding a
part; a different machine is a different document.

Where the document lives decides how "Perspective" it feels:

- **A Document tag** (`[MachineDemo]Scene`, dataType Document). Edited in
  the tag browser's JSON editor; versioned with the tag export; the page
  reads it through `?cmd=scene`. Cheapest. Editing JSON in the tag editor is
  honest but not friendly.
- **A view's custom props**. A `Machine/Scene` view whose `custom.parts` is
  the document, so it is edited in the Designer's property editor with its
  tree, its add-row buttons and its binding dialog. The page reads it via a
  WebDev route that opens the view resource, or the view pushes it into a
  session prop. Friendlier; still an iframe rendering it.

**What you get:** parts and bindings become Designer-editable data;
scripting drops to zero for a new machine; the reach report and the
simulator are untouched.

**What you do not get:** it is still an iframe, still WebDev, still not a
component in the palette. The Designer cannot show the model while you edit
it. The watermark stays true.

**Effort:** the renderer is ~300 lines replacing the ~400 lines of parts;
the existing page is the reference implementation of what the document has
to express. Two to three days to reach parity with today's cell.

## Option B — a Perspective component module (the real answer)

Build `gaskony.display.scene3d`: a Perspective component whose **props are
the scene document** above and whose implementation is React + three.js,
packaged as a signed module — the same shape as the other modules in this
workspace (React 18.3.1 UMD, gateway SystemJS).

Then it *is* Perspective:

- it sits in the palette; drag it onto a view;
- `props.parts[n].size[0]` binds to `[MachineDemo]Config/ConvLength_mm` in
  the ordinary binding dialog, bidirectionally if wanted;
- `props.parts[n].rotate.value` binds to `Robot/J2_deg` and the arm moves —
  no poll, no JSON route, no iframe, the session's own tag subscription;
- the Designer renders it live while it is edited;
- it goes wherever a view goes: embedded views, popups, docked panels,
  flex repeaters (one component per robot);
- there is no `?cmd=state` to maintain, no watermark to explain.

The simulator, the tags, the Geometry panel and the reach report carry
over unchanged: they are already tags and scripts, which is the point of
having built them that way.

**Effort:** this workspace has built six Perspective/Gateway modules and the
Playwright and Web Designer modules include React components, so the
scaffolding, signing and release path exist. A first component that renders
the scene document with box/cylinder/group parts and tag-bound transforms is
roughly a week; camera presets, HUD labels, fault highlighting and shadows
add another. The existing page is the specification.

**Risk:** module work is not Friday work. It is the thing to *propose* on
Friday, with today's page as the proof that the model, the tags and the
simulator already agree.

## Option C — stock components only (already on the Cell2D page)

The `Cell2D` view is the same robot built from stock Perspective containers
whose CSS transforms nest — a two-link arm with no JavaScript at all. It is
genuinely Perspective and genuinely tag-driven, and it is two-dimensional.
It answers "how far can you get with nothing but the palette" honestly:
this far, and no further. It stays as the counterpoint to the 3D page.

## Recommendation

For Friday: **present the page as it is now**, with the Geometry panel as
the centrepiece — it is the tag → screen argument made in Perspective, and
it is measured true end to end today. Say plainly that the rendering is
WebDev; the watermark already does.

Then propose **Option B** as the productisation path, with **Option A** as
the interim if a second machine has to be modelled before a component
exists. Option A's scene document is also the exact prop schema Option B
would take, so nothing done for A is thrown away.

## What was proved today

Measured on the module-testing gateway, 03/09/2026, driving the Perspective
client with a headless browser and reading the WebDev state route between
steps:

- Pressing **Default** wrote all fifteen tags; the state route showed the
  new station positions; the simulator's reach report went from *4 of 43
  placements 64 mm short* (the old positions) to *every placement within
  reach*; the page's banner listed the four tags that changed.
- Typing **350** into CASE HEIGHT and pressing Enter wrote `Config/CaseH_mm`;
  the simulator's derived stack top went from 1260 mm to 1910 mm; the page
  rebuilt and its banner read *CaseH_mm 220 → 350 · 5 x 12 interlock, 60 a
  pallet*; the HUD's pallet layer bars were rebuilt.
- Pressing **Euro, tall** produced a *4 x 8 interlock*, two cases a pick, 32 a
  pallet, every placement within reach; the pallet stations reported the new
  pattern name within a tick.
- No JavaScript errors in the page or the iframe across any rebuild.
- The drawer fits without scrolling at 1366 × 768 and at 1024 × 600, with no
  caption elided and no value clipped.
- Closed, the drawer is 0 px wide and the 3D view has the whole width (1366
  and 1024); open, it is 312 px and the view is 1054 / 712. Four consecutive
  toggles, correct every time, and the hidden fields are not focusable.
