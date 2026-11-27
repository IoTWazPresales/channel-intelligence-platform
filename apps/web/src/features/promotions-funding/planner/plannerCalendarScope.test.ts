import { describe, expect, it } from 'vitest';

import {
  PLANNER_PROMOTION_FAMILY,
  plannerViewFromSearch,
  stageNeedsHistory,
  withPlannerCalendarScope,
} from './plannerCalendarScope';

describe('withPlannerCalendarScope', () => {
  // Changed in step 2 (N-0122). The old assertion expected official_promotion_types=true, which keeps Sell out PP.
  // Warren (t454u): "Correct, Sell through, sell out is disti to reseller and is still valuable but not here."
  it('scopes to reporting customers, the customer sell-through family and open cases by default', () => {
    const sp = withPlannerCalendarScope(new URLSearchParams({ page: '1', page_size: '500' }));
    expect(sp.get('reporting_only')).toBe('true');
    expect(sp.get('promotion_family')).toBe(PLANNER_PROMOTION_FAMILY);
    expect(sp.get('open_only')).toBe('true');
    expect(sp.has('official_promotion_types')).toBe(false);
    expect(sp.get('page')).toBe('1');
  });

  it('History drops open_only and never widens the family', () => {
    const sp = withPlannerCalendarScope(new URLSearchParams({ open_only: 'true', official_promotion_types: 'true' }), {
      history: true,
    });
    expect(sp.has('open_only')).toBe(false);
    expect(sp.get('promotion_family')).toBe(PLANNER_PROMOTION_FAMILY);
    expect(sp.has('official_promotion_types')).toBe(false);
  });

  it('uses the customer sell-through family key the API knows', () => {
    expect(PLANNER_PROMOTION_FAMILY).toBe('customer_sell_through');
  });
});

describe('planner view', () => {
  it('reads Open unless the URL asks for History', () => {
    expect(plannerViewFromSearch(null)).toBe('open');
    expect(plannerViewFromSearch('open')).toBe('open');
    expect(plannerViewFromSearch('anything')).toBe('open');
    expect(plannerViewFromSearch('history')).toBe('history');
  });

  it('a closed stage filter needs History; an open stage does not', () => {
    for (const s of ['ended', 'settled', 'cancelled', 'rejected']) expect(stageNeedsHistory(s)).toBe(true);
    for (const s of ['draft', 'proposed', 'approved', 'active']) expect(stageNeedsHistory(s)).toBe(false);
    expect(stageNeedsHistory(null)).toBe(false);
    expect(stageNeedsHistory('')).toBe(false);
  });
});
