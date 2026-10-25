/**
 * Dashboard builder fixtures (N-0116). Recorded-shape answers of `GET /semantics/v2/catalog` and
 * `POST /query/v2/execute`, so the real builder components render with no network. Deterministic: no
 * randomness and no clock (the dashboard window is a fixed custom range). Every name is fictional;
 * every number is fixture data and only its presentation is under test.
 */

import type { Dashboard, DashboardWidget, WidgetVisual } from '@/features/dashboards/types';
import starterSnapshots from './builderStarters.json';
import type {
  CatalogV2,
  DashboardFilters,
  DashboardTemplate,
  DefinitionV2,
  V2Column,
  V2Measure,
  V2Request,
  V2Response,
  V2Row,
} from '@/features/dashboards/builder/types';

/* ------------------------------------------------------------------------------------------------
 * Catalog
 * ---------------------------------------------------------------------------------------------- */

const ALL_GRAINS = ['week', 'month', 'quarter', 'year'];

const DSI_BD = ['period', 'customer', 'distributor', 'product', 'bu', 'channel', 'region'];
const CST_BD = ['period', 'customer', 'product', 'bu', 'channel', 'region', 'site_label'];
const CPOR_BD = ['period', 'case', 'customer', 'distributor', 'product', 'bu', 'promo_type', 'status', 'workflow_status'];

const W_CST_NO_DISTRIBUTOR = 'Customer sell-through reports do not say which distributor supplied the stock.';
const W_SITE_CST_ONLY = 'Store / site comes only from customer sell-through reports. Distributor sell-out has no store.';

function base(
  id: string,
  label: string,
  unit: string,
  model: string,
  additivity: V2Measure['additivity'],
  breakdowns: string[],
  extra: Partial<V2Measure> = {},
): V2Measure {
  return {
    id,
    label,
    unit,
    model,
    kind: 'base',
    additivity,
    breakdowns,
    period_grains: breakdowns.includes('period') ? ALL_GRAINS : [],
    requires: [],
    legacy_key: null,
    ...extra,
  };
}

export const builderCatalog: CatalogV2 = {
  version: 'fixture-1',
  model_version: 1,
  groups: ['Time', 'Product', 'Customer', 'Distributor', 'Store', 'Promotion'],
  breakdowns: [
    { id: 'period', label: 'Period', group: 'Time', kind: 'period', grains: ALL_GRAINS },
    { id: 'customer', label: 'Customer', group: 'Customer', kind: 'entity' },
    { id: 'channel', label: 'Channel (current)', group: 'Customer', kind: 'attribute', of: 'customer' },
    { id: 'region', label: 'Region (current)', group: 'Customer', kind: 'attribute', of: 'customer' },
    { id: 'distributor', label: 'Distributor', group: 'Distributor', kind: 'entity' },
    { id: 'product', label: 'Product', group: 'Product', kind: 'entity' },
    { id: 'bu', label: 'Business unit (product line)', group: 'Product', kind: 'attribute', of: 'product' },
    { id: 'site_label', label: 'Store / site', group: 'Store', kind: 'local', models: ['cst_sellthrough'] },
    { id: 'case', label: 'Case', group: 'Promotion', kind: 'local', models: ['cpor'] },
    { id: 'promo_type', label: 'Promotion type', group: 'Promotion', kind: 'local', models: ['cpor'] },
    { id: 'status', label: 'Case status', group: 'Promotion', kind: 'local', models: ['cpor'] },
    { id: 'workflow_status', label: 'Case approval status', group: 'Promotion', kind: 'local', models: ['cpor'] },
  ],
  models: [
    {
      id: 'dsi_sellout',
      label: 'Distributor sell-out (DSI)',
      customer_role: 'dealer',
      breakdowns: DSI_BD,
      filter_refusals: {
        site_label: W_SITE_CST_ONLY,
        promo_type: 'Promotion type is not a breakdown of Distributor sell-out (DSI).',
        status: 'Case status is not a breakdown of Distributor sell-out (DSI).',
        workflow_status: 'Case approval status is not a breakdown of Distributor sell-out (DSI).',
      },
    },
    {
      id: 'cst_sellthrough',
      label: 'Customer sell-through (CST)',
      customer_role: 'retailer',
      breakdowns: CST_BD,
      filter_refusals: {
        distributor: W_CST_NO_DISTRIBUTOR,
        promo_type: 'Promotion type is not a breakdown of Customer sell-through (CST).',
        status: 'Case status is not a breakdown of Customer sell-through (CST).',
        workflow_status: 'Case approval status is not a breakdown of Customer sell-through (CST).',
      },
    },
    {
      id: 'cpor',
      label: 'CPOR promotion lines',
      customer_role: 'account',
      breakdowns: CPOR_BD,
      filter_refusals: { site_label: W_SITE_CST_ONLY },
    },
  ],
  measures: [
    base('dsi_sellout.units', 'Sell-out units', 'units', 'dsi_sellout', 'additive', DSI_BD, { legacy_key: 'sellout_units' }),
    base('dsi_sellout.lines', 'Sell-out lines', 'count', 'dsi_sellout', 'additive', DSI_BD),
    base('dsi_sellout.dealers', 'Dealers buying', 'count', 'dsi_sellout', 'non_additive', DSI_BD),
    base('cst_sellthrough.units', 'Sell-through units', 'units', 'cst_sellthrough', 'additive', CST_BD, { legacy_key: 'cst_sellthrough_units' }),
    base('cst_sellthrough.lines', 'Sell-through lines', 'count', 'cst_sellthrough', 'additive', CST_BD),
    {
      ...base('cst_sellthrough.units_per_week', 'Units per week', 'units_per_week', 'cst_sellthrough', 'non_additive', CST_BD),
      kind: 'calculated',
      calc: 'per_week_rate',
      inputs: ['cst_sellthrough.units'],
      requires: ['period or period.from+to'],
    },
    base('cst_sellthrough.reported_soh', 'Reported stock on hand (latest report)', 'units', 'cst_sellthrough', 'semi_additive', CST_BD.filter((b) => b !== 'period')),
    base('cst_sellthrough.stores_reporting', 'Stores / sites reporting', 'count', 'cst_sellthrough', 'non_additive', CST_BD),
    base('cpor.lines', 'Promotion lines', 'count', 'cpor', 'additive', CPOR_BD),
    base('cpor.cases', 'Promotion cases', 'count', 'cpor', 'non_additive', CPOR_BD),
    base('cpor.support_usd', 'Support USD', 'usd', 'cpor', 'additive', CPOR_BD),
    base('cpor.support_zar', 'Support ZAR', 'zar', 'cpor', 'additive', CPOR_BD),
    base('cpor.estimate_units', 'Estimated units', 'units', 'cpor', 'additive', CPOR_BD),
    base('cpor.result_units', 'Result units', 'units', 'cpor', 'additive', CPOR_BD),
    base('cpor.delivery_rate', 'Delivery rate', 'ratio', 'cpor', 'non_additive', CPOR_BD),
    {
      id: 'weeks_of_cover',
      label: 'Weeks of cover',
      unit: null,
      model: null,
      kind: 'governed',
      additivity: null,
      breakdowns: ['distributor', 'product'],
      grain_sets: [['distributor', 'product']],
      period_grains: [],
      requires: [],
      legacy_key: 'weeks_of_cover',
      metric_id: 'A3-02',
      status: 'implemented',
      handler_backed: true,
      refuse_all: false,
      refuse_reason: null,
      hidden: false,
      honours: { handler: 'a3_stock', filters: ['distributor', 'product'], dates: false, all_time_only: false, one_value_per_filter: true },
    },
    {
      id: 'pipeline_inbound',
      label: 'Pipeline (inbound)',
      unit: null,
      model: null,
      kind: 'governed',
      additivity: null,
      breakdowns: ['period'],
      grain_sets: [['period']],
      period_grains: ['week', 'month', 'quarter'],
      requires: [],
      legacy_key: 'pipeline_inbound',
      metric_id: 'A1-04',
      status: 'implemented',
      handler_backed: true,
      refuse_all: false,
      refuse_reason: null,
      hidden: false,
      honours: { handler: 'a1_pve', filters: ['bu'], dates: true, all_time_only: false, one_value_per_filter: true },
    },
  ],
  walls: [
    { id: 'W-CST-NO-DISTRIBUTOR', reason: W_CST_NO_DISTRIBUTOR, keeps: [] },
    { id: 'W-SITE-CST-ONLY', reason: W_SITE_CST_ONLY, keeps: [] },
    { id: 'W-A3-GRAIN-LOCK', reason: 'Channel stock and weeks of cover are worked out per distributor and product only.', keeps: [] },
    { id: 'W-CUSTOMER-ROLE', reason: 'A distributor’s dealer and a retailer are different customer roles, so their measures are never combined.', keeps: [] },
  ],
  limits: { max_breakdowns: 3, default_limit: 500, max_limit: 5000 },
  pending: [
    { id: 'cst_sellthrough.stock_cover', reason: 'Customer stock cover is not defined for the builder; show reported stock beside units per week (no derived cover).' },
    { id: 'cpor.open_cases', reason: 'Which statuses count as open is a proposed decision; nothing reads as open today.' },
  ],
};

/* ------------------------------------------------------------------------------------------------
 * Names (fictional) and the dashboard window
 * ---------------------------------------------------------------------------------------------- */

export const CUSTOMERS: [number, string][] = [
  [101, 'Kestrel Home Stores'],
  [102, 'Marula Electronics'],
  [103, 'Baobab Digital'],
  [104, 'Fynbos Office Supply'],
  [105, 'Protea Tech Outlet'],
  [106, 'Sable Retail Group'],
  [107, 'Impala Gadgets'],
  [108, 'Yellowwood Computer Warehouse and Home Office Centre'],
];
export const DISTRIBUTORS: [number, string][] = [
  [11, 'Harbour Distribution'],
  [12, 'Ridgeway Wholesale'],
  [13, 'Summit Supply Co'],
];
export const PRODUCTS: [number, string][] = [
  [201, 'Aero 14 laptop'],
  [202, 'Aero 16 laptop'],
  [203, 'Nimbus tablet 11'],
  [204, 'Pulse monitor 27'],
  [205, 'Orbit dock'],
  [206, 'Vega keyboard'],
];
const BUS = ['Notebook', 'Tablet', 'Monitor', 'Accessories'];
const CHANNELS = ['Retail', 'E-commerce', 'Corporate', 'Education'];
const REGIONS = ['Gauteng', 'Western Cape', 'KwaZulu-Natal'];
const PROMO_TYPES = ['Price drop', 'Bundle', 'Display', 'Cashback'];
const STATUSES = ['settled', 'ended', 'cancelled'];

/** 13 weeks, Monday 2026-07-06 to Sunday 2026-10-04 (ISO weeks 28 to 40). */
export const FIXTURE_WINDOW = { from: '2026-07-06', to: '2026-10-04' };

export const fixtureFilters: DashboardFilters = {
  date: { preset: 'custom', from: FIXTURE_WINDOW.from, to: FIXTURE_WINDOW.to },
  compare: 'previous_period',
  customer: [],
  distributor: [12],
  product: [],
  bu: [],
  channel: [],
  region: [],
};

const DAY = 86_400_000;
const iso = (t: number) => new Date(t).toISOString().slice(0, 10);
const START = Date.UTC(2026, 6, 6);

/* ------------------------------------------------------------------------------------------------
 * Response builders
 * ---------------------------------------------------------------------------------------------- */

const LABEL: Record<string, string> = Object.fromEntries(builderCatalog.breakdowns.map((b) => [b.id, b.label]));
const ENTITY: Record<string, [number, string][]> = {
  customer: CUSTOMERS, distributor: DISTRIBUTORS, product: PRODUCTS,
  case: [[301, 'Autumn promotion'], [302, 'Autumn promotion'], [303, 'Campus launch']],
};
const ATTR: Record<string, string[]> = { bu: BUS, channel: CHANNELS, region: REGIONS, promo_type: PROMO_TYPES, status: STATUSES, workflow_status: STATUSES, site_label: ['Rosebank', 'Sandton City', 'Canal Walk', 'Gateway', 'Menlyn', 'Eastgate'] };

function column(id: string): V2Column {
  if (id === 'period') return { id, kind: 'breakdown', label: 'Period', fields: ['bucket_key', 'bucket_start', 'bucket_end'] };
  if (ENTITY[id]) return { id, kind: 'breakdown', label: LABEL[id] ?? id, fields: [`${id}_id`, `${id}_name`] };
  return { id, kind: 'breakdown', label: LABEL[id] ?? id, fields: [id] };
}

function measureColumn(id: string): V2Column {
  const m = builderCatalog.measures.find((x) => x.id === id);
  return { id, kind: 'measure', label: m?.label ?? id, fields: [id], unit: m?.unit ?? null };
}

type Member = Record<string, unknown>;

function members(breakdown: string, grain: string | null | undefined, window?: { from?: string | null; to?: string | null }): Member[] {
  if (breakdown === 'period') {
    if (window?.from && window.to) {
      let start = new Date(`${window.from}T00:00:00Z`);
      const bound = new Date(`${window.to}T00:00:00Z`);
      if (grain === 'week') start = new Date(start.getTime() - ((start.getUTCDay() + 6) % 7) * DAY);
      else start = new Date(Date.UTC(start.getUTCFullYear(), grain === 'year' ? 0 : grain === 'quarter' ? Math.floor(start.getUTCMonth() / 3) * 3 : start.getUTCMonth(), 1));
      const out: Member[] = [];
      while (start <= bound && out.length < 200) {
        const next = grain === 'week' ? new Date(start.getTime() + 7 * DAY) : new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + (grain === 'year' ? 12 : grain === 'quarter' ? 3 : 1), 1));
        out.push({ bucket_key: iso(start.getTime()), bucket_start: iso(start.getTime()), bucket_end: iso(next.getTime() - DAY) });
        start = next;
      }
      return out;
    }
    if (grain === 'month') {
      return ['2026-07', '2026-08', '2026-09'].map((k, i) => ({
        bucket_key: k,
        bucket_start: `${k}-01`,
        bucket_end: iso(Date.UTC(2026, 7 + i, 0)),
      }));
    }
    if (grain === 'quarter') {
      return [
        { bucket_key: '2025-Q4', bucket_start: '2025-10-01', bucket_end: '2025-12-31' },
        { bucket_key: '2026-Q1', bucket_start: '2026-01-01', bucket_end: '2026-03-31' },
        { bucket_key: '2026-Q2', bucket_start: '2026-04-01', bucket_end: '2026-06-30' },
        { bucket_key: '2026-Q3', bucket_start: '2026-07-01', bucket_end: '2026-09-30' },
      ];
    }
    return Array.from({ length: 13 }, (_, i) => ({
      bucket_key: `2026-W${28 + i}`,
      bucket_start: iso(START + i * 7 * DAY),
      bucket_end: iso(START + (i * 7 + 6) * DAY),
    }));
  }
  if (ENTITY[breakdown]) return ENTITY[breakdown].map(([id, name]) => ({ [`${breakdown}_id`]: id, [`${breakdown}_name`]: name }));
  return (ATTR[breakdown] ?? ['A', 'B']).map((v) => ({ [breakdown]: v }));
}

/** A deterministic value per row and measure, shaped by the measure's unit. */
function value(measure: string, i: number, j: number): number {
  const seed = ((i + 3) * 37 + (j + 1) * 53) % 97;
  if (measure.endsWith('delivery_rate')) return Math.round((0.55 + (seed % 40) / 100) * 1000) / 1000;
  if (measure.endsWith('units_per_week')) return Math.round((1 + seed / 4) * 10) / 10;
  if (measure.endsWith('reported_soh')) return 2 + (seed % 60);
  if (measure.endsWith('support_usd')) return 1500 + seed * 210;
  if (measure.endsWith('support_zar')) return 27_000 + seed * 3_900;
  if (measure.endsWith('cases') || measure.endsWith('dealers') || measure.endsWith('stores_reporting')) return 3 + (seed % 25);
  if (measure.endsWith('estimate_units')) return 400 + seed * 9;
  if (measure.endsWith('result_units')) return 320 + seed * 8;
  return 120 + seed * 11;
}

function cross(breakdowns: string[], grain: string | null | undefined, window?: { from?: string | null; to?: string | null }): Member[] {
  let rows: Member[] = [{}];
  for (const b of breakdowns) {
    const ms = members(b, grain, window);
    rows = rows.flatMap((r) => ms.map((m) => ({ ...r, ...m })));
  }
  return rows;
}

const ADDITIVE = new Set(builderCatalog.measures.filter((m) => m.additivity === 'additive').map((m) => m.id));

export function fixtureResponse(req: V2Request, opts: { scale?: number; maxRows?: number; truncatedOf?: number; unassigned?: boolean } = {}): V2Response {
  const breakdowns = req.breakdowns ?? [];
  const grain = req.period?.grain ?? 'week';
  let combos = cross(breakdowns, grain, req.period);
  if (opts.unassigned && breakdowns.length === 1 && ENTITY[breakdowns[0]]) {
    combos = [...combos, { [`${breakdowns[0]}_id`]: null, [`${breakdowns[0]}_name`]: null }];
  }
  const scale = opts.scale ?? 1;
  const rows: V2Row[] = combos.map((c, i) => {
    const row: V2Row = { ...c };
    req.measures.forEach((m, j) => {
      const v = value(m, i, j);
      row[m] = ADDITIVE.has(m) ? Math.round(v * scale) : v;
    });
    return row;
  });
  const totals: Record<string, number | null> = {};
  for (const m of req.measures) {
    if (ADDITIVE.has(m)) totals[m] = rows.reduce((s, r) => s + (typeof r[m] === 'number' ? (r[m] as number) : 0), 0);
    else if (m.endsWith('units_per_week')) totals[m] = Math.round((rows.length ? (rows.reduce((s, r) => s + (r[m] as number), 0) / rows.length) * 4 : 0) * scale * 10) / 10;
    else if (m.endsWith('delivery_rate')) totals[m] = Math.round(0.78 * scale * 1000) / 1000;
    else totals[m] = Math.round(value(m, 0, 0) * 3 * scale);
  }
  const shown = opts.maxRows ? rows.slice(0, opts.maxRows) : rows;
  return {
    ok: true,
    columns: [...breakdowns.map(column), ...req.measures.map(measureColumn)],
    rows: shown,
    totals,
    truncated: Boolean(opts.truncatedOf),
    refusals: [],
    explain: { row_count: opts.truncatedOf ?? rows.length, data_vintage: { min: req.period?.from ?? '2024-01-02', max: req.period?.to ?? '2026-10-04' } },
  };
}

export function emptyResponse(req: V2Request): V2Response {
  return { ...fixtureResponse(req), rows: [], totals: Object.fromEntries(req.measures.map((m) => [m, null])), explain: { row_count: 0, data_vintage: { min: null, max: null } } };
}

export function refusedResponse(reason: string, measure: string | null = null): V2Response {
  return { ok: false, columns: [], rows: [], totals: {}, truncated: false, refusals: [{ measure, reason, wall: null }], explain: null };
}

/* ------------------------------------------------------------------------------------------------
 * Widgets: one per MUST visual, plus the state cards
 * ---------------------------------------------------------------------------------------------- */

let nextId = 1;
function widget(title: string, visual: WidgetVisual, def: DefinitionV2): DashboardWidget {
  const id = nextId++;
  return {
    id,
    dashboard_id: 900,
    title,
    visual,
    metric_key: def.query.measures[0],
    grains: [],
    filters: {},
    period_grain: null,
    layout_json: null,
    saved_report_id: null,
    sort_order: id,
    definition_v2: { kind: 'model', ...def },
  };
}

const q = (measures: string[], breakdowns: string[] = [], grain?: string, extra: Partial<DefinitionV2['query']> = {}): DefinitionV2['query'] => ({
  measures,
  ...(breakdowns.length ? { breakdowns } : {}),
  ...(grain ? { period: { grain } } : {}),
  ...extra,
});

export const visualWidgets: DashboardWidget[] = [
  widget('Sell-through units', 'kpi', { v: 1, query: q(['cst_sellthrough.units']), display: { kpi: { compare: true, sparkline: true } } }),
  widget('Sell-out units by business unit', 'bar', { v: 1, query: q(['dsi_sellout.units'], ['bu']), display: { compare: true } }),
  widget('Sell-through units by customer', 'hbar', { v: 1, query: q(['cst_sellthrough.units'], ['customer']), display: { top_n: 15 } }),
  widget('Sell-out units by month and business unit', 'stacked_bar', { v: 1, query: q(['dsi_sellout.units'], ['period', 'bu'], 'month') }),
  widget('Sell-through units by week', 'line', { v: 1, query: q(['cst_sellthrough.units'], ['period'], 'week'), display: { compare: true } }),
  widget('Sell-out units by week', 'area', { v: 1, query: q(['dsi_sellout.units'], ['period'], 'week'), display: { compare: true },
    dashboard: { ignore_filters: ['distributor'], fixed_window: { from: '2026-01-01', to: '2026-03-31' } } }),
  widget('Estimated and result units by quarter', 'combo', {
    v: 1,
    query: q(['cpor.estimate_units', 'cpor.result_units'], ['period'], 'quarter'),
    display: { series: { 'cpor.estimate_units': { kind: 'bar' }, 'cpor.result_units': { kind: 'line' } } },
  }),
  widget('Support and delivery rate by quarter', 'dual_axis', {
    v: 1, query: q(['cpor.support_usd', 'cpor.delivery_rate'], ['period'], 'quarter'),
    display: { series: { 'cpor.support_usd': { kind: 'bar', axis: 'left' }, 'cpor.delivery_rate': { kind: 'line', axis: 'right' } } },
  }),
  widget('Support against delivery rate by customer', 'scatter', { v: 1, query: q(['cpor.support_usd', 'cpor.delivery_rate'], ['customer']) }),
  widget('Sell-out units by customer and channel', 'pivot', { v: 1, query: q(['dsi_sellout.units'], ['customer', 'channel']) }),
  widget('Sell-out units by channel', 'pie', { v: 1, query: q(['dsi_sellout.units'], ['channel']) }),
  widget('Support USD by promotion type', 'donut', { v: 1, query: q(['cpor.support_usd'], ['promo_type']) }),
  widget('Stock beside sell-through, by product', 'table', {
    v: 1,
    query: q(['cst_sellthrough.units', 'cst_sellthrough.units_per_week', 'cst_sellthrough.reported_soh'], ['product'], undefined, {
      sort: { by: 'cst_sellthrough.units', dir: 'desc' },
    }),
    display: {
      compare: true,
      table: {
        rules: [
          { measure: 'cst_sellthrough.units_per_week', op: '<', value: 8, tone: 'warn' },
          { measure: 'cst_sellthrough.units_per_week', op: '>=', value: 20, tone: 'good' },
          { measure: 'cst_sellthrough.reported_soh', op: 'between', value: 0, value2: 10, tone: 'bad' },
        ],
      },
    },
  }),
];

const governedWoc: DashboardWidget = {
  ...widget('Weeks of cover', 'kpi', { v: 1, kind: 'governed', query: { measures: ['weeks_of_cover'], breakdowns: ['distributor', 'product'] } }),
  definition_v2: { v: 1, kind: 'governed', query: { measures: ['weeks_of_cover'], breakdowns: ['distributor', 'product'] } },
};

export const stateWidgets = {
  loading: widget('Dealers buying by region', 'hbar', { v: 1, query: q(['dsi_sellout.dealers'], ['region']) }),
  empty: widget('Support ZAR by case status', 'hbar', { v: 1, query: q(['cpor.support_zar'], ['status']) }),
  refused: widget('Dealers by customer and product', 'table', { v: 1, query: q(['dsi_sellout.dealers'], ['customer', 'product'], undefined, { limit: 6000 }) }),
  error: widget('Support ZAR by customer', 'hbar', { v: 1, query: q(['cpor.support_zar'], ['customer']) }),
  truncated: widget('Sell-out units by distributor, product and week', 'table', { v: 1, query: q(['dsi_sellout.units'], ['distributor', 'product', 'period'], 'week') }),
  governed: governedWoc,
  required: widget('Sell-through units for one account', 'kpi', { v: 1, query: q(['cst_sellthrough.units']) }),
};

/** Recorded answers by "measures|breakdowns"; filter values come from `<model>.lines` by one breakdown. */
export function fixtureExecute(req: V2Request): Promise<V2Response> {
  const key = `${req.measures.join(',')}|${(req.breakdowns ?? []).join(',')}`;
  switch (key) {
    case 'dsi_sellout.dealers|region':
      return new Promise(() => undefined); // loading, for ever
    case 'cpor.support_zar|status':
      return Promise.resolve(emptyResponse(req));
    case 'dsi_sellout.dealers|customer,product':
      return Promise.resolve(refusedResponse('Limit 6,000 is above the most rows one query returns (5,000). Lower the row limit.'));
    case 'cpor.support_zar|customer':
      return Promise.reject(new Error('Server error (502)'));
    case 'dsi_sellout.units|distributor,product,period':
      return Promise.resolve(fixtureResponse(req, { maxRows: 60, truncatedOf: 5_231 }));
    case 'cst_sellthrough.units|customer':
      return Promise.resolve(fixtureResponse(req, { unassigned: true }));
    case 'weeks_of_cover|distributor,product':
      return Promise.resolve({ ...fixtureResponse({ ...req, measures: ['dsi_sellout.dealers'] }), columns: [column('distributor'), column('product'), { id: 'weeks_of_cover', kind: 'measure', label: 'Weeks of cover', fields: ['weeks_of_cover'], unit: null }], totals: { weeks_of_cover: 6.4 }, rows: [{ distributor_id: 12, distributor_name: 'Ridgeway Wholesale', product_id: 201, product_name: 'Aero 14 laptop', weeks_of_cover: 6.4 }] });
    default:
      break;
  }
  // The KPI comparison: the same question over the window before the dashboard's.
  const month = req.period?.from ? new Date(`${req.period.from}T00:00:00Z`).getUTCMonth() : 6;
  return Promise.resolve(fixtureResponse(req, { scale: Math.round((0.7 + month * 0.05) * 100) / 100 }));
}

/* ------------------------------------------------------------------------------------------------
 * Starters (shape of GET /dashboards/templates)
 * ---------------------------------------------------------------------------------------------- */

const emptyBar = { customer: [], distributor: [], product: [], bu: [], channel: [], region: [] };

export const fixtureTemplates: DashboardTemplate[] = [
  {
    key: 'account_overview',
    title: 'Account overview',
    description: 'One retailer’s own sell-through: units, weekly rate, latest reported stock, top products and stores. Pick a customer above.',
    widget_count: 8,
    required_filters: ['customer'],
    filters_json: { date: { preset: 'last_52_weeks', from: null, to: null }, compare: 'previous_period', ...emptyBar, required: ['customer'] },
    left_out: [
      { what: 'Stock cover', reason: 'Customer stock cover is not defined for the builder; show reported stock beside units per week (no derived cover).', pending_id: 'cst_sellthrough.stock_cover' },
      { what: 'Restock flags', reason: 'Restock flags live in the sell-through overview’s SKU problem rules; not a compiler measure yet.', pending_id: 'cst_sellthrough.restock_flag' },
      { what: 'Sales value', reason: 'Proposed decision 3: the CST sales value and its VAT basis are not picked.', pending_id: 'cst_sellthrough.value' },
      { what: 'DSI sell-out to this customer as a dealer', reason: 'A distributor’s dealer is a different customer role; add a DSI widget by hand.', pending_id: null },
      { what: 'Colour rules on the stock table', reason: 'No agreed threshold, so no colour rule is set.', pending_id: null },
    ],
  },
  {
    key: 'sellthrough_stock',
    title: 'Sell-through & stock across customers',
    description: 'Sell-through and latest reported stock for each retailer side by side, and the monthly trend.',
    widget_count: 6,
    required_filters: [],
    filters_json: { date: { preset: 'last_52_weeks', from: null, to: null }, compare: 'previous_period', ...emptyBar },
    left_out: [
      { what: 'Stock cover in weeks', reason: 'Customer stock cover is not defined for the builder yet (proposed decision 5).', pending_id: 'cst_sellthrough.stock_cover' },
      { what: 'Restock flags', reason: 'Not a compiler measure yet.', pending_id: 'cst_sellthrough.restock_flag' },
      { what: 'Sales value', reason: 'Proposed decision 3.', pending_id: 'cst_sellthrough.value' },
    ],
  },
  {
    key: 'cpor_cases',
    title: 'CPOR cases',
    description: 'How many promotion cases there are, the support they carry, how well they delivered, and how they split by status, quarter and account.',
    widget_count: 8,
    required_filters: [],
    filters_json: { date: { preset: 'all_time', from: null, to: null }, compare: 'none', ...emptyBar },
    left_out: [
      { what: 'Open cases', reason: 'Which statuses count as open is a proposed decision (4).', pending_id: 'cpor.open_cases' },
      { what: 'Case value', reason: 'Proposed decision 4.', pending_id: null },
      { what: 'Cases as a pie', reason: 'Cases are a distinct count, so they do not add up into slices.', pending_id: null },
    ],
  },
];

/** A dashboard created from a starter (for the "Template — editable" chip and its note). */
export const fixtureStarterDashboard: Dashboard = {
  id: 901,
  name: 'Account overview',
  description: fixtureTemplates[0].description,
  visibility: 'personal',
  shared_roles: [],
  widgets: [],
  filters_json: fixtureTemplates[0].filters_json,
  template_key: 'account_overview',
};

/** Backend code-defined starter snapshot: all 22 widgets, with fixed fictional render dates. */
export const fixtureStarterDashboards: Dashboard[] = starterSnapshots.map((d) => ({
  ...d,
  filters_json: {
    ...d.filters_json,
    date: { preset: 'custom', from: FIXTURE_WINDOW.from, to: FIXTURE_WINDOW.to },
    ...(d.template_key === 'account_overview' ? { customer: [101] } : {}),
  },
})) as Dashboard[];
