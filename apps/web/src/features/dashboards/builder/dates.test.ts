import { describe, expect, it } from 'vitest';

import { autoGrain, bucketWindow, compareWindow, kpiDelta, minusOneYear, parseDay, resolvePreset } from './dates';

// Local noon, so the viewer's calendar day is 2026-10-23 in any time zone test runners use.
const NOW = new Date(2026, 9, 23, 12, 0, 0);

describe('date presets', () => {
  it('last N weeks end today and are 7N days long (inclusive)', () => {
    expect(resolvePreset({ preset: 'last_13_weeks', from: null, to: null }, NOW)).toEqual({ from: '2026-07-25', to: '2026-10-23' });
    expect(resolvePreset({ preset: 'last_52_weeks', from: null, to: null }, NOW)).toEqual({ from: '2025-10-25', to: '2026-10-23' });
  });

  it('this year and last quarter', () => {
    expect(resolvePreset({ preset: 'this_year', from: null, to: null }, NOW)).toEqual({ from: '2026-01-01', to: '2026-10-23' });
    expect(resolvePreset({ preset: 'last_quarter', from: null, to: null }, NOW)).toEqual({ from: '2026-07-01', to: '2026-09-30' });
    expect(resolvePreset({ preset: 'last_quarter', from: null, to: null }, new Date(2026, 1, 10, 12))).toEqual({ from: '2025-10-01', to: '2025-12-31' });
  });

  it('all time sends no dates; custom uses its own dates', () => {
    expect(resolvePreset({ preset: 'all_time', from: null, to: null }, NOW)).toBeNull();
    expect(resolvePreset(undefined, NOW)).toBeNull();
    expect(resolvePreset({ preset: 'custom', from: '2026-02-01', to: '2026-02-28' }, NOW)).toEqual({ from: '2026-02-01', to: '2026-02-28' });
    expect(resolvePreset({ preset: 'custom', from: null, to: null }, NOW)).toBeNull();
    expect(resolvePreset({ preset: 'custom', from: 'nonsense', to: '2026-02-28' }, NOW)).toEqual({ from: '2000-01-01', to: '2026-02-28' });
  });
});

describe('compare windows', () => {
  it('previous period: same length, immediately before', () => {
    expect(compareWindow({ from: '2026-07-06', to: '2026-10-04' }, 'previous_period')).toEqual({ from: '2026-04-06', to: '2026-07-05' });
    expect(compareWindow({ from: '2026-03-01', to: '2026-03-31' }, 'previous_period')).toEqual({ from: '2026-01-29', to: '2026-02-28' });
  });

  it('previous year: both dates one calendar year back', () => {
    expect(compareWindow({ from: '2026-01-01', to: '2026-10-23' }, 'previous_year')).toEqual({ from: '2025-01-01', to: '2025-10-23' });
  });

  it('leap day: 29 February becomes 28 February a year back', () => {
    expect(compareWindow({ from: '2028-02-01', to: '2028-02-29' }, 'previous_year')).toEqual({ from: '2027-02-01', to: '2027-02-28' });
    const d = parseDay('2024-02-29');
    expect(d && minusOneYear(d).toISOString().slice(0, 10)).toBe('2023-02-28');
    // A previous period across a leap February keeps the day count (29 days before 1 March 2028).
    expect(compareWindow({ from: '2028-03-01', to: '2028-03-29' }, 'previous_period')).toEqual({ from: '2028-02-01', to: '2028-02-29' });
  });

  it('none, or all time: no comparison', () => {
    expect(compareWindow({ from: '2026-01-01', to: '2026-01-31' }, 'none')).toBeNull();
    expect(compareWindow(null, 'previous_period')).toBeNull();
  });
});

describe('KPI delta', () => {
  it('(a - b) / b, rounded to one decimal, with a direction', () => {
    expect(kpiDelta(110, 100)).toEqual({ text: '+10.0%', direction: 'up' });
    expect(kpiDelta(90, 100)).toEqual({ text: '-10.0%', direction: 'down' });
    expect(kpiDelta(100, 100)).toEqual({ text: '0.0%', direction: 'flat' });
  });

  it('null rule: no delta when the comparison is 0, missing or not a number', () => {
    expect(kpiDelta(50, 0)).toBeNull();
    expect(kpiDelta(50, null)).toBeNull();
    expect(kpiDelta(null, 50)).toBeNull();
    expect(kpiDelta(50, Number.NaN)).toBeNull();
  });

  it('ratios change in points, and 0 is a valid comparison for points', () => {
    expect(kpiDelta(0.82, 0.78, { ratio: true })).toEqual({ text: '+4.0 pts', direction: 'up' });
    expect(kpiDelta(0.5, 0, { ratio: true })).toEqual({ text: '+50.0 pts', direction: 'up' });
  });
});

describe('grains and buckets', () => {
  it('sparkline grain: week up to 26 weeks, month up to two years, else quarter', () => {
    expect(autoGrain({ from: '2026-04-27', to: '2026-10-25' })).toBe('week');
    expect(autoGrain({ from: '2025-10-25', to: '2026-10-23' })).toBe('month');
    expect(autoGrain({ from: '2023-01-01', to: '2026-10-23' })).toBe('quarter');
    expect(autoGrain(null)).toBe('quarter');
  });

  it('a bucket click becomes its date window', () => {
    expect(bucketWindow({ bucket_start: '2026-07-06', bucket_end: '2026-07-12' })).toEqual({ from: '2026-07-06', to: '2026-07-12' });
    expect(bucketWindow({})).toBeNull();
  });
});
