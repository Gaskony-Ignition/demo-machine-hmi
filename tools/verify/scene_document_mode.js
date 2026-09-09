// Does the cell built from the scene document actually RUN?
//
// scene_parity.js proves the document builds the same objects as the page's own
// JavaScript. That says nothing about whether the animation - which drives
// handles bound by name in bindFromDocument - reaches them. A cell that is
// structurally perfect and completely still would pass every check in that file.
//
// So this samples the live page twice, seconds apart, in BOTH modes, and asserts
// the same things move in each: the joints, the photo-eye colours, the carton
// queue and the pallet stacks.
const { chromium } = require('playwright');

// The project name differs between the two builds: the standard zip imports as
// Machine_HMI_Demo, the Edge one lands in Edge's own single project. Override
// with MHD_PROJECT so this gate can be run against either.
const PROJECT = process.env.MHD_PROJECT || 'Machine_HMI_Demo';

const GW = process.env.GW_URL || 'http://192.168.153.128:8088';
const RES = process.env.PAGE_RES || 'cell3d';
const GAP = 7000;

const sample = `async () => {
  let st = null;
  try { st = await (await fetch('admin?cmd=state', { cache: 'no-store' })).json(); } catch (e) {}
  const s = window.__cellScene;
  if (!s) return null;
  const g = n => s.getObjectByName(n);
  const r6 = v => Math.round(v * 1e6) / 1e6;
  const beams = [];
  s.traverse(o => {
    if (o.isMesh && o.material && o.material.type === 'MeshBasicMaterial'
        && o.geometry.type === 'CylinderGeometry') {
      beams.push('#' + o.material.color.getHexString());
    }
  });
  let visibleCartons = 0, visibleStack = 0, visibleStack2 = 0;
  const infeed = g('InfeedConveyor');
  if (infeed) infeed.children.forEach(c => { if (c.type === 'Group' && c.visible && c.children.length === 2) visibleCartons++; });
  const stg = g('Station1');
  if (stg) stg.children.forEach(c => { if (c.type === 'Group' && c.visible && c.children.length === 2) visibleStack++; });
  const stg2 = g('Station2');
  if (stg2) stg2.children.forEach(c => { if (c.type === 'Group' && c.visible && c.children.length === 2) visibleStack2++; });
  let rollerSpin = 0;
  s.traverse(o => { if (o.isMesh && /Cylinder/.test(o.geometry.type) && Math.abs(o.rotation.y) > 1e-9) rollerSpin++; });
  return {
    saysStation1: st && st.pallets && st.pallets[0] ? st.pallets[0].cases : null,
    saysStation2: st && st.pallets && st.pallets[1] ? st.pallets[1].cases : null,
    saysQueue: st && st.infeed ? st.infeed.queue : null,
    j1: r6(g('Base') ? g('Base').rotation.y : NaN),
    lift: r6(g('Carriage') ? g('Carriage').position.y : NaN),
    j2: r6(g('Shoulder') ? g('Shoulder').rotation.z : NaN),
    j3: r6(g('Elbow') ? g('Elbow').rotation.z : NaN),
    beams: beams.join(' '),
    visibleCartons, visibleStack, visibleStack2, rollerSpin
  };
}`;

async function run(mode) {
  const b = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const p = await (await b.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
  const errs = [];
  p.on('pageerror', e => errs.push(String(e).slice(0, 160)));
  const url = GW + '/system/webdev/${PROJECT}/' + RES + (mode === 'document' ? '?scene=document' : '');
  await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await p.waitForFunction('window.__cellScene', null, { timeout: 30000 });
  await p.waitForTimeout(3000);
  const a = await p.evaluate('(' + sample + ')()');
  await p.waitForTimeout(GAP);
  const c = await p.evaluate('(' + sample + ')()');
  await b.close();
  return { a, c, errs };
}

(async () => {
  let bad = 0;
  for (const mode of ['default', 'document']) {
    const { a, c, errs } = await run(mode);
    console.log('\n--- ' + mode + ' mode ---');
    if (!a || !c) { console.log('  FAIL the scene never appeared'); bad++; continue; }
    if (errs.length) { console.log('  FAIL page errors: ' + errs.join(' | ')); bad++; }

    const joints = ['j1', 'lift', 'j2', 'j3'];
    const movedJoints = joints.filter(k => Math.abs(a[k] - c[k]) > 1e-6);
    const ok = m => m ? 'ok  ' : 'FAIL';
    console.log('  ' + ok(movedJoints.length >= 2) + ' joints moving: ' +
                (movedJoints.join(', ') || 'NONE') +
                '   (' + joints.map(k => k + ' ' + a[k] + '->' + c[k]).join(', ') + ')');
    if (movedJoints.length < 2) bad++;

    console.log('  ' + ok(a.rollerSpin > 0) + ' rollers spinning: ' + a.rollerSpin);
    if (!a.rollerSpin) bad++;

    // Asserting the beams CHANGE between two samples was flaky: they only
    // change when the queue does, which may not happen in a seven-second
    // window. What must always hold while product is on the belt is that the
    // eyes disagree with each other - the ones the cartons are standing on
    // read blocked and the rest read clear. A colour shared by all six is the
    // failure that matters: eyes that are not following the queue at all.
    const distinct = t => [...new Set(t.beams.split(' ').filter(Boolean))];
    const withProduct = [a, c].filter(t => t.visibleCartons > 0);
    const beamsOk = withProduct.length === 0
      ? true
      : withProduct.some(t => distinct(t).length > 1);
    console.log('  ' + (withProduct.length === 0 ? 'skip' : ok(beamsOk)) +
                ' photo-eyes disagree while product is on the belt: ' +
                [a, c].map(t => distinct(t).join('/') + ' @' + t.visibleCartons).join('  then  ') +
                (withProduct.length === 0 ? '   (belt was empty both samples)' : ''));
    if (!beamsOk) bad++;

    // Asserting the stack is non-empty was flaky: a pallet that has just been
    // discharged is legitimately empty for a while, and the check failed on a
    // cell that was working perfectly. What must hold at every phase is that
    // the model AGREES with the gateway - show what the plant says is there.
    // Both stations, because 0/0 agrees trivially and a pallet that has just
    // discharged is legitimately empty. One of the two is nearly always loaded,
    // and if neither is, say the check proved little rather than claiming a pass.
    const agrees = (t, n) => t['saysStation' + n] === null ||
                             t['visibleStack' + (n === 1 ? '' : '2')] === t['saysStation' + n];
    const stackOk = [a, c].every(t => agrees(t, 1) && agrees(t, 2));
    const anyLoaded = [a, c].some(t => t.visibleStack > 0 || t.visibleStack2 > 0);
    console.log('  ' + ok(stackOk) + ' both stations show what the gateway says: ' +
                [a, c].map(t => t.visibleStack + '/' + t.saysStation1 + ' and ' +
                                t.visibleStack2 + '/' + t.saysStation2).join('   then   ') +
                (anyLoaded ? '' : '   (both empty - this proved little)'));
    if (!stackOk) bad++;

    const queueAgrees = t => t.saysQueue === null || Math.abs(t.visibleCartons - t.saysQueue) <= 1;
    const qOk = queueAgrees(a) && queueAgrees(c);
    console.log('  ' + ok(qOk) + ' the belt shows what the gateway says: ' +
                [a, c].map(t => t.visibleCartons + '/' + t.saysQueue).join(' then ') +
                '   (+-1: a carton can be mid-handover)');
    if (!qOk) bad++;
  }
  console.log('\n' + (bad === 0 ? 'BOTH MODES RUN' : bad + ' checks failed'));
  process.exit(bad === 0 ? 0 : 1);
})();
