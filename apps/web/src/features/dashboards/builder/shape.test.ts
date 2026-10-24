import { describe, expect, it } from 'vitest';

import { periodByCategory } from './shape';
import type { V2Response } from './types';

describe('period series preserve grouped values', () => {
  it('does not sum omitted rates into an invented Other series or turn null into zero', () => {
    const response: V2Response = {
      ok: true, truncated: false, refusals: [], totals: {},
      columns: [
        { id: 'period', kind: 'breakdown', label: 'Month', fields: ['bucket_key', 'bucket_start', 'bucket_end'] },
        { id: 'customer', kind: 'breakdown', label: 'Customer', fields: ['customer_id', 'customer_name'] },
      ],
      rows: Array.from({ length: 10 }, (_, i) => ({ bucket_key: '2026-07', customer_id: i + 1, customer_name: `Customer ${i + 1}`, rate: i === 0 ? null : 0.3 })),
    };
    const shaped = periodByCategory(response, 'rate', 7, false);
    expect(shaped.series).toHaveLength(7);
    expect(shaped.omittedSeries).toBe(3);
    expect(shaped.series.some((s) => /Other/.test(s.label))).toBe(false);
    expect(shaped.data[0].s0).toBeNull();
    expect(shaped.data[0].s1).toBe(0.3);
    expect(shaped.data[0]).not.toHaveProperty('other');
  });
});
