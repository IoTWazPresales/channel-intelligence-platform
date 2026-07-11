import { describe, expect, it } from 'vitest';

import {
  addUtcDaysYmd,
  arrivingOrLandedWeekPresetDates,
  overdueSmartPresetDates,
  utcIsoWeekBoundsYmd,
  utcTodayYmd,
} from './shippingUtcDates';

describe('shippingUtcDates', () => {
  it('formats UTC today as YYYY-MM-DD', () => {
    expect(utcTodayYmd(new Date('2026-07-11T23:30:00.000Z'))).toBe('2026-07-11');
    expect(utcTodayYmd(new Date('2026-07-12T00:30:00.000Z'))).toBe('2026-07-12');
  });

  it('overdue date_to is utc yesterday (inclusive bound for promise_date < today)', () => {
    // Local ZA might already be Jul 12 while UTC is still Jul 11 — presets must follow UTC.
    const { referenceDate, dateTo } = overdueSmartPresetDates(new Date('2026-07-11T22:00:00.000Z'));
    expect(referenceDate).toBe('2026-07-11');
    expect(dateTo).toBe('2026-07-10');
  });

  it('ISO week bounds match Monday–Sunday UTC', () => {
    // 2026-07-11 is Saturday → week 2026-07-06 .. 2026-07-12
    expect(utcIsoWeekBoundsYmd('2026-07-11')).toEqual({
      weekStart: '2026-07-06',
      weekEnd: '2026-07-12',
    });
    expect(arrivingOrLandedWeekPresetDates(new Date('2026-07-11T12:00:00.000Z'))).toEqual({
      weekStart: '2026-07-06',
      weekEnd: '2026-07-12',
    });
  });

  it('addUtcDaysYmd crosses month boundaries', () => {
    expect(addUtcDaysYmd('2026-07-01', -1)).toBe('2026-06-30');
  });
});
