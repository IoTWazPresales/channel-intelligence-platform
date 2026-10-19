import { describe, expect, it } from 'vitest';

import { grainsFor, overviewQuery, readFilters, resolveWindow, writeFilters, type SellThroughPreset } from './sellThroughFilters';

const PRESETS: SellThroughPreset[] = [
  { key: 'last_4_weeks', label: 'Last 4 weeks', date_from: '2026-09-21', date_to: '2026-10-18', grain: 'day' },
  { key: 'last_13_weeks', label: 'Last 13 weeks', date_from: '2026-07-20', date_to: '2026-10-18', grain: 'week' },
];

describe('sell-through filters in the address', () => {
  it('defaults to the last 13 weeks against last year', () => {
    const f = readFilters(new URLSearchParams());
    expect(f.preset).toBe('last_13_weeks');
    expect(f.compare).toBe('prior_year');
    expect(resolveWindow(f, PRESETS)).toEqual({ dateFrom: '2026-07-20', dateTo: '2026-10-18', grain: 'week' });
  });

  it('round-trips customers, one product, added filters and custom dates', () => {
    const f = readFilters(
      new URLSearchParams(
        'from=2026-01-01&to=2026-06-30&customers=299,12&product=5&pl=X1400VA&f.spec%3ARAM=16GB&f.spec%3ARAM=32GB&f.site=&compare=none&vat=inc_vat',
      ),
    );
    expect(f.preset).toBeNull();
    expect(f.customers).toEqual([299, 12]);
    expect(f.product).toEqual({ id: 5, label: 'X1400VA' });
    expect(f.dims).toEqual([
      { key: 'spec:RAM', values: ['16GB', '32GB'] },
      { key: 'site', values: [] },
    ]);
    const again = readFilters(writeFilters(f));
    expect(again).toEqual(f);
    const w = resolveWindow(f, PRESETS);
    expect(w).toEqual({ dateFrom: '2026-01-01', dateTo: '2026-06-30', grain: 'week' });
    const q = new URLSearchParams(overviewQuery(f, w!));
    expect(q.get('customer_ids')).toBe('299,12');
    expect(q.get('product_ids')).toBe('5');
    expect(q.getAll('f.spec:RAM')).toEqual(['16GB', '32GB']);
    expect(q.has('f.site')).toBe(false); // an added filter with nothing picked does not filter
    expect(q.get('vat')).toBe('inc_vat');
  });

  it('reads links written before added filters', () => {
    const f = readFilters(new URLSearchParams('bu=NB|Gaming'));
    expect(f.dims).toEqual([{ key: 'prod:business_unit', values: ['NB', 'Gaming'] }]);
  });

  it('offers days only for windows up to 120 days', () => {
    expect(grainsFor({ dateFrom: '2026-01-01', dateTo: '2026-12-31' })).toEqual(['week', 'month', 'quarter']);
    expect(grainsFor({ dateFrom: '2026-09-01', dateTo: '2026-10-18' })).toContain('day');
  });
});

describe('incomplete periods', () => {
  it('names the customers still to report for the trailing periods only', async () => {
    const { incompleteNote } = await import('./SellThroughOverview');
    expect(
      incompleteNote([
        { label: 'W40', incomplete_customers: ['Old'] },
        { label: 'W41', incomplete_customers: [] },
        { label: 'W42', incomplete_customers: ['HiFi Corp', 'Incredible'] },
      ]),
    ).toBe('W42 not complete: HiFi Corp, Incredible not reported yet.');
    expect(incompleteNote([{ label: 'W42', incomplete_customers: [] }])).toBe('');
  });
});
