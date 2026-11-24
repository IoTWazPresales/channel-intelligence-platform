import { describe, expect, it } from 'vitest';

import {
  barGeometry,
  buildTimeline,
  defaultTimelineViewWindow,
  monthTicks,
  monthTicksForAxis,
  orderByCustomer,
  scrollLeftForViewWindow,
  statusLane,
  weekTicks,
} from './timelineModel';

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

describe('monthTicksForAxis', () => {
  it('thins labels on a long axis', () => {
    const ticks = monthTicksForAxis('2020-01-01', '2026-12-31', 6);
    expect(ticks.length).toBeLessThanOrEqual(7);
    expect(ticks[0].label).toMatch(/Jan 2020/);
    expect(ticks[ticks.length - 1].label).toMatch(/Dec 2026/);
  });
});

describe('defaultTimelineViewWindow', () => {
  it('centres roughly six months around today', () => {
    const w = defaultTimelineViewWindow('2026-06-15');
    expect(w.start).toBe('2026-03-01');
    expect(w.end).toBe('2026-09-30');
  });
});

describe('scrollLeftForViewWindow', () => {
  it('offsets scroll so the view window start is visible', () => {
    const left = scrollLeftForViewWindow('2026-03-01', '2020-01-01', '2026-12-31', 2400, 432);
    expect(left).toBeGreaterThan(0);
  });
});

describe('weekTicks', () => {
  it('ticks every Monday on the axis, with the day and month as the label', () => {
    // 2026-11-01 is a Sunday, so the first Monday is the 2nd.
    const ticks = weekTicks('2026-11-01', '2026-11-30');
    expect(ticks.map((t) => t.label)).toEqual(['2 Nov', '9 Nov', '16 Nov', '23 Nov', '30 Nov']);
    expect(ticks[0].leftPct).toBeCloseTo((1 / 30) * 100, 5);
    expect(ticks[4].leftPct).toBeCloseTo((29 / 30) * 100, 5);
  });
});

describe('statusLane', () => {
  it('maps case statuses onto the four mock-up lanes (Live, Approved, Planned, Ended)', () => {
    expect(statusLane('active')).toEqual({ key: 'live', label: 'Live' });
    expect(statusLane('approved')).toEqual({ key: 'approved', label: 'Approved' });
    for (const s of ['draft', 'proposed', 'rejected']) expect(statusLane(s)).toEqual({ key: 'planned', label: 'Planned' });
    for (const s of ['ended', 'settled']) expect(statusLane(s)).toEqual({ key: 'ended', label: 'Ended' });
    expect(statusLane('cancelled')).toEqual({ key: 'cancelled', label: 'Cancelled' });
  });
  it('never hides an unknown status: it keeps its own name', () => {
    expect(statusLane('on_hold')).toEqual({ key: 'other', label: 'on_hold' });
  });
});

describe('orderByCustomer', () => {
  const r = (id: number, name: string | null, s: string) => ({ ...row(id, s, '2026-12-31'), customer_name: name });
  it('groups bars by customer (name, case-insensitive), earliest start first, and marks the first row of each', () => {
    const t = buildTimeline(
      [r(1, 'beta', '2026-11-20'), r(2, 'Alpha', '2026-12-01'), r(3, 'Beta', '2026-11-05'), r(4, 'Alpha', '2026-11-02')],
      '2026-11-18',
    );
    const ordered = orderByCustomer(t.bars);
    expect(ordered.map((o) => o.bar.id)).toEqual([4, 2, 3, 1]);
    expect(ordered.map((o) => o.firstOfCustomer)).toEqual([true, false, true, false]);
  });
  it('puts cases without a customer name last, each its own group', () => {
    const t = buildTimeline([r(1, null, '2026-11-02'), r(2, 'Alpha', '2026-11-09')], '2026-11-18');
    const ordered = orderByCustomer(t.bars);
    expect(ordered.map((o) => o.bar.id)).toEqual([2, 1]);
    expect(ordered[1].firstOfCustomer).toBe(true);
  });
});
