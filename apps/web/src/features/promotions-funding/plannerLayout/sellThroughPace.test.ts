import { describe, expect, it } from 'vitest';

import { elapsedShare, paceApplies, reconTotals, sellThroughPace } from './sellThroughPace';

// Requirement (Warren, 27 Nov): "At risk means an open promotion whose sell-through is behind the plan for the time
// already elapsed." and "Ended, settled, and cancelled cases are not 'at risk'."
const open = (extra: Record<string, unknown> = {}) => ({
  id: 1,
  status: 'active',
  window_start: '2026-11-01',
  window_end: '2026-11-30',
  ...extra,
});
const recon = (lines: { estimate_qty: number; cst_units: number }[], extra: Record<string, unknown> = {}) => ({
  data_unavailable: false,
  reason: null,
  lines,
  cst_vintage: { max_period_start_date: '2026-11-16' },
  ...extra,
});

describe('elapsedShare', () => {
  it('counts whole days, today included', () => {
    expect(elapsedShare('2026-11-01', '2026-11-30', '2026-11-15')).toBeCloseTo(15 / 30);
    expect(elapsedShare('2026-11-01', '2026-11-01', '2026-11-01')).toBe(1);
  });
  it('is 1 once the window has ended and null before it starts', () => {
    expect(elapsedShare('2026-11-01', '2026-11-30', '2026-12-05')).toBe(1);
    expect(elapsedShare('2026-11-01', '2026-11-30', '2026-10-31')).toBeNull();
  });
  it('is null for a missing or inverted window', () => {
    expect(elapsedShare(null, '2026-11-30', '2026-11-15')).toBeNull();
    expect(elapsedShare('2026-11-30', '2026-11-01', '2026-11-15')).toBeNull();
  });
});

describe('paceApplies', () => {
  it('applies to every open stage once the window has started', () => {
    for (const status of ['draft', 'proposed', 'approved', 'active']) {
      expect(paceApplies(open({ status }), '2026-11-10')).toBe(true);
    }
  });
  it('never applies to ended, settled, cancelled or rejected cases', () => {
    for (const status of ['ended', 'settled', 'cancelled', 'rejected']) {
      expect(paceApplies(open({ status }), '2026-11-10')).toBe(false);
    }
  });
  it('does not apply before the window starts or to a replaced case', () => {
    expect(paceApplies(open(), '2026-10-31')).toBe(false);
    expect(paceApplies(open({ superseded_by_case_id: 2 }), '2026-11-10')).toBe(false);
  });
});

describe('sellThroughPace', () => {
  it('is behind when units sold are below plan times the share elapsed', () => {
    const p = sellThroughPace(open(), recon([{ estimate_qty: 200, cst_units: 40 }, { estimate_qty: 100, cst_units: 0 }]), '2026-11-15');
    expect(p).toMatchObject({ state: 'behind', planned: 300, sold: 40, expectedByNow: 150, dataThrough: '2026-11-16' });
  });
  it('is on pace at or above the expected units', () => {
    expect(sellThroughPace(open(), recon([{ estimate_qty: 300, cst_units: 150 }]), '2026-11-15').state).toBe('on_pace');
  });
  it('claims no risk without sell-through or planned units', () => {
    expect(sellThroughPace(open(), recon([], { data_unavailable: true, reason: 'no_cst' }), '2026-11-15')).toEqual({
      state: 'no_data',
      reason: 'no_cst',
    });
    expect(sellThroughPace(open(), recon([], { reason: 'no_estimate_lines' }), '2026-11-15')).toEqual({
      state: 'no_data',
      reason: 'no_estimate_lines',
    });
  });
  it('an ended case is never judged, whatever it sold', () => {
    expect(sellThroughPace(open({ status: 'ended' }), recon([{ estimate_qty: 300, cst_units: 0 }]), '2026-12-05')).toEqual({
      state: 'not_started',
    });
  });
});

describe('reconTotals', () => {
  it('sums planned and sold units over the plan products', () => {
    expect(reconTotals(recon([{ estimate_qty: 10, cst_units: 3 }, { estimate_qty: 5, cst_units: 7 }]))).toEqual({
      planned: 15,
      sold: 10,
    });
  });
  it('is null when nothing is planned or no sell-through exists', () => {
    expect(reconTotals(recon([]))).toBeNull();
    expect(reconTotals(recon([{ estimate_qty: 10, cst_units: 3 }], { data_unavailable: true }))).toBeNull();
  });
});
