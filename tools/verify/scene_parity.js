// Prove the scene DOCUMENT builds the same objects as the hand-coded page.
//
// Option A only earns its place if the data-driven renderer produces the cell
// we already ship. So: load the real page, let it build its scene with the real
// vendored three.js, then build the document in the same context and compare
// the two trees node for node - geometry parameters, transforms, materials and
// shadow flags.
//
// Scoped to what scene.json currently expresses: the floor, the guarding and
// the robot's kinematic chain. The config-driven parts (conveyor, stations,
// cartons, gripper head) are not in the document yet and are skipped by name,
// not silently: anything unexpected is a failure.
// playwright lives in the toolkit's verify-view tool dir; NODE_PATH points there
// (see the run line at the bottom of this file).
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const GW = process.env.GW_URL || 'http://192.168.153.128:8088';
const PAGE = GW + '/system/webdev/Machine_HMI_Demo/cell3d';

// Nodes the document does not claim to build.
//   - lights and GridHelper are scene furniture, not parts of the machine; a
//     parts list has no business describing the lighting rig
//   - the rest are built from Config tags and are the next tranche
const NOT_YET = [
  'HemisphereLight', 'AmbientLight', 'DirectionalLight', 'GridHelper',
  'InfeedConveyor', 'Station1', 'Station2'
];

// Parts the document DOES create but whose contents are still built from Config
// tags: the gripper group is in scene.json, the head plate, suction cups and
// held cases it carries are sized from the case and the pick count and are not.
const SKIP_CHILDREN = ['Gripper'];

const describe = `(root, skip, skipChildren) => {
  const out = [];
  const r6 = v => Math.round(v * 1e6) / 1e6;
  const walk = (o, depth) => {
    if (skip.includes(o.name) || skip.includes(o.type)) return;
    const d = {
      depth,
      kind: o.isMesh ? 'mesh' : (o.type === 'Group' ? 'group' : o.type),
      pos: [r6(o.position.x), r6(o.position.y), r6(o.position.z)],
      rot: [r6(o.rotation.x), r6(o.rotation.y), r6(o.rotation.z)],
      vis: o.visible
    };
    if (o.isMesh) {
      const g = o.geometry, p = g.parameters || {};
      d.geom = g.type + ':' + Object.keys(p).sort()
        .filter(k => typeof p[k] === 'number')
        .map(k => k + '=' + r6(p[k])).join(',');
      const m = o.material;
      d.mat = m ? [m.type, '#' + m.color.getHexString(),
                   'metal=' + r6(m.metalness === undefined ? -1 : m.metalness),
                   'rough=' + r6(m.roughness === undefined ? -1 : m.roughness),
                   'op=' + r6(m.opacity), 'trans=' + !!m.transparent,
                   'side=' + m.side, 'dw=' + !!m.depthWrite].join(' ') : 'none';
      d.shadow = (o.castShadow ? 'C' : '-') + (o.receiveShadow ? 'R' : '-');
    }
    out.push(d);
    if (skipChildren.includes(o.name)) return;
    o.children.forEach(c => walk(c, depth + 1));
  };
  root.children.forEach(c => walk(c, 0));
  return out;
}`;

(async () => {
  const doc = JSON.parse(fs.readFileSync(path.join(ROOT, 'src/cell3d/scene.json'), 'utf8'));
  const renderer = fs.readFileSync(path.join(ROOT, 'src/cell3d/scene-render.js'), 'utf8');

  const b = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const p = await (await b.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
  const errs = [];
  p.on('pageerror', e => errs.push(String(e)));

  await p.goto(PAGE, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await p.waitForFunction('window.__cellScene && window.THREE', null, { timeout: 30000 });

  const result = await p.evaluate(async ({ doc, renderer, describe, NOT_YET, SKIP_CHILDREN }) => {
    // The page's own config, so both trees are built from identical numbers.
    let cfg = {}, st = {};
    try {
      const r = await fetch('admin?cmd=state', { cache: 'no-store' });
      st = await r.json();
      cfg = st.config || {};
    } catch (e) { return { err: 'could not read admin?cmd=state: ' + e }; }

    (0, eval)(renderer);
    let built, err = null;
    try { built = window.buildScene(doc, cfg, window.THREE); }
    catch (e) { err = String(e && e.message || e); }
    if (err) return { err };

    // The live page damps each joint toward its target, so the arm is mid-move
    // and the document scene is at rest. Read the joint values straight off the
    // hand-coded objects, convert them back into the units the tags carry, and
    // drive the document scene with them. That tests the binding itself - right
    // object, right axis, right kind, right unit - without re-testing damping.
    const handJoints = {};
    const jointValues = {};
    built.joints.forEach(j => {
      const src = window.__cellScene.getObjectByName(j.name);
      if (!src) return;
      const jd = j.joint;
      if (jd.kind === 'translate') {
        const m = src.position[jd.axis];
        handJoints[j.name] = m;
        jointValues[jd.tag] = jd.unit === 'mm' ? m * 1000 : m;
      } else {
        const rad = src.rotation[jd.axis];
        handJoints[j.name] = rad;
        jointValues[jd.tag] = jd.unit === 'rad' ? rad : rad * 180 / Math.PI;
      }
    });
    window.applyJoints(built, jointValues);

    // A second, independent check: the live tag values on their own must move
    // every joint. A binding that silently does nothing would still pass the
    // tree comparison above, because both trees would sit at zero.
    const live = {
      'Robot/J1_deg': st.robot && st.robot.j1, 'Robot/J2_deg': st.robot && st.robot.j2,
      'Robot/J3_deg': st.robot && st.robot.j3, 'Robot/J4_deg': st.robot && st.robot.j4,
      'Robot/Lift_mm': st.robot && st.robot.lift
    };
    const probe = window.buildScene(doc, cfg, window.THREE);
    window.applyJoints(probe, live);
    const driven = probe.joints.map(j => {
      const jd = j.joint;
      const got = jd.kind === 'translate' ? j.object.position[jd.axis] : j.object.rotation[jd.axis];
      const want = jd.kind === 'translate'
        ? (jd.unit === 'mm' ? live[jd.tag] / 1000 : live[jd.tag])
        : (jd.unit === 'rad' ? live[jd.tag] : live[jd.tag] * Math.PI / 180);
      return { name: j.name, tag: jd.tag, sent: live[jd.tag], got, want,
               ok: Math.abs(got - want) < 1e-9 };
    });

    // A joint whose live value happens to be 0 is not proven by the check above
    // - nothing moved, and nothing moving is exactly the failure being looked
    // for. So drive each joint on its own with a distinctive value and assert
    // two things: the named axis takes it, and the other two do NOT move.
    const isolate = built.joints.map((j, idx) => {
      const fresh = window.buildScene(doc, cfg, window.THREE);
      const jd = fresh.joints[idx].joint;
      const obj = fresh.joints[idx].object;
      const sent = 11 + idx * 7;                 // distinct, non-zero, non-round
      const bag = {}; bag[jd.tag] = sent;
      window.applyJoints(fresh, bag);
      const axes = ['x', 'y', 'z'];
      const target = jd.kind === 'translate' ? obj.position : obj.rotation;
      const want = jd.kind === 'translate'
        ? (jd.unit === 'mm' ? sent / 1000 : sent)
        : (jd.unit === 'rad' ? sent : sent * Math.PI / 180);
      // The part's own resting transform is the baseline; a joint adds to
      // nothing, it SETS one axis. Others must read what the document gave them.
      const rest = window.buildScene(doc, cfg, window.THREE).joints[idx].object;
      const restT = jd.kind === 'translate' ? rest.position : rest.rotation;
      const moved = Math.abs(target[jd.axis] - want) < 1e-9;
      const others = axes.filter(a => a !== jd.axis)
                         .every(a => Math.abs(target[a] - restT[a]) < 1e-12);
      return { name: fresh.joints[idx].name, axis: jd.axis, sent,
               got: target[jd.axis], moved, others };
    });

    const desc = (0, eval)('(' + describe + ')');
    return {
      config: cfg,
      hand: desc(window.__cellScene, NOT_YET, SKIP_CHILDREN),
      docTree: desc(built.root, NOT_YET, SKIP_CHILDREN),
      driven, isolate,
      joints: built.joints.map(j => j.name + ' ' + j.joint.kind + ' ' + j.joint.axis + ' <- ' + j.joint.tag)
    };
  }, { doc, renderer, describe, NOT_YET, SKIP_CHILDREN });

  await b.close();

  if (result.err) { console.log('RENDERER ERROR: ' + result.err); process.exit(1); }
  if (errs.length) console.log('page errors: ' + errs.join(' | '));

  const key = n => JSON.stringify(n);
  const a = result.hand, c = result.docTree;
  console.log('hand-coded nodes: ' + a.length + '   document nodes: ' + c.length);
  console.log('joints found: ' + result.joints.length);
  result.joints.forEach(j => console.log('  ' + j));

  let jointBad = 0;
  console.log('\nlive tag values drive the document scene:');
  result.driven.forEach(d => {
    if (!d.ok) jointBad++;
    console.log('  ' + (d.ok ? 'ok  ' : 'FAIL') + ' ' + d.name.padEnd(9) +
                ' ' + d.tag.padEnd(15) + ' sent ' + d.sent +
                ' -> ' + (Math.round(d.got * 1e6) / 1e6));
  });

  console.log('\neach joint alone - named axis takes the value, others do not move:');
  result.isolate.forEach(d => {
    if (!d.moved || !d.others) jointBad++;
    console.log('  ' + (d.moved && d.others ? 'ok  ' : 'FAIL') + ' ' +
                d.name.padEnd(9) + ' ' + d.axis + ' <- ' + String(d.sent).padEnd(4) +
                ' => ' + (Math.round(d.got * 1e6) / 1e6) +
                (d.others ? '' : '   OTHER AXES MOVED'));
  });

  let bad = 0;
  const n = Math.max(a.length, c.length);
  for (let i = 0; i < n; i++) {
    if (key(a[i]) !== key(c[i])) {
      if (bad < 12) {
        console.log('\n#' + i + ' MISMATCH');
        console.log('  hand: ' + key(a[i]));
        console.log('  doc : ' + key(c[i]));
      }
      bad++;
    }
  }
  console.log('\n' + (bad === 0
    ? 'PARITY: identical across ' + a.length + ' nodes'
    : 'PARITY: ' + bad + ' of ' + n + ' nodes differ'));
  if (jointBad) console.log('JOINTS: ' + jointBad + ' did not take their tag value');
  process.exit(bad === 0 && jointBad === 0 && !errs.length ? 0 : 1);
})();

// Run:
//   NODE_PATH=/Home-Claude/ignition-claude-toolkit/plugins/ignition/skills/verify-view/tool/node_modules \
//     node tools/verify/scene_parity.js
