/**
 * A v2 response as chart data. Categories are keyed by breakdown + id (or value), never by label,
 * so two products with the same name stay two bars (fixes the v1 `categoryPoints` label merge, F4).
 * Entity names come from `{e}_name`; a missing id reads "Unassigned" and is not clickable.
 */

import type { SelectDatum } from './clickFilters';
import type { V2Column, V2FilterValue, V2Response, V2Row } from './types';

export type Cat = {
  /** "customer:18", "site_label:Rosebank", "period:2026-W14". */
  key: string;
  breakdown: string;
  value: V2FilterValue | null;
  label: string;
  window?: { from: string; to: string } | null;
};

export function breakdownColumns(resp: V2Response | undefined): V2Column[] {
  return (resp?.columns ?? []).filter((c) => c.kind === 'breakdown');
}

export function measureColumns(resp: V2Response | undefined): V2Column[] {
  return (resp?.columns ?? []).filter((c) => c.kind === 'measure');
}

export function catOf(row: V2Row, col: V2Column): Cat {
  if (col.id === 'period') {
    const k = row.bucket_key == null ? '' : String(row.bucket_key);
    const from = typeof row.bucket_start === 'string' ? row.bucket_start : null;
    const to = typeof row.bucket_end === 'string' ? row.bucket_end : null;
    return { key: `period:${k}`, breakdown: 'period', value: k, label: k || 'Unassigned', window: from && to ? { from, to } : null };
  }
  if (col.fields.length >= 2) {
    const idField = col.fields[0];
    const nameField = col.fields[1];
    const raw = row[idField];
    const id = raw == null || raw === '' ? null : (raw as V2FilterValue);
    const name = row[nameField];
    const label = typeof name === 'string' && name.trim() ? name : id == null ? 'Unassigned' : `Unnamed ${col.label.toLowerCase()}`;
    return { key: `${col.id}:${id ?? 'null'}`, breakdown: col.id, value: id, label };
  }
  const raw = row[col.fields[0] ?? col.id];
  const text = raw == null || String(raw).trim() === '' ? null : String(raw);
  // An attribute's "Unassigned" matches NULL in a v2 filter (N-0115 F4), so it stays clickable.
  return { key: `${col.id}:${text ?? 'Unassigned'}`, breakdown: col.id, value: text ?? 'Unassigned', label: text ?? 'Unassigned' };
}

export function toSelect(c: Cat): SelectDatum {
  return { breakdown: c.breakdown, value: c.value, label: c.label, window: c.window };
}

export function num(v: unknown): number | null {
  if (v == null || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export type CategoryPoint = { key: string; label: string; value: number | null; parts: Cat[]; values: Record<string, number | null> };

/** One point per distinct category (all non-period breakdowns joined), values per measure. */
export function categoryPoints(resp: V2Response | undefined, measureIds: string[]): CategoryPoint[] {
  const cols = breakdownColumns(resp).filter((c) => c.id !== 'period');
  const by = new Map<string, CategoryPoint>();
  for (const row of resp?.rows ?? []) {
    const parts = cols.map((c) => catOf(row, c));
    const key = parts.map((p) => p.key).join('|') || 'all';
    const label = parts.map((p) => p.label).join(' · ') || 'All';
    let pt = by.get(key);
    if (!pt) {
      pt = { key, label, value: null, parts, values: Object.fromEntries(measureIds.map((m) => [m, null])) };
      by.set(key, pt);
    }
    for (const m of measureIds) {
      const v = num(row[m]);
      if (v != null) pt.values[m] = (pt.values[m] ?? 0) + v;
    }
  }
  const first = measureIds[0];
  return [...by.values()].map((p) => ({ ...p, value: first ? p.values[first] : null }));
}

export type PeriodRow = { period: string; bucket_start?: string; bucket_end?: string } & Record<string, string | number | null | undefined>;

function bucketOrder(a: PeriodRow, b: PeriodRow): number {
  const sa = a.bucket_start ?? a.period;
  const sb = b.bucket_start ?? b.period;
  return sa < sb ? -1 : sa > sb ? 1 : 0;
}

/** One row per period bucket, a value per measure, in date order. */
export function periodRows(resp: V2Response | undefined, measureIds: string[]): PeriodRow[] {
  const by = new Map<string, PeriodRow>();
  for (const row of resp?.rows ?? []) {
    const k = row.bucket_key == null ? '' : String(row.bucket_key);
    let pr = by.get(k);
    if (!pr) {
      pr = {
        period: k,
        bucket_start: typeof row.bucket_start === 'string' ? row.bucket_start : undefined,
        bucket_end: typeof row.bucket_end === 'string' ? row.bucket_end : undefined,
      } as PeriodRow;
      for (const m of measureIds) pr[m] = null;
      by.set(k, pr);
    }
    for (const m of measureIds) {
      const v = num(row[m]);
      if (v != null) pr[m] = ((pr[m] as number | null) ?? 0) + v;
    }
  }
  return [...by.values()].sort(bucketOrder);
}

export type SplitSeries = { key: string; label: string; cat: Cat | null; other?: boolean };

/**
 * Period x one category: cap named series without manufacturing an aggregated "Other" value.
 * Additive measures rank by sum; non-additive measures keep the server's category order.
 */
export function periodByCategory(
  resp: V2Response | undefined,
  measureId: string,
  maxSeries = 7,
  additive = true,
): { data: PeriodRow[]; series: SplitSeries[]; omittedSeries?: number } {
  const catCol = breakdownColumns(resp).find((c) => c.id !== 'period');
  if (!catCol) return { data: periodRows(resp, [measureId]), series: [{ key: measureId, label: measureId, cat: null }] };
  const totals = new Map<string, { cat: Cat; total: number }>();
  for (const row of resp?.rows ?? []) {
    const cat = catOf(row, catCol);
    const t = totals.get(cat.key) ?? { cat, total: 0 };
    t.total += num(row[measureId]) ?? 0;
    totals.set(cat.key, t);
  }
  const ranked = additive ? [...totals.values()].sort((a, b) => b.total - a.total || a.cat.label.localeCompare(b.cat.label)) : [...totals.values()];
  const named = ranked.slice(0, maxSeries);
  const index = new Map(named.map((t, i) => [t.cat.key, `s${i}`]));
  const series: SplitSeries[] = named.map((t, i) => ({ key: `s${i}`, label: t.cat.label, cat: t.cat }));
  const by = new Map<string, PeriodRow>();
  for (const row of resp?.rows ?? []) {
    const sk = index.get(catOf(row, catCol).key);
    if (sk == null) continue;
    const k = row.bucket_key == null ? '' : String(row.bucket_key);
    let pr = by.get(k);
    if (!pr) {
      pr = {
        period: k,
        bucket_start: typeof row.bucket_start === 'string' ? row.bucket_start : undefined,
        bucket_end: typeof row.bucket_end === 'string' ? row.bucket_end : undefined,
      } as PeriodRow;
      for (const s of series) pr[s.key] = null;
      by.set(k, pr);
    }
    pr[sk] = num(row[measureId]);
  }
  return { data: [...by.values()].sort(bucketOrder), series, omittedSeries: ranked.length - named.length };
}

/** Data vintage end ("Data to 2026-10-09"), from model explain or a governed handler's vintage. */
export function vintageTo(resp: V2Response | undefined): string | null {
  const dv = resp?.explain?.data_vintage as Record<string, unknown> | null | undefined;
  if (!dv) return null;
  for (const k of ['max', 'bucket_max', 'as_of', 'as_of_date', 'latest']) {
    const v = dv[k];
    if (typeof v === 'string' && v) return v.slice(0, 10);
  }
  return null;
}

export function rowCount(resp: V2Response | undefined): number {
  const n = resp?.explain?.row_count;
  return typeof n === 'number' ? n : resp?.rows.length ?? 0;
}
