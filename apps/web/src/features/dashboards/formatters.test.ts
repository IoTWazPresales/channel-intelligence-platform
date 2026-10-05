import { describe, expect, it } from 'vitest';

import { formatVintage } from './formatters';

describe('formatVintage', () => {
  it('keeps grain and dates and leaves the source table off the caption', () => {
    expect(
      formatVintage({
        source_table: 'fact_sales_sellout',
        period_grain: 'week',
        bucket_min: '2024-12-30',
        bucket_max: '2026-06-08',
      }),
    ).toBe('week · 2024-12-30 → 2026-06-08');
  });
});
