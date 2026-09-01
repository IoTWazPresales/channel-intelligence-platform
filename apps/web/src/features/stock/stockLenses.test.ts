import { describe, expect, it } from 'vitest';

import { DEFAULT_STOCK_LENS, parseStockLens, stockLensLabel, wocBucket } from '@/features/stock/stockLenses';

describe('stockLenses', () => {
  it('defaults unknown lens to movement', () => {
    expect(parseStockLens(null)).toBe(DEFAULT_STOCK_LENS);
    expect(parseStockLens('bogus')).toBe('movement');
  });

  it('parses valid lenses', () => {
    expect(parseStockLens('cover')).toBe('cover');
    expect(parseStockLens('EXECUTION')).toBe('execution');
  });

  it('returns buyer-facing labels', () => {
    expect(stockLensLabel('execution')).toBe('Fill vs plan');
    expect(stockLensLabel('movement')).toBe('Sell-out');
  });

  it('buckets weeks of cover', () => {
    expect(wocBucket(1.2)).toBe('lt2');
    expect(wocBucket(3)).toBe('2to4');
    expect(wocBucket(6)).toBe('4to8');
    expect(wocBucket(10)).toBe('8to13');
    expect(wocBucket(20)).toBe('gte13');
    expect(wocBucket(null)).toBeNull();
  });
});
