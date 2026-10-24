import { axisTitle, type MeasureUnit } from '@/features/workbench-ui/charts';
import { isAdditive, measureUnit } from './catalog';
import { catOf, num, type Cat } from './shape';
import type { V2Measure, V2Response, V2Row, WidgetDisplay } from './types';

export function semanticUnit(m: V2Measure): string {
  return m.unit ?? measureUnit(m);
}

export function measureHeading(m: V2Measure): string {
  if (m.unit === 'units_per_week') return `${m.label} (units/week)`;
  if (m.unit === 'usd_per_unit') return `${m.label} (US$/unit)`;
  const known = ['units', 'count', 'usd', 'zar', 'ratio'];
  if (m.unit && !known.includes(m.unit)) return `${m.label} (${m.unit.replace(/_/g, ' ')})`;
  return axisTitle(m.label, measureUnit(m));
}

export type AdvancedSeries = {
  key: string; label: string; kind: 'bar' | 'line' | 'area';
  axis: 'left' | 'right'; unit: MeasureUnit;
};

// Normalize old/invalid stored assignments to exactly one measure on each axis.
export function dualSeries(ms: V2Measure[], display?: WidgetDisplay): AdvancedSeries[] {
  const right = ms.find((m) => display?.series?.[m.id]?.axis === 'right')?.id ?? ms[1]?.id;
  return ms.map((m, i) => ({
    key: m.id, label: m.label,
    kind: display?.series?.[m.id]?.kind ?? (i === 0 ? 'bar' : 'line'),
    axis: m.id === right ? 'right' : 'left', unit: measureUnit(m),
  }));
}

export type GrainRow = V2Row & { __key: string; __label: string; __cat: Cat };
export type ShapeResult<T> = { ok: true; value: T } | { ok: false; reason: string };

export function grainRows(resp: V2Response, breakdownId: string): ShapeResult<GrainRow[]> {
  const col = resp.columns.find((c) => c.kind === 'breakdown' && c.id === breakdownId);
  if (!col) return { ok: false, reason: 'The answer is missing the selected breakdown.' };
  const seen = new Set<string>();
  const out: GrainRow[] = [];
  for (const row of resp.rows) {
    const cat = catOf(row, col);
    if (seen.has(cat.key)) return { ok: false, reason: 'The answer has repeated categories. Use a table to inspect it.' };
    seen.add(cat.key);
    out.push({ ...row, __key: cat.key, __label: cat.label, __cat: cat });
  }
  // Period query sort can be by value. Draw time in chronological order.
  if (breakdownId === 'period') out.sort((a, b) =>
    String(a.__cat.window?.from ?? a.__cat.label).localeCompare(String(b.__cat.window?.from ?? b.__cat.label)));
  return { ok: true, value: out };
}

export type ScatterDatum = { key: string; label: string; x: number; y: number; cat: Cat };
export function scatterRows(rows: GrainRow[], x: string, y: string) {
  const data: ScatterDatum[] = [];
  for (const row of rows) {
    const xv = num(row[x]);
    const yv = num(row[y]);
    if (xv != null && yv != null) data.push({ key: row.__key, label: row.__label, x: xv, y: yv, cat: row.__cat });
  }
  return { data, omitted: rows.length - data.length };
}

export type PivotField = { field: string; category: Cat; measure: V2Measure };
export type PivotRow = { key: string; cat: Cat; values: Record<string, number | null>; totals: Record<string, number | null> };
export type Pivot = {
  columns: Cat[]; fields: PivotField[]; rows: PivotRow[];
  columnTotals: Record<string, number | null>; grand: Record<string, number | null>;
  additive: V2Measure[]; partial: boolean;
};

const sumPresent = (values: (number | null)[]): number | null => {
  const finite = values.filter((v): v is number => v != null);
  return finite.length ? finite.reduce((a, b) => a + b, 0) : null;
};

export function pivotRows(resp: V2Response, ms: V2Measure[], ids: string[]): ShapeResult<Pivot> {
  if (ids.length !== 2 || ms.length === 0) return { ok: false, reason: 'Pivot needs two breakdowns and at least one measure.' };
  const bds = ids.map((id) => resp.columns.find((c) => c.kind === 'breakdown' && c.id === id));
  const [rcol, ccol] = bds;
  if (!rcol || !ccol) return { ok: false, reason: 'The answer is missing a pivot breakdown.' };
  const columns = new Map<string, Cat>();
  const rows = new Map<string, PivotRow>();
  const seen = new Set<string>();
  const raw = resp.rows.map((row) => ({ row, r: catOf(row, rcol), c: catOf(row, ccol) }));
  for (const { r, c } of raw) {
    const key = JSON.stringify([r.key, c.key]);
    if (seen.has(key)) return { ok: false, reason: 'The answer has repeated pivot cells. Use a table to inspect it.' };
    seen.add(key);
    columns.set(c.key, c);
    if (!rows.has(r.key)) rows.set(r.key, { key: r.key, cat: r, values: {}, totals: {} });
  }
  if (columns.size > 24) return { ok: false, reason: 'Too many columns; filter or swap' };
  // Preserve API category order; period headings must be chronological.
  const cols = [...columns.values()];
  if (ids[1] === 'period') cols.sort((a, b) => String(a.window?.from ?? a.label).localeCompare(String(b.window?.from ?? b.label)));
  const fieldMap = new Map<string, string>();
  const fields = cols.flatMap((category, ci) => ms.map((measure, mi) => {
    const field = `v${ci}_${mi}`;
    fieldMap.set(JSON.stringify([category.key, measure.id]), field);
    return { field, category, measure };
  }));
  for (const r of rows.values()) for (const f of fields) r.values[f.field] = null;
  for (const { row, r, c } of raw) for (const m of ms) {
    const field = fieldMap.get(JSON.stringify([c.key, m.id]))!;
    rows.get(r.key)!.values[field] = num(row[m.id]);
  }
  const additive = resp.truncated ? [] : ms.filter(isAdditive);
  for (const r of rows.values()) for (const m of additive)
    r.totals[m.id] = sumPresent(fields.filter((f) => f.measure.id === m.id).map((f) => r.values[f.field]));
  const columnTotals: Record<string, number | null> = {};
  for (const f of fields) if (additive.some((m) => m.id === f.measure.id))
    columnTotals[f.field] = sumPresent([...rows.values()].map((r) => r.values[f.field]));
  const rr = [...rows.values()];
  if (ids[0] === 'period') rr.sort((a, b) => String(a.cat.window?.from ?? a.cat.label).localeCompare(String(b.cat.window?.from ?? b.cat.label)));
  return { ok: true, value: {
    columns: cols, fields, rows: rr, additive, columnTotals,
    grand: Object.fromEntries(ms.map((m) => [m.id, num(resp.totals[m.id])])), partial: resp.truncated,
  } };
}
