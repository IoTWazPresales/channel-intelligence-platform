export type LineupApprovalFilter = 'all' | 'pending';

export type LineupScope = {
  approval: LineupApprovalFilter;
  periodLabel: string;
  assortmentLabel: string;
};

export const DEFAULT_LINEUP_SCOPE: LineupScope = {
  approval: 'all',
  periodLabel: 'Q1+Q2',
  assortmentLabel: '26Q3 assortment',
};

export function parseLineupApprovalFilter(raw: string | null | undefined): LineupApprovalFilter {
  return raw === 'pending' ? 'pending' : 'all';
}

/** Cover deep-link `?product=` — integer product_id only. Missing or non-integer → no filter. */
export function parseExactLineupProductId(raw: string | null | undefined): number | null {
  if (raw == null) return null;
  const trimmed = raw.trim();
  if (trimmed === '') return null;
  if (!/^\d+$/.test(trimmed)) return null;
  const n = Number(trimmed);
  if (!Number.isSafeInteger(n) || n < 1 || String(n) !== trimmed) return null;
  return n;
}

export function filterLineupRowsByExactProductId<T extends { product_id?: number | null }>(
  rows: T[],
  productId: number,
): T[] {
  return rows.filter((row) => row.product_id === productId);
}

export function lineupTaskSubtitle(scope: LineupScope): string {
  if (scope.approval === 'pending') return 'Pending approval';
  return scope.assortmentLabel;
}
