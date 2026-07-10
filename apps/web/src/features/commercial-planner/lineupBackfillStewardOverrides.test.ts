import { describe, expect, it } from 'vitest';

import {
  buildAutoBaseline,
  buildCumulativeStewardPayload,
  collectPendingStewardDeltas,
  hasPendingStewardDeltas,
} from './lineupBackfillStewardOverrides';

const proposals = [
  {
    proposal_key: 'f0:Sheet1:NB:2025 Q1',
    period_label: '2025 Q1',
    business_unit: 'NB',
  },
  {
    proposal_key: 'f1:Sheet1:NR:unknown',
    period_label: null,
    business_unit: 'NR',
  },
];

describe('lineupBackfillStewardOverrides', () => {
  it('builds cumulative payload from auto baseline across multiple steward passes', () => {
    const baseline = buildAutoBaseline(proposals);

    const afterFixA = buildCumulativeStewardPayload(
      proposals,
      { [proposals[0].proposal_key]: '2025 Q1', [proposals[1].proposal_key]: '2026 Q1' },
      { [proposals[0].proposal_key]: 'NB', [proposals[1].proposal_key]: 'NR' },
      baseline,
    );
    expect(afterFixA[proposals[1].proposal_key]).toEqual({ period_label: '2026 Q1' });

    const proposalsAfterRerun = [
      { ...proposals[0] },
      { ...proposals[1], period_label: '2026 Q1' },
    ];
    const afterFixB = buildCumulativeStewardPayload(
      proposalsAfterRerun,
      {
        [proposals[0].proposal_key]: '2025 Q1',
        [proposals[1].proposal_key]: '2026 Q1',
      },
      {
        [proposals[0].proposal_key]: 'PF',
        [proposals[1].proposal_key]: 'NR',
      },
      baseline,
    );
    expect(afterFixB[proposals[0].proposal_key]).toEqual({ business_unit: 'PF' });
    expect(afterFixB[proposals[1].proposal_key]).toEqual({ period_label: '2026 Q1' });
  });

  it('detects pending deltas only before re-run', () => {
    const pending = collectPendingStewardDeltas(
      [{ proposal_key: 'a', period_label: 'Q1', business_unit: 'NB' }],
      { a: 'Q2' },
      { a: 'NB' },
    );
    expect(pending.a).toEqual({ period_label: 'Q2' });
    expect(
      hasPendingStewardDeltas(
        [{ proposal_key: 'a', period_label: 'Q2', business_unit: 'NB' }],
        { a: 'Q2' },
        { a: 'NB' },
      ),
    ).toBe(false);
  });
});
