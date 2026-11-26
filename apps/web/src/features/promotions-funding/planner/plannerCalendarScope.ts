/**
 * The planner's default scope (step 2, N-0122). Warren, standing rules: "Promotions are sell-throughs. Sell-out is
 * distributor (disti) to customer. They must not be mixed. The promotion planner shows customer promotions, never
 * sell-out." and "The planner never shows closed, settled or ended cases (or old years) by default."
 *
 * The family name is the API's vocabulary key (`promotion_type_vocab.PROMOTION_FAMILIES`); which stored types belong
 * to it is decided on the API, in one place, never here.
 */
export const PLANNER_PROMOTION_FAMILY = 'customer_sell_through';

/** Statuses the API's `open_only` keeps (`CPOR_OPEN_CASE_STATUSES`); any other stage is history. */
export const PLANNER_OPEN_STAGES = ['draft', 'proposed', 'approved', 'active'] as const;

export type PlannerView = 'open' | 'history';

/** The URL value of the Open | History toggle (`?view=history`); anything else is the default Open view. */
export function plannerViewFromSearch(value: string | null | undefined): PlannerView {
  return value === 'history' ? 'history' : 'open';
}

/** A stage filter on a closed status (ended, settled, cancelled, rejected) can only be answered by History. */
export function stageNeedsHistory(stage: string | null | undefined): boolean {
  return stage != null && stage !== '' && !(PLANNER_OPEN_STAGES as readonly string[]).includes(stage);
}

/** Query flags for the planner timeline and the case list under it: reporting customers, the customer family. */
export const PLANNER_CALENDAR_SCOPE_PARAMS = {
  reporting_only: 'true',
  promotion_family: PLANNER_PROMOTION_FAMILY,
} as const;

/**
 * Adds the planner scope to a case-list query. `open_only=true` unless History is asked for. History drops only
 * `open_only`; it never widens the family.
 */
export function withPlannerCalendarScope(
  sp: URLSearchParams,
  { history = false }: { history?: boolean } = {},
): URLSearchParams {
  const next = new URLSearchParams(sp);
  next.set('reporting_only', PLANNER_CALENDAR_SCOPE_PARAMS.reporting_only);
  next.set('promotion_family', PLANNER_CALENDAR_SCOPE_PARAMS.promotion_family);
  if (history) next.delete('open_only');
  else next.set('open_only', 'true');
  next.delete('official_promotion_types');
  return next;
}
