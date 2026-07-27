import { describe, expect, it } from 'vitest';

import {
  DSI_MATCH_BASIS_CROSS_DISTI,
  DSI_MATCH_BASIS_TEMPORAL_SAME_DISTI,
  isReservedDsiDuplicateMatchBasis,
  parseStewardPossibleDuplicateHint,
} from './stewardDuplicateHintContract';
import { contextPossibleDuplicateOf } from '@/app/(app)/admin/imports/dsi/dsiStewardCandidateFilterLogic';

describe('parseStewardPossibleDuplicateHint', () => {
  it('parses reserved match_basis values without dropping them', () => {
    const hint = parseStewardPossibleDuplicateHint({
      normalized_key: 'peer',
      similarity_score: 0.9,
      match_basis: DSI_MATCH_BASIS_TEMPORAL_SAME_DISTI,
    });
    expect(hint?.match_basis).toBe(DSI_MATCH_BASIS_TEMPORAL_SAME_DISTI);
    expect(isReservedDsiDuplicateMatchBasis(hint?.match_basis)).toBe(true);
  });

  it('parses optional evidence metadata', () => {
    const hint = parseStewardPossibleDuplicateHint({
      normalized_key: 'peer',
      similarity_score: 1,
      match_basis: DSI_MATCH_BASIS_CROSS_DISTI,
      matched_value: 'Acme Ltd',
      matched_field: 'dealer_group_raw',
      dealer_group_norm: 'acme',
      source_customer_norm: 'acme store',
      distributor_scope: [1, 2],
      evidence_reason: 'cross_disti_single_product',
    });
    expect(hint).toMatchObject({
      normalized_key: 'peer',
      match_basis: DSI_MATCH_BASIS_CROSS_DISTI,
      matched_value: 'Acme Ltd',
      distributor_scope: [1, 2],
    });
  });
});

describe('contextPossibleDuplicateOf (contract-backed)', () => {
  it('round-trips reserved basis through context parser', () => {
    const hints = contextPossibleDuplicateOf({
      possible_duplicate_of: [
        {
          normalized_key: 'peer',
          similarity_score: 0.88,
          match_basis: 'source_customer_similar',
        },
      ],
    });
    expect(hints[0]?.match_basis).toBe('source_customer_similar');
  });
});
