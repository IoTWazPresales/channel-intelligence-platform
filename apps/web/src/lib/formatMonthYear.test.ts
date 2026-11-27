import { describe, expect, it } from 'vitest';

import { formatMonthYear } from './formatMonthYear';

describe('formatMonthYear', () => {
  it('formats a date-only value and a timestamp as short month and year', () => {
    expect(formatMonthYear('2026-07-06')).toBe('Jul 2026');
    expect(formatMonthYear('2026-07-31T23:30:00Z')).toBe('Jul 2026');
  });

  it('does not move a first-of-month date into the previous month', () => {
    expect(formatMonthYear('2026-08-01')).toBe('Aug 2026');
  });

  it('returns null for an empty or unreadable value', () => {
    expect(formatMonthYear(null)).toBeNull();
    expect(formatMonthYear('')).toBeNull();
    expect(formatMonthYear('not a date')).toBeNull();
  });
});
