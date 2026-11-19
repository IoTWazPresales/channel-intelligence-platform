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

/** Final wave (b): `?customer=<id>&period=<YYYY-MM-DD>` opens one customer's slice of the master line-up. */
export type LineupSlice = { customerId: number; periodStart: string };

export function parseLineupSlice(customer: string | null | undefined, period: string | null | undefined): LineupSlice | null {
  const customerId = parseExactLineupProductId(customer);
  const p = (period ?? '').trim();
  if (customerId == null || !/^\d{4}-\d{2}-\d{2}$/.test(p)) return null;
  return { customerId, periodStart: p };
}

/** Link to the workbench (plan lines and economics) scoped to the same customer/period slice. */
export function workbenchSliceHref(slice: LineupSlice): string {
  const q = new URLSearchParams({ customer: String(slice.customerId), period: slice.periodStart });
  return `/commercial-planner?${q.toString()}`;
}

export function filterLineupRowsBySlice<T extends { customer_id?: number | null; period_start: string }>(
  rows: T[],
  slice: LineupSlice | null,
): T[] {
  if (!slice) return rows;
  return rows.filter((r) => r.customer_id === slice.customerId && r.period_start === slice.periodStart);
}

export type LineupGroup = {
  key: string;
  customerId: number;
  customerName: string;
  periodStart: string;
  periodLabel: string;
  lines: number;
  pending: number;
  approved: number;
  rejected: number;
  plannedUnits: number;
};

const PENDING = new Set(['draft', 'pending_approval', 'submitted']);

/** One group per customer and period, newest period first, then customer name. Rows without a customer id are skipped. */
export function groupLineupRows(
  rows: Array<{
    customer_id?: number | null;
    customer_name?: string | null;
    customer_code?: string | null;
    period_start: string;
    period_label: string | null;
    approval_status: string;
    planned_volume_units: number;
  }>,
): LineupGroup[] {
  const groups = new Map<string, LineupGroup>();
  for (const r of rows) {
    if (r.customer_id == null) continue;
    const key = `${r.customer_id}|${r.period_start}`;
    let g = groups.get(key);
    if (!g) {
      g = {
        key,
        customerId: r.customer_id,
        customerName: r.customer_name || r.customer_code || `Customer ${r.customer_id}`,
        periodStart: r.period_start,
        periodLabel: r.period_label || r.period_start,
        lines: 0,
        pending: 0,
        approved: 0,
        rejected: 0,
        plannedUnits: 0,
      };
      groups.set(key, g);
    }
    g.lines += 1;
    if (PENDING.has(r.approval_status)) g.pending += 1;
    else if (r.approval_status === 'approved') g.approved += 1;
    else if (r.approval_status === 'rejected') g.rejected += 1;
    g.plannedUnits += Number(r.planned_volume_units) || 0;
  }
  return [...groups.values()].sort(
    (a, b) => b.periodStart.localeCompare(a.periodStart) || a.customerName.localeCompare(b.customerName),
  );
}
