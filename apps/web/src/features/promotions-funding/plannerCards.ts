/**
 * Planner-specific headline cards (final wave (e)). Pure functions over what the API returns.
 *
 * Warren 2026-11-19: the cards show EXACT counts. Counts come from `GET /cpor/cases/counts` (current
 * cases only, no page cap) and the aged-stock money value from the aged-stock API's `valuation`.
 * Nothing here prices anything or invents a figure: a missing value is `null`, never zero.
 */

import { PLANNER_PROMOTION_FAMILY } from '@/features/promotions-funding/planner/plannerCalendarScope';

/**
 * True when a paged response carries every row the filter matched (`total` <= rows returned). Used by the
 * action queue's partial-view wording; the cards no longer read a page, they read the count endpoint.
 */
export function pageIsComplete(page: { items: readonly unknown[]; total?: number | null } | undefined | null): boolean {
  return page != null && typeof page.total === 'number' && page.total <= page.items.length;
}

export const STARTING_WINDOW_DAYS = 28;

/** Statuses that are not a live commitment: never counted as "starting". */
export const STARTING_EXCLUDED_STATUSES = ['cancelled', 'rejected'] as const;

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

// --- exact case counts ----------------------------------------------------------------------------

/** `GET /cpor/cases/counts`: current cases only (replaced cases left out), not capped by a page size. */
export type CaseCounts = {
  total_current: number;
  status_counts_current: Record<string, number>;
};

/** Planner headline cards default to reporting customers only (same definition as the timeline). */
const PLANNER_COUNTS_REPORTING = 'reporting_only=true';
/**
 * Step 2 (N-0122): every planner count uses the timeline's scope, the customer sell-through family, so no count
 * includes sell-out (Warren: "The promotion planner shows customer promotions, never sell-out.").
 */
const PLANNER_COUNTS_FAMILY = `promotion_family=${PLANNER_PROMOTION_FAMILY}`;
/** The default (Open) view: open statuses, not replaced, window not ended (the API's `open_only`). */
const PLANNER_COUNTS_OPEN = 'open_only=true';
const COUNTS_PATH = '/api/v1/cpor/cases/counts';

/** The cards' default counts: open customer sell-through cases of reporting customers. */
export const BASE_COUNTS_URL = `${COUNTS_PATH}?${PLANNER_COUNTS_REPORTING}&${PLANNER_COUNTS_FAMILY}&${PLANNER_COUNTS_OPEN}`;

/**
 * The family's whole current book (open and closed), for the cards that count closed cases (Ended). Without it the
 * Ended card would read a made-up zero under the Open scope.
 */
export const BOOK_COUNTS_URL = `${COUNTS_PATH}?${PLANNER_COUNTS_REPORTING}&${PLANNER_COUNTS_FAMILY}`;

/** Awaiting approval: current, open cases in Proposed. */
export function awaitingCountUrl(): string {
  return `${COUNTS_PATH}?${PLANNER_COUNTS_REPORTING}&status=proposed&${PLANNER_COUNTS_FAMILY}&${PLANNER_COUNTS_OPEN}`;
}

/** Starting in 4 weeks: window starts in [today, today + 28 days], cancelled and rejected left out. */
export function startingCountUrl(today: string): { url: string; from: string; to: string } {
  const from = todayIso(today);
  const to = addDaysIso(from, STARTING_WINDOW_DAYS);
  const excluded = STARTING_EXCLUDED_STATUSES.map((s) => `&exclude_status=${s}`).join('');
  return {
    url: `${COUNTS_PATH}?${PLANNER_COUNTS_REPORTING}&window_from=${from}&window_to=${to}${excluded}&${PLANNER_COUNTS_FAMILY}&${PLANNER_COUNTS_OPEN}`,
    from,
    to,
  };
}

/** Count of one status in a counts response; null until the response exists (never a made-up zero). */
export function statusCount(counts: CaseCounts | undefined | null, status: string): number | null {
  if (!counts) return null;
  return counts.status_counts_current?.[status] ?? 0;
}

// --- aged stock (money value computed on the API) -------------------------------------------------

export type AgedStockLineLike = {
  customer_id?: number;
  product_id?: number;
  stock_on_hand?: number | null;
  suggestion_executed?: boolean;
  executed_actions?: string[];
};

export type AgedValueBlock = {
  lines: number;
  units: number;
  /** null when no listed line has a cost. */
  value: number | null;
  lines_with_cost: number;
  lines_without_cost: number;
  units_without_cost: number;
};

export type AgedStockResponseLike = {
  lines?: AgedStockLineLike[];
  truncated?: boolean;
  valuation?: { cost_basis?: string; unplanned: AgedValueBlock; all?: AgedValueBlock };
};

export type UnplannedAgedStock = {
  /** False when the API sent no valuation (units only). */
  valued: boolean;
  /** ZAR value of lines that have a cost; null when none has. Computed on the API. */
  value: number | null;
  units: number;
  lineCount: number;
  linesWithCost: number;
  /** Lines with no cost: counted, never priced at zero. */
  linesWithoutCost: number;
  unitsWithoutCost: number;
  truncated: boolean;
};

/** Slow / unsold stock on lines with no open action. The value is the API's; the client never prices. */
export function unplannedAgedStock(aged: AgedStockResponseLike | undefined | null): UnplannedAgedStock {
  const truncated = Boolean(aged?.truncated);
  const block = aged?.valuation?.unplanned;
  if (block) {
    return {
      valued: true,
      value: block.value,
      units: block.units,
      lineCount: block.lines,
      linesWithCost: block.lines_with_cost,
      linesWithoutCost: block.lines_without_cost,
      unitsWithoutCost: block.units_without_cost,
      truncated,
    };
  }
  const lines = (aged?.lines ?? []).filter((l) => !l.suggestion_executed && !(l.executed_actions?.length ?? 0));
  return {
    valued: false,
    value: null,
    units: lines.reduce((n, l) => n + (Number(l.stock_on_hand) || 0), 0),
    lineCount: lines.length,
    linesWithCost: 0,
    linesWithoutCost: 0,
    unitsWithoutCost: 0,
    truncated,
  };
}

// --- calendar clashes -------------------------------------------------------------------------------

/** `GET /customer-calendar/clashes/summary`; `data_unavailable` when the calendar migration is not applied. */
export type CalendarClashSummary =
  | { clash_count: number; promotion_count: number; customer_count: number; from: string | null; to: string | null }
  | { data_unavailable: true; message?: string };

/** Clashes of our open customer sell-through promotions that end today or later (no sell-out on the planner). */
export function calendarClashUrl(today: string): string {
  return `/api/v1/customer-calendar/clashes/summary?from=${todayIso(today)}&${PLANNER_COUNTS_FAMILY}`;
}

export type ClashCardFigure =
  | { kind: 'count'; count: number; promotions: number; customers: number }
  | { kind: 'unavailable'; message?: string };

export function clashCardFigure(summary: CalendarClashSummary): ClashCardFigure {
  if ('data_unavailable' in summary) return { kind: 'unavailable', message: summary.message };
  return {
    kind: 'count',
    count: summary.clash_count,
    promotions: summary.promotion_count,
    customers: summary.customer_count,
  };
}
