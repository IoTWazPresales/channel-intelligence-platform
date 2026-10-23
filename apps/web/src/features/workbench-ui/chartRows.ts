/**
 * Row helpers behind the chart toolbar (N-0114): sort and top N for category charts.
 *
 * Pure and value-preserving: they reorder and slice the rows they are given. They never add an
 * "Other" row, never sum, and never touch a value, so the chart shows the caller's numbers as-is.
 */

/** How many rows a category chart shows. The toolbar offers 5/10/15/25/All; callers may start elsewhere. */
export type TopN = number | 'all';

export const TOP_N_OPTIONS: readonly TopN[] = [5, 10, 15, 25, 'all'];

/** `period` keeps the caller's order: rows already arrive chronologically (or in a ranked order). */
export type RowSort = { by: 'value' | 'name' | 'period'; dir?: 'desc' | 'asc' };

export type RowAccessors<T> = {
  value: (row: T) => number | null | undefined;
  name: (row: T) => string;
};

/** The first `n` rows of already-sorted rows, plus how many there were. Same objects, same order. */
export function applyTopN<T>(rows: T[], n: TopN): { shown: T[]; total: number } {
  const total = rows.length;
  if (n === 'all' || n >= total) return { shown: rows.slice(), total };
  return { shown: rows.slice(0, Math.max(0, n)), total };
}

const byName = (a: string, b: string) => a.localeCompare(b, 'en', { sensitivity: 'base', numeric: true });

/**
 * Sort rows for a category chart.
 * - `value`: numeric, highest first unless `dir: 'asc'`; rows without a value go last; ties by name.
 * - `name`: A–Z (case-insensitive, "Store 2" before "Store 10"); `dir: 'desc'` reverses.
 * - `period`: the input order (callers supply rows chronologically; period strings are never parsed).
 */
export function sortRows<T>(rows: T[], sort: RowSort, acc: RowAccessors<T>): T[] {
  if (sort.by === 'period') return rows.slice();
  if (sort.by === 'name') {
    const dir = sort.dir === 'desc' ? -1 : 1;
    return rows.slice().sort((a, b) => dir * byName(acc.name(a), acc.name(b)));
  }
  const dir = sort.dir === 'asc' ? 1 : -1;
  const num = (r: T) => {
    const v = acc.value(r);
    return v == null || !Number.isFinite(v) ? null : v;
  };
  return rows.slice().sort((a, b) => {
    const va = num(a);
    const vb = num(b);
    if (va == null && vb == null) return byName(acc.name(a), acc.name(b));
    if (va == null) return 1;
    if (vb == null) return -1;
    if (va !== vb) return dir * (va - vb);
    return byName(acc.name(a), acc.name(b));
  });
}

/** "Top 10 of 37" when rows were left out; otherwise nothing to say. */
export function topNCaption(shown: number, total: number): string | null {
  return shown < total ? `Top ${shown} of ${total}` : null;
}
