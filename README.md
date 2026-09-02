# Machine HMI Demo

**Machine-level operator control in Ignition Perspective — including a live 3D
model of the cell — for a machine builder evaluating Ignition as an HMI
replacement.**

It exists because of one comment from a customer looking at Ignition for the
first time:

> I took a look at those demos, they are all quite 'dashboard-like', rather than
> machine level operator control (ie edge).

That is a fair criticism of most Ignition demonstrations, and it is not answered
by argument. This is the answer instead: a simulated robotic palletising cell
with the screens an operator and a fitter would actually stand in front of — a
line overview, manual control with permissives and hold-to-run jog, an alarm
page, and a 3D view of the machine driven by the same tags as everything else.

Every screen runs on **Ignition Edge Panel** as well as the standard platform,
with no database connection.

---

![The 3D palletising cell inside a Perspective session](docs/img/final-3d-overview.jpg)

*The 3D cell inside a Perspective page. The header and the state chip are
Perspective components bound to tags; the scene below is a WebGL page served by
this project's own WebDev resource. Both pallets build in a real 4x3 interlocked
pattern because the robot is genuinely placing cases.*

![Robot close-up](docs/img/final-3d-robot.jpg)

*The arm follows five joint tags and a lift position, solved by real inverse
kinematics in the simulator, and is holding a case at -68 kPa of vacuum. Photo-eye
beams along the infeed glow green while clear.*

![A conveyor jam, highlighted on the model](docs/img/final-3d-fault.jpg)

*One button injects a conveyor jam. The infeed pulses red **in the model**, the
banner names it in plain words, and the cell status flips to FAULT — so a fitter
knows where to walk before reading anything. That is the argument for 3D on a
machine screen: not that it looks impressive, but that **location is
information**.*

---

## What it demonstrates

| | |
| --- | --- |
| **3D model rendering** | A palletising cell — robot, infeed, two pallet stations, guarding — animated from live tags. Camera presets, orbit and pinch-zoom for a touch panel, faults highlighted on the geometry itself. |
| **Access control by security zone** | The same Manual screen is fully live for maintenance and visibly read-only for an operator, with the reason stated on screen rather than silently disabled. |
| **Alarming** | Alarm status and journal tables scoped to this demo's own tag provider, with acknowledge and shelve. |
| **Operator control** | Hold-to-run jog, a permissive list that answers "why won't it move?", service routines, and per-zone start/stop. |

## Install

Import `build/Machine_HMI_Demo-<version>.zip` in the Designer, then open the
**Setup** page and press one button. That creates the `MachineDemo` tag provider,
94 tags, 11 alarms and starts the simulator — through `system.config` and
`system.tag.configure`, so there is no config scan, no restart and no credential.

Headless equivalent:

```bash
curl "http://<gateway>/system/webdev/Machine_HMI_Demo/admin?cmd=setup"
curl "http://<gateway>/system/webdev/Machine_HMI_Demo/admin?cmd=check"
```

## Driving it in a meeting

The Setup page doubles as a presenter console, and every control has a URL:

```bash
?cmd=fault&name=ConveyorJam     # also WrapperFilmFeed VacuumLow GuardOpen RobotAxisFault
?cmd=clear&name=ConveyorJam
?cmd=reset                      # back to steady state
?cmd=speed&value=2              # simulation speed
?cmd=state                      # the live snapshot the 3D page polls
```

## How the 3D page works

Perspective has no native 3D component, so the scene is a WebGL page served by
this project's own **WebDev** resource and shown in Perspective's inline-frame
component. It polls `?cmd=state` and interpolates between updates.

**three.js is vendored inside the project**, served from
`webdev/resources/lib/three.min.js` by a path resolved from the gateway's own
install directory — so it works on an air-gapped machine, which is the normal
condition for the panels this is aimed at. `tools/package.sh` fails the build if
that file is ever missing from the zip.

Because it is all inside the project, importing the project is the entire
install. There is no CDN, no extra module and no second file to place.

## Layout

| Path | What it is |
| --- | --- |
| `project/` | The Ignition project, as the gateway holds it. Source of truth. |
| `tools/package.sh` | Builds the importable zip; stamps the version into the Title and Description. |
| `docs/CONTRACT.md` | Tag contract, WebDev routes, the frozen `?cmd=state` shape and the robot's kinematic convention. |

## Development

Deploy to the local module-testing gateway (which runs as uid 2003, so no
`chown` is needed and none should be attempted):

```bash
cd project && tar cf - . | docker exec -i ignition-module-testing \
  tar xf - -C /usr/local/bin/ignition/data/projects/Machine_HMI_Demo
node /Home-Claude/ignition-claude-toolkit/plugins/ignition/skills/scan/tool/scan.js \
  --gateway module-testing
```

Pull the gateway's copy back over `project/` before editing — the gateway is the
source of truth and a local mirror is stale by default.

## Verified behaviours

These are checked, not assumed — each was tested against the running gateway:

| Claim | How it was verified |
| --- | --- |
| The 3D library is served from the project, not a CDN | Fetched off the gateway and md5-compared to the file on disk: identical, 669,884 bytes. |
| The 3D page survives losing its tag feed | Blocked the `admin` route in a live session: the page reported *"no tag data — showing local motion"*, the model kept moving (lift 277 mm → 774 mm), and it returned to *"live from [MachineDemo] tags"* by itself when the route was restored. |
| The robot never solves an impossible pose | Sampled `?cmd=state` across full cycles and computed forward kinematics: wrist never below 0.95 m, reach never above 2.38 m against a 2.50 m arm. |
| The arm travels over the stack, not through it | 48 mid-swing samples; tightest clearance over the taller pallet 0.349 m. |
| It works on the panels it targets | HUD checked for overlap and overflow at 1024×600, 1280×800 and 1920×1080. |
| The zip actually imports | `tools/package.sh` gates on archive integrity, a file count against the tree, and a resource-manifest pass (valid JSON, `lastModification` present, `files[]` matching the directory) — the three ways a project imports "successfully" with a resource the gateway silently never scans. |

## Known conditions

- The module-testing gateway runs **unlicensed in trial mode**. Perspective and
  WebDev return HTTP 402 once the two hours expire while `/StatusPing` still
  says `RUNNING`, so check a real page — not the health endpoint — before
  demonstrating, and reset the trial if needed.
