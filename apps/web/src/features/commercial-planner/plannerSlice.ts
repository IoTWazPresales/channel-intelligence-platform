import type { LineupSlice } from '@/features/lineup/lineupViews';

/**
 * Final wave (b): a customer/period slice of the workbench. The slice is a filtered view of the
 * plan lines and their stored economics (the same rows and the same `profit_definition` results the
 * calculator already wrote); nothing here prices, copies or recalculates a line.
 */

type PlanWindow = { id: number; period_start: string; period_end: string | null };

const day = (v: string): string => v.slice(0, 10);

/**
 * The plan a line-up period belongs to: the plan whose date window covers the period start
 * (`period_end` empty means open-ended). When windows overlap, the most recently started plan wins,
 * then the highest id, so the answer is deterministic.
 */
export function planCoveringPeriod<T extends PlanWindow>(plans: T[], periodStart: string): T | null {
  const p = day(periodStart);
  let best: T | null = null;
  for (const plan of plans) {
    if (day(plan.period_start) > p) continue;
    if (plan.period_end != null && day(plan.period_end) < p) continue;
    if (
      best == null ||
      day(plan.period_start) > day(best.period_start) ||
      (day(plan.period_start) === day(best.period_start) && plan.id > best.id)
    ) {
      best = plan;
    }
  }
  return best;
}

/** Same row objects, only the slice customer's. No slice returns the very same array. */
export function filterPlanLinesBySlice<T extends { customer_id: number }>(lines: T[], slice: LineupSlice | null): T[] {
  if (!slice) return lines;
  return lines.filter((l) => l.customer_id === slice.customerId);
}

type SummableLine = {
  target_units: number;
  calc_internal_gp_amount?: number | null;
  calc_campaign_support_reserve_amount?: number | null;
  calc_non_campaign_reserve_amount?: number | null;
  calc_flags?: string[] | null;
  economics_calc_currency_code?: string | null;
};

export type SliceSummary = {
  line_count: number;
  total_units: number;
  total_internal_gp_amount: number;
  total_campaign_support_reserve_amount: number;
  total_non_campaign_reserve_amount: number;
  economics_calc_currency_code: string | null;
  flags: string[];
};

const round4 = (n: number): number => Math.round(n * 10_000) / 10_000;

/**
 * Totals for a slice: the same sums `GET /plans/{id}/summary` takes over every line of the plan,
 * taken over the slice's lines instead (that endpoint cannot be scoped to a customer).
 */
export function summarizeSliceLines(lines: SummableLine[]): SliceSummary {
  let units = 0;
  let gp = 0;
  let promo = 0;
  let nonPromo = 0;
  const flags = new Set<string>();
  let ccy: string | null = null;
  for (const l of lines) {
    units += Number(l.target_units) || 0;
    gp += Number(l.calc_internal_gp_amount) || 0;
    promo += Number(l.calc_campaign_support_reserve_amount) || 0;
    nonPromo += Number(l.calc_non_campaign_reserve_amount) || 0;
    for (const f of l.calc_flags ?? []) flags.add(String(f));
    if (ccy == null && (l.economics_calc_currency_code ?? '').trim()) ccy = (l.economics_calc_currency_code as string).trim();
  }
  return {
    line_count: lines.length,
    total_units: round4(units),
    total_internal_gp_amount: round4(gp),
    total_campaign_support_reserve_amount: round4(promo),
    total_non_campaign_reserve_amount: round4(nonPromo),
    economics_calc_currency_code: ccy,
    flags: [...flags].sort(),
  };
}

/** "Customer X · period" chip text. The name comes from the plan's own lines; falls back to code, then id. */
export function sliceChipLabel(
  slice: LineupSlice,
  lines: Array<{ customer_id: number; customer_name?: string | null; customer_code?: string | null }>,
): string {
  const hit = lines.find((l) => l.customer_id === slice.customerId);
  const who = hit?.customer_name?.trim() || hit?.customer_code?.trim() || `Customer ${slice.customerId}`;
  return `${who} · ${day(slice.periodStart)}`;
}
