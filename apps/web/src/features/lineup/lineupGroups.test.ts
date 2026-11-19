import { describe, expect, it } from 'vitest';

import { filterLineupRowsBySlice, groupLineupRows, parseLineupSlice } from './lineupViews';

const row = (over: Record<string, unknown>) => ({
  customer_id: 1,
  customer_name: 'Customer A',
  customer_code: 'A',
  period_start: '2026-01-01',
  period_label: '26Q1',
  approval_status: 'draft',
  planned_volume_units: 10,
  ...over,
});

describe('line-up groups and slices (Final wave b)', () => {
  it('parses a slice only for an integer customer and an ISO date', () => {
    expect(parseLineupSlice('5', '2026-01-01')).toEqual({
      customerId: 5,
      periodStart: '2026-01-01',
    });
    expect(parseLineupSlice('x', '2026-01-01')).toBeNull();
    expect(parseLineupSlice('5', 'Q1')).toBeNull();
    expect(parseLineupSlice(null, null)).toBeNull();
  });

  it('filters the master rows to one customer and period, and returns all rows without a slice', () => {
    const rows = [row({}), row({ customer_id: 2 }), row({ period_start: '2026-04-01' })];
    expect(filterLineupRowsBySlice(rows, { customerId: 1, periodStart: '2026-01-01' })).toEqual([
      rows[0],
    ]);
    expect(filterLineupRowsBySlice(rows, null)).toBe(rows);
  });

  it('groups by customer and period with status counts, newest period first', () => {
    const groups = groupLineupRows([
      row({ approval_status: 'draft' }),
      row({ approval_status: 'approved', planned_volume_units: 5 }),
      row({ approval_status: 'rejected' }),
      row({
        customer_id: 2,
        customer_name: 'Customer B',
        period_start: '2026-04-01',
        period_label: '26Q2',
      }),
      row({ customer_id: null }),
    ]);
    expect(
      groups.map((g) => [g.key, g.lines, g.pending, g.approved, g.rejected, g.plannedUnits])
    ).toEqual([
      ['2|2026-04-01', 1, 1, 0, 0, 10],
      ['1|2026-01-01', 3, 1, 1, 1, 25],
    ]);
  });
});
