import { describe, expect, it } from 'vitest';

import {
  shipmentContextPossibleDuplicateOf,
  shipmentDuplicateReviewDecision,
  shipmentHasUnresolvedDuplicateReview,
} from './shipmentMappingCandidateDisplay';

describe('shipmentMappingCandidateDisplay duplicate helpers', () => {
  it('parses string and object possible_duplicate_of hints', () => {
    expect(shipmentContextPossibleDuplicateOf({ possible_duplicate_of: ['a', 'b'] })).toEqual(['a', 'b']);
    expect(
      shipmentContextPossibleDuplicateOf({
        possible_duplicate_of: [{ normalized_key: 'c', similarity_score: 0.9 }, 'd'],
      })
    ).toEqual(['c', 'd']);
  });

  it('detects unresolved vs decided duplicate review', () => {
    const unresolved = { possible_duplicate_of: ['peer'] };
    expect(shipmentHasUnresolvedDuplicateReview(unresolved)).toBe(true);
    expect(shipmentDuplicateReviewDecision(unresolved)).toBeNull();

    const decided = {
      possible_duplicate_of: ['peer'],
      duplicate_review: { decision: 'same_entity' },
    };
    expect(shipmentHasUnresolvedDuplicateReview(decided)).toBe(false);
    expect(shipmentDuplicateReviewDecision(decided)).toBe('same_entity');
  });
});
