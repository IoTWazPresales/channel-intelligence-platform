/**
 * Reports presentation model (N-0109). Pure functions that turn the governed query API response
 * into what the page shows: plain-word labels, units, table columns with recomputed totals, ranked
 * bars and KPI tiles. No number is changed here — values are passed through from the API response
 * and only formatted; totals are recomputed from the same rows (Σ, or Σ numerator ÷ Σ denominator
 * for ratios), never averaged.
 */
import {
  formatMeasure,
  thresholdState,
  unitWord,
  type ChartTone,
  type MeasureUnit,
  type RankedBarDatum,
} from '@/features/workbench-ui/charts';
import { coverPairStatus, coverStatusLabel, coverStatusTone, type CoverPairStatus } from '@/features/stock/coverStatus';

/* ------------------------------------------------------------------------------------------------
 * API shapes (as returned by /api/v1/semantics/catalog and /api/v1/query/execute)
 * ---------------------------------------------------------------------------------------------- */

export type SemanticMetric = {
  id: string;
  key: string;
  label: string;
  status: string;
  formula: string;
  allowed_grains: string[][];
  refuse_all?: boolean;
  handler_backed?: boolean;
  refuse_reason?: string | null;
  owner_surface?: string | null;
  calendar_period?: boolean | null;
  hidden?: boolean | null;
};

export type CatalogResponse = {
  version: number;
  source_doc: string;
  metrics: SemanticMetric[];
  dimensions: { id: string; label: string; description?: string }[];
};

export type QueryResult = {
  ok: boolean;
  status: string;
  metric_id: string | null;
  metric_key: string | null;
  grains: string[];
  filters: Record<string, unknown>;
  validation: { ok: boolean; message: string; allowed_grains?: string[][] };
  invariants_applied: string[];
  data_vintage: Record<string, unknown> | null;
  value: unknown;
  rows: Record<string, unknown>[] | null;
  scorecard: Record<string, unknown> | null;
  cache: { hit: boolean; ttl_seconds: number; key: string } | null;
  message: string | null;
  handler: string | null;
};

export type DistributorOption = { id: number; distributor_code: string; distributor_name: string };
export type CustomerOption = { id: number; customer_code: string; customer_name: string };
export type EntityLookups = {
  distributors: Map<number, DistributorOption>;
  customers: Map<number, CustomerOption>;
};

export function buildLookups(opts?: { distributors?: DistributorOption[]; customers?: CustomerOption[] } | null): EntityLookups {
  return {
    distributors: new Map((opts?.distributors ?? []).map((d) => [Number(d.id), d])),
    customers: new Map((opts?.customers ?? []).map((c) => [Number(c.id), c])),
  };
}

/* ------------------------------------------------------------------------------------------------
 * Plain words
 * ---------------------------------------------------------------------------------------------- */

/** Catalog `owner_surface` → the area name people see in the navigation. */
const FAMILY_LABEL: Record<string, string> = {
  'channel-ops': 'Stock & sell-through',
  'channel-intelligence': 'Retailer sell-through',
  'plan-vs-executed': 'Plan vs executed',
  shipping: 'Shipping',
  'cpor-cases': 'Promotions & funding',
  forecasts: 'Forecasts',
};
const FAMILY_ORDER = ['Stock & sell-through', 'Retailer sell-through', 'Plan vs executed', 'Shipping', 'Promotions & funding', 'Forecasts', 'Other'];

export function familyLabel(m: Pick<SemanticMetric, 'owner_surface'>): string {
  return FAMILY_LABEL[String(m.owner_surface ?? '')] ?? 'Other';
}

export function groupMetricsByFamily(metrics: SemanticMetric[]): { family: string; metrics: SemanticMetric[] }[] {
  const by = new Map<string, SemanticMetric[]>();
  for (const m of metrics) {
    const f = familyLabel(m);
    by.set(f, [...(by.get(f) ?? []), m]);
  }
  return [...by.entries()]
    .sort(([a], [b]) => FAMILY_ORDER.indexOf(a) - FAMILY_ORDER.indexOf(b))
    .map(([family, ms]) => ({ family, metrics: ms }));
}

const DIMENSION_LABEL: Record<string, string> = {
  period: 'Period',
  customer: 'Customer',
  distributor: 'Distributor',
  product: 'Product',
  bu: 'Product line',
  sales_model: 'Sales model',
  channel: 'Channel',
  region: 'Region',
  site_label: 'Site',
  promo_type: 'Promo type',
};

export function dimensionLabel(id: string): string {
  return DIMENSION_LABEL[id] ?? humanize(id);
}

/** "distributor,product" → "Distributor × Product". */
export function grainSetLabel(grains: string[]): string {
  if (!grains.length) return 'Total only';
  return grains.map(dimensionLabel).join(' × ');
}

export function grainSetKey(grains: string[]): string {
  return [...grains].sort().join(',');
}

/** snake_case or kebab-case → "Sentence case words" (fallback only). */
export function humanize(s: string): string {
  const t = s.replace(/[_.-]+/g, ' ').trim();
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : s;
}

type MetricPresentation = {
  unit: MeasureUnit;
  about: string;
  /** Lower is worse against week thresholds: state colours, threshold line, ascending sort. */
  coverType?: boolean;
  betterWhen?: 'up' | 'down';
  /** Σ-additive across rows (units, counts, money). Ratios and averages are not. */
  additive?: boolean;
  /** Ratio recomputed for the totals row as Σ numerator ÷ Σ denominator (first pair found in rows). */
  ratioOf?: [string, string][];
};

/**
 * Plain-word description per governed metric, written from the catalog formula (apps/api
 * semantics/catalog/default.yaml). Unknown metrics fall back to the catalog text.
 */
const METRIC: Record<string, MetricPresentation> = {
  fill_rate: { unit: 'percent', betterWhen: 'up', about: 'Share of planned units that shipped, counting each plan line only up to its planned quantity. A line counts as shipped only when it is marked shipped.' },
  line_hit_rate: { unit: 'percent', betterWhen: 'up', about: 'Share of plan lines that shipped at least their planned quantity.' },
  over_plan_intake_rate: { unit: 'units', additive: true, about: 'Units shipped above plan on plan lines (shipped against plan, not proof of delivery).' },
  short_exposure: { unit: 'units', additive: true, betterWhen: 'down', about: 'Units planned but not shipped on plan lines.' },
  unplanned_intake: { unit: 'units', additive: true, about: 'Units shipped on lines that had no plan.' },
  no_po_blind_spot: { unit: 'count', additive: true, betterWhen: 'down', about: 'Plan lines still waiting for a purchase order, with their planned units.' },
  pipeline_inbound: { unit: 'units', additive: true, about: 'Units on open orders against plan lines, still in the pipeline.' },
  volume_bias: { unit: 'percent', about: 'Average gap between shipped and planned, as a share of plan, by product line. Above zero means more shipped than planned.' },
  slip: { unit: 'quarters', betterWhen: 'down', about: 'How many quarters the actual ship quarter moved from the lineup quarter on linked purchase orders. Uses the ship confirmation, then the scheduled ship date — not proof of delivery.' },
  lifecycle_buckets: { unit: 'count', additive: true, about: 'Shipment lines grouped by where they are: shipped, in the pipeline, or landed.' },
  commercial_cohorts: { unit: 'count', additive: true, about: 'Shipments grouped by arrival: arriving, overdue, or landed this week.' },
  pod_completeness: { unit: 'days', about: 'How long shipments have been waiting for proof of delivery.' },
  support_spend: { unit: 'usd', additive: true, about: 'Promotion support paid, calculated in USD with ZAR shown for reference. Voided cases are left out.' },
  delivery_rate: { unit: 'percent', betterWhen: 'up', about: 'Units sold under promotion as a share of the estimate. Voided cases and cases with no estimate are left out.' },
  support_norms: { unit: 'usd', about: 'Typical support over the last four quarters, in money and as a share of the shelf price.' },
  comparable_cases: { unit: 'count', about: 'Past cases ranked by how closely they match: customer, product line, promo type, quarter, then volume.' },
  support_cost_per_unit_sold: { unit: 'usd', betterWhen: 'down', about: 'Support paid per unit sold under promotion, in USD (ZAR shown for reference).' },
  channel_stock: { unit: 'units', additive: true, about: 'Stock at each distributor: the latest reported stock, minus sell-out since that report, plus delivered shipments since. Stock still in transit is not counted.' },
  weeks_of_cover: {
    unit: 'weeks',
    coverType: true,
    betterWhen: 'up',
    about: 'How many weeks the stock at a distributor lasts at its usual selling pace: stock ÷ average weekly sell-out over the last 52 weeks. Where almost nothing sells, cover is left blank.',
    ratioOf: [
      ['channel_stock', 'weekly_velocity'],
      ['soh_units', 'avg_weekly_units'],
    ],
  },
  replenishment_flag: { unit: 'count', about: 'Marks distributor and product pairs whose cover is above zero but under the reorder threshold (4 weeks unless set otherwise).' },
  sellout_units: { unit: 'units', additive: true, betterWhen: 'up', about: 'Units sold by distributors, grouped by week, month or quarter. Raw units, not a weekly rate.' },
  cst_sellthrough_units: { unit: 'units', additive: true, betterWhen: 'up', about: 'Units sold by retailers, grouped by the period they were reported in.' },
  forecast_units: { unit: 'units', additive: true, about: 'Forecast units, added up across whatever you break them down by.' },
  forecast_confidence: { unit: 'number', about: 'How confident each forecast is: low, medium, high, or set by hand.' },
  forecast_band: { unit: 'units', about: 'The low and high range around each forecast.' },
  forecast_method: { unit: 'number', about: 'How each forecast was made: from selling pace, from a similar product, or set by hand.' },
  analogue_provenance: { unit: 'number', about: 'Which similar product a forecast was based on.' },
};

export function metricPresentation(m: Pick<SemanticMetric, 'key' | 'formula'> | null | undefined): MetricPresentation {
  if (!m) return { unit: 'number', about: '' };
  return METRIC[m.key] ?? { unit: 'number', about: m.formula ? humanize(m.formula) : '' };
}

/** Rules the query engine applied, in plain words (codes never reach the screen). */
const RULE_LABEL: Record<string, string> = {
  tenant_scope: "Only your organisation's data",
  latest_snapshot: 'Latest stock report',
  latest_per_distributor_product_soh: 'Uses the latest stock report for each distributor and product',
  never_sum_snapshot_history: 'Stock reports from different dates are never added together',
  pipeline_never_counts: 'Stock still in transit is not counted',
  pipeline_excluded_from_fill_numerator: 'Stock still in transit does not count as shipped',
  pod_landed_shipped_only_inbound: 'Only shipments with proof of delivery are added to stock',
  raw_units_not_velocity: 'Raw units, not a weekly rate',
  calendar_period_grain_week_month_quarter: 'Grouped by week, month or quarter — never by day',
  no_daily_widget_grain: 'No daily breakdown',
  cst_never_finer_than_stored_period_type: 'Retailer sell-through is never split finer than the period it was reported in',
  dsi_customer_is_not_cst_customer: 'Distributor customers are kept apart from retailer sell-through customers',
  in_plan_rows_planned_gt_zero: 'Only plan lines with a planned quantity count',
  line_state_shipped_evidence: 'A line counts as shipped only when it is marked shipped',
  shipped_only_fill: 'Fill counts shipped lines only',
  usd_compute_zar_display: 'Calculated in USD; ZAR shown for reference',
  voided_and_zero_estimate_excluded: 'Voided cases and cases with no estimate are left out',
  claim_rate_not_fabricated: 'Claim rate is not estimated',
};

export function ruleLabel(code: string): string {
  return RULE_LABEL[code] ?? humanize(code);
}

/* ------------------------------------------------------------------------------------------------
 * Row fields
 * ---------------------------------------------------------------------------------------------- */

type FieldKind = 'name' | 'code' | 'dim' | 'measure' | 'hidden';
type FieldSpec = { kind: FieldKind; label: string; unit?: MeasureUnit; additive?: boolean; order: number };

const FIELD: Record<string, FieldSpec> = {
  distributor_name: { kind: 'name', label: 'Distributor', order: 1 },
  customer_name: { kind: 'name', label: 'Customer', order: 2 },
  product_name: { kind: 'name', label: 'Product', order: 3 },
  distributor_code: { kind: 'code', label: 'Distributor code', order: 11 },
  customer_code: { kind: 'code', label: 'Customer code', order: 12 },
  sku: { kind: 'code', label: 'SKU', order: 13 },
  product_sku: { kind: 'code', label: 'SKU', order: 13 },
  product_id: { kind: 'code', label: 'Product ID', order: 14 },
  distributor_id: { kind: 'hidden', label: 'Distributor ID', order: 99 },
  customer_id: { kind: 'hidden', label: 'Customer ID', order: 99 },
  bucket_key: { kind: 'dim', label: 'Period', order: 20 },
  period: { kind: 'dim', label: 'Period', order: 21 },
  week: { kind: 'dim', label: 'Week', order: 22 },
  bu: { kind: 'dim', label: 'Product line', order: 23 },
  promo_type: { kind: 'dim', label: 'Promo type', order: 24 },
  site_label: { kind: 'dim', label: 'Site', order: 25 },
  state: { kind: 'dim', label: 'State', order: 26 },
  age_bucket: { kind: 'dim', label: 'Age', order: 27 },
  bucket_start: { kind: 'hidden', label: 'Bucket start', order: 99 },
  bucket_end: { kind: 'hidden', label: 'Bucket end', order: 99 },
  channel_stock: { kind: 'measure', label: 'Channel stock', unit: 'units', additive: true, order: 40 },
  soh_units: { kind: 'measure', label: 'Stock on hand', unit: 'units', additive: true, order: 40 },
  weekly_velocity: { kind: 'measure', label: 'Avg weekly sell-out', unit: 'units', additive: true, order: 41 },
  avg_weekly_units: { kind: 'measure', label: 'Avg weekly sell-out', unit: 'units', additive: true, order: 41 },
  replenishment_flag: { kind: 'hidden', label: 'Below reorder threshold', order: 99 },
};

const TIME_KEYS = ['bucket_key', 'week', 'period'] as const;

/** Best name for a row's distributor/customer/product; null when the API gives only an id we cannot resolve. */
function resolvedNames(row: Record<string, unknown>, lk: EntityLookups) {
  const did = row.distributor_id != null ? Number(row.distributor_id) : null;
  const cid = row.customer_id != null ? Number(row.customer_id) : null;
  const d = did != null ? lk.distributors.get(did) : undefined;
  const c = cid != null ? lk.customers.get(cid) : undefined;
  return {
    distributor_name: (row.distributor_name as string | undefined) ?? d?.distributor_name ?? null,
    distributor_code: (row.distributor_code as string | undefined) ?? d?.distributor_code ?? null,
    customer_name: (row.customer_name as string | undefined) ?? c?.customer_name ?? null,
    customer_code: (row.customer_code as string | undefined) ?? c?.customer_code ?? null,
  };
}

/** Label for a row in a chart: names first; ids only as a last resort (#id). */
export function rowLabel(row: Record<string, unknown>, lk: EntityLookups): string {
  const n = resolvedNames(row, lk);
  const parts: string[] = [];
  if (row.distributor_id != null || n.distributor_name) parts.push(n.distributor_name ?? `Distributor #${row.distributor_id}`);
  if (row.customer_id != null || n.customer_name) parts.push(n.customer_name ?? `Customer #${row.customer_id}`);
  if (row.product_name != null) parts.push(String(row.product_name));
  else if (row.product_id != null) parts.push(`Product #${row.product_id}`);
  for (const k of [...TIME_KEYS, 'bu', 'promo_type', 'state', 'age_bucket', 'site_label']) {
    if (row[k] != null && row[k] !== '') {
      parts.push(String(row[k]));
      break;
    }
  }
  return parts.join(' · ') || 'Total';
}

/* ------------------------------------------------------------------------------------------------
 * Result table
 * ---------------------------------------------------------------------------------------------- */

export type ResultColumn = {
  field: string;
  header: string;
  kind: Exclude<FieldKind, 'hidden'> | 'state';
  unit?: MeasureUnit;
  numeric: boolean;
};

export type ResultTable = {
  columns: ResultColumn[];
  rows: Record<string, unknown>[];
  /** Totals row keyed by column field; `null` = not meaningful for that column. */
  totals: Record<string, number | string | null>;
  totalLabel: string;
};

function headerWithUnit(label: string, unit?: MeasureUnit): string {
  const w = unit ? unitWord(unit) : null;
  // "Weeks of cover" already names its unit; "Channel stock" gets "(units)".
  if (!w || label.toLowerCase().includes(w.toLowerCase())) return label;
  return `${label} (${w})`;
}

export type ReportContext = {
  metric: SemanticMetric | null;
  result: QueryResult;
  lookups: EntityLookups;
};

/** Threshold for cover-type metrics: the API's reorder threshold when it sends one, else 4 weeks. */
export function coverThreshold(result: QueryResult | null): number {
  const t = Number((result?.data_vintage as Record<string, unknown> | null)?.replenishment_threshold_weeks);
  return Number.isFinite(t) && t > 0 ? t : 4;
}

export function buildResultTable({ metric, result, lookups }: ReportContext): ResultTable {
  const p = metricPresentation(metric);
  const apiRows = result.rows ?? [];
  const metricKey = metric?.key ?? result.metric_key ?? '';
  const measureLabel = metric?.label ?? 'Value';

  const rows = apiRows.map((r) => {
    const n = resolvedNames(r, lookups);
    const out: Record<string, unknown> = { ...r };
    for (const [k, v] of Object.entries(n)) if (v != null && out[k] == null) out[k] = v;
    if (p.coverType) {
      const st = coverPairStatus(typeof r.value === 'number' ? r.value : null);
      out.__state = st && st !== 'ok' ? st : null;
    }
    return out;
  });

  const fields = new Set<string>();
  for (const r of rows) for (const k of Object.keys(r)) fields.add(k);
  // A distributor/customer id with no resolvable name still gets a name column ("—"): names first.
  if (fields.has('distributor_id')) fields.add('distributor_name');
  if (fields.has('customer_id')) fields.add('customer_name');

  const cols: (ResultColumn & { order: number })[] = [];
  for (const f of fields) {
    if (f === 'value' || f === '__state') continue;
    if (f === metricKey) continue; // duplicate of `value` (e.g. weeks_of_cover on a weeks_of_cover run)
    const spec = FIELD[f];
    if (spec?.kind === 'hidden') continue;
    const sample = rows.find((r) => r[f] != null)?.[f];
    if (spec) {
      cols.push({
        field: f,
        header: spec.kind === 'measure' ? headerWithUnit(spec.label, spec.unit) : spec.label,
        kind: spec.kind,
        unit: spec.unit,
        numeric: spec.kind === 'measure' || f === 'product_id',
        order: spec.order,
      });
    } else if (typeof sample === 'number') {
      cols.push({ field: f, header: humanize(f), kind: 'measure', unit: 'number', numeric: true, order: 50 });
    } else if (typeof sample === 'object' && sample !== null) {
      continue; // nested payloads (series points etc.) are not table cells
    } else {
      cols.push({ field: f, header: humanize(f), kind: 'dim', numeric: false, order: 30 });
    }
  }
  cols.push({ field: 'value', header: headerWithUnit(measureLabel, p.unit), kind: 'measure', unit: p.unit, numeric: true, order: 45 });
  if (p.coverType) cols.push({ field: '__state', header: 'State', kind: 'state', numeric: false, order: 60 });
  cols.sort((a, b) => a.order - b.order || a.header.localeCompare(b.header));

  // Totals: Σ for additive measures; ratio measure recomputed as Σ num ÷ Σ den; else the API's
  // governed overall value when it is a number; never an average of ratios.
  const sum = (f: string) => rows.reduce((a, r) => a + (typeof r[f] === 'number' && Number.isFinite(r[f] as number) ? (r[f] as number) : 0), 0);
  const hasNumbers = (f: string) => rows.some((r) => typeof r[f] === 'number');
  const totals: Record<string, number | string | null> = {};
  for (const c of cols) {
    if (c.field === 'value') {
      const pair = p.ratioOf?.find(([a, b]) => hasNumbers(a) && hasNumbers(b));
      if (pair) {
        const den = sum(pair[1]);
        totals.value = den > 0 ? sum(pair[0]) / den : null;
      } else if (p.additive) {
        totals.value = sum('value');
      } else if (typeof result.value === 'number' && Number.isFinite(result.value)) {
        totals.value = result.value;
      } else {
        totals.value = null;
      }
    } else if (c.kind === 'measure') {
      const spec = FIELD[c.field];
      totals[c.field] = spec?.additive && hasNumbers(c.field) ? sum(c.field) : null;
    } else {
      totals[c.field] = null;
    }
  }

  return {
    columns: cols.map(({ order: _o, ...c }) => c),
    rows,
    totals,
    totalLabel: `Total · ${rows.length} ${rows.length === 1 ? 'row' : 'rows'}`,
  };
}

export function formatCell(col: ResultColumn, v: unknown): string {
  if (v == null || v === '') return '—';
  if (col.kind === 'state') return coverStatusLabel(v as CoverPairStatus);
  if (col.numeric && typeof v === 'number') {
    if (col.field === 'product_id') return String(v);
    return formatMeasure(v, col.unit ?? 'number');
  }
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (typeof v === 'object') return '—';
  return String(v);
}

export function stateTone(v: unknown): 'danger' | 'warning' | 'info' | 'success' | 'neutral' {
  return coverStatusTone(v as CoverPairStatus);
}

/* ------------------------------------------------------------------------------------------------
 * Bars
 * ---------------------------------------------------------------------------------------------- */

export type BarsModel = {
  data: RankedBarDatum[];
  sort: 'asc' | 'desc';
  threshold?: { value: number; label: string };
  unit: MeasureUnit;
  key?: { tone: ChartTone; label: string }[];
};

export function buildBars({ metric, result, lookups }: ReportContext): BarsModel {
  const p = metricPresentation(metric);
  const rows = result.rows ?? [];
  if (p.coverType) {
    const warn = coverThreshold(result);
    const limits = { stop: 2, warn };
    const tone = (v: number | null): ChartTone => {
      const s = thresholdState(v, limits);
      return s === 'stop' ? 'danger' : s === 'warn' ? 'warning' : 'primary';
    };
    return {
      data: rows.map((r, i) => {
        const v = typeof r.value === 'number' ? r.value : null;
        return { key: String(i), label: rowLabel(r, lookups), value: v, tone: tone(v) };
      }),
      sort: 'asc',
      threshold: { value: warn, label: `${formatMeasure(warn, 'weeks', 'bare').replace(/\.0$/, '')}-week threshold` },
      unit: p.unit,
      key: [
        { tone: 'danger', label: 'Under 2 weeks' },
        { tone: 'warning', label: `Under ${formatMeasure(warn, 'weeks', 'bare').replace(/\.0$/, '')} weeks` },
        { tone: 'primary', label: 'Enough cover' },
      ],
    };
  }
  return {
    data: rows.map((r, i) => ({
      key: String(i),
      label: rowLabel(r, lookups),
      value: typeof r.value === 'number' ? r.value : r.value != null && Number.isFinite(Number(r.value)) ? Number(r.value) : null,
      tone: 'primary' as ChartTone,
    })),
    sort: 'desc',
    unit: p.unit,
  };
}

/* ------------------------------------------------------------------------------------------------
 * Series (time breakdowns) and KPI tiles
 * ---------------------------------------------------------------------------------------------- */

/** A single time series: every row has a time key and no other breakdown varies. */
export function seriesOf(result: QueryResult | null): { label: string; value: number }[] | null {
  const rows = result?.rows ?? [];
  if (rows.length < 2) return null;
  const grains = result?.grains ?? [];
  if (grains.some((g) => g !== 'period')) return null;
  const key = TIME_KEYS.find((k) => rows.every((r) => r[k] != null));
  if (!key) return null;
  return rows.map((r) => ({ label: String(r[key]), value: typeof r.value === 'number' ? r.value : Number(r.value) || 0 }));
}

export type KpiTile = {
  id: string;
  label: string;
  value: string;
  unit?: string;
  severity: 'neutral' | 'good' | 'warn' | 'bad';
  delta?: { text: string; direction: 'up' | 'down' | 'flat'; goodWhen?: 'up' | 'down' | 'neutral'; period?: string };
  target?: string;
  caption?: string;
  sparkline?: { values: number[]; label: string };
  state: 'ready' | 'empty' | 'stale';
  stateNote?: string;
  lead?: boolean;
  /** Raw number shown (for tests: same numbers before/after). */
  raw: number | null;
};

const STALE_DAYS = 14;

function asOfDate(result: QueryResult): Date | null {
  const v = (result.data_vintage ?? {}) as Record<string, unknown>;
  const s = (v.cover_as_of_date ?? v.as_of ?? v.as_of_date ?? v.as_of_utc) as string | undefined;
  if (!s) return null;
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function asOfLabel(result: QueryResult): string | null {
  const d = asOfDate(result);
  if (!d) return null;
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function buildKpis({ metric, result, lookups }: ReportContext, now: Date = new Date()): KpiTile[] {
  const p = metricPresentation(metric);
  const label = metric?.label ?? 'Result';
  const rows = result.rows ?? [];
  const raw = typeof result.value === 'number' && Number.isFinite(result.value) ? result.value : null;
  const unit = p.unit === 'percent' ? undefined : unitWord(p.unit) ?? undefined;
  const asOf = asOfLabel(result);
  const asOfDt = asOfDate(result);
  const missing = Boolean((result.data_vintage as Record<string, unknown> | null)?.missing_data_alert) || result.message === 'missing_data';
  const stale = asOfDt != null && now.getTime() - asOfDt.getTime() > STALE_DAYS * 86_400_000;
  const series = seriesOf(result);
  const scopeBits = [asOf ? `As of ${asOf}` : null, rows.length ? `${rows.length} ${rows.length === 1 ? 'row' : 'rows'}` : null].filter(Boolean);

  const lead: KpiTile = {
    id: 'lead',
    lead: true,
    label,
    value: formatMeasure(raw, p.unit, p.unit === 'usd' ? 'short' : 'bare'),
    unit: p.unit === 'usd' ? undefined : unit,
    raw,
    severity: 'neutral',
    caption: series ? `${series[0].label} – ${series[series.length - 1].label}` : scopeBits.join(' · ') || undefined,
    state: raw == null || missing ? 'empty' : stale ? 'stale' : 'ready',
    stateNote:
      raw == null || missing
        ? 'No data for this selection yet. Check that the latest files have been imported.'
        : stale
          ? `Data as of ${asOf} — more than ${STALE_DAYS} days old.`
          : undefined,
  };
  if (series) {
    lead.sparkline = { values: series.map((s) => s.value), label: `${label} by period, ${series[0].label} to ${series[series.length - 1].label}` };
  }

  const tiles: KpiTile[] = [lead];

  if (p.coverType) {
    const warn = coverThreshold(result);
    lead.target = `target ≥ ${formatMeasure(warn, 'weeks', 'bare').replace(/\.0$/, '')} weeks`;
    const s = thresholdState(raw, { stop: 2, warn });
    lead.severity = s === 'stop' ? 'bad' : s === 'warn' ? 'warn' : 'neutral';
    const valued = rows.filter((r) => typeof r.value === 'number');
    const limits = { stop: 2, warn };
    const under2 = valued.filter((r) => thresholdState(r.value as number, limits) === 'stop').length;
    const twoTo = valued.filter((r) => thresholdState(r.value as number, limits) === 'warn').length;
    const of = `of ${valued.length}`;
    tiles.push({ id: 'under2', label: 'Under 2 weeks', value: formatMeasure(under2, 'count'), unit: of, raw: under2, severity: under2 > 0 ? 'bad' : 'neutral', state: 'ready', caption: 'Rows that run out first' });
    tiles.push({
      id: 'under4',
      label: `2–${formatMeasure(warn, 'weeks', 'bare').replace(/\.0$/, '')} weeks`,
      value: formatMeasure(twoTo, 'count'),
      unit: of,
      raw: twoTo,
      severity: twoTo > 0 ? 'warn' : 'neutral',
      state: 'ready',
      caption: 'Below the reorder threshold',
    });
  }

  if (series && series.length >= 2) {
    const last = series[series.length - 1];
    const prev = series[series.length - 2];
    const diff = last.value - prev.value;
    tiles.push({
      id: 'latest',
      label: `Latest · ${last.label}`,
      value: formatMeasure(last.value, p.unit, p.unit === 'usd' ? 'short' : 'bare'),
      unit: p.unit === 'usd' || p.unit === 'percent' ? undefined : unit,
      raw: last.value,
      severity: 'neutral',
      delta: {
        text: p.unit === 'percent' ? `${formatMeasure(Math.abs(diff), 'number')} pts` : formatMeasure(Math.abs(diff), p.unit, 'short'),
        direction: diff > 0 ? 'up' : diff < 0 ? 'down' : 'flat',
        goodWhen: p.betterWhen ?? 'neutral',
        period: prev.label,
      },
      state: 'ready',
    });
  }

  void lookups;
  return tiles;
}

/** Plain-word scope of a run for the chips and the "About this figure" disclosure. */
export function scopeLabel(filters: Record<string, unknown>, lookups: EntityLookups, productLineLabel?: (code: string) => string): string {
  const bits: string[] = [];
  if (filters.distributor_id != null && filters.distributor_id !== '') {
    const d = lookups.distributors.get(Number(filters.distributor_id));
    bits.push(d?.distributor_name ?? 'One distributor');
  } else {
    bits.push('All distributors');
  }
  if (filters.bu) bits.push(productLineLabel ? productLineLabel(String(filters.bu)) : `Product line ${filters.bu}`);
  if (filters.period_from || filters.period_to) {
    const a = String(filters.period_from ?? '');
    const b = String(filters.period_to ?? '');
    bits.push(a && b && a !== b ? `${a} to ${b}` : a || b);
  }
  return bits.join(' · ');
}
