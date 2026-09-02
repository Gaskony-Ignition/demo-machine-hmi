# Machine_HMI_Demo — build contract

A demonstration for a palletising-machine builder evaluating Ignition as an HMI
replacement (Edge Panel on small machines, standard Ignition where there are two
panels). It must look and behave like **machine-level operator control**, not a
dashboard.

Gateway: `ignition-module-testing`, http://192.168.153.128:8088 (8.3.8), local docker.
Container: `ignition-module-testing`. Projects dir:
`/usr/local/bin/ignition/data/projects`.

Project name: **`Machine_HMI_Demo`** (never change the name — it breaks URLs).
Title/description carry the version: `Machine HMI Demo 1.0.0` … `· v1.0.0`.

## Hard rules

- **No gateway restart.** Apply project resources with a Projects "Scan File System"
  (`node /Home-Claude/ignition-claude-toolkit/plugins/ignition/skills/scan/tool/scan.js
  --gateway module-testing`), config resources with the Platform Overview scan.
- Every resource dir needs a `resource.json` listing its `files` with a
  `lastModification` block, or the scan silently ignores it.
- `doGet` must be the **first byte** of a WebDev `doGet.py` — no docstring, no
  comment above it, or the route returns an empty 200.
- Project declares `color-scheme` in the stylesheet.
- Perspective app bar hidden (`appBar.togglePosition: hidden`).
- Tab-indented, pure-ASCII Python in script resources.
- Files written into the container as uid 1000 must be `chown -R root:root`ed after.

## Tag contract — provider `MachineDemo` (STANDARD, created by setup)

All paths below are relative to `[MachineDemo]`. Types are Ignition dataTypes.

```
Line/          Running Bool | Mode String("Auto"/"Manual") | CasesPerMin Float8
               CycleTime_s Float8 | CasesTotal Int4 | SimEnabled Bool
               SimSpeed Float8 | ShiftTarget Int4

Safety/        EStopOK Bool | GuardsClosed Bool | AirPressureOK Bool
               InterfacesOK Bool | AirPressure_kPa Float8

Robot/         State String("Idle"/"Picking"/"Placing"/"Homing"/"Fault")
               J1_deg Float8 (-170..170)   base rotation
               J2_deg Float8 (-60..90)     shoulder
               J3_deg Float8 (-140..40)    elbow
               J4_deg Float8 (-180..180)   wrist
               Lift_mm Float8 (0..1200)
               GripperClosed Bool | Vacuum_kPa Float8 (-80..0)
               MotorsOn Bool | Homed Bool | Ready Bool | Healthy Bool
               CycleCount Int4 | CycleTime_s Float8
               Fault Bool | FaultText String

Pallet/Station1/  Present Bool | CasesPlaced Int4 (0..60) | Layer Int4 (0..5)
                  Complete Bool | PatternName String
Pallet/Station2/  (identical)

Conveyor/      C1_Run Bool | C2_Run Bool | C3_Run Bool
               C1_Speed_mpm Float8 | C2_Speed_mpm Float8 | C3_Speed_mpm Float8
               PE_Infeed Bool | PE_Carton Bool | PE_Length1 Bool | PE_Length2 Bool
               PE_InPos1 Bool | PE_InPos2 Bool | PE_Clear Bool
               Gate1_Up Bool | Gate2_Up Bool | Clamp_Extended Bool
               LastBarcode String | ScanOK Bool

Zones/Z1..Z8/  Name String | State String | Running Bool | Fault Bool
               (Z1 Robot 1, Z2 Robot 2, Z3 Robot 3, Z4 Robot 4,
                Z5 Wrapper, Z6 Shuttle, Z7 Pallet Outfeed, Z8 Tray Conveyors)

Faults/        WrapperFilmFeed Bool | ConveyorJam Bool | VacuumLow Bool
               GuardOpen Bool | RobotAxisFault Bool
```

Alarms are configured on the `Faults/*` tags, the `Safety/*` booleans
(alarm when false) and `Robot/Fault`, with real display paths and notes.

## WebDev routes — project `Machine_HMI_Demo`

Base: `http://192.168.153.128:8088/system/webdev/Machine_HMI_Demo/<name>`

| Resource | Route | Purpose |
| --- | --- | --- |
| `admin` | `?cmd=setup\|check\|status\|reset\|fault&name=\|speed&value=` | one-button install + presenter control |
| `admin` | `?cmd=state` | **compact live JSON the 3D page polls** |
| `cell3d` | (no query) | the 3D palletising cell page, served as HTML |
| `lib` | `?f=three` | vendored three.js (proves it works with no internet) |

### `cell3d` is a Text Resource, and that is deliberate

It began as a `doGet.py` that read a `page.html` sitting beside it. That worked
and the Designer could not see it — Web Dev lists resources, and a loose file
inside a resource folder is not one, so anyone opening `cell3d` in the Designer
found the Python and no way to reach the page.

A **text-resource** appears in Web Dev, opens in the Designer's editor with
HTML, CSS and JavaScript all syntax-highlighted, and is served directly at the
same URL with no Python in the way. Its on-disk form is:

```json
{ "resource-type": "text-resource", "content-type": "text/html", "text": "…" }
```

— the whole page as one JSON string, with `files: ["config.json"]` and nothing
else in the directory.

That is unreadable in git, so **`src/cell3d/page.html` is the source of truth**
and the resource is generated:

```
python3 tools/webdev_page.py build      # src/cell3d/page.html -> the resource
python3 tools/webdev_page.py extract    # the resource -> src/cell3d/page.html
```

**Run `extract` after editing in the Designer, before committing.** The two
directions are not automatic, and the next `build` overwrites whatever was typed
in the Designer. This is the one cost of the split, and it buys the thing the
demo is trying to prove: that a customer can maintain the 3D page in the
Designer without a web toolchain.

`admin` and `lib` remain python-resources — they are code, not pages.

### `?cmd=state` response shape — FROZEN, the 3D page depends on it

```json
{
  "ok": true, "ts": 1756800000000,
  "line": {"running": true, "mode": "Auto", "cpm": 14.2, "cycle": 12.6,
           "cases": 1284, "target": 1800},
  "robot": {"state": "Placing", "j1": -42.0, "j2": 18.5, "j3": -61.0,
            "j4": 12.0, "lift": 340.0, "grip": true, "vac": -62.4,
            "cycles": 812, "fault": false, "faultText": ""},
  "pallets": [{"present": true, "cases": 37, "layer": 3, "complete": false,
               "pattern": "5x3 interlock"}, {...}],
  "conv": {"c1": true, "c2": true, "c3": false,
           "pe": {"infeed": true, "carton": false, "len1": true, "len2": false,
                  "inpos1": true, "inpos2": false, "clear": true},
           "gate1": false, "gate2": true, "clamp": true,
           "barcode": "T12783", "scanOK": true},
  "safety": {"estop": true, "guards": true, "air": true, "interfaces": true},
  "faults": {"WrapperFilmFeed": false, "ConveyorJam": false, "VacuumLow": false,
             "GuardOpen": false, "RobotAxisFault": false},
  "zones": [{"id":"Z1","name":"Robot 1","state":"Running","running":true,"fault":false}, ...]
}
```

Robot joint convention for the 3D page (right-handed, Y up, mm):
`j1` rotates the base about **Y**; `j2` is the shoulder about **Z** (positive
lifts the upper arm); `j3` is the elbow about **Z** relative to the upper arm;
`j4` rotates the wrist about **Y**; `lift` raises the whole column in mm.

## Ownership — do not write outside your own list

| Owner | Files |
| --- | --- |
| **lead (Claude)** | `com.inductiveautomation.webdev/resources/cell3d/*`, `.../lib/*`, project skeleton, `project.json`, stylesheet, session-props |
| **agent: sim** | `ignition/script-python/MachineDemo/*`, `com.inductiveautomation.webdev/resources/admin/*`, `ignition/timer/*` |
| **agent: views** | `com.inductiveautomation.perspective/views/*`, `.../page-config/*` |

Nobody else edits `project.json`, the stylesheet or session-props.
