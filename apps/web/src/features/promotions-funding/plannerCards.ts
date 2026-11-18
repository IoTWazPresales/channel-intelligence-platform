/**
 * Planner-specific headline cards (final wave (e)). Pure functions over data the planner already loads.
 * Nothing here invents a price or a cost: a card that has no API value says so (units, not money).
 */

export type PlannerCardCase = {
  id: number;
  case_code: string;
  status: string;
  window_start?: string | null;
};

/** Statuses that are not a live commitment: never counted as "starting". */
const NOT_STARTING = new Set(['cancelled', 'rejected', 'voided', 'superseded']);

export const STARTING_WINDOW_DAYS = 28;

const DAY_MS = 86_400_000;

function isoToUtcMs(iso: string): number {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return Date.UTC(y, (m ?? 1) - 1, d ?? 1);
}

function utcMsToIso(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

/** Calendar date (YYYY-MM-DD) of a Date or ISO string, in the viewer's local calendar for a Date. */
export function todayIso(now: Date | string = new Date()): string {
  if (typeof now === 'string') return now.slice(0, 10);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
}

export function addDaysIso(iso: string, days: number): string {
  return utcMsToIso(isoToUtcMs(iso) + days * DAY_MS);
}

export type CaseCardResult = { count: number; ids: number[] };

/** Cases in the existing proposed (awaiting approval) status. */
export function awaitingApproval(cases: readonly PlannerCardCase[]): CaseCardResult {
  const ids = cases.filter((c) => c.status === 'proposed').map((c) => c.id);
  return { count: ids.length, ids };
}

export type StartingResult = CaseCardResult & { from: string; to: string };

/** Cases whose window_start is in [today, today + 28 days], excluding non-commitments. */
export function startingNext4Weeks(cases: readonly PlannerCardCase[], today: Date | string = new Date()): StartingResult {
  const from = todayIso(today);
  const to = addDaysIso(from, STARTING_WINDOW_DAYS);
  const ids = cases
    .filter((c) => {
      if (!c.window_start || NOT_STARTING.has(c.status)) return false;
      const s = c.window_start.slice(0, 10);
      return s >= from && s <= to;
    })
    .map((c) => c.id);
  return { count: ids.length, ids, from, to };
}

export type AgedStockLineLike = {
  customer_id?: number;
  product_id?: number;
  stock_on_hand?: number | null;
  suggestion_executed?: boolean;
  executed_actions?: string[];
};

export type AgedStockResponseLike = { lines?: AgedStockLineLike[]; truncated?: boolean };

export type UnplannedAgedStock = {
  /** The aged-stock API returns stock on hand in units only, no money value. An API value is a follow-up. */
  unit: 'units';
  value: number;
  lineCount: number;
  truncated: boolean;
};

/** Slow / unsold stock on lines with no open action (no executed action, flag false). Units, not money. */
export function unplannedAgedStockValue(aged: AgedStockResponseLike | undefined | null): UnplannedAgedStock {
  const lines = (aged?.lines ?? []).filter((l) => !l.suggestion_executed && !(l.executed_actions?.length ?? 0));
  const value = lines.reduce((n, l) => n + (Number(l.stock_on_hand) || 0), 0);
  return { unit: 'units', value, lineCount: lines.length, truncated: Boolean(aged?.truncated) };
}

/**
 * Reserved place for the calendar-clash card. It needs the customer promotion calendar endpoint (lane (d)),
 * which is not merged yet. `available: false` means the surface renders nothing and never a placeholder figure.
 */
export const CALENDAR_CLASH_CARD = {
  key: 'calendar_clashes',
  label: 'Calendar clashes',
  available: false,
  blockedBy: 'final-wave (d) customer promotion calendar endpoint',
} as const;
