// Resolve every --md-* variable in every theme, and assert the dark ones are
// byte-identical to the literal they replaced.
//
// This is the gate that matters. Diffing rendered pages proves the colours did
// not move where something happened to be on screen; this proves it for the
// whole table at once, including the variables that only appear when a fault
// is raised or a pallet completes. A custom property's own computed value is
// the token text, not a colour, so each one is resolved by painting it onto a
// probe element and reading back `color`.
//
// Usage:  node tools/verify/md_vars_check.js <gateway-url>
// Run from the verify-view tool directory (that is where playwright lives).
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

// The project name differs between the two builds: the standard zip imports as
// Machine_HMI_Demo, the Edge one lands in Edge's own single project. Override
// with MHD_PROJECT so this gate can be run against either.
const PROJECT = process.env.MHD_PROJECT || 'Machine_HMI_Demo';

// The gateway comes from argv[2] or $GW_URL and there is NO default. There used
// to be one - http://localhost:8088 - and it is the module-testing gateway on
// this workstation, so a run that forgot the argument swept a DIFFERENT gateway
// and reported a clean result about a project that was not this one.
const BASE = process.argv[2] || process.env.GW_URL;
if (!BASE) { console.error('give the gateway URL as the first argument, or set $GW_URL'); process.exit(2); }
const DARK = ['dark', 'dark-cool', 'dark-warm'];
const LIGHT = ['light', 'light-cool', 'light-warm'];

// #rrggbb from either serialisation. rgb(from ...) computes to color(srgb ...).
const NORM = `(s => {
  const c = /^color\\(\\s*srgb\\s+([-\\d.eE]+)\\s+([-\\d.eE]+)\\s+([-\\d.eE]+)/.exec(s);
  const v = c ? [c[1], c[2], c[3]].map(x => Math.round(+x * 255))
              : (s.match(/[\\d.]+/g) || []).slice(0, 3).map(Number);
  return '#' + v.map(x => Math.max(0, Math.min(255, Math.round(x)))
                          .toString(16).padStart(2, '0')).join('');
})`;

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1366, height: 768 } });
  await p.goto(`${BASE}/data/perspective/client/${PROJECT}/`,
               { waitUntil: 'networkidle', timeout: 60000 }).catch(() => {});
  await p.waitForTimeout(3000);

  // Every --md-* the project stylesheet declares, and the literal each one
  // carries as its fallback - which is the value it must keep in the dark.
  // Every --md-* the project stylesheet declares, and what each must keep in
  // a dark theme. Read from the file rather than from document.styleSheets:
  // the served sheet is there, but its cssRules list is empty as often as not
  // when the probe runs, and a check that silently finds nothing to check is
  // worse than no check.
  const SHEET = path.join(__dirname, '..', '..', 'project',
                          'com.inductiveautomation.perspective',
                          'stylesheet', 'stylesheet.css');
  const css = fs.readFileSync(SHEET, 'utf8');
  const names = {};
  for (const m of css.matchAll(/(--md-[a-z0-9-]+):\s*([^;]+);/gi)) {
    const v = m[2].trim();
    let hit = /^#[0-9a-f]{6}$/i.exec(v);
    if (hit) { names[m[1]] = { want: hit[0].toLowerCase() }; continue; }
    // Declared as var(--neutral-N, #hex): what it must keep in a dark theme
    // is the TOKEN, not the fallback. The fallback is only what it shows
    // where no theme is loaded at all.
    hit = /^var\(--(neutral-\d+),\s*(#[0-9a-f]{6})\s*\)$/i.exec(v);
    if (hit) names[m[1]] = { want: '--' + hit[1], lit: hit[2].toLowerCase() };
  }
  const keys = Object.keys(names).sort();
  console.log(`${keys.length} --md-* variables declared\n`);

  const table = {};
  for (const theme of DARK.concat(LIGHT)) {
    await p.evaluate(t => {
      const l = document.querySelector('link[href*="/data/perspective/themes/"]');
      if (l) l.href = l.href.replace(/themes\/[^/]+\.css/, 'themes/' + t + '.css');
    }, theme);
    await p.waitForTimeout(1200);
    table[theme] = await p.evaluate(([ks, normSrc]) => {
      const norm = eval(normSrc);
      const probe = document.createElement('span');
      probe.style.position = 'fixed'; probe.style.left = '-9999px';
      document.body.appendChild(probe);
      const out = {};
      for (const k of ks) {
        probe.style.color = 'rgb(1, 2, 3)';
        probe.style.color = `var(${k})`;
        out[k] = norm(getComputedStyle(probe).color);
      }
      for (let n = 10; n <= 100; n += 10) {
        probe.style.color = 'rgb(1, 2, 3)';
        probe.style.color = `var(--neutral-${n})`;
        out['--neutral-' + n] = norm(getComputedStyle(probe).color);
      }
      probe.remove();
      return out;
    }, [keys, NORM]);
  }
  await b.close();

  let bad = 0;
  console.log('variable'.padEnd(20) +
              DARK.concat(LIGHT).map(t => t.padEnd(10)).join('') + ' literal');
  for (const k of keys) {
    const want = names[k].want;
    const row = DARK.concat(LIGHT).map(t => table[t][k]);
    const expected = t => want.startsWith('--') ? table[t][want] : want;
    const wrong = DARK.some(t => table[t][k] !== expected(t));
    if (wrong) bad++;
    console.log(k.padEnd(20) + row.map(v => v.padEnd(10)).join('') +
                ' ' + want + (wrong ? '   <-- MOVED IN A DARK THEME' : ''));
  }
  console.log(`\ndark-theme values that differ from the literal they replaced: ${bad}`);
  process.exit(bad ? 1 : 0);
})();
