import { describe, expect, it } from 'vitest';

import {
  filterPlanLinesBySlice,
  planCoveringPeriod,
  sliceChipLabel,
  summarizeSliceLines,
} from '@/features/commercial-planner/plannerSlice';

describe('planCoveringPeriod (a period is tied to the plan whose date window covers it)', () => {
  const plans = [
    { id: 1, period_start: '2026-07-01', period_end: null },
    { id: 2, period_start: '2026-01-01', period_end: '2026-03-31' },
    { id: 3, period_start: '2026-04-01', period_end: '2026-06-30' },
  ];

  it('picks the plan whose window contains the period start', () => {
    expect(planCoveringPeriod(plans, '2026-01-01')?.id).toBe(2);
    expect(planCoveringPeriod(plans, '2026-03-31')?.id).toBe(2);
    expect(planCoveringPeriod(plans, '2026-04-01')?.id).toBe(3);
  });

  it('treats a plan with no end date as open-ended', () => {
    expect(planCoveringPeriod(plans, '2027-02-01')?.id).toBe(1);
  });

  it('returns null when no plan covers the period', () => {
    expect(planCoveringPeriod(plans, '2025-12-01')).toBeNull();
    expect(planCoveringPeriod([], '2026-01-01')).toBeNull();
  });

  it('prefers the most recently started plan when windows overlap, then the highest id', () => {
    const overlapping = [
      { id: 10, period_start: '2026-01-01', period_end: null },
      { id: 11, period_start: '2026-04-01', period_end: null },
      { id: 12, period_start: '2026-04-01', period_end: '2026-12-31' },
    ];
    expect(planCoveringPeriod(overlapping, '2026-05-01')?.id).toBe(12);
    expect(planCoveringPeriod(overlapping, '2026-02-01')?.id).toBe(10);
  });

  it('ignores a time part on plan dates', () => {
    expect(
      planCoveringPeriod([{ id: 5, period_start: '2026-01-01T00:00:00', period_end: '2026-03-31T00:00:00' }], '2026-03-31')?.id,
    ).toBe(5);
  });
});

describe('filterPlanLinesBySlice (a view of the plan lines, never a copy)', () => {
  const lines = [
    { id: 1, customer_id: 7 },
    { id: 2, customer_id: 8 },
    { id: 3, customer_id: 7 },
  ];

  it('keeps only the slice customer, preserving the same row objects', () => {
    const out = filterPlanLinesBySlice(lines, { customerId: 7, periodStart: '2026-01-01' });
    expect(out.map((l) => l.id)).toEqual([1, 3]);
    expect(out[0]).toBe(lines[0]);
  });

  it('returns the very same array when there is no slice', () => {
    expect(filterPlanLinesBySlice(lines, null)).toBe(lines);
  });
});

describe('summarizeSliceLines (adds up stored per-line results, recalculates nothing)', () => {
  it('sums units, margin and reserves and unions the flags', () => {
    const s = summarizeSliceLines([
      {
        target_units: 10,
        calc_internal_gp_amount: 5.5,
        calc_campaign_support_reserve_amount: 1,
        calc_non_campaign_reserve_amount: 2,
        calc_flags: ['a'],
        economics_calc_currency_code: 'EUR',
      },
      {
        target_units: 5,
        calc_internal_gp_amount: null,
        calc_campaign_support_reserve_amount: 0.5,
        calc_non_campaign_reserve_amount: null,
        calc_flags: ['b', 'a'],
        economics_calc_currency_code: null,
      },
    ]);
    expect(s).toEqual({
      line_count: 2,
      total_units: 15,
      total_internal_gp_amount: 5.5,
      total_campaign_support_reserve_amount: 1.5,
      total_non_campaign_reserve_amount: 2,
      economics_calc_currency_code: 'EUR',
      flags: ['a', 'b'],
    });
  });

  it('is empty-safe', () => {
    expect(summarizeSliceLines([])).toEqual({
      line_count: 0,
      total_units: 0,
      total_internal_gp_amount: 0,
      total_campaign_support_reserve_amount: 0,
      total_non_campaign_reserve_amount: 0,
      economics_calc_currency_code: null,
      flags: [],
    });
  });
});

describe('sliceChipLabel', () => {
  it('names the customer and period', () => {
    expect(sliceChipLabel({ customerId: 7, periodStart: '2026-01-01' }, [{ customer_id: 7, customer_name: 'Customer A', customer_code: 'A' }])).toBe(
      'Customer A · 2026-01-01',
    );
  });

  it('falls back to the code, then to the id, when the plan has no line for the customer', () => {
    expect(sliceChipLabel({ customerId: 7, periodStart: '2026-01-01' }, [{ customer_id: 7, customer_name: null, customer_code: 'A' }])).toBe(
      'A · 2026-01-01',
    );
    expect(sliceChipLabel({ customerId: 7, periodStart: '2026-01-01' }, [])).toBe('Customer 7 · 2026-01-01');
  });
});
