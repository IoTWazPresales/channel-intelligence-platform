/** Default query flags for the planner timeline and the case list under it (reporting customers, official promo types). */
export const PLANNER_CALENDAR_SCOPE_PARAMS = {
  reporting_only: 'true',
  official_promotion_types: 'true',
} as const;

export function withPlannerCalendarScope(sp: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(sp);
  next.set('reporting_only', PLANNER_CALENDAR_SCOPE_PARAMS.reporting_only);
  next.set('official_promotion_types', PLANNER_CALENDAR_SCOPE_PARAMS.official_promotion_types);
  return next;
}