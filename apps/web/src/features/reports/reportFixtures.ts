/**
 * Test fixtures shaped exactly like the governed API responses (N-0109). The weeks-of-cover run
 * mirrors apps/api/app/query/handlers/a3_stock.py `_payload_from_stock_vel`: per-pair
 * channel_stock / weekly_velocity / weeks_of_cover / replenishment_flag, `value` = the metric, and
 * the top-level `value` = Σ stock ÷ Σ velocity. No real customer data.
 */
import type { CatalogResponse, QueryResult } from './reportPresentation';

export const fixtureCatalog: CatalogResponse = {
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
    { id: 'A3-01', key: 'channel_stock', label: 'Derived channel stock', status: 'implemented', owner_surface: 'channel-ops', formula: 'latest reported SOH − sell-out since snapshot', allowed_grains: [['distributor', 'product']] },
    { id: 'A3-04', key: 'sellout_units', label: 'Sell-out units', status: 'implemented', owner_surface: 'channel-ops', formula: 'Sum of distributor sell-out units', allowed_grains: [['distributor', 'product'], ['period'], ['period', 'distributor']], calendar_period: true },
    { id: 'A1-01', key: 'fill_rate', label: 'Fill rate', status: 'implemented', owner_surface: 'plan-vs-executed', formula: 'Σ min(shipped, planned) / Σ planned', allowed_grains: [['period'], ['bu', 'period']] },
    { id: 'A2-05', key: 'support_spend', label: 'Support spend by customer / BU / promo type', status: 'implemented', owner_surface: 'cpor-cases', formula: 'Σ ttl_support_usd', allowed_grains: [['customer']] },
    { id: 'A2-03', key: 'claim_rate', label: 'Claim rate', status: 'do_not_build', owner_surface: 'none', formula: 'Non-computable', allowed_grains: [], refuse_all: true },
  ],
};

export const fixtureDistributors = [
  { id: 3, distributor_code: 'KZN-01', distributor_name: 'Kwazulu Channel Partners' },
  { id: 5, distributor_code: 'CTS-02', distributor_name: 'Coastal Tech Supply' },
  { id: 7, distributor_code: 'MER-03', distributor_name: 'Meridian Distribution' },
  { id: 9, distributor_code: 'HVW-04', distributor_name: 'Highveld Wholesale' },
];

/** [distributor_id, product_id, channel_stock, weekly_velocity] */
const PAIRS: [number, number, number, number][] = [
  [3, 1040, 168, 420],
  [7, 1041, 336, 240],
  [5, 1042, 504, 420],
  [9, 1043, 1092, 420],
  [7, 1044, 2478, 420],
  [5, 1045, 1302, 420],
  [3, 1046, 2646, 420],
  [9, 1047, 3654, 420],
  [7, 1048, 0, 0],
  [3, 1049, 1848, 120],
];

function isoDaysAgo(days: number, now: Date = new Date()): string {
  return new Date(now.getTime() - days * 86_400_000).toISOString().slice(0, 10);
}

export function fixtureWeeksOfCover(now: Date = new Date()): QueryResult {
  const rows = PAIRS.map(([d, p, stock, vel]) => {
    const woc = vel > 0 ? stock / vel : null;
    return {
      distributor_id: d,
      product_id: p,
      channel_stock: stock,
      weekly_velocity: vel,
      weeks_of_cover: woc,
      replenishment_flag: woc != null && woc > 0 && woc < 4,
      value: woc,
    };
  });
  const totalStock = PAIRS.reduce((a, r) => a + r[2], 0);
  const totalVel = PAIRS.reduce((a, r) => a + r[3], 0);
  return {
    ok: true,
    status: 'ok',
    metric_id: 'A3-02',
    metric_key: 'weeks_of_cover',
    grains: ['distributor', 'product'],
    filters: {},
    validation: { ok: true, message: 'ok' },
    invariants_applied: ['latest_per_distributor_product_soh', 'never_sum_snapshot_history', 'pipeline_never_counts'],
    data_vintage: {
      as_of_utc: new Date(now.getTime()).toISOString(),
      grain: 'distributor_x_product',
      pair_count: rows.length,
      replenishment_threshold_weeks: 4,
      woc_source: 'observations',
      missing_data_alert: false,
      cover_as_of_date: isoDaysAgo(4, now),
    },
    value: totalStock / totalVel,
    rows,
    scorecard: { total_channel_stock: totalStock, total_weekly_velocity: totalVel, portfolio_weeks_of_cover: totalStock / totalVel },
    cache: null,
    message: null,
    handler: 'a3_stock',
  };
}

export const SELL_WEEKS = ['2026-W28', '2026-W29', '2026-W30', '2026-W31', '2026-W32', '2026-W33', '2026-W34', '2026-W35', '2026-W36', '2026-W37', '2026-W38', '2026-W39'];
export const SELL_UNITS = [11820, 12450, 12010, 13240, 12890, 14120, 13560, 12980, 14410, 15020, 14280, 15560];

export function fixtureSelloutByPeriod(): QueryResult {
  return {
    ok: true,
    status: 'ok',
    metric_id: 'A3-04',
    metric_key: 'sellout_units',
    grains: ['period'],
    filters: { period_from: '26Q3', period_to: '26Q3' },
    validation: { ok: true, message: 'ok' },
    invariants_applied: ['calendar_period_grain_week_month_quarter', 'raw_units_not_velocity'],
    data_vintage: { period_grain: 'week', bucket_min: SELL_WEEKS[0], bucket_max: SELL_WEEKS[11], row_count: 12 },
    value: SELL_UNITS.reduce((a, b) => a + b, 0),
    rows: SELL_WEEKS.map((w, i) => ({ bucket_key: w, value: SELL_UNITS[i] })),
    scorecard: null,
    cache: null,
    message: null,
    handler: 'volume_series',
  };
}

export function fixtureSavedReports() {
  return {
    items: [
      { id: 1, name: 'Weekly cover by distributor', description: null, visibility: 'published', shared_roles: [], metric_key: 'weeks_of_cover', grains: ['distributor', 'product'], filters: {}, visual: 'bar' },
      { id: 2, name: 'Sell-out trend', description: null, visibility: 'personal', shared_roles: [], metric_key: 'sellout_units', grains: ['period'], filters: {}, visual: 'line' },
    ],
    count: 2,
  };
}

export function fixtureSchedules() {
  return {
    items: [{ id: 11, saved_report_id: 1, name: 'Monday cover', cadence: 'weekly_monday_0700', enabled: true, last_run_at: null, next_run_at: null }],
    count: 1,
  };
}

export function fixtureInbox(now: Date = new Date()) {
  const at = (h: number) => new Date(now.getTime() - h * 3_600_000).toISOString();
  return {
    items: [
      { id: 101, saved_report_id: 1, trigger: 'schedule', format: 'xlsx', status: 'delivered', subject: 'Weekly cover by distributor (weeks_of_cover)', missing_data_alert: false, created_at: at(5) },
      { id: 102, saved_report_id: 2, trigger: 'manual', format: 'xlsx', status: 'delivered', subject: '[MISSING DATA] Sell-out trend (sellout_units)', missing_data_alert: true, created_at: at(30) },
      { id: 103, saved_report_id: null, trigger: 'digest', format: 'html', status: 'delivered', subject: 'Shipping digest (shipping_digest)', missing_data_alert: false, created_at: at(2) },
    ],
    count: 3,
  };
}

export function fixtureDashboards() {
  return { items: [{ id: 1, name: 'Weekly trading', widgets: [{ saved_report_id: 1 }, { saved_report_id: null }] }], count: 1 };
}
