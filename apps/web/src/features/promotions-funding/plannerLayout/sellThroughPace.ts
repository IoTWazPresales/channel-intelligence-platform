/**
 * Sell-through pace of an open promotion (Warren, 27 Nov): "At risk means an open promotion whose sell-through is
 * behind the plan for the time already elapsed." and "Ended, settled, and cancelled cases are not 'at risk'."
 *
 * Planned units are the case lines' `estimate_qty`; sold units are the customer's own sell-through inside the case
 * window, both as `GET /cpor/cases/{id}/promo-load-recon` returns them. Nothing here reads sell-out.
 */
import { PLANNER_OPEN_STAGES } from '@/features/promotions-funding/planner/plannerCalendarScope';

export const promoLoadReconUrl = (caseId: number) => `/api/v1/cpor/cases/${caseId}/promo-load-recon`;
export const promoLoadReconKey = (caseId: number) => ['cpor', 'cases', caseId, 'promo-load-recon'] as const;

/** The part of `promo-load-recon` the pace reads. */
export type PromoLoadReconLike = {
  data_unavailable?: boolean;
  reason?: string | null;
  lines?: ReadonlyArray<{ estimate_qty?: number | null; cst_units?: number | null }>;
  cst_vintage?: { max_period_start_date?: string | null } | null;
};

export type PaceCase = {
  id: number;
  status: string;
  window_start?: string | null;
  window_end?: string | null;
  superseded_by_case_id?: number | null;
};

export type SellThroughPace =
  | { state: 'not_started' }
  /** No sell-through for the customer, no window, or no planned units: no pace exists, so no risk is claimed. */
  | { state: 'no_data'; reason: string | null }
  | {
      state: 'behind' | 'on_pace';
      planned: number;
      sold: number;
      /** Planned units times the share of the window already elapsed. */
      expectedByNow: number;
      /** Share of the window elapsed, 0..1 (1 once the window has ended). */
      elapsed: number;
      /** Latest sell-through period start loaded for the customer, if the API reports it. */
      dataThrough: string | null;
    };

const DAY_MS = 86_400_000;

function dayNumber(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(`${String(iso).slice(0, 10)}T00:00:00Z`);
  return Number.isFinite(t) ? Math.round(t / DAY_MS) : null;
}

/** Open (draft, proposed, approved, active), not replaced, and its window has started by `today`. */
export function paceApplies(row: PaceCase, today: string): boolean {
  if (row.superseded_by_case_id != null) return false;
  if (!(PLANNER_OPEN_STAGES as readonly string[]).includes(row.status)) return false;
  const start = dayNumber(row.window_start);
  const now = dayNumber(today);
  return start != null && now != null && start <= now;
}

/**
 * Share of the window elapsed through the end of `today`, counting whole days (a one-day window is fully elapsed on
 * its day). Null when the window is missing, inverted, or has not started.
 */
export function elapsedShare(windowStart: string | null | undefined, windowEnd: string | null | undefined, today: string): number | null {
  const start = dayNumber(windowStart);
  const end = dayNumber(windowEnd);
  const now = dayNumber(today);
  if (start == null || end == null || now == null || end < start || now < start) return null;
  const total = end - start + 1;
  return Math.min(1, (now - start + 1) / total);
}

export function sellThroughPace(row: PaceCase, recon: PromoLoadReconLike, today: string): SellThroughPace {
  if (!paceApplies(row, today)) return { state: 'not_started' };
  if (recon.data_unavailable) return { state: 'no_data', reason: recon.reason ?? null };
  const elapsed = elapsedShare(row.window_start, row.window_end, today);
  if (elapsed == null) return { state: 'no_data', reason: 'missing_window' };
  const totals = reconTotals(recon);
  if (totals == null) return { state: 'no_data', reason: recon.reason ?? 'no_estimate_lines' };
  const { planned, sold } = totals;
  const expectedByNow = planned * elapsed;
  return {
    state: sold < expectedByNow ? 'behind' : 'on_pace',
    planned,
    sold,
    expectedByNow,
    elapsed,
    dataThrough: recon.cst_vintage?.max_period_start_date ?? null,
  };
}

/** Planned units and the customer's sell-through units inside the window, summed over the plan's products. */
export function reconTotals(recon: PromoLoadReconLike): { planned: number; sold: number } | null {
  if (recon.data_unavailable) return null;
  let planned = 0;
  let sold = 0;
  for (const ln of recon.lines ?? []) {
    planned += Number(ln.estimate_qty) || 0;
    sold += Number(ln.cst_units) || 0;
  }
  return planned > 0 ? { planned, sold } : null;
}

/** Why a started open case has no pace, in plain words. */
export function noPaceReason(reason: string | null): string {
  switch (reason) {
    case 'no_cst':
      return 'No customer sell-through is loaded for this customer yet.';
    case 'missing_window':
      return 'The case has no complete window, so no pace can be worked out.';
    case 'no_estimate_lines':
      return 'The plan has no planned units yet.';
    default:
      return 'No sell-through pace is available for this case.';
  }
}
