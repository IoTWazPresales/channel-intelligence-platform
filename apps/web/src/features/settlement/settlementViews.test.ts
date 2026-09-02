import { describe, expect, it } from 'vitest';

import {
  parseSettlementSavedView,
  parseSettlementStateFilter,
  settlementStateToStatusParam,
} from '@/features/settlement/settlementViews';

describe('settlementViews', () => {
  it('parses state filter with open default', () => {
    expect(parseSettlementStateFilter(null)).toBe('open');
    expect(parseSettlementStateFilter('blocked')).toBe('blocked');
    expect(parseSettlementStateFilter('bogus')).toBe('open');
  });

  it('parses saved view', () => {
    expect(parseSettlementSavedView('desk')).toBe('desk');
    expect(parseSettlementSavedView('blocked')).toBe('blocked');
    expect(parseSettlementSavedView('other')).toBe('desk');
  });

  it('maps open state to multi-status API hint', () => {
    expect(settlementStateToStatusParam('open')).toContain('active');
    expect(settlementStateToStatusParam('blocked')).toBe('');
  });
});
