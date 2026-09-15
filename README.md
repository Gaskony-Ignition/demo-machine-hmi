# Machine HMI Demo

**Machine-level operator control in Ignition Perspective — including a live 3D
model of the cell — for machine builders evaluating Ignition as an HMI
replacement.**

## Why this exists

Most Ignition demonstrations look like a dashboard, not the screen an
operator or a fitter stands in front of at a machine. This is a simulated
robotic palletising cell with those screens instead: a line overview, manual
control with permissives and hold-to-run jog, an alarm page, and a 3D view
driven by the same tags as everything else.

Every screen runs on **Ignition Edge Panel** as well as the standard
platform. On a gateway that can have a database, the demo brings its own — a
SQLite file beside the gateway, made by one button, no server, no credential,
no config scan. Edge Panel has no database connectivity at all, so there the
same button configures Edge's own internal alarm journal instead: alarms are
still journalled, and removing the demo still deletes nothing but its own
resources.

## What it looks like

![The 3D palletising cell inside a Perspective session](docs/img/final-3d-overview.jpg)

*The header and state chip are Perspective components bound to tags; the
scene below is a WebGL page served by this project's own WebDev resource.
Both pallets build a real 4×3 interlocked pattern because the robot is
genuinely placing cases.*

![Robot close-up](docs/img/final-3d-robot.jpg)

*The arm follows five joint tags and a lift position, solved by real inverse
kinematics in the simulator, and is holding a case at -68 kPa of vacuum.
Photo-eye beams along the infeed glow green while clear.*

![A conveyor jam, highlighted on the model](docs/img/final-3d-fault.jpg)

*One button injects a conveyor jam. The infeed pulses red in the model, the
banner names it in plain words, and the cell status flips to FAULT — so a
fitter knows where to walk before reading anything.*

## What it does

| | |
| --- | --- |
| **3D model rendering** | Robot, infeed, two pallet stations, guarding — animated from live tags, with camera presets, orbit, pinch-zoom and faults highlighted on the geometry. The shape is a parts list edited in the Designer, not code. |
| **Access control by security zone** | The Manual screen is live for maintenance and read-only for an operator, with the reason stated on screen. |
| **Alarming** | Status and journal on the demo's own tag provider, connection and journal profile — acknowledge and shelve included. |
| **Your own CAD on a screen** | The **CAD** tab loads plain STL files off the gateway and lets an operator orbit, zoom, pan and click a part to identify it — no module, no licence, no internet. See [docs/CAD-VIEWER.md](docs/CAD-VIEWER.md). |
| **Operator control** | Hold-to-run jog, a permissive list that answers "why won't it move?", service routines, per-zone start/stop. |

| Tab | What it is |
| --- | --- |
| **OVERVIEW** | The line: eight zones, the mimic, per-zone start/stop and the alarm strip. |
| **3D CELL** | The cell in WebGL, animated from live tags, with the Geometry panel. |
| **2D CELL** | The same cell, drawn with stock Perspective components only. |
| **CAD** | The customer's own STL, orbit/zoom/pan/pick. |
| **MANUAL** | Jog, permissives, service routines, access by security zone. |
| **ALARMS** | Status and journal, this machine only. |
| **SETUP** | One-button install, health checks, and the presenter console. |

## How to use it

Import `build/Machine_HMI_Demo-<version>.zip` in the Designer, then open the
**Setup** page and press the one button. Setup writes 112 tags and 11 alarms
into its own `MachineDemo` tag provider and starts the simulator. What it does
about a database depends on the gateway:

- **Standard Ignition (or Maker)** — also creates a `MachineDemoDB` SQLite
  connection and a `MachineDemo` alarm journal writing into it.
- **Ignition Edge Panel** — has no database connectivity at all: the SQL
  Bridge module is not part of the Edge build, so setup configures the
  `MachineDemo` alarm journal as Edge's own **LOCAL** profile instead — alarms
  are still journalled, with no datasource anywhere.

It all goes through `system.config` and `system.tag.configure`: no config
scan, no restart, no credential. Re-running setup is safe — every step is an
upsert.

### Installing on Edge

There are **two release zips** — Edge permits exactly one realtime tag
provider, called `edge` out of the box, so the Edge build is the same project
with the provider name substituted at build time.

| Gateway | Zip |
| --- | --- |
| Standard Ignition, Maker | `Machine_HMI_Demo-<version>.zip` |
| Ignition Edge Panel | `Machine_HMI_Demo_Edge-<version>.zip` |

There is no project import on Edge. Install by copying the unzipped project
over Edge's own project folder (`data/projects/Edge/` by default), `chown` it
to the gateway user, then Config → Platform → Projects → **Scan File
System**. First, change Config → Platform → **Ignition Edge** →
**Visualization Module** from Vision to Perspective, or no Perspective
session opens at all. Then open Setup and press **RUN SETUP**.

---

## Driving it in a meeting

The Setup page doubles as a presenter console, calling the `MachineDemo`
library in-process with nothing to configure. HTTP is **read-only** — every
write verb is refused with 405, credentialed or not. The other way to drive
it is the Designer's Script Console:

```python
MachineDemo.api.setFault("ConveyorJam", True)   # also WrapperFilmFeed VacuumLow GuardOpen RobotAxisFault
MachineDemo.api.reset()                         # back to steady state
MachineDemo.api.setSpeed(2)                     # simulation speed
MachineDemo.api.setMode("Auto")                 # hand the cell back to the auto cycle
```

## How the 3D page works

Perspective has no native 3D component, so the scene is a WebGL page served
by this project's own WebDev resource, shown in an inline-frame and vendoring
three.js so it works air-gapped. Changing the modelled machine is
[docs/CHANGING-THE-3D-CELL.md](docs/CHANGING-THE-3D-CELL.md); how close it is
to "programmed in Perspective", and the tag/route contract it depends on, are
[docs/3D-AS-PERSPECTIVE.md](docs/3D-AS-PERSPECTIVE.md) and
[docs/CONTRACT.md](docs/CONTRACT.md).

## Layout

| Path | What it is |
| --- | --- |
| `project/` | The Ignition project, as the gateway holds it. Source of truth. |
| `tools/package.sh` | Builds the importable zip; stamps Title/Description. README-gated (`--skip-readme-check` bypasses). |
| `docs/CONTRACT.md` | Tag contract, WebDev routes, the frozen `?cmd=state` shape, the robot's kinematic convention. |
| `docs/CHANGING-THE-3D-CELL.md` | The three levels at which the modelled machine can change. |
| `docs/REAL-DATA.md` | What changes when tags come from a PLC instead of the simulator. |
| `docs/3D-AS-PERSPECTIVE.md` | How close the 3D view is to a Perspective component, and how to close the gap. |

## Development

Point the repo at your own gateway once (`cp tools/env.example.sh
tools/env.local.sh`, then edit it — gitignored, holds the container name,
projects directory and gateway URL). Deploy and scan:

```bash
source tools/env.local.sh
cd project && tar cf - . | docker exec -i "$GW_CONTAINER" \
  tar xf - -C "$GW_PROJECTS/Machine_HMI_Demo"
../tools/scan.sh
```

`chown` the files you wrote to the account the gateway runs as, never
`chown -R` the whole projects directory — that stops every scan silently.
Pull the gateway's copy back over `project/` before editing; the gateway is
the source of truth.

Two throwaway gateways, one per edition, live in `dockers/` — `docker compose
up -d` from `dockers/edge/` (:8388) or `dockers/standard/` (:8488). The gates
in `tools/verify/` take the gateway URL as their first argument and the
project name in `$MHD_PROJECT`, since the Edge build lands in a differently
named project. Edge Panel permits exactly one concurrent Perspective session,
so run the Edge gates one at a time with a gap between them, and press RESET
DEMO on the Setup page first — a stopped line has no rollers turning.

## What this demo proves

- The 3D library is served from the project, not a CDN.
- The robot never solves an impossible pose — checked against the arm's reach.
- Hold-to-run jog is a real momentary bit: release stops the axis dead.
- An open guard circuit disables the jog button independently of the screen.
- Colour is spent only on the abnormal: a running line reads grey, a fault is
  the only saturated thing on screen.
- It survives a gateway restart unattended, with no step to re-run.
- The 3D and CAD pages resolve their own project name at runtime, so they
  work under any project name, including every Edge.
- `tools/package.sh` gates the release zip on archive integrity, file count
  and a resource-manifest pass — a resource the gateway silently never scans
  still "imports successfully" without them.

## Licensing

Licensed **Apache-2.0** — see [LICENSE](LICENSE). Vendors two third-party
works, licences reproduced in [NOTICE](NOTICE): `three.min.js` (MIT) and the
sample UR5 meshes (BSD-3-Clause, from
[ros-industrial/universal_robot](https://github.com/ros-industrial/universal_robot)
— delete them and drop your own in). That package's UR20/UR30/UR15/UR18
meshes are **not** BSD.

It runs unlicensed, on the two-hour trial, by design. An expiry does not look
like an outage: Perspective and WebDev return **HTTP 402** while
`/StatusPing` still reports `RUNNING`, so check an actual page, not the
health endpoint. A restart resets the trial too, and the demo survives one
unattended.
