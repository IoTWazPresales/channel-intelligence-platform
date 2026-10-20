import { describe, expect, it } from 'vitest';

import {
  categoryLabel,
  categoryPoints,
  effectiveVisual,
  formatValue,
  metricUnit,
  periodByCategory,
  rowLabel,
  tableColumns,
  topWithOther,
  visualsFor,
} from './widgetModel';

describe('widget labels use names, never id codes (Warren 2026-10-20)', () => {
  it('labels by customer and product name', () => {
    expect(categoryLabel({ customer_id: 11, customer_name: 'Amazon SA', product_id: 21, product_name: 'X1407VA', value: 3 })).toBe(
      'Amazon SA · X1407VA',
    );
    expect(rowLabel({ bucket_key: '2026-W42', customer_name: 'Hifi', value: 1 })).toBe('Hifi · 2026-W42');
    expect(categoryLabel({ customer_id: 11, value: 1 })).toBe('Unnamed customer');
    expect(categoryLabel({ customer_id: 11, value: 1 })).not.toContain('C11');
  });

  it('table shows names and hides id columns, value last', () => {
    const cols = tableColumns([{ value: 5, distributor_id: 2, distributor_name: 'Disti', product_id: 1, product_name: 'X1' }]);
    expect(cols.map((c) => c.headerName)).toEqual(['Distributor', 'Product', 'Value']);
  });
});

describe('visuals that fit the breakdown', () => {
  it('offers lines only with a period and pies only for one category', () => {
    expect(visualsFor([])).toEqual(['kpi', 'table']);
    expect(visualsFor(['period'])).toContain('line');
    expect(visualsFor(['customer'])).toEqual(['hbar', 'bar', 'donut', 'pie', 'table', 'kpi']);
    expect(visualsFor(['customer', 'product'])).not.toContain('pie');
    expect(visualsFor(['customer', 'product'])).not.toContain('line');
    expect(visualsFor(['period', 'customer'])).toContain('stacked_bar');
  });

  it('a saved line over customers falls back to ranked bars', () => {
    expect(effectiveVisual('line', ['customer', 'product'])).toBe('hbar');
    expect(effectiveVisual('pie', ['customer'])).toBe('pie');
  });
});

describe('top N with Other', () => {
  it('keeps the biggest and folds the rest', () => {
    const pts = topWithOther(
      [5, 1, 9, 3, 7].map((v, i) => ({ label: `c${i}`, value: v })),
      3,
    );
    expect(pts).toEqual([
      { label: 'c2', value: 9 },
      { label: 'c4', value: 7 },
      { label: 'Other (3)', value: 9, other: true },
    ]);
  });

  it('sums rows with the same name', () => {
    expect(categoryPoints([{ customer_name: 'A', value: 2 }, { customer_name: 'A', value: 3 }])).toEqual([{ label: 'A', value: 5 }]);
  });

  it('splits periods by category with an Other series', () => {
    const rows = ['A', 'B', 'C'].flatMap((c, i) => [
      { bucket_key: '2026-W01', customer_name: c, value: 10 - i },
      { bucket_key: '2026-W02', customer_name: c, value: 1 },
    ]);
    const m = periodByCategory(rows, 1);
    expect(m.keys).toEqual([
      { key: 's0', label: 'A' },
      { key: 'other', label: 'Other (2)', other: true },
    ]);
    expect(m.data[0]).toEqual({ period: '2026-W01', s0: 10, other: 17 });
  });
});

describe('values', () => {
  it("formats by the metric's unit, not by the size of the value", () => {
    expect(metricUnit('fill_rate')).toBe('percent');
    expect(metricUnit('cst_sellthrough_units')).toBe('units');
    expect(formatValue(1, 'units')).toBe('1');
    expect(formatValue(0.82, 'percent')).toBe('82.0%');
    expect(formatValue(1.2, 'weeks')).toBe('1.2w');
  });
});
