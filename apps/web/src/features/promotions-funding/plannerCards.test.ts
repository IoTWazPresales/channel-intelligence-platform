import { describe, expect, it } from 'vitest';

import {
  CALENDAR_CLASH_CARD,
  addDaysIso,
  awaitingApproval,
  startingNext4Weeks,
  unplannedAgedStockValue,
  type PlannerCardCase,
} from './plannerCards';

const c = (id: number, status: string, window_start: string | null): PlannerCardCase => ({
  id,
  case_code: `C-${id}`,
  status,
  window_start,
});

describe('addDaysIso', () => {
  it('adds days across month and year ends', () => {
    expect(addDaysIso('2026-11-18', 28)).toBe('2026-12-16');
    expect(addDaysIso('2026-12-20', 28)).toBe('2027-01-17');
  });
});

describe('awaitingApproval', () => {
  it('counts only proposed cases and returns their ids', () => {
    const r = awaitingApproval([c(1, 'proposed', null), c(2, 'draft', null), c(3, 'proposed', null), c(4, 'approved', null)]);
    expect(r).toEqual({ count: 2, ids: [1, 3] });
  });
  it('is zero for an empty list', () => {
    expect(awaitingApproval([])).toEqual({ count: 0, ids: [] });
  });
});

describe('startingNext4Weeks', () => {
  const today = '2026-11-18';
  it('includes both ends of [today, today+28]', () => {
    const r = startingNext4Weeks(
      [c(1, 'approved', '2026-11-18'), c(2, 'approved', '2026-12-16'), c(3, 'approved', '2026-12-17'), c(4, 'approved', '2026-11-17')],
      today,
    );
    expect(r.ids).toEqual([1, 2]);
    expect(r.count).toBe(2);
    expect(r.from).toBe('2026-11-18');
    expect(r.to).toBe('2026-12-16');
  });
  it('drops cancelled, rejected, voided and superseded cases and cases with no start', () => {
    const r = startingNext4Weeks(
      [
        c(1, 'cancelled', '2026-11-20'),
        c(2, 'rejected', '2026-11-20'),
        c(3, 'voided', '2026-11-20'),
        c(4, 'superseded', '2026-11-20'),
        c(5, 'approved', null),
        c(6, 'draft', '2026-11-20'),
        c(7, 'active', '2026-11-20'),
      ],
      today,
    );
    expect(r.ids).toEqual([6, 7]);
  });
  it('accepts a Date for today', () => {
    const r = startingNext4Weeks([c(1, 'approved', '2026-11-19')], new Date(Date.UTC(2026, 10, 18, 22, 0, 0)));
    expect(r.ids).toEqual([1]);
  });
});

describe('unplannedAgedStockValue', () => {
  it('sums stock on hand for lines with no open action, in units (the API returns no money value)', () => {
    const r = unplannedAgedStockValue({
      lines: [
        { customer_id: 1, product_id: 1, stock_on_hand: 10, suggestion_executed: false, executed_actions: [] },
        { customer_id: 1, product_id: 2, stock_on_hand: 5.5, suggestion_executed: true, executed_actions: ['promote'] },
        { customer_id: 2, product_id: 3, stock_on_hand: 4 },
        { customer_id: 2, product_id: 4, stock_on_hand: null },
      ],
      truncated: false,
    });
    expect(r.unit).toBe('units');
    expect(r.value).toBe(14);
    expect(r.lineCount).toBe(3);
    expect(r.truncated).toBe(false);
  });
  it('treats a line with executed actions but a false flag as having an open action', () => {
    const r = unplannedAgedStockValue({
      lines: [{ customer_id: 1, product_id: 1, stock_on_hand: 9, suggestion_executed: false, executed_actions: ['move'] }],
    });
    expect(r.value).toBe(0);
    expect(r.lineCount).toBe(0);
  });
  it('carries the truncation flag and handles no data', () => {
    expect(unplannedAgedStockValue({ lines: [], truncated: true })).toMatchObject({ value: 0, truncated: true });
    expect(unplannedAgedStockValue(undefined)).toMatchObject({ value: 0, lineCount: 0, truncated: false });
  });
});

describe('calendar clash placeholder', () => {
  it('is named, unrendered and carries no figure', () => {
    expect(CALENDAR_CLASH_CARD.key).toBe('calendar_clashes');
    expect(CALENDAR_CLASH_CARD.available).toBe(false);
    expect(CALENDAR_CLASH_CARD).not.toHaveProperty('value');
  });
});
