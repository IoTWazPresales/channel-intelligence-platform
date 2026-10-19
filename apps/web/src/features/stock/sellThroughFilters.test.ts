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

  it('round-trips customers, product groups and custom dates', () => {
    const f = readFilters(
      new URLSearchParams('from=2026-01-01&to=2026-06-30&customers=299,12&bu=NB|Gaming&compare=none&vat=inc_vat'),
    );
    expect(f.preset).toBeNull();
    expect(f.customers).toEqual([299, 12]);
    expect(f.businessUnits).toEqual(['NB', 'Gaming']);
    expect(writeFilters(f).toString()).toBe(
      'from=2026-01-01&to=2026-06-30&compare=none&vat=inc_vat&customers=299%2C12&bu=NB%7CGaming',
    );
    const w = resolveWindow(f, PRESETS);
    expect(w).toEqual({ dateFrom: '2026-01-01', dateTo: '2026-06-30', grain: 'week' });
    const q = new URLSearchParams(overviewQuery(f, w!));
    expect(q.get('customer_ids')).toBe('299,12');
    expect(q.get('business_units')).toBe('NB|Gaming');
    expect(q.get('vat')).toBe('inc_vat');
  });

  it('offers days only for windows up to 120 days', () => {
    expect(grainsFor({ dateFrom: '2026-01-01', dateTo: '2026-12-31' })).toEqual(['week', 'month', 'quarter']);
    expect(grainsFor({ dateFrom: '2026-09-01', dateTo: '2026-10-18' })).toContain('day');
  });
});
