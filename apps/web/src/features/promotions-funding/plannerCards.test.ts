import { describe, expect, it } from 'vitest';

import {
  BASE_COUNTS_URL,
  BOOK_COUNTS_URL,
  STARTING_EXCLUDED_STATUSES,
  addDaysIso,
  awaitingCountUrl,
  calendarClashUrl,
  clashCardFigure,
  pageIsComplete,
  startingCountUrl,
  statusCount,
  unplannedAgedStock,
} from './plannerCards';

describe('addDaysIso', () => {
  it('adds days across month and year ends', () => {
    expect(addDaysIso('2026-11-18', 28)).toBe('2026-12-16');
    expect(addDaysIso('2026-12-20', 28)).toBe('2027-01-17');
  });
});

describe('pageIsComplete', () => {
  it('is complete only when the response carries every matching row (used by the action queue)', () => {
    expect(pageIsComplete({ items: [{}, {}] as never[], total: 2 })).toBe(true);
    expect(pageIsComplete({ items: [{}, {}] as never[], total: 501 })).toBe(false);
  });
  it('is not complete when there is no response or no total', () => {
    expect(pageIsComplete(undefined)).toBe(false);
    expect(pageIsComplete({ items: [] as never[] } as never)).toBe(false);
  });
});

// Step 2 (N-0122) changed the four exact URLs below: each now ends with the customer sell-through family (and
// open_only where the card counts open cases). The old URLs had no family, so they counted Sell out PP.
// Warren (t454u): "Correct, Sell through, sell out is disti to reseller and is still valuable but not here."
// Warren (standing rule): "The promotion planner shows customer promotions, never sell-out."
describe('exact count requests (API counts, not a capped page)', () => {
  it('awaiting approval asks the count endpoint for Proposed', () => {
    expect(awaitingCountUrl()).toBe(
      '/api/v1/cpor/cases/counts?reporting_only=true&status=proposed&promotion_family=customer_sell_through&open_only=true',
    );
  });
  it('starting asks for the [today, today+28] window and leaves out cancelled and rejected', () => {
    const r = startingCountUrl('2026-11-19');
    expect(r.from).toBe('2026-11-19');
    expect(r.to).toBe('2026-12-17');
    expect(r.url).toBe(
      '/api/v1/cpor/cases/counts?reporting_only=true&window_from=2026-11-19&window_to=2026-12-17&exclude_status=cancelled&exclude_status=rejected&promotion_family=customer_sell_through&open_only=true',
    );
    expect([...STARTING_EXCLUDED_STATUSES]).toEqual(['cancelled', 'rejected']);
  });
  it('the Ended card reads the family book (closed cases included); no URL counts another family', () => {
    expect(BOOK_COUNTS_URL).toBe('/api/v1/cpor/cases/counts?reporting_only=true&promotion_family=customer_sell_through');
    for (const u of [BASE_COUNTS_URL, BOOK_COUNTS_URL, awaitingCountUrl(), startingCountUrl('2026-11-19').url]) {
      expect(u).toContain('promotion_family=customer_sell_through');
      expect(u).not.toContain('official_promotion_types');
    }
  });
  it('drafts and ended read the per-status split of the unfiltered counts', () => {
    expect(BASE_COUNTS_URL).toBe(
      '/api/v1/cpor/cases/counts?reporting_only=true&promotion_family=customer_sell_through&open_only=true',
    );
    const counts = { total_current: 9, status_counts_current: { draft: 4, ended: 5 } };
    expect(statusCount(counts, 'draft')).toBe(4);
    expect(statusCount(counts, 'ended')).toBe(5);
    expect(statusCount(counts, 'proposed')).toBe(0);
  });
  it('has no figure at all before the response arrives (never zero)', () => {
    expect(statusCount(undefined, 'draft')).toBeNull();
  });
});

describe('unplannedAgedStock (value comes from the API, never priced here)', () => {
  const valuation = {
    cost_basis: 'customer_reported_unit_mac_else_unit_cost_ex_vat',
    unplanned: {
      lines: 3,
      units: 19,
      value: 65,
      lines_with_cost: 2,
      lines_without_cost: 1,
      units_without_cost: 5,
    },
  };
  it('reads the unplanned block: value, units and how many lines had no cost', () => {
    const r = unplannedAgedStock({ lines: [], truncated: false, valuation });
    expect(r).toMatchObject({
      valued: true,
      value: 65,
      units: 19,
      lineCount: 3,
      linesWithCost: 2,
      linesWithoutCost: 1,
      unitsWithoutCost: 5,
      truncated: false,
    });
  });
  it('keeps "no value" as null, not zero, when no line has a cost', () => {
    const r = unplannedAgedStock({
      valuation: {
        ...valuation,
        unplanned: { ...valuation.unplanned, value: null, lines_with_cost: 0, lines_without_cost: 3, units_without_cost: 19 },
      },
    });
    expect(r.value).toBeNull();
    expect(r.linesWithoutCost).toBe(3);
  });
  it('without a valuation block it shows units only and says it is not valued', () => {
    const r = unplannedAgedStock({
      lines: [
        { customer_id: 1, product_id: 1, stock_on_hand: 10, suggestion_executed: false, executed_actions: [] },
        { customer_id: 1, product_id: 2, stock_on_hand: 5, suggestion_executed: true, executed_actions: ['promote'] },
      ],
    });
    expect(r.valued).toBe(false);
    expect(r.value).toBeNull();
    expect(r.units).toBe(10);
    expect(r.lineCount).toBe(1);
  });
  it('carries the truncation flag and handles no data', () => {
    expect(unplannedAgedStock({ lines: [], truncated: true, valuation })).toMatchObject({ truncated: true });
    expect(unplannedAgedStock(undefined)).toMatchObject({ valued: false, value: null, lineCount: 0 });
  });
});

describe('calendar clash card', () => {
  // Step 2 (N-0122): the clash card counts customer sell-through promotions only (see the quotes above).
  it('asks for clashes of customer sell-through promotions ending today or later', () => {
    expect(calendarClashUrl('2026-11-19')).toBe(
      '/api/v1/customer-calendar/clashes/summary?from=2026-11-19&promotion_family=customer_sell_through',
    );
  });
  it('shows the exact clash count with the promotions and customers involved', () => {
    expect(
      clashCardFigure({ clash_count: 3, promotion_count: 2, customer_count: 2, from: '2026-11-19', to: null }),
    ).toEqual({ kind: 'count', count: 3, promotions: 2, customers: 2 });
  });
  it('is a real zero when there are no clashes', () => {
    expect(clashCardFigure({ clash_count: 0, promotion_count: 0, customer_count: 0, from: null, to: null })).toMatchObject({
      kind: 'count',
      count: 0,
    });
  });
  it('is unavailable, not zero, when the calendar tables are not set up', () => {
    expect(clashCardFigure({ data_unavailable: true, message: 'x' })).toEqual({ kind: 'unavailable', message: 'x' });
  });
});
