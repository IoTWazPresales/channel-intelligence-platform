import { describe, expect, it } from 'vitest';

import { replenishmentRows, type CoverPair } from './StockHealthPanel';

const pair = (id: string, woc: number | null, status: CoverPair['status']): CoverPair => ({
  id, distributor_name: 'D', product_name: 'P', weeks_of_cover: woc, derived_stock: 1, inbound_open: 0, status,
});

describe('replenishmentRows', () => {
  it('keeps the existing breach band only, lowest cover first, capped', () => {
    const rows = replenishmentRows([pair('a', 1.5, 'breach'), pair('b', 0.2, 'breach'), pair('c', 3, 'watch'), pair('d', null, 'breach'), pair('e', 9, 'excess')], 5);
    expect(rows.map((r) => r.id)).toEqual(['b', 'a']);
    expect(replenishmentRows(Array.from({ length: 9 }, (_, i) => pair(String(i), i / 10, 'breach')), 5)).toHaveLength(5);
    expect(replenishmentRows(undefined)).toEqual([]);
  });
});