// Confirm dashboard widgets stack at 390 and stay side by side at 1440.
const path = require('path');
const { chromium } = require(path.resolve(__dirname, '../../../../apps/web/node_modules/@playwright/test'));

const BASE = 'http://127.0.0.1:3000';

function bodyFor(url, method) {
  const p = new URL(url).pathname.replace(/^\/api\/v1/, '');
  if (p === '/auth/me') {
    return { id: 1, email: 'audit@example.test', display_name: 'Audit Fixture', role: 'admin', tenant_id: 'default' };
  }
  if (p === '/dashboards') {
    return {
      items: [{
        id: 1, name: 'Channel', description: null, visibility: 'personal', shared_roles: [],
        widgets: [
          { id: 11, dashboard_id: 1, title: 'Sell-out units', visual: 'kpi', metric_key: 'sellout_units', grains: [], filters: {}, period_grain: null, layout_json: { x: 0, y: 0, w: 4, h: 4 }, saved_report_id: null, sort_order: 0 },
          { id: 12, dashboard_id: 1, title: 'Sell-out by week', visual: 'bar', metric_key: 'sellout_units', grains: ['week'], filters: {}, period_grain: 'week', layout_json: { x: 4, y: 0, w: 8, h: 8 }, saved_report_id: null, sort_order: 1 },
        ],
      }],
    };
  }
  if (p.startsWith('/semantics/catalog')) {
    return { version: 1, source_doc: 'fixture', metrics: [{ id: 'sellout_units', key: 'sellout_units', label: 'Sell-out units', status: 'implemented', formula: 'Units sold by distributors in the selected period', allowed_grains: [['week']] }], dimensions: [] };
  }
  if (p.startsWith('/query/execute') || (method === 'POST' && p.includes('query'))) {
    return { ok: true, status: 'ok', metric_key: 'sellout_units', grains: [], validation: { ok: true, message: '' }, invariants_applied: [], data_vintage: { as_of: '2026-10-05' }, value: 12840, rows: null, series: [{ bucket_key: 'W36', value: 2100 }, { bucket_key: 'W37', value: 2400 }, { bucket_key: 'W38', value: 1800 }, { bucket_key: 'W39', value: 3200 }, { bucket_key: 'W40', value: 3340 }], message: null, handler: 'fixture' };
  }
  return { items: [], count: 0, events: [], rows: [], tasks: [], signals: [], active_count: 0, data_unavailable: true };
}

(async () => {
  const browser = await chromium.launch();
  for (const width of [1440, 390]) {
    const ctx = await browser.newContext({ viewport: { width, height: width === 1440 ? 1100 : 844 }, colorScheme: 'light' });
    await ctx.addInitScript(() => {
      window.localStorage.setItem('cip-ui', JSON.stringify({ state: { density: 'comfortable', colorMode: 'light' }, version: 0 }));
      window.localStorage.setItem('cip.auth.token.v1', 'audit-mock-token');
    });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', (err) => errors.push(String(err)));
    await page.route('**/api/v1/**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(bodyFor(route.request().url(), route.request().method())) });
    });
    await page.goto(BASE + '/dashboards', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(1800);
    const boxes = await page.evaluate(() => {
      const cards = [...document.querySelectorAll('[data-testid^="dashboard-widget-"]')].filter((el) => /^dashboard-widget-\d+$/.test(el.getAttribute('data-testid') || ''));
      return cards.map((el) => {
        const r = el.getBoundingClientRect();
        return { id: el.getAttribute('data-testid'), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
      });
    });
    const ticks = (await page.locator('[data-testid="dashboard-widget-chart"] text').allTextContents().catch(() => [])).join('|');
    await page.screenshot({ path: path.join(__dirname, `stack-dashboards-${width}-light.png`), fullPage: false });
    console.log(errors.length ? 'CRASH' : 'UP', width, JSON.stringify(boxes), ticks, errors[0] || '');
    await ctx.close();
  }
  await browser.close();
})();
