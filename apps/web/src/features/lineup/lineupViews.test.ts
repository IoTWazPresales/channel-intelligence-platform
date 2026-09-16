import { describe, expect, it } from 'vitest';

import {
  filterLineupRowsByExactProductId,
  lineupTaskSubtitle,
  parseExactLineupProductId,
  parseLineupApprovalFilter,
} from '@/features/lineup/lineupViews';

describe('lineupViews', () => {
  it('parses approval filter', () => {
    expect(parseLineupApprovalFilter(null)).toBe('all');
    expect(parseLineupApprovalFilter('pending')).toBe('pending');
    expect(parseLineupApprovalFilter('other')).toBe('all');
  });

  it('task subtitle reflects pending view', () => {
    expect(lineupTaskSubtitle({ approval: 'all', periodLabel: 'Q1+Q2', assortmentLabel: '26Q3 assortment' })).toBe(
      '26Q3 assortment',
    );
    expect(lineupTaskSubtitle({ approval: 'pending', periodLabel: 'Q1+Q2', assortmentLabel: '26Q3 assortment' })).toBe(
      'Pending approval',
    );
  });

  it('parses Cover ?product= as an exact integer id', () => {
    expect(parseExactLineupProductId(null)).toBeNull();
    expect(parseExactLineupProductId('')).toBeNull();
    expect(parseExactLineupProductId('  ')).toBeNull();
    expect(parseExactLineupProductId('abc')).toBeNull();
    expect(parseExactLineupProductId('12.3')).toBeNull();
    expect(parseExactLineupProductId('0123')).toBeNull();
    expect(parseExactLineupProductId('12sku')).toBeNull();
    expect(parseExactLineupProductId('42')).toBe(42);
    expect(parseExactLineupProductId(' 7 ')).toBe(7);
  });

  it('filters lineup rows by exact product_id only', () => {
    const rows = [
      { id: 1, product_id: 42 },
      { id: 2, product_id: 420 },
      { id: 3, product_id: 4 },
      { id: 4, product_id: null },
    ];
    expect(filterLineupRowsByExactProductId(rows, 42).map((r) => r.id)).toEqual([1]);
    expect(filterLineupRowsByExactProductId(rows, 4).map((r) => r.id)).toEqual([3]);
    expect(filterLineupRowsByExactProductId(rows, 99)).toEqual([]);
  });
});
