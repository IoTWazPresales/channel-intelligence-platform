import { describe, expect, it } from 'vitest';

import { withPlannerCalendarScope } from './plannerCalendarScope';

describe('withPlannerCalendarScope', () => {
  it('adds reporting and official promotion type flags', () => {
    const sp = withPlannerCalendarScope(new URLSearchParams({ page: '1', page_size: '500' }));
    expect(sp.get('reporting_only')).toBe('true');
    expect(sp.get('official_promotion_types')).toBe('true');
    expect(sp.get('page')).toBe('1');
  });
});