// Reports every element that would draw a scroll bar: overflow auto/scroll with
// content larger than its box. Perspective flex containers default to
// overflow:auto, so 1 px of overflow draws a bar on Windows. Headless Chromium
// hides scroll bars unless --hide-scrollbars is dropped, so a "no page scroll"
// check never sees these. Covers the pages, the popups they open, and, inside
// the CAD and 3D frames, the WebDev documents too.
//
// Only an intentional list, table or text pane may scroll; each one is named in
// ALLOWED below with the reason. Everything else is a finding, and any finding
// exits 1.
//
//   node tools/verify/scrollbar_sweep.js <gateway-url>
//   MHD_PROJECT=Machine_HMI_Demo_Edge node tools/verify/scrollbar_sweep.js <url>
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const BASE = process.argv[2] || process.env.GW_URL;
if (!BASE) { console.error('give the gateway URL as the first argument, or set $GW_URL'); process.exit(2); }
const PROJECT = process.env.MHD_PROJECT || process.env.PROJECT || 'Machine_HMI_Demo';
const PERSP = path.join(__dirname, '..', '..', 'project', 'com.inductiveautomation.perspective');
const SIZES = [[1366, 640], [1366, 768], [1600, 900], [1920, 1080]];

// Every popup a page can open, by the button that opens it. Popups only exist
// once clicked, so a sweep of the bare pages never sees them.
const POPUPS = [
  { route: '/cad', button: 'Upload / delete', id: 'cadModels', view: 'Machine/CadModels' },
  { route: '/cad', button: 'Simulate alarm', id: 'cadSim', view: 'Machine/CadSim' },
  // Shown only on a short window, where the panel itself is not on the page.
  { route: '/manual', button: 'THIS USER MAY', id: 'manualAccess', view: 'Machine/ManualAccess', short: true },
];

// The only scrollers allowed. `view` + `name` match the component's name path
// in view.json (a suffix), `cls` matches the element's class.
const ALLOWED = [
  { cls: /status-page-body/, why: "Ignition's own connection/status overlay, not project content" },
  { cls: /ia_table/, why: 'table body - a table scrolls its rows' },
  { view: 'Machine/Setup', name: 'Status/Body/RawBox', why: 'RAW REPLY: the full JSON reply, a text pane labelled "scrolls"' },
  { view: 'Machine/Setup', name: 'Presenter/Body', why: 'RUNNING ORDER: six-step list, scrolls only on a short window' },
  { view: 'Machine/Overview', name: 'Rail/Zones', why: 'eight zone start/stop cards, a list; scrolls only on a short window' },
  { view: 'Machine/Manual', name: 'Messages/Body', why: 'MESSAGES: list of up to 20 live alarm lines' },
  { view: 'Machine/Manual', name: 'Stations/Body', why: 'pallet stations and interlock list, scrolls only on a short window' },
  { view: 'Machine/ManualAccess', name: 'Body', why: 'popup copy of the permission list; fits, allowed as a list' },
];

const pageConfig = JSON.parse(fs.readFileSync(path.join(PERSP, 'page-config', 'config.json'), 'utf8')).pages;
const viewCache = {};
function viewJson(v) {
  if (!(v in viewCache)) {
    try { viewCache[v] = JSON.parse(fs.readFileSync(path.join(PERSP, 'views', v, 'view.json'), 'utf8')); }
    catch (e) { viewCache[v] = null; }
  }
  return viewCache[v];
}
// "C.0:1:2" / "PcadSim.0:1:2" -> "Body/Right/Stations" from the view's own names.
function nameOf(view, domPath) {
  const v = viewJson(view);
  const m = /^[^.]+\.0((?::\d+)*)$/.exec(domPath || '');
  if (!v || !m) return '';
  let node = v.root; const names = [];
  for (const i of m[1].split(':').filter(Boolean)) {
    node = (node.children || [])[+i];
    if (!node) return '';
    names.push(node.meta.name);
  }
  return names.join('/');
}

function scan(scope) {
  const root = scope ? document.querySelector(scope) : document;
  const out = [];
  if (!root) return out;
  for (const el of root.querySelectorAll('*')) {
    // A closed modal or a display:none panel draws no bar, whatever it measures.
    if (!el.checkVisibility({ visibilityProperty: true })) continue;
    if (!scope && el.closest('.popups-pane')) continue;
    const cs = getComputedStyle(el);
    const v = /(auto|scroll)/.test(cs.overflowY) && el.scrollHeight > el.clientHeight;
    const h = /(auto|scroll)/.test(cs.overflowX) && el.scrollWidth > el.clientWidth;
    if (!v && !h) continue;
    if (el.clientHeight === 0 && el.clientWidth === 0) continue;
    out.push({ axis: (v ? 'y' : '') + (h ? 'x' : ''),
      path: el.getAttribute('data-component-path') || '',
      comp: el.getAttribute('data-component') || el.tagName.toLowerCase(),
      cls: String(el.className && el.className.baseVal === undefined ? el.className : '').slice(0, 80),
      over: v ? el.scrollHeight - el.clientHeight : el.scrollWidth - el.clientWidth,
      txt: (el.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 40) });
  }
  return out;
}

async function settle(page) {
  const start = Date.now();
  while (Date.now() - start < 20000) {
    if (await page.evaluate(() => document.querySelectorAll('[data-component]').length) > 0) break;
    await page.waitForTimeout(500);
  }
  await page.waitForTimeout(2500);
  const body = await page.evaluate(() => document.body.innerText || '');
  if (/Trial Expired/i.test(body)) {
    console.error('scrollbar-sweep: the Perspective trial has expired - reset it and run again');
    process.exit(2);
  }
}

let bad = 0;
const allowedSeen = new Map();
function report(tag, view, found) {
  for (const x of found) {
    const name = nameOf(view, x.path);
    const ok = ALLOWED.find(a => a.cls ? a.cls.test(x.cls)
      : (a.view === view && name && (name === a.name || name.endsWith('/' + a.name))));
    if (ok) { allowedSeen.set(ok.why, (allowedSeen.get(ok.why) || 0) + 1); continue; }
    bad++;
    console.log(`${tag} ${x.axis} +${x.over}px ${name || x.comp} ${x.path} "${x.txt}"`);
  }
}

(async () => {
  const browser = await chromium.launch({ ignoreDefaultArgs: ['--hide-scrollbars'] });
  for (const [w, hgt] of SIZES) {
    const page = await browser.newPage({ viewport: { width: w, height: hgt } });
    for (const [route, cfg] of Object.entries(pageConfig)) {
      const url = `${BASE}/data/perspective/client/${PROJECT}${route === '/' ? '' : route}`;
      await page.goto(url, { waitUntil: 'networkidle' }).catch(() => {});
      await settle(page);
      for (const f of page.frames()) {
        let found = [];
        try { found = await f.evaluate(scan, null); } catch (e) { continue; }
        report(`${w}x${hgt} ${route}${f === page.mainFrame() ? '' : ' [frame]'}`, f === page.mainFrame() ? cfg.viewPath : '', found);
      }
      for (const pop of POPUPS.filter(p => p.route === route)) {
        const btn = page.getByRole('button', { name: pop.button, exact: true });
        if (!(await btn.isVisible().catch(() => false))) {
          // A short-window popup has no button on a tall window, by design.
          if (pop.short && hgt > 819) continue;
          bad++;
          console.log(`${w}x${hgt} ${route} popup "${pop.button}": button not found`);
          continue;
        }
        await btn.click();
        const opened = await page.waitForSelector(`#popup-${pop.id}`, { timeout: 8000 }).catch(() => null);
        if (!opened) {
          bad++;
          console.log(`${w}x${hgt} ${route} popup "${pop.button}": did not open`);
          continue;
        }
        await page.waitForTimeout(1500);
        report(`${w}x${hgt} ${route} popup:${pop.id}`, pop.view, await page.evaluate(scan, `#popup-${pop.id}`));
        await page.goto(url, { waitUntil: 'networkidle' }).catch(() => {});
        await settle(page);
      }
    }
    await page.close();
  }
  await browser.close();
  for (const [why, n] of allowedSeen) console.log(`allowed x${n}: ${why}`);
  console.log(bad ? `scrollbar-sweep: ${bad} stray scroll bar(s)` : 'scrollbar-sweep: none');
  process.exit(bad ? 1 : 0);
})();
