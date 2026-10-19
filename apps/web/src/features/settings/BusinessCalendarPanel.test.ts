import { describe, expect, it } from 'vitest';

import { parseCustomPeriods } from './BusinessCalendarPanel';

describe('parseCustomPeriods', () => {
  it('reads one period per line', () => {
    const { periods, errors } = parseCustomPeriods('2026-01-05, 2026, 1, Jan\n\n2026-02-02;2026;1');
    expect(errors).toEqual([]);
    expect(periods).toEqual([
      { start: '2026-01-05', fiscal_year: 2026, quarter: 1, label: 'Jan' },
      { start: '2026-02-02', fiscal_year: 2026, quarter: 1, label: null },
    ]);
  });

  it('names the line that cannot be read', () => {
    const { errors } = parseCustomPeriods('2026-01-05, 2026, 1\n5 Jan 2026, 2026, 5');
    expect(errors).toEqual(['Line 2: write it as 2026-01-05, 2026, 1, Jan']);
  });
});
