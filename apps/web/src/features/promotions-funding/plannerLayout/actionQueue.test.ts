import { describe, expect, it } from 'vitest';

import { buildActionQueue } from './actionQueue';

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
  it('is empty when nothing waits', () => {
    expect(buildActionQueue({ cases: [], proposed: [], ended: [] })).toEqual([]);
  });
  it('carries a label with the case code and a stage-appropriate hint', () => {
    const [i] = buildActionQueue({ cases: [], proposed: [{ id: 3, case_code: 'C', status: 'proposed', ...base }], ended: [] });
    expect(i.label).toContain('C');
    expect(i.hint.length).toBeGreaterThan(0);
  });
});
