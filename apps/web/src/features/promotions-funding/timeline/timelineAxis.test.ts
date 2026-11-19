import { describe, expect, it } from 'vitest';
import { barPosition, dateAxis } from './timelineAxis';

describe('shared calendar date axis', () => {
  it('uses inclusive days across month and daylight-saving boundaries', () => {
    const axis = dateAxis(['2026-03-28'], ['2026-04-02']);
    expect(axis.days).toBe(6);
    const bar = barPosition('2026-03-30', '2026-03-31', axis);
    expect(bar?.left).toBeCloseTo(100 / 3, 6);
    expect(bar?.width).toBeCloseTo(100 / 3, 6);
  });
  it('clips events at the requested range and hides ranges outside it', () => {
    const axis = dateAxis([], [], '2026-03-01', '2026-03-10');
    expect(barPosition('2026-02-01', '2026-03-05', axis)).toEqual({ left: 0, width: 50 });
    expect(barPosition('2026-04-01', '2026-04-02', axis)).toBeNull();
  });
  it('has a one-day axis when no evidence exists', () => {
    expect(dateAxis([], [], '2026-03-01', '2026-03-01').days).toBe(1);
  });
});
