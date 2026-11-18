import { describe, expect, it } from 'vitest';

import { barGeometry, buildTimeline, monthTicks } from './timelineModel';

const row = (id: number, s: string | null, e: string | null, status = 'approved') => ({
  id,
  case_code: `C-${id}`,
  status,
  window_start: s,
  window_end: e,
});

describe('buildTimeline', () => {
  it('drops cases with no dates and sorts by start', () => {
    const t = buildTimeline([row(2, '2026-12-01', '2026-12-10'), row(1, '2026-11-01', '2026-11-15'), row(3, null, null)], '2026-11-18');
    expect(t.bars.map((b) => b.id)).toEqual([1, 2]);
    expect(t.undated).toBe(1);
  });
  it('spans all windows and today, padded to whole months', () => {
    const t = buildTimeline([row(1, '2026-11-10', '2026-12-05')], '2026-11-18');
    expect(t.start).toBe('2026-11-01');
    expect(t.end).toBe('2026-12-31');
  });
  it('places a today marker as a percentage inside the axis', () => {
    const t = buildTimeline([row(1, '2026-11-10', '2026-12-05')], '2026-11-18');
    expect(t.todayPct).toBeGreaterThan(0);
    expect(t.todayPct).toBeLessThan(100);
  });
  it('is empty without dated cases', () => {
    const t = buildTimeline([], '2026-11-18');
    expect(t.bars).toEqual([]);
  });
  it('treats an end before the start as a one-day bar', () => {
    const t = buildTimeline([row(1, '2026-11-10', '2026-11-01')], '2026-11-18');
    expect(t.bars[0].widthPct).toBeGreaterThan(0);
  });
});

describe('barGeometry', () => {
  it('gives left and width as percentages of the axis, window end inclusive', () => {
    const g = barGeometry('2026-11-01', '2026-11-10', '2026-11-01', '2026-11-30');
    expect(g.leftPct).toBe(0);
    expect(g.widthPct).toBeCloseTo((10 / 30) * 100, 5);
  });
});

describe('monthTicks', () => {
  it('lists each month start with its position', () => {
    const ticks = monthTicks('2026-11-01', '2026-12-31');
    expect(ticks.map((t) => t.label)).toEqual(['Nov 2026', 'Dec 2026']);
    expect(ticks[0].leftPct).toBe(0);
    expect(ticks[1].leftPct).toBeCloseTo((30 / 61) * 100, 5);
  });
});
