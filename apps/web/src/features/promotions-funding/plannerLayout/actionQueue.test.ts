import { describe, expect, it } from 'vitest';

import { buildActionQueue, queueSummary } from './actionQueue';

const base = { customer_name: 'N', window_start: '2026-11-01', window_end: '2026-11-10' };

describe('buildActionQueue', () => {
  it('returns awaiting-approval, reapproval and claim-evidence-pending items, deduped by case and kind', () => {
    const q = buildActionQueue({
      cases: [
        { id: 1, case_code: 'A', status: 'approved', needs_reapproval: true, ...base },
        { id: 2, case_code: 'B', status: 'draft', ...base },
      ],
      proposed: [{ id: 3, case_code: 'C', status: 'proposed', ...base }],
      ended: [
        { id: 4, case_code: 'D', status: 'ended', settle_readiness: { claim_evidence_count: 0 }, ...base },
        { id: 5, case_code: 'E', status: 'ended', settle_readiness: { claim_evidence_count: 2 }, ...base },
        { id: 1, case_code: 'A', status: 'ended', needs_reapproval: true, settle_readiness: { claim_evidence_count: 1 }, ...base },
      ],
    });
    expect(q.map((i) => [i.kind, i.caseId])).toEqual([
      ['reapproval', 1],
      ['awaiting_approval', 3],
      ['claim_evidence_pending', 4],
    ]);
  });
  it('treats ended cases without readiness data as claim evidence pending (existing rule: count defaults to 0)', () => {
    const q = buildActionQueue({ cases: [], proposed: [], ended: [{ id: 9, case_code: 'Z', status: 'ended', ...base }] });
    expect(q.map((i) => i.kind)).toEqual(['claim_evidence_pending']);
  });
  it('leaves out replaced cases (superseded_by_case_id set), in every condition', () => {
    const q = buildActionQueue({
      cases: [{ id: 1, case_code: 'A', status: 'approved', needs_reapproval: true, superseded_by_case_id: 8, ...base }],
      proposed: [
        { id: 2, case_code: 'B', status: 'proposed', superseded_by_case_id: 8, ...base },
        { id: 3, case_code: 'C', status: 'proposed', superseded_by_case_id: null, ...base },
      ],
      ended: [{ id: 4, case_code: 'D', status: 'ended', superseded_by_case_id: 8, ...base }],
    });
    expect(q.map((i) => [i.kind, i.caseId])).toEqual([['awaiting_approval', 3]]);
  });
  it('is empty when nothing waits', () => {
    expect(buildActionQueue({ cases: [], proposed: [], ended: [] })).toEqual([]);
  });
  it('carries a label with the case code and a stage-appropriate hint', () => {
    const [i] = buildActionQueue({ cases: [], proposed: [{ id: 3, case_code: 'C', status: 'proposed', ...base }], ended: [] });
    expect(i.label).toContain('C');
    expect(i.hint.length).toBeGreaterThan(0);
  });
});

describe('overdue approvals', () => {
  const proposed = (id: number, start: string | null) => ({ id, case_code: `P${id}`, status: 'proposed', customer_name: 'N', window_start: start, window_end: '2026-12-31' });
  it('flags a proposed case whose window has started as an overdue approval', () => {
    const q = buildActionQueue({
      cases: [],
      proposed: [proposed(1, '2026-11-10'), proposed(2, '2026-11-19'), proposed(3, '2026-12-01'), proposed(4, null)],
      ended: [],
      today: '2026-11-19',
    });
    expect(q.map((i) => [i.caseId, i.overdue])).toEqual([
      [1, true],
      [2, false],
      [3, false],
      [4, false],
    ]);
    expect(q[0].label).toContain('overdue');
    expect(q[0].hint).toContain('2026-11-10');
    expect(q[1].label).not.toContain('overdue');
  });
  it('flags nothing as overdue when no day is given', () => {
    const q = buildActionQueue({ cases: [], proposed: [proposed(1, '2020-01-01')], ended: [] });
    expect(q[0].overdue).toBe(false);
  });
});

describe('queueSummary', () => {
  it('counts the queue by kind for the queue cards', () => {
    const q = buildActionQueue({
      cases: [{ id: 1, case_code: 'A', status: 'approved', needs_reapproval: true, customer_name: 'N', window_start: '2026-11-01', window_end: '2026-11-10' }],
      proposed: [
        { id: 2, case_code: 'B', status: 'proposed', customer_name: 'N', window_start: '2026-11-01', window_end: '2026-11-10' },
        { id: 3, case_code: 'C', status: 'proposed', customer_name: 'N', window_start: '2026-12-01', window_end: '2026-12-10' },
      ],
      ended: [{ id: 4, case_code: 'D', status: 'ended', customer_name: 'N', window_start: '2026-10-01', window_end: '2026-10-10' }],
      today: '2026-11-19',
    });
    // Warren (27 Nov) added `behindPlan` to the summary; the other counts are unchanged.
    expect(queueSummary(q)).toEqual({
      total: 4,
      reapproval: 1,
      awaitingApproval: 2,
      overdueApprovals: 1,
      evidenceOutstanding: 1,
      behindPlan: 0,
    });
  });
  it('is all zero for an empty queue', () => {
    expect(queueSummary([])).toEqual({
      total: 0,
      reapproval: 0,
      awaitingApproval: 0,
      overdueApprovals: 0,
      evidenceOutstanding: 0,
      behindPlan: 0,
    });
  });
});

describe('sell-through behind plan (Warren, 27 Nov)', () => {
  const behind = (id: number, extra: Record<string, unknown> = {}) => ({
    id,
    case_code: `B${id}`,
    status: 'active',
    window_start: '2026-11-01',
    window_end: '2026-11-30',
    planned: 300,
    sold: 40,
    expectedByNow: 190,
    elapsed: 19 / 30,
    ...extra,
  });
  it('queues each behind-plan case once and counts it as behindPlan', () => {
    const q = buildActionQueue({ cases: [], proposed: [], ended: [], behindPlan: [behind(7), behind(7)] });
    expect(q).toHaveLength(1);
    expect(q[0]).toMatchObject({ kind: 'sell_through_behind', caseId: 7, label: 'B7 · sell-through behind plan' });
    expect(q[0].hint).toBe('Sold 40 of 300 planned units; about 190 expected with 63% of the window gone.');
    expect(queueSummary(q).behindPlan).toBe(1);
  });
  it('skips a replaced case', () => {
    const q = buildActionQueue({ cases: [], proposed: [], ended: [], behindPlan: [behind(8, { superseded_by_case_id: 9 })] });
    expect(q).toEqual([]);
  });
  it('an ended case without a claim file is evidence outstanding, never behind plan', () => {
    const q = buildActionQueue({
      cases: [],
      proposed: [],
      ended: [{ id: 4, case_code: 'D', status: 'ended', window_start: '2026-10-01', window_end: '2026-10-10' }],
    });
    expect(queueSummary(q)).toMatchObject({ evidenceOutstanding: 1, behindPlan: 0 });
  });
});
