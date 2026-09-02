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

Every screen runs on **Ignition Edge Panel** as well as the standard platform, and
the demo brings its own database with it: **a SQLite file beside the gateway**,
made by the same one button. There is no database server to stand up, no
credential and no config scan. Because the connection and the alarm journal are
this demo's own rather than borrowed, its alarm history sits in its own file with
its own retention, and removing the demo is deleting a file.

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
| **Alarming** | Alarm status and journal tables on the demo's own tag provider, its own SQLite connection and its own journal profile — acknowledge and shelve included. The alarm page shows this machine only, and the history lives in the demo's own file with its own retention. |
| **Operator control** | Hold-to-run jog, a permissive list that answers "why won't it move?", service routines, and per-zone start/stop. |

## Install

Import `build/Machine_HMI_Demo-<version>.zip` in the Designer, then open the
**Setup** page and press one button. That creates the demo's own gateway
resources — the `MachineDemo` tag provider, the `MachineDemoDB` SQLite connection
and the `MachineDemo` alarm journal that writes into it — then writes 97 tags and
11 alarms and starts the simulator. All of it through `system.config` and
`system.tag.configure`, so there is no config scan, no restart and no credential:
SQLite is a file under the gateway's data directory, and the connection has no
username and no password to hold.

Headless equivalent. Reading is open; anything that changes the gateway is a
**POST** and needs a gateway login (see *Driving it in a meeting* for the one
line of set-up that puts the password in a file instead of the command):

```bash
curl -sS -X POST --netrc-file ~/.ignition-netrc \
     "http://<gateway>/system/webdev/Machine_HMI_Demo/admin?cmd=setup"
curl -sS "http://<gateway>/system/webdev/Machine_HMI_Demo/admin?cmd=check"
```

`?cmd=setup` is safe to repeat: every step is an upsert, and on a gateway that
already has everything it creates nothing and reports the same counts.

## Driving it in a meeting

The Setup page doubles as a presenter console, and it is the way to drive the
demo: its buttons call the `MachineDemo` library in-process, as the signed-in
Perspective session, so they need nothing configured and no second window.

The same commands are reachable over HTTP, and the split between them is the
point of the security pillar:

| | Verb | Auth |
| --- | --- | --- |
| `state` `status` `version` `check` `faults` `alarms` `alarmcheck` | GET | none — the 3D page polls `?cmd=state` from an iframe |
| `setup` `fix` `fault` `clear` `reset` `speed` `mode` `jog` `guards` | POST | a gateway user |

A write attempted on GET is refused with **HTTP 405** and
`{"ok": false, "error": "writes are not accepted on GET"}`. Nobody on the
network can open the guard circuit or jog the arm with a URL.

```bash
curl -sS -X POST --netrc-file ~/.ignition-netrc \
     "http://<gateway>/system/webdev/Machine_HMI_Demo/admin?cmd=fault&name=ConveyorJam"
     # also WrapperFilmFeed VacuumLow GuardOpen RobotAxisFault
curl -sS -X POST --netrc-file ~/.ignition-netrc "...?cmd=clear&name=ConveyorJam"
curl -sS -X POST --netrc-file ~/.ignition-netrc "...?cmd=reset"
curl -sS -X POST --netrc-file ~/.ignition-netrc "...?cmd=speed&value=2"
curl -sS -X POST --netrc-file ~/.ignition-netrc "...?cmd=mode&value=Auto"
curl -sS "...?cmd=state"                        # the live snapshot, no login
```

Arguments may also travel as a JSON body — `-H 'Content-Type: application/json'
-d '{"cmd":"speed","value":5}'` — which is the friendlier form from a script.

**The credential never belongs in the command.** WebDev answers HTTP Basic, so
put it in a netrc file once and let curl read it:

```bash
umask 077
printf 'machine <gateway-host> login <user> password <password>\n' > ~/.ignition-netrc
```

A password typed into a `curl -u` argument is visible to every process on the
machine and lands in the shell history; a 0600 netrc is neither. `--netrc-file`
takes the path, not the secret. `curl -sS -X POST` with no credential returns
**401** with `WWW-Authenticate: BASIC realm="Machine_HMI_Demo"`.

Which user source WebDev checks the password against is named in
`project/com.inductiveautomation.webdev/resources/admin/config.json` —
`doPost.user-source`. It ships as `temp`, the source this demo was built
against. **On any other gateway, set it to a user source that exists there**, or
POST answers 500 `No user source for project.` Reads and the Setup page are
unaffected either way, so a mis-set name costs the curl path only.

The third way in is the Designer's **Script Console**, which needs no HTTP at
all:

```python
MachineDemo.api.setFault("ConveyorJam", True)
MachineDemo.api.setFault("ConveyorJam", False)
MachineDemo.api.reset()
MachineDemo.api.setMode("Auto")
MachineDemo.setup.run()
```

**After demonstrating manual control, hand the cell back before `reset`.** Taking
a cell to manual leaves it there, and `?cmd=reset` clears faults but will not
restart a cell the operator still owns — so the line sits stopped at 0 cases/min
and the 3D view goes still. The sequence that returns everything to a running
demo is `?cmd=mode&value=Auto` and then `?cmd=reset`.

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

## What "its own resources" does and does not mean

The demo creates four named things and owns all of them: the `MachineDemo` tag
provider, the `MachineDemoDB` SQLite connection, the `MachineDemo` alarm journal
that writes into it, and the tables inside that file. Removing the demo is
deleting the project and those three gateway resources — nothing else is touched,
and no shared database server is involved.

**One honest limitation, measured rather than assumed.** A journal profile is not
a per-project filter. Ignition writes *every* alarm event on the gateway into
*every* enabled journal profile unless a source filter list is configured, and no
filter-list resource type exists on 8.3.8 to configure one with. So on a gateway
that is also running other projects, this demo's file will accumulate their alarms
too — measured here at 1,511 rows of which 6 were the demo's own, the rest from
two other projects on the same test rig.

That does not undo the change and it is not visible to anyone using the demo:

- The **Alarms page filters by source** (`prov:MachineDemo:/tag:*`), so what is
  displayed is this machine and nothing else.
- On a gateway running only this demo — which is the customer case, and the case
  the importable zip is built for — there are no other alarms to collect.
- What was actually fixed is ownership: its own file, its own retention, no
  dependency on a shared database server, and a clean removal.

If true isolation is ever needed on a shared gateway, the fix is a source filter
list on the journal profile's `dataFilters.sourceFilterName`, not a second table.

## Verified behaviours

These are checked, not assumed — each was tested against the running gateway:

| Claim | How it was verified |
| --- | --- |
| The 3D library is served from the project, not a CDN | Fetched off the gateway and md5-compared to the file on disk: identical, 669,884 bytes. |
| The 3D page survives losing its tag feed | Blocked the `admin` route in a live session: the page reported *"no tag data — showing local motion"*, the model kept moving (lift 277 mm → 774 mm), and it returned to *"live from [MachineDemo] tags"* by itself when the route was restored. |
| The robot never solves an impossible pose | Sampled `?cmd=state` across full cycles and computed forward kinematics: wrist never below 0.95 m, reach never above 2.38 m against a 2.50 m arm. |
| The arm travels over the stack, not through it | 48 mid-swing samples; tightest clearance over the taller pallet 0.349 m. |
| Hold-to-run jog is a real momentary bit | Driven through the actual UI: pressing `JOG −` set `Robot/JogDown` true and the lift fell 838 → 476 mm; releasing cleared the bit and the axis stopped dead (476 mm, unchanged 2 s later). The HMI sets the bit; the simulator, standing in for the PLC, owns the motion. |
| The machine refuses independently of the screen | With the guard circuit open the jog button was disabled, the bit never set, and the axis did not move (476 → 476 mm) — belt and braces, the way a real cell behaves. |
| The alarm strip cannot silently show nothing | Checked in BOTH states: with a jam standing it read `Palletiser / Infeed / Carton Jam - Active, Unacknowledged`; cleared, it returned to a neutral zero-active state rather than a stuck placeholder. |
| It works on the panels it targets | HUD checked for overlap and overflow at 1024×600, 1280×800 and 1920×1080. |
| It survives a gateway restart unattended | The gateway was restarted out from under the demo mid-session (not by this project). It came back with all 97 tags and 11 alarms present, `?cmd=check` green on all four items, the simulator resumed on its own at 13.6 cases/min, the pallets kept their progress, and the 3D page reconnected to live tags with no intervention. Nothing has to be re-run after a restart. |
| Colour is spent only on the abnormal | Measured from the rendered page, not the code. In the normal state the Overview carries no large saturated areas: running zones read grey with a small green LED, and the per-zone STOP buttons are neutral with red text rather than red fills. Inject a fault and the faulted zone is the only saturated thing on screen. The alarm strip distinguishes three states — active is red `#ff8d92`, cleared-but-unacknowledged is amber `#eebf5e`, acknowledged is grey — so a page with zero active alarms never reads as an emergency. |
| The zip actually imports | `tools/package.sh` gates on archive integrity, a file count against the tree, and a resource-manifest pass (valid JSON, `lastModification` present, `files[]` matching the directory) — the three ways a project imports "successfully" with a resource the gateway silently never scans. |

## Licensing

**This is built to run unlicensed, on the two-hour trial, by design.** Nothing here
needs a licence and none of it is worth licensing a gateway for — it is a
demonstration, and the trial resets.

The one practical thing to know is how an expiry presents, because it does not look
like an outage: Perspective and WebDev start returning **HTTP 402 while
`/StatusPing` still reports `RUNNING`**. A health check will tell you the gateway is
fine when no page will load. So check an actual page before demonstrating, not the
health endpoint.

Resetting the trial does **not** require a restart:

```bash
node <workspace>/launchpad/tools/reset_trial.js --gateway <name>
```

A gateway restart also resets it, and the demo survives one unattended — see the
table above.
