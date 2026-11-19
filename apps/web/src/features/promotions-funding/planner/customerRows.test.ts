import { describe, expect, it } from 'vitest';

import { buildTimeline, type TimelineCase } from '@/features/promotions-funding/plannerLayout/timelineModel';

import { customerRows } from './customerRows';

const c = (id: number, customer: string | null, start: string, end: string, status = 'active'): TimelineCase => ({
  id,
  case_code: `C-${id}`,
  customer_name: customer,
  status,
  window_start: start,
  window_end: end,
});

describe('customerRows', () => {
  it('makes one row per customer, ordered by name, with every promotion of that customer in the row', () => {
    const model = buildTimeline(
      [
        c(1, 'Beta', '2026-11-01', '2026-11-10'),
        c(2, 'Alpha', '2026-11-05', '2026-11-12'),
        c(3, 'Beta', '2026-12-01', '2026-12-10'),
      ],
      '2026-11-19',
    );
    const rows = customerRows(model.bars);
    expect(rows.map((r) => r.customer)).toEqual(['Alpha', 'Beta']);
    expect(rows[1].bars.map((b) => b.id)).toEqual([1, 3]);
    // Non-overlapping promotions share one lane: one visual row per customer.
    expect(rows[1].laneCount).toBe(1);
  });

  it('stacks overlapping promotions of one customer in extra lanes instead of drawing them on top of each other', () => {
    const model = buildTimeline(
      [c(1, 'Alpha', '2026-11-01', '2026-11-20'), c(2, 'Alpha', '2026-11-10', '2026-11-30'), c(3, 'Alpha', '2026-12-05', '2026-12-09')],
      '2026-11-19',
    );
    const [row] = customerRows(model.bars);
    expect(row.laneCount).toBe(2);
    expect(row.bars.find((b) => b.id === 1)!.lane).toBe(0);
    expect(row.bars.find((b) => b.id === 2)!.lane).toBe(1);
    // The third starts after the first ended, so it reuses lane 0.
    expect(row.bars.find((b) => b.id === 3)!.lane).toBe(0);
  });

  it('groups names case-insensitively and puts cases with no customer name in one last row', () => {
    const model = buildTimeline(
      [c(1, 'alpha', '2026-11-01', '2026-11-03'), c(2, 'Alpha ', '2026-11-05', '2026-11-06'), c(3, null, '2026-11-01', '2026-11-02')],
      '2026-11-19',
    );
    const rows = customerRows(model.bars);
    expect(rows).toHaveLength(2);
    expect(rows[0].bars.map((b) => b.id)).toEqual([1, 2]);
    expect(rows[1].customer).toBe('');
  });
});
