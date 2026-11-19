import { describe, expect, it } from 'vitest';

import {
  EMPTY_SELECTION,
  SOURCE_OPTIONS,
  allProductIds,
  approveBody,
  basisHeadline,
  evidenceText,
  proposalPath,
  quarterLabel,
  reconcileSelection,
  requestKey,
  toggleProduct,
  toggleSelection,
} from './proposalModel';
import type { Proposal, ProposalLine } from './types';

const pmLine: ProposalLine = {
  product_id: 1,
  sku: 'S-1',
  label: 'One',
  seed_source: 'pm_bottom_cost',
  evidence: { kind: 'pm_bottom_cost', pm_bottom_cost: 12.5, currency: 'USD' },
};

const prevLine: ProposalLine = {
  product_id: 2,
  sku: 'S-2',
  label: 'Two',
  seed_source: 'previous_lineups',
  evidence: { kind: 'previous_lineups', scope: 'master', periods: ['2026-10-01', '2026-07-01'] },
};

function proposal(over: Partial<Proposal>): Proposal {
  return {
    customer: { id: 7, code: 'C-7', name: 'Seven' },
    period_start: '2026-10-01',
    period_label: '2026 Q4',
    source: 'previous_lineups',
    fallback: 'master',
    periods_used: ['2026-10-01', '2026-07-01'],
    basis: 'basis text',
    line_count: 1,
    lines: [prevLine],
    ...over,
  };
}

describe('SOURCE_OPTIONS', () => {
  it('offers exactly the two seed sources with an explanation each', () => {
    expect(SOURCE_OPTIONS.map((o) => o.value)).toEqual(['pm_bottom_cost', 'previous_lineups']);
    const prev = SOURCE_OPTIONS.find((o) => o.value === 'previous_lineups');
    expect(prev?.explanation).toMatch(/own/i);
    expect(prev?.explanation).toMatch(/master/i);
    expect(prev?.explanation).toMatch(/3 most recent/i);
    // Warren 2026-11-19: strictly before the requested quarter; the requested quarter never counts.
    expect(prev?.explanation).toMatch(/before the requested quarter/i);
    expect(prev?.explanation).toMatch(/requested quarter never counts/i);
    expect(SOURCE_OPTIONS.find((o) => o.value === 'pm_bottom_cost')?.explanation).toMatch(/PM bottom cost/);
  });
});

describe('quarterLabel', () => {
  it('turns a period start into a quarter label', () => {
    expect(quarterLabel('2026-10-01')).toBe('2026 Q4');
    expect(quarterLabel('2027-01-01')).toBe('2027 Q1');
    expect(quarterLabel('2026-04-15')).toBe('2026 Q2');
  });
});

describe('evidenceText', () => {
  it('shows the PM bottom cost with its currency', () => {
    expect(evidenceText(pmLine)).toBe('PM bottom cost 12.5 USD');
  });
  it('lists the line-up periods a SKU came from', () => {
    expect(evidenceText(prevLine)).toBe('In line-ups: 2026 Q4, 2026 Q3');
  });
});

describe('basisHeadline', () => {
  it('says which fallback was used and the periods', () => {
    expect(basisHeadline(proposal({ fallback: 'master' }))).toBe(
      'Master line-up, all customers: 2026 Q4, 2026 Q3',
    );
    expect(basisHeadline(proposal({ fallback: 'customer_own' }))).toBe(
      "This customer's own line-ups: 2026 Q4, 2026 Q3",
    );
  });
  it('says nothing about periods for the PM bottom cost source', () => {
    expect(basisHeadline(proposal({ source: 'pm_bottom_cost', fallback: null, periods_used: [] }))).toBe(
      'Master-catalogue items with a PM bottom cost',
    );
  });
  it('says so when no periods were found', () => {
    expect(basisHeadline(proposal({ periods_used: [], lines: [], line_count: 0 }))).toBe(
      'Master line-up, all customers: no line-up periods found',
    );
  });
});

describe('selection', () => {
  it('starts with every proposed line and toggles one at a time', () => {
    const p = proposal({ lines: [pmLine, prevLine], line_count: 2 });
    expect(allProductIds(p)).toEqual(new Set([1, 2]));
    const without = toggleProduct(allProductIds(p), 1);
    expect(without).toEqual(new Set([2]));
    expect(toggleProduct(without, 1)).toEqual(new Set([1, 2]));
  });
  it('builds the approve body from the ticked lines in id order', () => {
    expect(approveBody('pm_bottom_cost', '2026-10-01', new Set([5, 2]))).toEqual({
      source: 'pm_bottom_cost',
      period_start: '2026-10-01',
      product_ids: [2, 5],
    });
  });
});

describe('reconcileSelection', () => {
  const lineFor = (id: number): ProposalLine => ({ ...prevLine, product_id: id, sku: `S-${id}` });
  const withIds = (...ids: number[]) => proposal({ lines: ids.map(lineFor), line_count: ids.length });
  const keyA = requestKey({ customerId: 7, source: 'previous_lineups', periodStart: '2026-10-01' });

  it('ticks every line for a request it has not seen', () => {
    const s = reconcileSelection(EMPTY_SELECTION, keyA, withIds(1, 2));
    expect(s.selected).toEqual(new Set([1, 2]));
    expect(s.unreviewed.size).toBe(0);
  });

  it('keeps exclusions on a refresh, drops vanished lines and leaves new lines unticked', () => {
    const first = reconcileSelection(EMPTY_SELECTION, keyA, withIds(1, 2, 3));
    const unticked = toggleSelection(first, 1);
    const refreshed = reconcileSelection(unticked, keyA, withIds(1, 2, 4));
    expect(refreshed.selected).toEqual(new Set([2]));
    expect(refreshed.unreviewed).toEqual(new Set([4]));
    // A second refresh does not tick the new line either; ticking it counts as reviewed.
    const again = reconcileSelection(refreshed, keyA, withIds(1, 2, 4));
    expect(again.selected).toEqual(new Set([2]));
    const reviewed = toggleSelection(again, 4);
    expect(reviewed.selected).toEqual(new Set([2, 4]));
    expect(reviewed.unreviewed.size).toBe(0);
  });

  it('resets when the customer, period or source changes', () => {
    const unticked = toggleSelection(reconcileSelection(EMPTY_SELECTION, keyA, withIds(1, 2)), 1);
    const otherPeriod = requestKey({ customerId: 7, source: 'previous_lineups', periodStart: '2027-01-01' });
    const otherSource = requestKey({ customerId: 7, source: 'pm_bottom_cost', periodStart: '2026-10-01' });
    const otherCustomer = requestKey({ customerId: 8, source: 'previous_lineups', periodStart: '2026-10-01' });
    for (const key of [otherPeriod, otherSource, otherCustomer]) {
      expect(reconcileSelection(unticked, key, withIds(1, 2)).selected).toEqual(new Set([1, 2]));
    }
  });
});

describe('proposalPath', () => {
  it('encodes the customer, source and period', () => {
    expect(proposalPath(7, 'pm_bottom_cost', '2026-10-01')).toBe(
      '/api/v1/lineup/new-customer/7/proposal?source=pm_bottom_cost&period_start=2026-10-01',
    );
  });
});
