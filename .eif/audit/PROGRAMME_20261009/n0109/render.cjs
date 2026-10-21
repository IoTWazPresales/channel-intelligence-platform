// N-0109 unit 1 render harness (audit evidence, not product source).
// Same approach as .eif/audit/PROGRAMME_20261008/reports/render.cjs: the local web is real, every
// /api/v1/** call is fulfilled in the browser from fixtures (no credentials, no cip reads/writes).
// Fixture shapes mirror apps/web/src/features/reports/reportFixtures.ts.
const path = require('path');
const { chromium } = require(path.resolve(__dirname, '../../../../apps/web/node_modules/@playwright/test'));

const BASE = 'http://127.0.0.1:3000';
const OUT = __dirname;

const catalog = {
  version: 2,
  source_doc: 'fixture',
  dimensions: [
    { id: 'period', label: 'Period' },
    { id: 'distributor', label: 'Distributor' },
    { id: 'product', label: 'Product' },
    { id: 'customer', label: 'Customer / account' },
    { id: 'bu', label: 'Business unit / product line' },
  ],
  metrics: [
    { id: 'A3-02', key: 'weeks_of_cover', label: 'Weeks of cover', status: 'implemented', owner_surface: 'channel-ops', formula: 'derived_stock / velocity', allowed_grains: [['distributor', 'product']] },
    { id: 'A3-01', key: 'channel_stock', label: 'Derived channel stock', status: 'implemented', owner_surface: 'channel-ops', formula: 'latest reported SOH - sell-out since snapshot', allowed_grains: [['distributor', 'product']] },
    { id: 'A3-04', key: 'sellout_units', label: 'Sell-out units', status: 'implemented', owner_surface: 'channel-ops', formula: 'Sum of distributor sell-out units', allowed_grains: [['distributor', 'product'], ['period'], ['period', 'distributor']], calendar_period: true },
    { id: 'A1-01', key: 'fill_rate', label: 'Fill rate', status: 'implemented', owner_surface: 'plan-vs-executed', formula: 'sum min(shipped, planned) / sum planned', allowed_grains: [['period'], ['bu', 'period']] },
    { id: 'A2-05', key: 'support_spend', label: 'Support spend by customer / BU / promo type', status: 'implemented', owner_surface: 'cpor-cases', formula: 'sum ttl_support_usd', allowed_grains: [['customer']] },
    { id: 'A2-03', key: 'claim_rate', label: 'Claim rate', status: 'do_not_build', owner_surface: 'none', formula: 'Non-computable', allowed_grains: [], refuse_all: true },
  ],
};

const distributors = [
  { id: 3, distributor_code: 'KZN-01', distributor_name: 'Kwazulu Channel Partners' },
  { id: 5, distributor_code: 'CTS-02', distributor_name: 'Coastal Tech Supply' },
  { id: 7, distributor_code: 'MER-03', distributor_name: 'Meridian Distribution' },
  { id: 9, distributor_code: 'HVW-04', distributor_name: 'Highveld Wholesale' },
];

// [distributor_id, product_id, channel_stock, weekly_velocity]
const PAIRS = [
  [3, 1040, 168, 420], [7, 1041, 336, 240], [5, 1042, 504, 420], [9, 1043, 1092, 420], [7, 1044, 2478, 420],
  [5, 1045, 1302, 420], [3, 1046, 2646, 420], [9, 1047, 3654, 420], [7, 1048, 0, 0], [3, 1049, 1848, 120],
];

const now = new Date();
const daysAgo = (d) => new Date(now.getTime() - d * 86400000).toISOString().slice(0, 10);
const hoursAgo = (h) => new Date(now.getTime() - h * 3600000).toISOString();

function weeksOfCover() {
  const rows = PAIRS.map(([d, p, stock, vel]) => {
    const woc = vel > 0 ? stock / vel : null;
    return { distributor_id: d, product_id: p, channel_stock: stock, weekly_velocity: vel, weeks_of_cover: woc, replenishment_flag: woc != null && woc > 0 && woc < 4, value: woc };
  });
  const ts = PAIRS.reduce((a, r) => a + r[2], 0);
  const tv = PAIRS.reduce((a, r) => a + r[3], 0);
  return {
    ok: true, status: 'ok', metric_id: 'A3-02', metric_key: 'weeks_of_cover', grains: ['distributor', 'product'], filters: {},
    validation: { ok: true, message: 'ok' },
    invariants_applied: ['latest_per_distributor_product_soh', 'never_sum_snapshot_history', 'pipeline_never_counts'],
    data_vintage: { as_of_utc: now.toISOString(), grain: 'distributor_x_product', pair_count: rows.length, replenishment_threshold_weeks: 4, woc_source: 'observations', missing_data_alert: false, cover_as_of_date: daysAgo(4) },
    value: ts / tv, rows, scorecard: { total_channel_stock: ts, total_weekly_velocity: tv, portfolio_weeks_of_cover: ts / tv }, cache: null, message: null, handler: 'a3_stock',
  };
}

const WEEKS = ['2026-W28', '2026-W29', '2026-W30', '2026-W31', '2026-W32', '2026-W33', '2026-W34', '2026-W35', '2026-W36', '2026-W37', '2026-W38', '2026-W39'];
const SELL = [11820, 12450, 12010, 13240, 12890, 14120, 13560, 12980, 14410, 15020, 14280, 15560];

function selloutByPeriod() {
  return {
    ok: true, status: 'ok', metric_id: 'A3-04', metric_key: 'sellout_units', grains: ['period'], filters: {},
    validation: { ok: true, message: 'ok' }, invariants_applied: ['calendar_period_grain_week_month_quarter', 'raw_units_not_velocity'],
    data_vintage: { period_grain: 'week', bucket_min: WEEKS[0], bucket_max: WEEKS[11], row_count: 12 },
    value: SELL.reduce((a, b) => a + b, 0), rows: WEEKS.map((w, i) => ({ bucket_key: w, value: SELL[i] })), scorecard: null, cache: null, message: null, handler: 'volume_series',
  };
}

function respond(url, method, postData) {
  const u = new URL(url);
  const p = u.pathname.replace(/^\/api\/v1/, '');
  if (p === '/auth/me') return { id: 1, email: 'audit@example.test', display_name: 'Audit Fixture', role: 'admin', tenant_id: 'default' };
  if (p === '/semantics/catalog') return catalog;
  if (p === '/saved-reports') return { items: [
    { id: 1, name: 'Weekly cover by distributor', description: null, visibility: 'published', shared_roles: [], metric_key: 'weeks_of_cover', grains: ['distributor', 'product'], filters: {}, visual: 'bar' },
    { id: 2, name: 'Sell-out trend', description: null, visibility: 'personal', shared_roles: [], metric_key: 'sellout_units', grains: ['period'], filters: {}, visual: 'line' },
  ], count: 2 };
  if (p === '/reports/schedules') return { items: [{ id: 11, saved_report_id: 1, name: 'Monday cover', cadence: 'weekly_monday_0700', enabled: true, last_run_at: null, next_run_at: null }], count: 1 };
  if (p === '/reports/inbox') return { items: [
    { id: 101, saved_report_id: 1, trigger: 'schedule', format: 'xlsx', status: 'delivered', subject: 'Weekly cover by distributor (weeks_of_cover)', missing_data_alert: false, created_at: hoursAgo(5) },
    { id: 102, saved_report_id: 2, trigger: 'manual', format: 'xlsx', status: 'delivered', subject: '[MISSING DATA] Sell-out trend (sellout_units)', missing_data_alert: true, created_at: hoursAgo(30) },
    { id: 103, saved_report_id: null, trigger: 'digest', format: 'html', status: 'delivered', subject: 'Shipping digest (shipping_digest)', missing_data_alert: false, created_at: hoursAgo(2) },
  ], count: 3 };
  if (p === '/dashboards' && method === 'GET') return { items: [{ id: 1, name: 'Weekly trading', widgets: [{ saved_report_id: 1 }, { saved_report_id: null }] }], count: 1 };
  if (p === '/sellout/filter-options') return { distributors, customers: [] };
  if (p === '/catalog/product-lines') return { product_lines: [], null_product_line_count: 0 };
  if (p === '/query/execute') {
    let b = {};
    try { b = JSON.parse(postData || '{}'); } catch (e) {}
    return b.metric === 'sellout_units' ? selloutByPeriod() : weeksOfCover();
  }
  return { items: [], count: 0, rows: [], tasks: [], active_count: 0, data_unavailable: true };
}

async function mockApi(page) {
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request();
    const body = respond(req.url(), req.method(), req.postData());
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
}

async function runReport(page, visual) {
  await page.getByTestId('report-run').click();
  await page.getByTestId('report-result').waitFor();
  await page.waitForTimeout(800);
  await page.getByTestId('report-visual-mode').getByRole('button', { name: visual, exact: true }).click();
  await page.waitForTimeout(1200);
}

async function trend(page) {
  if (await page.getByTestId('report-metric-sellout_units').isVisible().catch(() => false)) {
    await page.getByTestId('report-metric-sellout_units').click();
  } else {
    await page.getByTestId('report-metric-select').click();
    await page.getByRole('option', { name: 'Sell-out units' }).click();
  }
  await page.getByTestId('report-grain-select').click();
  await page.getByRole('option', { name: 'Period', exact: true }).click();
  await runReport(page, 'Trend');
}

async function shot(browser, mode, name, viewport, act) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, colorScheme: mode });
  await ctx.addInitScript(([m]) => {
    try {
      window.localStorage.setItem('cip-ui', JSON.stringify({ state: { density: 'comfortable', colorMode: m }, version: 0 }));
      window.localStorage.setItem('cip.auth.token.v1', 'audit-mock-token');
    } catch (e) {}
  }, [mode]);
  const page = await ctx.newPage();
  page.on('pageerror', (e) => console.log('PAGEERR', name, mode, String(e.stack || e).slice(0, 400)));
  await mockApi(page);
  try {
    await page.goto(BASE + '/reports', { waitUntil: 'networkidle', timeout: 45000 });
    await page.getByTestId('report-run').waitFor({ timeout: 20000 });
    await page.waitForTimeout(800);
    if (act) await act(page);
    const file = path.join(OUT, `${name}-${viewport.width}-${mode}.png`);
    await page.screenshot({ path: file, fullPage: true });
    if (process.env.ABOUT) {
      await page.getByRole('button', { name: 'About this figure' }).click();
      await page.waitForTimeout(400);
      await page.getByTestId('report-about').screenshot({ path: path.join(OUT, `${name}-about-${viewport.width}-${mode}.png`) });
    }
    console.log('OK', name, viewport.width, mode);
  } catch (e) {
    console.log('FAIL', name, viewport.width, mode, String(e).slice(0, 300));
  }
  await ctx.close();
}

(async () => {
  const which = process.argv[2] || 'all';
  const browser = await chromium.launch();
  const jobs = [
    ['reports-landing', null],
    ['reports-kpi', (p) => runReport(p, 'KPI')],
    ['reports-table', (p) => runReport(p, 'Table')],
    ['reports-bar', (p) => runReport(p, 'Bar')],
    ['reports-trend', trend],
  ].filter(([n]) => which === 'all' || n.includes(which));
  for (const width of [1440, 390]) {
    const viewport = width === 1440 ? { width: 1440, height: 900 } : { width: 390, height: 844 };
    for (const mode of ['light', 'dark']) {
      for (const [name, act] of jobs) await shot(browser, mode, name, viewport, act);
    }
  }
  await browser.close();
})();
