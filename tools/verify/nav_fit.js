// Does the nav bar fit, on every view that carries it, at every width a panel
// is likely to have?
//
// The bar went from six tabs to eight in 1.15.0. Eight is enough that "it looked
// fine on my monitor" stops being evidence: the header also holds the line
// title, three status chips, a theme picker and the sign-in block, and the tabs
// are the part that gives. The failure is not a crash - it is a tab that wraps
// to a second row, or sits past the right edge where nobody scrolls to find it.
//
// Usage:  node tools/verify/nav_fit.js <gateway-url>
//         MHD_PROJECT=Edge node tools/verify/nav_fit.js http://host:8388
const { chromium } = require('playwright');

const PROJECT = process.env.MHD_PROJECT || 'Machine_HMI_Demo';
const BASE = process.argv[2] || process.env.GW_URL;
if (!BASE) { console.error('give the gateway URL as the first argument, or set $GW_URL'); process.exit(2); }

// 1280 is the narrowest panel this demo targets; 1366 is the view's own
// defaultSize. Cell3D, SceneDoc, Cell2D and CadModel are full-bleed model
// screens with a Back button instead of the bar, so they are not listed.
const WIDTHS = [1280, 1366, 1600, 1920];
const PAGES = ['', 'manual', 'alarms', 'setup'];
const EXPECTED = ['OVERVIEW', '3D CELL', 'SCENE', '2D CELL', 'CAD', 'MANUAL', 'ALARMS', 'SETUP'];

// Perspective prefixes a project style class with psc-, so the class in the DOM
// is psc-nav-tab, not nav-tab. Matching on the bare name finds nothing and the
// gate passes having measured zero tabs.
const PROBE = `(() => {
  const tabs = [...document.querySelectorAll('[class*=nav-tab]')];
  const vw = document.documentElement.clientWidth;
  const boxes = tabs.map(t => {
    const b = t.getBoundingClientRect();
    return { text: t.textContent.trim(), right: Math.round(b.right),
             top: Math.round(b.top), clipped: t.scrollWidth > t.clientWidth + 1 };
  });
  return {
    texts: boxes.map(b => b.text),
    rows: new Set(boxes.map(b => b.top)).size,
    offscreen: boxes.filter(b => b.right > vw).map(b => b.text),
    clipped: boxes.filter(b => b.clipped).map(b => b.text),
    overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    components: document.querySelectorAll('[data-component]').length,
    body: document.body.innerText.slice(0, 100)
  };
})()`;

(async () => {
  const b = await chromium.launch();
  // ONE page for the whole run: Edge Panel permits a single concurrent
  // Perspective session, and a page-per-route browser gets "Sessions Exceeded"
  // on every route after the first - which renders, measures clean, and is not
  // the project.
  const p = await b.newPage({ viewport: { width: WIDTHS[0], height: 900 } });
  let bad = 0;

  for (const w of WIDTHS) {
    await p.setViewportSize({ width: w, height: 900 });
    for (const pg of PAGES) {
      await p.goto(`${BASE}/data/perspective/client/${PROJECT}/${pg}`,
                   { waitUntil: 'networkidle', timeout: 60000 }).catch(() => {});
      await p.waitForTimeout(3200);
      const r = await p.evaluate(PROBE);

      if (r.components === 0) {
        console.error(`page /${pg} did not render the project: ${JSON.stringify(r.body)}`);
        process.exit(1);
      }
      const missing = EXPECTED.filter(t => !r.texts.includes(t));
      const ok = r.rows === 1 && !r.offscreen.length && !r.clipped.length
                 && !r.overflowX && !missing.length;
      if (!ok) bad++;
      console.log(`${String(w).padEnd(5)} /${(pg || '').padEnd(7)} ${ok ? 'ok  ' : 'FAIL'} ` +
                  `${r.texts.length} tabs, ${r.rows} row(s)` +
                  (missing.length ? `  missing: ${missing.join(',')}` : '') +
                  (r.offscreen.length ? `  offscreen: ${r.offscreen.join(',')}` : '') +
                  (r.clipped.length ? `  clipped: ${r.clipped.join(',')}` : '') +
                  (r.overflowX ? '  page scrolls sideways' : ''));
    }
  }
  await b.close();
  console.log(bad ? `\n${bad} failing width/page combination(s)` : '\nthe nav bar fits everywhere');
  process.exit(bad ? 1 : 0);
})();
