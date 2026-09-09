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

// The project name differs between the two builds: the standard zip imports as
// Machine_HMI_Demo, the Edge one lands in Edge's own single project. Override
// with MHD_PROJECT so this gate can be run against either.
const PROJECT = process.env.MHD_PROJECT || 'Machine_HMI_Demo';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
// The gateway comes from argv[2] or $GW_URL and there is NO default. There used
// to be one - http://localhost:8088 - and it is the module-testing gateway on
// this workstation, so a run that forgot the argument swept a DIFFERENT gateway
// and reported a clean result about a project that was not this one.
const GW = process.argv[2] || process.env.GW_URL;
if (!GW) { console.error('give the gateway URL as the first argument, or set $GW_URL'); process.exit(2); }
// PAGE can be pointed at a scratch copy of the resource, so a change to the
// page can be proved before it goes anywhere near the one the demo serves.
const PAGE = process.env.PAGE_URL ||
  (GW + '/system/webdev/' + PROJECT + '/' + (process.env.PAGE_RES || 'cell3d'));

// Nodes the document does not claim to build.
//   - lights and GridHelper are scene furniture, not parts of the machine; a
//     parts list has no business describing the lighting rig
//   - the rest are built from Config tags and are the next tranche
const NOT_YET = [
  'HemisphereLight', 'AmbientLight', 'DirectionalLight', 'GridHelper',
  'InfeedConveyor', 'Station1', 'Station2', 'Gripper'
];

// Parts the document DOES create but whose contents are still built from Config
// tags: the gripper group is in scene.json, the head plate, suction cups and
// held cases it carries are sized from the case and the pick count and are not.
const SKIP_CHILDREN = [];

// Subtrees compared on their own, by name, because their siblings inside the
// same parent are not in the document yet. The infeed group also carries six
// photo-eyes and a pool of cartons; the frame under it is fully described.
// Subtrees compared on their own, by name. `prefix` means the page's group
// carries more children than the document describes - the pallet stations hold
// their case stacks, whose layout is the pattern algorithm the simulator also
// owns - so the document's nodes are compared against the page's first N and
// the remainder is checked to be exactly those case stacks and nothing else.
const SUBTREES = [
  { name: 'InfeedConveyor', stateVisible: 'group' },
  { name: 'Station1', prefix: true },
  { name: 'Station2', prefix: true },
  // The held cases are shown and hidden as the cycle runs, so their visibility
  // is state, not structure. Comparing it made this gate depend on where the
  // arm happened to be when it ran - passing or failing on the same code.
  { name: 'Gripper', unordered: true, stateVisible: 'group' }
];

// The page spins the rollers to show the belt running, so their rotation about
// the barrel axis is animation, not structure, and the document does not
// describe it - the same class of thing as a joint angle. It is excluded from
// the comparison and then asserted separately, because a roller that had
// stopped spinning would otherwise pass silently.
const ANIMATED = {
  InfeedConveyor: {
    geom: 'CylinderGeometry', axis: 1,   // roller spin
    // A photo-eye beam's colour AND opacity are its live tag - green clear,
    // red blocked, pulsing. Neither is structure.
    matStateOf: 'MeshBasicMaterial',
    // The cartons shuffle down the belt as the queue moves, so where one IS
    // is state. Where the POOL sits - count, pitch, start - is structure, and
    // is asserted directly below instead.
    statePosOf: 'infeedCase'
  }
};

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

  const result = await p.evaluate(async ({ doc, renderer, describe, NOT_YET, SKIP_CHILDREN, SUBTREES, ANIMATED }) => {
    // The page's own config, so both trees are built from identical numbers.
    let cfg = {}, st = {}, geo = {};
    try {
      const r = await fetch('admin?cmd=state', { cache: 'no-store' });
      st = await r.json();
      cfg = st.config || {};
      geo = st.geometry || {};
    } catch (e) { return { err: 'could not read admin?cmd=state: ' + e }; }

    // The document the GATEWAY serves, out of the Machine/Scene view's custom
    // properties - which is what the page will actually render. Testing the
    // repo file alone would prove the renderer and nothing about the plumbing:
    // a view that failed to deploy, or custom props edited in the Designer and
    // never extracted, would both pass.
    let served = null, serveErr = null;
    try {
      const r2 = await fetch('admin?cmd=scene', { cache: 'no-store' });
      const j = await r2.json();
      if (j && j.ok) served = j.scene;
      else serveErr = (j && j.error) || 'admin?cmd=scene did not answer ok';
    } catch (e) { serveErr = String(e); }
    // Compare canonically. Jython's jsonDecode hands back an unordered map, so
    // the served document's keys come out in a different order every time -
    // which is not drift. Array order IS meaningful (it is the child order in
    // the scene graph) and is preserved.
    const canon = v => {
      if (Array.isArray(v)) return '[' + v.map(canon).join(',') + ']';
      if (v && typeof v === 'object') {
        return '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + canon(v[k])).join(',') + '}';
      }
      return JSON.stringify(v);
    };
    const drift = served ? (canon(served) !== canon(doc)) : null;
    // Build from what the gateway serves when it is available. If it is not,
    // say so loudly and fall back to the repo file rather than reporting a
    // pass that was never about the deployed thing.
    if (served) doc = served;

    (0, eval)(renderer);
    let built, err = null;
    try { built = window.buildScene(doc, cfg, window.THREE, geo); }
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
    const probe = window.buildScene(doc, cfg, window.THREE, geo);
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
      const fresh = window.buildScene(doc, cfg, window.THREE, geo);
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
      const rest = window.buildScene(doc, cfg, window.THREE, geo).joints[idx].object;
      const restT = jd.kind === 'translate' ? rest.position : rest.rotation;
      const moved = Math.abs(target[jd.axis] - want) < 1e-9;
      const others = axes.filter(a => a !== jd.axis)
                         .every(a => Math.abs(target[a] - restT[a]) < 1e-12);
      return { name: fresh.joints[idx].name, axis: jd.axis, sent,
               got: target[jd.axis], moved, others };
    });

    // Photo-eyes, matched as a SET rather than by tree position: the page does
    // not name them, and the gate must not deploy a renamed page to a shared
    // gateway just to make itself easier to write. An eye is a group of two
    // posts and a beam, so that is how they are found on the hand side. Beam
    // COLOUR is a live tag and is excluded; that each beam owns its material
    // is asserted instead, which is the property that matters.
    const eyeShape = g => {
      if (!g.isGroup && g.type !== 'Group') return null;
      const boxes = g.children.filter(c => c.isMesh && c.geometry.type === 'BoxGeometry');
      const cyls = g.children.filter(c => c.isMesh && c.geometry.type === 'CylinderGeometry');
      if (boxes.length !== 2 || cyls.length !== 1 || g.children.length !== 3) return null;
      const r6 = v => Math.round(v * 1e6) / 1e6;
      const beam = cyls[0];
      return {
        posts: boxes.map(b => [r6(b.position.x), r6(b.position.y), r6(b.position.z)]).sort(),
        beam: [r6(beam.position.x), r6(beam.position.y), r6(beam.position.z)],
        beamLen: r6(beam.geometry.parameters.height),
        beamSeg: beam.geometry.parameters.radialSegments,
        beamRot: [r6(beam.rotation.x), r6(beam.rotation.y), r6(beam.rotation.z)],
        matType: beam.material.type
      };
    };
    const collectEyes = root => {
      const out = [];
      root.traverse(o => { const e = eyeShape(o); if (e) out.push({ e, mat: o.children.find(c => c.geometry && c.geometry.type === 'CylinderGeometry').material }); });
      out.sort((a, b) => a.e.beam[0] - b.e.beam[0]);
      return out;
    };
    const handInfeed = window.__cellScene.getObjectByName('InfeedConveyor');
    const docInfeed = built.root.getObjectByName('InfeedConveyor');
    const he = handInfeed ? collectEyes(handInfeed) : [];
    const de = docInfeed ? collectEyes(docInfeed) : [];
    const eyes = {
      handCount: he.length,
      docCount: de.length,
      shapes: de.map((d, i) => ({ doc: d.e, hand: he[i] ? he[i].e : null })),
      // Six beams must be six DIFFERENT materials, or one blocked eye would
      // turn them all red together.
      distinctMaterials: new Set(de.map(d => d.mat)).size,
      // Beam opacity is animated - the page pulses it - so it is excluded from
      // the shape comparison above and checked here instead: the live beams must
      // show more than one value, or the pulse has stopped.
      handOpacities: he.map(d => Math.round(d.mat.opacity * 1000) / 1000),
      docOpacity: de.length ? Math.round(de[0].mat.opacity * 1000) / 1000 : null
    };

    const desc = (0, eval)('(' + describe + ')');
    return {
      serveErr, drift, servedParts: served ? served.parts.length : null,
      eyes,
      config: cfg,
      hand: desc(window.__cellScene, NOT_YET, SKIP_CHILDREN),
      docTree: desc(built.root, NOT_YET, SKIP_CHILDREN),
      subtrees: SUBTREES.map(spec => {
        const name = spec.name;
        const h = window.__cellScene.getObjectByName(name);
        const c = built.root.getObjectByName(name);
        const an = ANIMATED[name];
        const strip = list => {
          if (!an || !list) return { list, spinning: 0 };
          let spinning = 0;
          const out = list.map(n => {
            let out = n;
            if (n.geom && n.geom.indexOf(an.geom) === 0) {
              if (Math.abs(n.rot[an.axis]) > 1e-9) spinning++;
              const r = n.rot.slice(); r[an.axis] = 'animated';
              out = Object.assign({}, out, { rot: r });
            }
            if (an.matStateOf && n.mat && n.mat.indexOf(an.matStateOf) === 0) {
              out = Object.assign({}, out, {
                mat: n.mat.replace(/op=[\d.]+/, 'op=state').replace(/#[0-9a-f]{6}/, '#state')
              });
            }
            return out;
          });
          return { list: out, spinning };
        };
        // desc() walks a node's CHILDREN, so describing a subtree by its root
        // would leave the root's own transform unchecked - and these roots are
        // exactly where the tag-driven placement lives: the pallet stations sit
        // at Config/station1X_mm, the gripper hangs at -0.14 off the wrist.
        // Wrapping in a synthetic parent brings the root itself into the diff.
        const withSelf = n => (n ? desc({ children: [n] }, [], []) : null);
        const hideState = l => (!spec.stateVisible || !l) ? l : l.map(n =>
          n.kind === spec.stateVisible ? Object.assign({}, n, { vis: 'state' }) : n);
        // Carton POSITION is state. Blank it on the nodes that are cartons -
        // found by shape, a group of a body box and a thin seam box - on both
        // sides, so neither tree can hide a wrong one behind the other.
        const isCarton = (l, i) => {
          const n = l[i];
          if (!n || n.kind !== 'group') return false;
          const kids = [];
          for (let k = i + 1; k < l.length && l[k].depth > n.depth; k++) {
            if (l[k].depth === n.depth + 1) kids.push(l[k]);
          }
          // A carton is a body box with a thin seam box on its face. Keyed on
          // the SHAPE rather than on the seam's exact height, so editing that
          // dimension in the document does not quietly stop the detector
          // recognising cartons and blow up the diff somewhere else.
          if (kids.length !== 2 || !kids.every(x => x.geom && x.geom.indexOf('BoxGeometry') === 0)) return false;
          const h = kids.map(x => parseFloat((x.geom.match(/height=([\d.]+)/) || [])[1]));
          return Math.min(...h) < 0.02 && Math.max(...h) > 0.05;
        };
        const blankCartonPos = l => (!(an && an.statePosOf) || !l) ? l :
          l.map((n, i) => isCarton(l, i) ? Object.assign({}, n, { pos: 'state' }) : n);
        const H = strip(blankCartonPos(hideState(withSelf(h))));
        const C = strip(blankCartonPos(hideState(withSelf(c))));
        const res = { name, hand: H.list, doc: C.list, spinning: an ? H.spinning : undefined };
        if (spec.unordered && H.list && C.list) {
          // Sibling order carries no meaning here, so compare as a multiset.
          const norm = l => l.map(n => JSON.stringify(Object.assign({}, n, { depth: n.depth }))).sort();
          res.hand = norm(H.list).map(x => JSON.parse(x));
          res.doc = norm(C.list).map(x => JSON.parse(x));
          res.unordered = true;
        }
        if (spec.stateVisible && c) {
          // Excluding a property is only safe if the thing it was protecting is
          // asserted another way: the document must still BUILD the held cases
          // hidden, or a fresh page would open with three cartons in mid-air.
          const held = [];
          c.traverse(o => {
            if (o.name && (o.name.indexOf('heldCase') === 0 || o.name.indexOf('infeedCase') === 0)) held.push(o);
          });
          res.held = held.length;
          res.heldHidden = held.filter(o => o.visible === false).length;
          res.heldWhat = c.name === 'Gripper' ? 'held cases' : 'cartons';
          const pool = held.filter(o => o.name.indexOf('infeedCase') === 0)
                           .sort((a2, b2) => a2.position.x - b2.position.x);
          if (pool.length > 2) {
            const gaps = [];
            for (let i = 1; i < pool.length; i++) {
              gaps.push(Math.round((pool[i].position.x - pool[i - 1].position.x) * 1e6) / 1e6);
            }
            res.pitchSet = [...new Set(gaps)];
            res.poolY = [...new Set(pool.map(o => Math.round(o.position.y * 1e6) / 1e6))];
          }
        }
        if (spec.prefix && H.list && C.list) {
          res.tail = H.list.length - C.list.length;
          // Everything past the described prefix must be a carton: a group of
          // a body box and a seam box. Anything else means the document has
          // dropped a real part rather than stopping where it meant to.
          const tailNodes = H.list.slice(C.list.length);
          res.tailOdd = tailNodes.filter(n =>
            !(n.kind === 'group' || (n.geom && n.geom.indexOf('BoxGeometry') === 0))).length;
          res.hand = H.list.slice(0, C.list.length);
        }
        return res;
      }),
      driven, isolate,
      joints: built.joints.map(j => j.name + ' ' + j.joint.kind + ' ' + j.joint.axis + ' <- ' + j.joint.tag)
    };
  }, { doc, renderer, describe, NOT_YET, SKIP_CHILDREN, SUBTREES, ANIMATED });

  await b.close();

  if (result.err) { console.log('RENDERER ERROR: ' + result.err); process.exit(1); }
  if (errs.length) console.log('page errors: ' + errs.join(' | '));

  if (result.serveErr) {
    console.log('SCENE ROUTE: ' + result.serveErr);
    console.log('  the gateway is not serving the document; what follows tested the REPO FILE only');
  } else {
    console.log('scene route: gateway serves ' + result.servedParts + ' parts from Machine/Scene' +
                (result.drift ? '  DRIFT - it differs from src/cell3d/scene.json' : ', identical to src/cell3d/scene.json'));
  }

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
  // Photo-eyes.
  const E = result.eyes;
  console.log('\nphoto-eyes: page has ' + E.handCount + ', document builds ' + E.docCount);
  if (E.handCount !== E.docCount) { console.log('  FAIL count differs'); bad++; }
  let eyeBad = 0;
  E.shapes.forEach((s2, i) => {
    if (key(s2.doc) !== key(s2.hand)) {
      if (eyeBad < 3) {
        console.log('  #' + i + ' MISMATCH\n    hand: ' + key(s2.hand) + '\n    doc : ' + key(s2.doc));
      }
      eyeBad++;
    }
  });
  console.log('  ' + (eyeBad === 0 ? 'ok   every eye matches in posts, beam and material type'
                                   : 'FAIL ' + eyeBad + ' differ'));
  const opacities = [...new Set(E.handOpacities)];
  const pulsing = opacities.length > 1;
  console.log('  ' + (pulsing ? 'ok  ' : 'FAIL') + ' beam opacity is animated on the page (' +
              opacities.join(', ') + '), document builds them at ' + E.docOpacity +
              (pulsing ? '' : ' - the pulse has stopped'));
  if (!pulsing) bad++;

  const distinctOk = E.distinctMaterials === E.docCount;
  console.log('  ' + (distinctOk ? 'ok  ' : 'FAIL') + ' ' + E.distinctMaterials + ' of ' +
              E.docCount + ' beams own their material' +
              (distinctOk ? '' : ' - one blocked eye would recolour them all'));
  bad += eyeBad + (distinctOk ? 0 : 1);

  // Named subtrees, compared on their own.
  result.subtrees.forEach(t => {
    if (!t.hand || !t.doc) {
      console.log('\nsubtree ' + t.name + ': MISSING from ' + (t.hand ? 'the document' : 'the page'));
      bad++;
      return;
    }
    let sb = 0;
    const m = Math.max(t.hand.length, t.doc.length);
    for (let i = 0; i < m; i++) {
      if (key(t.hand[i]) !== key(t.doc[i])) {
        if (sb < 4) {
          console.log('\nsubtree ' + t.name + ' #' + i + ' MISMATCH');
          console.log('  hand: ' + key(t.hand[i]));
          console.log('  doc : ' + key(t.doc[i]));
        }
        sb++;
      }
    }
    console.log('\nsubtree ' + t.name + ': ' + (sb === 0
      ? 'identical across ' + t.hand.length + ' nodes' +
        (t.unordered ? ' (as a set)' : '') + ' (excluding animated axes)'
      : sb + ' of ' + m + ' nodes differ'));
    if (t.held !== undefined) {
      const ok = t.held > 0 && t.heldHidden === t.held;
      console.log('  ' + (ok ? 'ok  ' : 'FAIL') + ' ' + t.heldHidden + ' of ' + t.held +
                  ' ' + t.heldWhat + ' are built hidden' +
                  (ok ? ' (visibility itself is state, excluded above)'
                      : ' - a fresh page would open showing product that is not there'));
      if (!ok) bad++;
    }
    if (t.pitchSet) {
      const ok = t.pitchSet.length === 1 && t.pitchSet[0] > 0 && t.poolY.length === 1;
      console.log('  ' + (ok ? 'ok  ' : 'FAIL') + ' the pool is evenly pitched at ' +
                  t.pitchSet.join('/') + ' m on one level' +
                  (ok ? '' : ' - pitch or height is not uniform'));
      if (!ok) bad++;
    }
    if (t.tail !== undefined) {
      const tailOk = t.tail > 0 && t.tailOdd === 0;
      console.log('  ' + (tailOk ? 'ok  ' : 'FAIL') + ' ' + t.tail +
                  ' further nodes on the page are the case stacks' +
                  (t.tailOdd ? ' - but ' + t.tailOdd + ' are not cartons' : ''));
      if (!tailOk) bad++;
    }
    if (t.spinning !== undefined) {
      const ok = t.spinning > 0;
      console.log('  ' + (ok ? 'ok  ' : 'FAIL') + ' ' + t.spinning +
                  ' rollers are actually spinning' + (ok ? '' : ' - the belt is not running'));
      if (!ok) bad++;
    }
    bad += sb;
  });

  console.log('\n' + (bad === 0
    ? 'PARITY: identical across ' + a.length + ' nodes'
    : 'PARITY: ' + bad + ' of ' + n + ' nodes differ'));
  if (jointBad) console.log('JOINTS: ' + jointBad + ' did not take their tag value');
  process.exit(bad === 0 && jointBad === 0 && !errs.length && !result.serveErr && !result.drift ? 0 : 1);
})();

// Run:
//   NODE_PATH=/Home-Claude/ignition-claude-toolkit/plugins/ignition/skills/verify-view/tool/node_modules \
//     node tools/verify/scene_parity.js
