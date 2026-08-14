import { describe, expect, it } from 'vitest';

import {
  hydratePlannerRows,
  markDirty,
  mergePromoPlanSuggestions,
  resetField,
  type SuggestionLine,
} from './promoPlanDraftMerge';

const line = (id: number, qty: number, mac: number): SuggestionLine => ({
  row_key: `${id}::26Q2:${id}`,
  seed_line_id: id,
  product_id: id,
  srp: 100,
  suggested_estimate_qty: qty,
  suggested_cost_basis: mac,
  pod_quarter: '26Q2',
  cover: { weeks: 4, source: 'tenant_default' },
  intake_weighted: {
    cost_basis: mac,
    bucket_a_on_hand: { qty: 1 },
    sellout_value: { flags: ['sellout_value_display_only'] },
  },
});

describe('promoPlanDraftMerge', () => {
  it('hydrates suggestions as clean working values', () => {
    const rows = hydratePlannerRows([line(1, 10, 12.5)]);
    expect(rows[0].estimate_qty).toBe(10);
    expect(rows[0].cost_basis).toBe(12.5);
    expect(rows[0].dirty_fields).toEqual([]);
  });

  it('refresh does not clobber dirty MAC; other cells update', () => {
    let rows = hydratePlannerRows([line(1, 10, 12.5), line(2, 20, 8)]);
    rows = [markDirty(rows[0], 'cost_basis', 18), rows[1]];
    const merged = mergePromoPlanSuggestions(rows, [line(1, 99, 1.1), line(2, 21, 9)]);
    expect(merged[0].cost_basis).toBe(18);
    expect(merged[0].estimate_qty).toBe(99);
    expect(merged[0].dirty_fields).toContain('cost_basis');
    expect(merged[1].cost_basis).toBe(9);
    expect(merged[1].estimate_qty).toBe(21);
  });

  it('reset restores suggested MAC and clears dirty', () => {
    let row = hydratePlannerRows([line(1, 10, 12.5)])[0];
    row = markDirty(row, 'cost_basis', 18);
    row = resetField(row, 'cost_basis');
    expect(row.cost_basis).toBe(12.5);
    expect(row.dirty_fields).toEqual([]);
  });
});
