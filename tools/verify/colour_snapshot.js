// Record the painted colour of every text-bearing element on every page, so a
// change that is supposed to leave the dark themes alone can be PROVED to have
// left them alone rather than asserted.
//
// The gate this exists for: hoisting 1400 literal hex values into CSS variables
// is only safe if the variables resolve, in the dark themes, to exactly what
// the literals were. "Looks the same" is not a check - a card that moved one
// step down the neutral ramp looks the same in a screenshot and is a different
// colour.
//
// Elements are keyed by their position in the tree (a path of child indices),
// not by their text, because the demo is live: counters, cycle times and the
// clock all differ between two runs of the same build. Colours do not.
//
// Usage:
//   node tools/verify/colour_snapshot.js <gateway-url> <out.json> [--theme NAME]
//   node tools/verify/colour_snapshot.js --diff b1.json,b2.json a1.json,a2.json
//
// Several samples a side, comma separated - see the note on the diff below.
//
// Run from the verify-view tool directory (that is where playwright lives).
const fs = require('fs');

const PAGES = ['', 'cell3d', 'cell2d', 'manual', 'alarms', 'setup'];

const PROBE = `(() => {
  const out = [];
  function path(el) {
    const p = [];
    while (el && el.parentElement) {
      p.push(Array.prototype.indexOf.call(el.parentElement.children, el));
      el = el.parentElement;
    }
    return p.reverse().join('.');
  }
  for (const el of document.querySelectorAll('*')) {
    if (el.children.length) continue;
    const t = (el.textContent || '').trim();
    if (!t) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    out.push({ k: path(el), tag: el.tagName,
               fg: cs.color, bg: cs.backgroundColor,
               bc: cs.borderColor, fs: cs.fontSize });
  }
  // Backgrounds matter even where there is no text - a panel is a panel.
  const surf = [];
  for (const el of document.querySelectorAll('*')) {
    const cs = getComputedStyle(el);
    const bg = cs.backgroundColor;
    if (bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent') continue;
    surf.push({ k: path(el), bg, bc: cs.borderColor });
  }
  return { text: out, surf };
})()`;

// The demo is RUNNING while it is measured: a photo-eye makes, a zone goes
// from Idle to Running, and the lamp that was #262e36 is #46d07c a second
// later. A single before/after pair reports those as changes and they are not.
//
// So each side is several samples, and an element is only reported when the
// set of colours it wore afterwards shares NOTHING with the set it wore
// before. A lamp that toggles between two project colours in both runs is
// silent; a lamp whose off state moved one step down the ramp is not.
function load(list) {
  const files = list.split(',').map(f => JSON.parse(fs.readFileSync(f, 'utf8')));
  const seen = {};
  for (const pg of PAGES) {
    seen[pg] = { text: new Map(), surf: new Map(), n: [] };
    for (const F of files) {
      const s = F[pg] || { text: [], surf: [] };
      seen[pg].n.push([s.text.length, s.surf.length]);
      for (const kind of ['text', 'surf']) {
        const fields = kind === 'text' ? ['fg', 'bg', 'bc'] : ['bg', 'bc'];
        for (const x of s[kind]) {
          const m = seen[pg][kind];
          if (!m.has(x.k)) m.set(x.k, new Set());
          m.get(x.k).add(fields.map(f => x[f]).join('|'));
        }
      }
    }
  }
  return seen;
}

function diff(aList, bList) {
  const A = load(aList), B = load(bList);
  let changed = 0, onlyA = 0, onlyB = 0;
  const examples = [];
  for (const pg of PAGES) {
    for (const kind of ['text', 'surf']) {
      for (const [k, av] of A[pg][kind]) {
        const bv = B[pg][kind].get(k);
        if (!bv) { onlyA++; continue; }
        let shared = false;
        for (const v of av) if (bv.has(v)) { shared = true; break; }
        if (!shared) {
          changed++;
          if (examples.length < 25)
            examples.push(`${pg || '/'} ${kind} ${k}: {${[...av].join(' / ')}}` +
                          ` -> {${[...bv].join(' / ')}}`);
        }
      }
      for (const k of B[pg][kind].keys()) if (!A[pg][kind].has(k)) onlyB++;
    }
    const a = A[pg].n[0], b = B[pg].n[0];
    console.log(`  ${(pg || '/').padEnd(8)} text ${String(a[0]).padStart(4)} -> ` +
                `${String(b[0]).padStart(4)}   surfaces ${String(a[1]).padStart(4)} -> ` +
                `${String(b[1]).padStart(4)}`);
  }
  console.log(`\nelements whose computed colour CHANGED: ${changed}`);
  console.log(`elements present before and not after:   ${onlyA}`);
  console.log(`elements present after and not before:   ${onlyB}`);
  for (const e of examples) console.log('   ', e);
  process.exit(changed ? 1 : 0);
}

if (process.argv[2] === '--diff') { diff(process.argv[3], process.argv[4]); return; }

const { chromium } = require('playwright');

// The project name differs between the two builds: the standard zip imports as
// Machine_HMI_Demo, the Edge one lands in Edge's own single project. Override
// with MHD_PROJECT so this gate can be run against either.
const PROJECT = process.env.MHD_PROJECT || 'Machine_HMI_Demo';

const BASE = process.argv[2];
const OUT = process.argv[3];
const ti = process.argv.indexOf('--theme');
const THEME = ti > 0 ? process.argv[ti + 1] : null;

(async () => {
  const b = await chromium.launch();
  const all = {};
  const errors = [];
  for (const pg of PAGES) {
    const p = await b.newPage({ viewport: { width: 1366, height: 768 } });
    p.on('pageerror', e => errors.push(`${pg || '/'}: ${e.message}`));
    p.on('console', m => { if (m.type() === 'error') errors.push(`${pg || '/'} console: ${m.text()}`); });
    await p.goto(`${BASE}/data/perspective/client/${PROJECT}/${pg}` +
                 (THEME ? `?theme=${THEME}` : ''),
                 { waitUntil: 'networkidle', timeout: 60000 }).catch(() => {});
    await p.waitForTimeout(3500);
    all[pg] = await p.evaluate(PROBE);
    await p.close();
  }
  await b.close();
  fs.writeFileSync(OUT, JSON.stringify(all, null, 1));
  let n = 0, s = 0;
  for (const pg of PAGES) { n += all[pg].text.length; s += all[pg].surf.length; }
  console.log(`${OUT}: ${n} text elements, ${s} painted surfaces` +
              (THEME ? ` (theme=${THEME})` : ''));
  if (errors.length) {
    console.log(`JavaScript errors: ${errors.length}`);
    for (const e of errors.slice(0, 20)) console.log('   ', e);
  } else console.log('JavaScript errors: 0');
})();
