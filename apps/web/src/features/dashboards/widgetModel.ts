/**
 * How a query result becomes a chart (Warren 2026-10-20).
 *
 * - Rows are labelled by name (customer, distributor, product, store, period), never by id codes.
 * - Each breakdown only offers visuals that make sense for it: lines and areas need a period; pie and
 *   donut need exactly one category; a single number is a KPI.
 * - Long category lists keep the biggest values and fold the rest into "Other".
 */

import { metricPresentation } from '@/features/reports/reportPresentation';
import { formatMeasure, type MeasureUnit } from '@/features/workbench-ui/charts';

import type { WidgetVisual } from './types';

export const VISUALS: { id: WidgetVisual; label: string; hint: string }[] = [
  { id: 'kpi', label: 'Number', hint: 'One headline figure' },
  { id: 'table', label: 'Table', hint: 'Every row, sortable' },
  { id: 'hbar', label: 'Ranked bars', hint: 'Biggest first, names readable' },
  { id: 'bar', label: 'Columns', hint: 'Compare a few categories or periods' },
  { id: 'stacked_bar', label: 'Stacked', hint: 'Each period split by a category' },
  { id: 'line', label: 'Line', hint: 'Trend over time' },
  { id: 'area', label: 'Area', hint: 'Trend over time, filled' },
  { id: 'pie', label: 'Pie', hint: 'Share of a whole, few categories' },
  { id: 'donut', label: 'Donut', hint: 'Share of a whole, few categories' },
];

const CATEGORY_GRAINS = new Set(['customer', 'distributor', 'product', 'bu', 'sales_model', 'channel', 'region', 'site_label', 'promo_type']);

export const TOP_N = 15;
export const PIE_SLICES = 6; // five named slices plus "Other"
export const SERIES_MAX = 7; // seven named series plus "Other"

/** Which visuals make sense for a breakdown, best first. */
export function visualsFor(grains: string[]): WidgetVisual[] {
  const g = grains.map((x) => x.trim().toLowerCase()).filter(Boolean);
  const hasPeriod = g.includes('period');
  const cats = g.filter((x) => CATEGORY_GRAINS.has(x));
  // A Number tile shows the metric's overall total, whatever the breakdown.
  if (!g.length) return ['kpi', 'table'];
  if (hasPeriod && cats.length === 0) return ['line', 'area', 'bar', 'table', 'kpi'];
  if (hasPeriod && cats.length === 1) return ['line', 'stacked_bar', 'area', 'table', 'kpi'];
  if (hasPeriod) return ['table', 'line', 'stacked_bar', 'kpi'];
  if (cats.length === 1) return ['hbar', 'bar', 'donut', 'pie', 'table', 'kpi'];
  return ['hbar', 'table', 'kpi'];
}

/** The visual to use: the saved one when it fits the breakdown, otherwise the best fit. */
export function effectiveVisual(saved: WidgetVisual, grains: string[]): WidgetVisual {
  const ok = visualsFor(grains);
  return ok.includes(saved) ? saved : ok[0];
}

type Row = Record<string, unknown>;

function str(v: unknown): string | null {
  if (v == null) return null;
  const s = String(v).trim();
  return s ? s : null;
}

/** Period label of a row or series point. */
export function periodLabel(r: Row): string | null {
  return str(r.bucket_key) ?? str(r.period) ?? str(r.period_label) ?? str(r.quarter) ?? str(r.week) ?? null;
}

const NAME_FIELDS: Array<[string, string, string]> = [
  ['customer_name', 'customer_id', 'Unnamed customer'],
  ['distributor_name', 'distributor_id', 'Unnamed distributor'],
  ['product_name', 'product_id', 'Unnamed product'],
];

/** Category label of a row by name; ids never shown as codes. */
export function categoryLabel(r: Row): string {
  const parts: string[] = [];
  for (const [nameKey, idKey, unnamed] of NAME_FIELDS) {
    const n = str(r[nameKey]);
    if (n) parts.push(n);
    else if (r[idKey] != null) parts.push(unnamed);
  }
  for (const k of ['sales_model', 'bu', 'product_line', 'channel', 'region', 'site_label', 'promo_type']) {
    const v = str(r[k]);
    if (v) parts.push(v);
  }
  return parts.join(' · ') || 'All';
}

/** Full row label: category, then period when there is one. */
export function rowLabel(r: Row): string {
  const cat = categoryLabel(r);
  const per = periodLabel(r);
  if (per && cat !== 'All') return `${cat} · ${per}`;
  return per ?? cat;
}

export type Point = { label: string; value: number; other?: boolean };

/** Biggest ``n`` first; the rest summed into one "Other" point. */
export function topWithOther(points: Point[], n: number): Point[] {
  const sorted = [...points].sort((a, b) => b.value - a.value);
  if (sorted.length <= n) return sorted;
  const head = sorted.slice(0, n - 1);
  const rest = sorted.slice(n - 1).reduce((a, p) => a + p.value, 0);
  return [...head, { label: `Other (${sorted.length - n + 1})`, value: rest, other: true }];
}

function num(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

/** Points by category (no period): rows summed by label. */
export function categoryPoints(rows: Row[] | null): Point[] {
  const by = new Map<string, number>();
  for (const r of rows ?? []) {
    const k = categoryLabel(r);
    by.set(k, (by.get(k) ?? 0) + num(r.value));
  }
  return [...by.entries()].map(([label, value]) => ({ label, value }));
}

/** Points by period, in period order (series first, else rows). */
export function periodPoints(series: Row[] | null, rows: Row[] | null): Point[] {
  const src = series?.length ? series : rows ?? [];
  const by = new Map<string, number>();
  for (const r of src) {
    const k = periodLabel(r) ?? 'All';
    by.set(k, (by.get(k) ?? 0) + num(r.value));
  }
  return [...by.entries()].map(([label, value]) => ({ label, value }));
}

export type SeriesModel = {
  /** One object per period: { period, [seriesKey]: value }. */
  data: Array<Record<string, string | number>>;
  /** Series in colour order; the last may be "Other". */
  keys: { key: string; label: string; other?: boolean }[];
};

/** Period × one category: one series per category, biggest totals first, the tail folded into Other. */
export function periodByCategory(rows: Row[] | null, maxSeries = SERIES_MAX): SeriesModel {
  const totals = new Map<string, number>();
  const cells = new Map<string, Map<string, number>>();
  const periods: string[] = [];
  for (const r of rows ?? []) {
    const p = periodLabel(r) ?? 'All';
    const c = categoryLabel(r);
    if (!cells.has(p)) {
      cells.set(p, new Map());
      periods.push(p);
    }
    cells.get(p)!.set(c, (cells.get(p)!.get(c) ?? 0) + num(r.value));
    totals.set(c, (totals.get(c) ?? 0) + num(r.value));
  }
  const ranked = [...totals.entries()].sort((a, b) => b[1] - a[1]).map(([c]) => c);
  const named = ranked.length > maxSeries + 1 ? ranked.slice(0, maxSeries) : ranked;
  const hasOther = named.length < ranked.length;
  const keys: SeriesModel["keys"] = named.map((label, i) => ({ key: `s${i}`, label }));
  if (hasOther) keys.push({ key: 'other', label: `Other (${ranked.length - named.length})`, other: true });
  const index = new Map(named.map((c, i) => [c, `s${i}`]));
  periods.sort();
  const data = periods.map((p) => {
    const row: Record<string, string | number> = { period: p };
    for (const k of keys) row[k.key] = 0;
    for (const [c, v] of cells.get(p)!) {
      const k = index.get(c) ?? 'other';
      row[k] = (row[k] as number) + v;
    }
    return row;
  });
  return { data, keys };
}

/** Unit of a metric, from the same table the Reports page uses (never guessed from the value's size). */
export function metricUnit(metricKey: string, formula?: string): MeasureUnit {
  return metricPresentation({ key: metricKey, formula: formula ?? '' }).unit;
}

export function formatValue(v: unknown, unit: MeasureUnit): string {
  if (v == null) return '—';
  if (typeof v === 'number') return formatMeasure(v, unit, 'short');
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  return String(v);
}

/** Table columns: names instead of ids, ids hidden; value last. */
export function tableColumns(rows: Row[] | null): { field: string; headerName: string }[] {
  const keys = new Set<string>();
  for (const r of rows ?? []) Object.keys(r).forEach((k) => keys.add(k));
  const hidden = new Set(['customer_id', 'distributor_id', 'product_id', 'bucket_start', 'bucket_end']);
  const header: Record<string, string> = {
    bucket_key: 'Period',
    customer_name: 'Customer',
    distributor_name: 'Distributor',
    product_name: 'Product',
    site_label: 'Store',
    sales_model: 'Sales model',
    bu: 'Business unit',
    product_line: 'Product line',
    promo_type: 'Promotion type',
    value: 'Value',
  };
  const order = ['bucket_key', 'customer_name', 'distributor_name', 'product_name', 'sales_model', 'bu', 'product_line', 'site_label', 'channel', 'region', 'promo_type'];
  const fields = [...keys].filter((k) => !hidden.has(k));
  fields.sort((a, b) => {
    const ia = a === 'value' ? 999 : order.indexOf(a) === -1 ? 500 : order.indexOf(a);
    const ib = b === 'value' ? 999 : order.indexOf(b) === -1 ? 500 : order.indexOf(b);
    return ia - ib;
  });
  return fields.map((f) => ({ field: f, headerName: header[f] ?? f.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase()) }));
}
