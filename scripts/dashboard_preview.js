// Local stand-in for the dashboard runtime, to look at the page at phone and desktop widths.
// Usage: node render.js <page.html> <csv dir> <out dir> [theme]
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const [page, csvDir, outDir, theme = 'light'] = process.argv.slice(2);
fs.mkdirSync(outDir, { recursive: true });
const datasets = {};
for (const f of fs.readdirSync(csvDir)) if (f.endsWith('.csv')) datasets[f.replace('.csv', '')] = fs.readFileSync(path.join(csvDir, f), 'utf8');
const params = { players: +(process.env.PLAYERS || 4), rules: 'Official rules', opponents: 'Simple bots', deal: "Completes the buyer's set", price: 650, square: 24, property: 19, view: '3d', popp: 'Simple bots', pprice: 600 };

const tokens = `
:root { --font-anthropic-sans: system-ui, sans-serif; --font-anthropic-serif: Georgia, serif;
  --cds-font-size-caption: 12px; --cds-font-size-body: 14px; --cds-font-size-heading: 16px; --cds-font-size-title: 26px;
  --cds-font-weight-medium: 500; --cds-gap-xs: 4px; --cds-gap-sm: 8px; --cds-gap-md: 12px; --cds-gap-lg: 20px; --cds-gap-xl: 32px;
  --cds-pad-xs: 4px; --cds-pad-sm: 8px; --cds-pad-md: 12px; --cds-pad-lg: 16px; --cds-pad-xl: 24px; --cds-radius: 8px;
  --cds-dur-slow: 300ms; --cds-ease-out: ease-out; --cds-shadow-popover: 0 4px 16px rgba(0,0,0,.15);
  --color-fg: #1a1a18; --color-fg-muted: #6b6a66; --color-bg: #fafaf8; --color-panel: #ffffff; --color-border-line: #e3e2dc;
  --color-ok: #1b7f4b; --color-warn: #a86400; --color-bad: #c2362f; --cds-surface-popover: #fff; --cds-border: #ddd;
  --cds-text-secondary: #6b6a66; --cds-chart-grid: #ecebe6; --cds-chart-axis: #c9c8c0; --cds-chart-reference: #9b9a93;
  --cds-chart-muted: #b9b8b0; --cds-chart-status-critical: #d03b3b; }
:root[data-theme=dark] { --color-fg: #ecebe6; --color-fg-muted: #a3a29b; --color-bg: #1c1c1a; --color-panel: #262624; --color-border-line: #3a3936;
  --cds-surface-popover: #2e2e2b; --cds-border: #444; --cds-text-secondary: #a3a29b; --cds-chart-grid: #33322f; --cds-chart-axis: #55544f;
  --cds-chart-reference: #77766f; --cds-chart-muted: #5d5c57; --color-ok: #4cc38a; --color-bad: #f07167; }
body { margin: 0; background: var(--color-bg); color: var(--color-fg); font-family: var(--font-anthropic-sans); font-size: 14px; }
#dash-root { padding: 16px; } `;

const runtime = `
(() => {
  const raw = ${JSON.stringify(datasets)};
  const data = {};
  for (const [k, v] of Object.entries(raw)) { const rows = d3.csvParse(v); data[k] = { status: 'ok', data: rows, columns: rows.columns, meta: [] }; }
  let params = ${JSON.stringify(params)};
  const draws = {}, onDatas = [];
  const visible = (el) => !el.closest('[hidden]');
  const runAll = () => {
    onDatas.forEach((f) => { try { f(); } catch (e) { console.error('onData', e.stack); } });
    for (const [name, fn] of Object.entries(draws))
      document.querySelectorAll('[data-draw="' + name + '"]').forEach((el) => { if (visible(el)) { try { fn(el); } catch (e) { console.error('draw ' + name, e.stack); } } });
  };
  window.dash = {
    data: (id) => data[id] || { status: 'missing', data: [] },
    params: () => ({ ...params }),
    setParams: (p) => { params = { ...params, ...p }; runAll(); },
    resetParams: () => {}, setLink: () => {}, refresh: () => {},
    colors: ['#2a78d6', '#eb6834', '#1baf7a', '#6250d6', '#e87ba4', '#c79a1e', '#3fb6c6', '#8c8c8c'],
    draw: (name, fn) => { draws[name] = typeof fn === 'function' ? fn : (el) => fn.update(el, fn.mount(el)); },
    onData: (fn) => { onDatas.push(fn); },
    calc: () => {}, loader: () => {},
  };
  window.__runAll = runAll;
  let queued = false;
  const mo = new MutationObserver(() => { if (!queued) { queued = true; requestAnimationFrame(() => { queued = false; runAll(); }); } });
  window.__observePages = () => document.querySelectorAll('[data-page]').forEach((s) => mo.observe(s, { attributes: true, attributeFilter: ['hidden'] }));
  let w = innerWidth; addEventListener('resize', () => { if (innerWidth !== w) { w = innerWidth; runAll(); } });
})();`;

(async () => {
  const html = fs.readFileSync(page, 'utf8');
  const doc = `<!doctype html><html${theme === 'dark' ? ' data-theme="dark"' : ''}><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>${tokens}</style><script>${fs.readFileSync(path.join(__dirname, 'node_modules/d3/dist/d3.min.js'), 'utf8')}</script><script>${runtime}</script></head>
<body><div id="dash-root"></div><template id="page">${html}</template>
<script>
  const root = document.getElementById('dash-root');
  root.appendChild(document.getElementById('page').content.cloneNode(true));
  root.querySelectorAll('script').forEach((old) => { const s = document.createElement('script'); s.textContent = old.textContent; old.replaceWith(s); });
  window.__observePages();
  setTimeout(() => window.__runAll(), 50);
</script></body></html>`;
  fs.writeFileSync(path.join(outDir, 'harness.html'), doc);
  const browser = await chromium.launch();
  for (const [label, width, height] of [['phone', 390, 844], ['desktop', 1280, 900]]) {
    const p = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: label === 'phone' ? 2 : 1 });
    const errors = [];
    p.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
    p.on('pageerror', (e) => errors.push(e.message));
    await p.goto('file://' + path.join(outDir, 'harness.html'));
    await p.waitForTimeout(400);
    const tabs = process.env.TABS ? process.env.TABS.split(',') : await p.$$eval('[data-tab]', (bs) => bs.map((b) => b.dataset.tab));
    for (const tab of tabs) {
      await p.click(`[data-tab="${tab}"]`);
      await p.waitForTimeout(300);
      const overflow = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      await p.screenshot({ path: path.join(outDir, `${label}-${tab}.png`), fullPage: true });
      console.log(label, tab, 'horizontal overflow px:', overflow);
    }
    if (errors.length) console.log(label, 'ERRORS:\n' + [...new Set(errors)].join('\n'));
    await p.close();
  }
  await browser.close();
})();
