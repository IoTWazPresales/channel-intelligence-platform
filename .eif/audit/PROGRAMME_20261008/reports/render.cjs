// Audit render harness (EIF Audit Mode, not product source).
// Renders design-lab and production report surfaces at 1440x900 in light and dark.
// Signed-in surfaces use the repo's own e2e pattern: page.route mocks for /api/v1/** (no credentials used).
const path = require('path');
const { chromium } = require(path.resolve(__dirname, '../../../../apps/web/node_modules/@playwright/test'));

const BASE = 'http://127.0.0.1:3000';
const OUT = __dirname;

const catalog = {
  version: 1,
  source_doc: 'audit-fixture',
  metrics: [
    { id: 'M1', key: 'weeks_of_cover', label: 'Weeks of cover', status: 'implemented', formula: 'soh / avg_weekly_sell_out', allowed_grains: [['distributor', 'product'], ['distributor']] },
    { id: 'M2', key: 'sellout_units', label: 'Sell-out units', status: 'implemented', formula: 'sum(units)', allowed_grains: [['period'], ['distributor', 'period'], ['distributor']], calendar_period: true },
    { id: 'M3', key: 'fill_rate', label: 'Fill rate', status: 'implemented', formula: 'shipped_in_plan / planned', allowed_grains: [['customer'], ['period']] },
  ],
  dimensions: [{ id: 'distributor', label: 'Distributor' }, { id: 'product', label: 'Product' }, { id: 'period', label: 'Period' }],
};

const weeks = ['2026-W28', '2026-W29', '2026-W30', '2026-W31', '2026-W32', '2026-W33', '2026-W34', '2026-W35', '2026-W36', '2026-W37', '2026-W38', '2026-W39'];
const sell = [11820, 12450, 12010, 13240, 12890, 14120, 13560, 12980, 14410, 15020, 14280, 15560];

function queryResult(body) {
  const metric = body.metric || 'weeks_of_cover';
  const grains = body.grains || [];
  const base = { ok: true, status: 'ok', metric_id: 'M', metric_key: metric, grains, filters: {}, validation: { ok: true, message: 'ok' }, invariants_applied: ['tenant_scope', 'latest_snapshot'], cache: null, message: null, handler: 'audit', scorecard: null, series: null };
  if (metric === 'sellout_units' && (body.period_grain || grains.includes('period'))) {
    return { ...base, value: sell.reduce((a, b) => a + b, 0), data_vintage: { period_grain: 'week', bucket_min: weeks[0], bucket_max: weeks[11], row_count: 12 }, series: weeks.map((w, i) => ({ bucket_key: w, value: sell[i] })), rows: weeks.map((w, i) => ({ bucket_key: w, value: sell[i] })) };
  }
  if (metric === 'sellout_units') {
    const rows = [3, 5, 7, 9, 11].map((d, i) => ({ distributor_id: d, value: [48210, 36120, 22980, 14550, 6230][i] }));
    return { ...base, value: 128090, data_vintage: { row_count: rows.length }, rows };
  }
  if (metric === 'fill_rate') {
    const rows = [101, 102, 103, 104].map((c, i) => ({ customer_id: c, value: [0.92, 0.81, 0.67, 0.99][i] }));
    return { ...base, value: 0.86, data_vintage: { row_count: 4 }, rows };
  }
  // weeks_of_cover by distributor x product: realistic cover values, several <= 1.5 weeks
  const rows = [];
  const vals = [0.8, 1.2, 1.4, 2.6, 3.1, 4.4, 5.9, 6.3, 8.7, 11.2, 0.4, 1.0, 7.5, 9.9];
  vals.forEach((v, i) => rows.push({ distributor_id: [3, 5, 7][i % 3], product_id: 1040 + i, value: v, soh_units: Math.round(v * 420), avg_weekly_units: 420 }));
  return { ...base, value: 4.37, data_vintage: { as_of: '2026-10-05', row_count: rows.length }, rows };
}

const dashboards = {
  items: [
    {
      id: 1, name: 'Weekly trading', description: null, visibility: 'personal', shared_roles: [],
      widgets: [
        { id: 11, dashboard_id: 1, title: 'Weeks of cover (network)', visual: 'kpi', metric_key: 'weeks_of_cover', grains: ['distributor'], filters: {}, period_grain: null, layout_json: { x: 0, y: 0, w: 3, h: 3 }, saved_report_id: null, sort_order: 0 },
        { id: 12, dashboard_id: 1, title: 'Fill rate', visual: 'kpi', metric_key: 'fill_rate', grains: ['customer'], filters: {}, period_grain: null, layout_json: { x: 3, y: 0, w: 3, h: 3 }, saved_report_id: null, sort_order: 1 },
        { id: 13, dashboard_id: 1, title: 'Sell-out by distributor', visual: 'bar', metric_key: 'sellout_units', grains: ['distributor'], filters: {}, period_grain: null, layout_json: { x: 6, y: 0, w: 6, h: 5 }, saved_report_id: null, sort_order: 2 },
        { id: 14, dashboard_id: 1, title: 'Sell-out trend', visual: 'line', metric_key: 'sellout_units', grains: ['period'], filters: {}, period_grain: 'week', layout_json: { x: 0, y: 3, w: 6, h: 5 }, saved_report_id: null, sort_order: 3 },
        { id: 15, dashboard_id: 1, title: 'Cover by distributor x product', visual: 'table', metric_key: 'weeks_of_cover', grains: ['distributor', 'product'], filters: {}, period_grain: null, layout_json: { x: 6, y: 5, w: 6, h: 6 }, saved_report_id: null, sort_order: 4 },
      ],
    },
  ],
};

const movement = {
  headlines: { sell_out_week: '2026-W39', sell_out_units: 15560, sell_out_wow_pct: 8.96, shipped_week: '2026-W39', shipped_units: 13120, soh: 412880, families_growing: 7, families_total: 12 },
  sell_out_weekly: weeks.map((w, i) => ({ week: w, week_start: w, sellOut: sell[i] })),
  family_week: [['Refrigeration', 4210, 6.1], ['Laundry', 3380, -2.4], ['Cooking', 2950, 11.2], ['Dishwashing', 1840, 3.3], ['Small appliances', 1610, -7.8], ['Air care', 1570, 0.4]].map(([family, units, wow]) => ({ family, units, wow })),
  sell_out_through: '2026-09-27', shipped_through: '2026-09-27',
};

const summary = {
  sell_out_this_quarter: { units: 168200, revenue: 98120400, has_data: true }, sell_out_prior_year_quarter: { units: 151900, revenue: 88210300 }, sell_out_yoy_pct: 0.107,
  total_inventory_units: 412880, weeks_of_cover: 5.4, replenishment_threshold_weeks: 4, replenishment_flag: true, replenishment_pairs_below_threshold: 38, replenishment_pair_count: 220,
  distributors_reporting: 4, distributors_expected: 5, active_customers_this_period: 64, active_customers_prior_period: 59, has_velocity_data: true, has_forecast_data: false, has_reconciliation_data: true,
};

const brief = {
  as_of: '2026-10-08T06:00:00Z', read: 'Cover is tightening at two distributors; funding claims ageing past 60 days.', signal_count: 4,
  signals: [
    { id: 's1', rank: 1, severity: 'stop', title: 'Cover below 2 weeks', detail: '14 distributor x product pairs', meta: '14 pairs', meta_hot: true, action_label: 'Open cover', action_href: '/stock?lens=cover', suggested: true },
    { id: 's2', rank: 2, severity: 'warn', title: 'Funding claims ageing', detail: 'R 1.2m outstanding > 60 days', meta: '60d+', meta_hot: false, action_label: 'Case book', action_href: '/promotions' },
    { id: 's3', rank: 3, severity: 'warn', title: 'Shipments overdue', detail: '9 lines past promise date', meta: '9 lines', meta_hot: false, action_label: 'Shipments', action_href: '/supply/shipments' },
    { id: 's4', rank: 4, severity: 'ok', title: 'Imports fresh', detail: 'All templates within 24h', meta: '6h', meta_hot: false, action_label: 'Imports', action_href: '/admin/imports' },
  ],
};

function respond(url, method, postData) {
  const p = new URL(url).pathname.replace(/^\/api\/v1/, '');
  if (p === '/auth/me') return { id: 1, email: 'audit@example.test', display_name: 'Audit Fixture', role: 'admin', tenant_id: 'default' };
  if (p === '/semantics/catalog') return catalog;
  if (p === '/saved-reports') return { items: [ { id: 1, name: 'Weekly cover by distributor', description: null, visibility: 'published', shared_roles: [], metric_key: 'weeks_of_cover', grains: ['distributor'], filters: {}, visual: 'bar' }, { id: 2, name: 'Sell-out trend', description: null, visibility: 'personal', shared_roles: [], metric_key: 'sellout_units', grains: ['period'], filters: {}, visual: 'table' } ], count: 2 };
  if (p === '/query/execute') { let b = {}; try { b = JSON.parse(postData || '{}'); } catch (e) {} return queryResult(b); }
  if (p === '/dashboards' && method === 'GET') return dashboards;
  if (p === '/brief/signals') return brief;
  if (p === '/channel-ops/movement-lens') return movement;
  if (p === '/channel-ops/summary') return summary;
  if (p === '/channel-ops/weekly-series') return { weeks: 12, points: weeks.map((w, i) => ({ week_start: w, units: sell[i] })) };
  if (p === '/channel-ops/cover-distribution') return { buckets: { lt2: 14, '2to4': 24, '4to8': 96, gt8: 86 }, pair_count: 220, under_4w: 38, mean_woc: 5.4, cover_as_of_date: '2026-10-05' };
  return { items: [], count: 0, rows: [], tasks: [], active_count: 0, data_unavailable: true };
}

async function mockApi(page) {
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request();
    const body = respond(req.url(), req.method(), req.postData());
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
}

async function shot(browser, mode, route, name, opts = {}) {
  const ctx = await browser.newContext({ viewport: opts.viewport || { width: 1440, height: 900 }, deviceScaleFactor: 1, colorScheme: mode });
  await ctx.addInitScript(([m, auth]) => {
    try {
      window.localStorage.setItem('cip-ui', JSON.stringify({ state: { density: 'comfortable', colorMode: m }, version: 0 }));
      if (auth) window.localStorage.setItem('cip.auth.token.v1', 'audit-mock-token');
    } catch (e) {}
  }, [mode, !!opts.mock]);
  const page = await ctx.newPage();
  page.on('pageerror', (e) => console.log('PAGEERR', name, mode, String(e.stack || e).slice(0, 600)));
  page.on('request', (r) => { if (r.url().includes('/api/v1/') && process.env.LOGREQ) console.log('REQ', r.method(), r.url()); });
  if (opts.mock) await mockApi(page);
  try {
    await page.goto(opts.url || BASE + route, { waitUntil: 'networkidle', timeout: 45000 });
    await page.waitForTimeout(1500);
    if (opts.act) await opts.act(page);
    const file = path.join(OUT, `${name}-${mode}.png`);
    await page.screenshot({ path: file, fullPage: !!opts.full });
    console.log('OK', name, mode, page.url());
  } catch (e) {
    console.log('FAIL', name, mode, String(e).slice(0, 300));
  }
  await ctx.close();
}

async function runReport(page, visual) {
  await page.getByTestId('report-visual-mode').getByRole('button', { name: visual }).click();
  await page.getByTestId('report-run').click();
  await page.waitForTimeout(2000);
  const el = page.getByTestId('report-result');
  await el.scrollIntoViewIfNeeded().catch(() => {});
}

(async () => {
  const which = process.argv[2] || 'all';
  const browser = await chromium.launch();
  const jobs = [];
  if (which === 'all' || which === 'lab') {
    jobs.push(['/design-lab/reports', 'lab-reports', { full: true }]);
    jobs.push(['/design-lab', 'lab-overview', { full: false }]);
    jobs.push(['/design-lab/stock', 'lab-stock', { full: false }]);
    jobs.push(['/design-lab/funding', 'lab-funding', { full: false }]);
  }
  if (which === 'dash') { jobs.push(['/dashboards', 'prod-dashboards-settled', { mock: true, full: false, act: (p) => p.waitForTimeout(8000) }]); }
  if (which === 'mockup') {
    const u = 'file:///' + path.join(OUT, 'mockup-report-system.html').replace(/\\/g, '/');
    jobs.push(['', 'mockup-report-system', { url: u, full: true }]);
    jobs.push(['', 'mockup-report-system-390', { url: u, full: true, viewport: { width: 390, height: 844 } }]);
  }
  if (which === 'probe') { jobs.push(['/reports', 'prod-reports-landing', { mock: true, full: false }]); }
  if (which === 'all' || which === 'prod') {
    jobs.push(['/reports', 'prod-reports-kpi', { mock: true, full: true, act: (p) => runReport(p, 'KPI') }]);
    jobs.push(['/reports', 'prod-reports-table', { mock: true, full: true, act: (p) => runReport(p, 'Table') }]);
    jobs.push(['/reports', 'prod-reports-bar', { mock: true, full: true, act: (p) => runReport(p, 'Bar') }]);
    jobs.push(['/dashboards', 'prod-dashboards', { mock: true, full: true }]);
    jobs.push(['/brief', 'prod-brief', { mock: true, full: false }]);
    jobs.push(['/stock?lens=movement', 'prod-stock-movement', { mock: true, full: true }]);
  }
  for (const mode of ['dark', 'light']) {
    for (const [route, name, opts] of jobs) await shot(browser, mode, route, name, opts);
  }
  await browser.close();
})();
