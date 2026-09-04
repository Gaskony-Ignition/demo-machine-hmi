// Contrast sweep over every page, as a gate rather than an opinion.
//
// Two things this gets right that a naive sweep does not, both learned the
// hard way on 04/09/2026:
//
//   * It COMPOSITES the whole ancestor stack. Reading the top background as
//     opaque turns rgba(255,255,255,0.06) over rgb(33,39,42) into white, and
//     reports a header chip at 1.71:1 that is really 7.4:1. The first run of
//     this found 13 failures; 10 of them were this bug.
//   * It exempts DISABLED controls. Looking dimmed is how a disabled button
//     says it is disabled. A tab with cursor:pointer and no disabled
//     attribute is not exempt, however quiet it looks.
//
// Usage:  node tools/verify/contrast_sweep.js <gateway-url> [--light] [--theme NAME]
// Run from the verify-view tool directory (that is where playwright lives).
//
//   --light        overrides the ten --neutral-* tokens with an APPROXIMATION
//                  of Ignition's light ramp. Kept unchanged so the numbers
//                  stay comparable with the 04/09/2026 baseline of 190-191.
//                  It is only an approximation: nothing else the theme
//                  defines moves, so --input stays black and the theme
//                  dropdown reads as a failure that a real light theme does
//                  not have.
//   --theme NAME   swaps the REAL theme stylesheet. Perspective serves it at
//                  /data/perspective/themes/<name>.css and links it in the
//                  head, so replacing that one href gives the genuine article
//                  - the real ramp, the real component styles, the real
//                  --success/--error - without a session or a designer. This
//                  is the honest measurement; --light is the historical one.
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'http://localhost:8088';
const LIGHT = process.argv.includes('--light');
const ti = process.argv.indexOf('--theme');
const THEME = ti > 0 ? process.argv[ti + 1] : null;
const PAGES = ['', 'cell3d', 'cell2d', 'manual', 'alarms', 'setup'];
// Ignition's light ramp is the dark one inverted.
const RAMP = {'--neutral-10':'#FAFAFA','--neutral-20':'#F0F0F0','--neutral-30':'#E4E4E4',
  '--neutral-40':'#D0D0D0','--neutral-50':'#B0B0B0','--neutral-60':'#8A8A8A',
  '--neutral-70':'#6A6A6A','--neutral-80':'#4A4A4A','--neutral-90':'#2A2A2A','--neutral-100':'#161616'};

const PROBE = `(() => {
  // A colour derived with relative colour syntax - rgb(from ...) - computes
  // to the color(srgb 0..1) form, not rgb(0..255). Reading its channels as
  // 0-255 turns every such colour into near-black and reports contrast that
  // is not there, so both forms are parsed rather than one.
  const P = s => {
    const c = /^color\\(\\s*srgb\\s+([-\\d.eE]+)\\s+([-\\d.eE]+)\\s+([-\\d.eE]+)(?:\\s*\\/\\s*([\\d.]+)(%?))?/.exec(s);
    if (c) return {r:+c[1]*255, g:+c[2]*255, b:+c[3]*255,
                   a: c[4]===undefined ? 1 : (+c[4] / (c[5] ? 100 : 1))};
    const m=(s.match(/[\\d.]+/g)||[]).map(Number);
    return {r:m[0]||0,g:m[1]||0,b:m[2]||0,a:m.length>3?m[3]:1}; };
  const L = c => { const f=[c.r,c.g,c.b].map(v=>{v/=255;
    return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4)});
    return .2126*f[0]+.7152*f[1]+.0722*f[2]; };
  const over = (f,b) => ({r:f.a*f.r+(1-f.a)*b.r, g:f.a*f.g+(1-f.a)*b.g,
                          b:f.a*f.b+(1-f.a)*b.b, a:1});
  function bgOf(el){
    const layers=[]; let e=el;
    while(e){ const c=P(getComputedStyle(e).backgroundColor);
      if(c.a>0) layers.push(c);
      if(c.a>=1) break;
      e=e.parentElement; }
    let base=(layers.length&&layers[layers.length-1].a>=1)?layers.pop():{r:255,g:255,b:255,a:1};
    for(let i=layers.length-1;i>=0;i--) base=over(layers[i],base);
    return base;
  }
  function exempt(el){
    let e=el;
    for(let i=0;i<3&&e;i++,e=e.parentElement){
      if(e.hasAttribute&&e.hasAttribute('disabled')) return true;
      if(e.getAttribute&&e.getAttribute('aria-disabled')==='true') return true;
      if(/--disable/.test((e.className||'').toString())) return true;
    }
    return false;
  }
  const out=[];
  for(const el of document.querySelectorAll('*')){
    if(el.children.length) continue;
    const t=(el.textContent||'').trim(); if(!t) continue;
    const cs=getComputedStyle(el);
    if(cs.visibility==='hidden'||cs.display==='none'||+cs.opacity===0) continue;
    const r=el.getBoundingClientRect(); if(!r.width||!r.height) continue;
    const bg=bgOf(el), fg=over(P(cs.color),bg);
    const l1=L(fg), l2=L(bg);
    const ratio=(Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05);
    const big=parseFloat(cs.fontSize)>=18.66||(parseFloat(cs.fontSize)>=14&&+cs.fontWeight>=700);
    out.push({t:t.slice(0,32), ratio:Math.round(ratio*100)/100, big, exempt:exempt(el),
      fg:'rgb('+[fg.r,fg.g,fg.b].map(Math.round).join(',')+')',
      bg:'rgb('+[bg.r,bg.g,bg.b].map(Math.round).join(',')+')'});
  }
  return out;
})()`;

(async () => {
  const b = await chromium.launch();
  let total = 0; const fails = [];
  for (const pg of PAGES) {
    const p = await b.newPage({ viewport: { width: 1366, height: 768 } });
    await p.goto(`${BASE}/data/perspective/client/Machine_HMI_Demo/${pg}`,
                 { waitUntil: 'networkidle', timeout: 60000 }).catch(() => {});
    await p.waitForTimeout(3200);
    if (THEME) {
      await p.evaluate(t => {
        const l = document.querySelector('link[href*="/data/perspective/themes/"]');
        if (l) l.href = l.href.replace(/themes\/[^/]+\.css/, 'themes/' + t + '.css');
      }, THEME);
      await p.waitForTimeout(1500);
    }
    if (LIGHT) await p.evaluate(R => { for (const [k, v] of Object.entries(R))
      document.documentElement.style.setProperty(k, v); }, RAMP);
    await p.waitForTimeout(900);
    const r = await p.evaluate(PROBE);
    total += r.length;
    for (const x of r) {
      // Gateway chrome, not ours.
      if (/Insecure Connection|Trial Mode|Remaining trial|Connected:/.test(x.t)) continue;
      if (x.exempt) continue;
      if (x.ratio < 3.0) fails.push({ pg: pg || '/', ...x });
    }
    await p.close();
  }
  await b.close();
  console.log(`ramp=${LIGHT ? 'light' : 'dark'}  theme=${THEME || 'session default'}` +
              `  texts=${total}  below 3.0 = ${fails.length}`);
  for (const f of fails.slice(0, 30)) console.log('  ', JSON.stringify(f));
  if (fails.length > 30) console.log(`   ... and ${fails.length - 30} more`);
  process.exit(fails.length ? 1 : 0);
})();
