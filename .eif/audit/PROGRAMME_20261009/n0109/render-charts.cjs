// Rich fixture for the four N-0109 surfaces that still needed a chart on screen.
// Real web, mocked /api/v1. Not live cip data.
const path = require('path');
const { chromium } = require(path.resolve(__dirname, '../../../../apps/web/node_modules/@playwright/test'));

const BASE = 'http://127.0.0.1:3000';

const plan = {
  data_unavailable: false,
  period_range: { from: '26Q2', to: '26Q2' },
  drill: { customer_id: null, product_id: null, sales_model: null },
  product_group_by: 'description',
  default_period: '26Q2',
  available_periods: [
    { year: 2026, quarter: 2, label: '26Q2' },
    { year: 2026, quarter: 3, label: '26Q3' },
  ],
  scorecard: {
    fill_rate: 0.46,
    line_hit_rate: 0.35,
    planned_units: 100,
    shipped_units_in_plan: 62,
    shipped_units_total: 70,
    pipeline_units_in_plan: 8,
    short_exposure_units: 38,
    deal_stock_units: 10,
    unplanned_intake_units: 5,
    no_po_blind_spot: { line_count: 2, planned_units: 20, planned_value_plan: 1000 },
    pending_split: { inbound_pipeline_lines: 1, inbound_pipeline_units: 8, cold_lines: 3, cold_planned_units: 12 },
    value: {
      planned_value_plan: 5000,
      shipped_value_plan: 3000,
      shipped_value_cost: 2500,
      short_exposure_value_plan: 800,
      deal_stock_value_plan: 200,
      unplanned_intake_value_plan: 100,
      fx_partial: false,
    },
    flag_summary: { matched: 10, short: 5, over: 2 },
    buckets: { executed_vs_plan: 17, off_plan: 3, pending: 4 },
  },
  exceptions: {
    customer: { short_ships: [], over_ships: [], unplanned_intake: [], no_po_blind_spots: [] },
    product: { short_ships: [], over_ships: [], unplanned_intake: [], no_po_blind_spots: [] },
    bu: { short_ships: [], over_ships: [], unplanned_intake: [], no_po_blind_spots: [] },
  },
  trend: [
    { period_label: '25Q3', fill_rate: 0.4, line_hit_rate: 0.3 },
    { period_label: '25Q4', fill_rate: 0.52, line_hit_rate: 0.41 },
    { period_label: '26Q1', fill_rate: 0.48, line_hit_rate: 0.33 },
    { period_label: '26Q2', fill_rate: 0.46, line_hit_rate: 0.35 },
  ],
  drill_rows: [
    { customer_label: 'North', customer_id: 1, planned_units: 40, shipped_units: 22 },
    { customer_label: 'South', customer_id: 2, planned_units: 35, shipped_units: 30 },
    { customer_label: 'East', customer_id: 3, planned_units: 25, shipped_units: 10 },
  ],
  data_quality: { backlog_066_affected_periods: [], backlog_066_message: null },
  scope_notes: { out_of_scope: ['Sell-through — DSI.'] },
};

function respond(url, method) {
  const p = new URL(url).pathname.replace(/^\/api\/v1/, '');
  if (p === '/auth/me') {
    return { id: 1, email: 'audit@example.test', display_name: 'Audit Fixture', role: 'admin', tenant_id: 'default' };
  }
  if (p === '/dashboards' || p.startsWith('/dashboards/')) {
    return {
      items: [
        {
          id: 1,
          name: 'Channel',
          description: null,
          visibility: 'personal',
          shared_roles: [],
          widgets: [
            {
              id: 11,
              dashboard_id: 1,
              title: 'Sell-out units',
              visual: 'kpi',
              metric_key: 'sellout_units',
              grains: [],
              filters: {},
              period_grain: null,
              layout_json: { x: 0, y: 0, w: 4, h: 3 },
              saved_report_id: null,
              sort_order: 0,
            },
            {
              id: 12,
              dashboard_id: 1,
              title: 'Sell-out by week',
              visual: 'bar',
              metric_key: 'sellout_units',
              grains: ['week'],
              filters: {},
              period_grain: 'week',
              layout_json: { x: 4, y: 0, w: 8, h: 8 },
              saved_report_id: null,
              sort_order: 1,
            },
          ],
        },
      ],
    };
  }
  if (p.startsWith('/semantics/catalog')) {
    return {
      version: 1,
      source_doc: 'fixture',
      metrics: [
        {
          id: 'sellout_units',
          key: 'sellout_units',
          label: 'Sell-out units',
          status: 'implemented',
          formula: 'Units sold by distributors in the selected period',
          allowed_grains: [['week']],
        },
      ],
      dimensions: [],
    };
  }
  if (p.startsWith('/query/execute') || method === 'POST' && p.includes('query')) {
    return {
      ok: true,
      status: 'ok',
      metric_key: 'sellout_units',
      grains: [],
      period_grain: 'week',
      validation: { ok: true, message: '' },
      invariants_applied: [],
      data_vintage: { as_of: '2026-10-05' },
      value: 12840,
      rows: null,
      series: [
        { bucket_key: 'W36', value: 2100 },
        { bucket_key: 'W37', value: 2400 },
        { bucket_key: 'W38', value: 1800 },
        { bucket_key: 'W39', value: 3200 },
        { bucket_key: 'W40', value: 3340 },
      ],
      message: null,
      handler: 'fixture',
    };
  }
  if (p.startsWith('/shipping/commercial-summary')) {
    return {
      reference_date: '2026-10-10',
      week_start: '2026-10-05',
      week_end: '2026-10-11',
      total_lines: 10,
      pipeline_in_transit: { line_count: 4, quantity: 40, value_by_currency: [{ currency_code: 'USD', amount: 1200 }] },
      arriving_this_week: { total: 3, quantity: 12, line_count: 2, by_distributor: [{ label: 'North', count: 8 }, { label: 'South', count: 4 }] },
      delivered_this_week: { total: 5, quantity: 8, line_count: 5 },
      overdue: { count: 1, line_count: 1, quantity: 2, pct_of_total_lines: 0.1, pct_of_current_incoming: 0.25 },
      eta_shifts: { slipped_count: 2, improved_count: 1, net_direction: 'slipped' },
    };
  }
  if (p.startsWith('/shipping/eta-shifts')) {
    return { slipped_count: 2, improved_count: 1, net_direction: 'slipped', samples: [] };
  }
  if (p.startsWith('/channel-ops/summary')) {
    return {
      sell_out_this_quarter: { units: 12840, revenue: 240000, has_data: true, period_start: '2026-10-01', period_end: '2026-12-31' },
      sell_out_prior_year_quarter: { units: 11000, revenue: 200000 },
      sell_out_yoy_pct: 0.167,
      sell_out_data_vintage: { max_transaction_date: '2026-10-05', current_quarter_has_data: true, as_of_date: '2026-10-11' },
      total_inventory_units: 4200,
      weeks_of_cover: 3.2,
      replenishment_threshold_weeks: 4,
      replenishment_flag: true,
      replenishment_pairs_below_threshold: 6,
      replenishment_pair_count: 20,
      distributors_reporting: 4,
      distributors_expected: 5,
      active_customers_this_period: 18,
      active_customers_prior_period: 16,
      has_velocity_data: true,
      has_forecast_data: true,
      has_reconciliation_data: true,
    };
  }
  if (p.startsWith('/channel-ops/weekly-series')) {
    return {
      weeks: 8,
      points: [
        { week_start: '2026-08-17', units: 900 },
        { week_start: '2026-08-24', units: 1100 },
        { week_start: '2026-08-31', units: 800 },
        { week_start: '2026-09-07', units: 1400 },
        { week_start: '2026-09-14', units: 1250 },
        { week_start: '2026-09-21', units: 1600 },
        { week_start: '2026-09-28', units: 1500 },
        { week_start: '2026-10-05', units: 1700 },
      ],
    };
  }
  if (p.startsWith('/channel-ops/movement-lens')) {
    return {
      data_unavailable: false,
      headlines: {
        sell_out_week: 'W40',
        sell_out_units: 1700,
        sell_out_wow_pct: 13.3,
        shipped_week: 'W40',
        shipped_units: 900,
        soh: 4200,
        families_growing: 2,
        families_total: 4,
      },
      sell_out_weekly: [
        { week: 'W37', week_start: '2026-09-07', sellOut: 1400 },
        { week: 'W38', week_start: '2026-09-14', sellOut: 1250 },
        { week: 'W39', week_start: '2026-09-21', sellOut: 1600 },
        { week: 'W40', week_start: '2026-09-28', sellOut: 1700 },
      ],
      family_week: [
        { family: 'North', units: 800, wow: 0.1 },
        { family: 'South', units: 500, wow: -0.05 },
        { family: 'East', units: 400, wow: 0.2 },
      ],
      sell_out_through: '2026-10-05',
      shipped_through: '2026-10-05',
    };
  }
  if (p.startsWith('/plan-vs-executed')) return plan;
  return { items: [], count: 0, events: [], rows: [], tasks: [], signals: [], active_count: 0, data_unavailable: true };
}

const PAGES = [
  ['dashboards', '/dashboards', 'Sell-out units'],
  ['shipping', '/supply/shipments', 'Arriving this week'],
  ['movement', '/stock?lens=movement', 'Sell-out by week'],
  ['execution', '/stock?lens=execution', 'Fill rate'],
];

(async () => {
  const browser = await chromium.launch();
  for (const width of [1440, 390]) {
  for (const mode of ['light', 'dark']) {
    const ctx = await browser.newContext({
      viewport: width === 1440 ? { width: 1440, height: 1100 } : { width: 390, height: 844 },
      colorScheme: mode,
      deviceScaleFactor: 1,
    });
    await ctx.addInitScript(([m]) => {
      try {
        window.localStorage.setItem('cip-ui', JSON.stringify({ state: { density: 'comfortable', colorMode: m }, version: 0 }));
        window.localStorage.setItem('cip.auth.token.v1', 'audit-mock-token');
        window.localStorage.setItem('cip_intel_depth', 'operational');
      } catch (e) {}
    }, [mode]);
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', (err) => errors.push(String(err)));
    await page.route('**/api/v1/**', async (route) => {
      const body = respond(route.request().url(), route.request().method());
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });
    for (const [name, href, needle] of PAGES) {
      errors.length = 0;
      await page.goto(BASE + href, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.waitForTimeout(1800);
      const text = await page.locator('body').innerText();
      const hit = text.toLowerCase().includes(needle.toLowerCase());
      const crash = text.includes('client-side exception') || text.includes('Application error');
      await page.screenshot({ path: path.join(__dirname, `charts-${name}-${width}-${mode}.png`), fullPage: false });
      let ticks = '';
      if (name === 'dashboards') {
        ticks = (await page.locator('[data-testid="dashboard-widget-chart"] text').allTextContents().catch(() => [])).join('|');
      }
      console.log(crash || errors.length ? 'CRASH' : hit ? 'UP' : 'MISS', name, width, mode, 'errs=' + errors.length, ticks, errors[0] ? errors[0].slice(0, 160) : '');
    }
    await ctx.close();
  }
  }
  await browser.close();
})();
