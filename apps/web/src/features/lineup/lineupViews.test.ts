import { describe, expect, it } from 'vitest';

import { lineupTaskSubtitle, parseLineupApprovalFilter } from '@/features/lineup/lineupViews';

describe('lineupViews', () => {
  it('parses approval filter', () => {
    expect(parseLineupApprovalFilter(null)).toBe('all');
    expect(parseLineupApprovalFilter('pending')).toBe('pending');
    expect(parseLineupApprovalFilter('other')).toBe('all');
  });

  it('task subtitle reflects pending view', () => {
    expect(lineupTaskSubtitle({ approval: 'all', periodLabel: 'Q1+Q2', assortmentLabel: '26Q3 assortment' })).toBe(
      '26Q3 assortment',
    );
    expect(lineupTaskSubtitle({ approval: 'pending', periodLabel: 'Q1+Q2', assortmentLabel: '26Q3 assortment' })).toBe(
      'Pending approval',
    );
  });
});
