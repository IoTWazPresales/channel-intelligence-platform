import { describe, expect, it } from 'vitest';

import { nextLineupQuarter } from './lineupQuarter';

describe('nextLineupQuarter', () => {
  it('uses the following quarter inside a year', () => {
    expect(nextLineupQuarter(new Date('2026-09-30T12:00:00Z'))).toEqual({
      periodStart: '2026-10-01',
      periodLabel: '2026Q4',
    });
  });

  it('rolls Q4 into Q1 of the next year', () => {
    expect(nextLineupQuarter(new Date('2026-12-31T23:00:00Z'))).toEqual({
      periodStart: '2027-01-01',
      periodLabel: '2027Q1',
    });
  });
});
