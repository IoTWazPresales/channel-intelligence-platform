import { describe, expect, it } from 'vitest';

import {
  classifyDuplicateSameEntityCase,
  contextDistributorMasterCollision,
  contextPossibleDuplicateOf,
  suggestedCustomerIdForDuplicateSameEntity,
} from './dsiStewardCandidateFilterLogic';

describe('contextDistributorMasterCollision', () => {
  it('returns collision when present on context', () => {
    const hit = contextDistributorMasterCollision({
      distributor_master_collision: { distributor_id: 42, distributor_name: 'Harbor Wholesale' },
    });
    expect(hit).toEqual({ distributor_id: 42, distributor_name: 'Harbor Wholesale' });
  });

  it('returns null when missing or invalid', () => {
    expect(contextDistributorMasterCollision(null)).toBeNull();
    expect(contextDistributorMasterCollision({})).toBeNull();
    expect(
      contextDistributorMasterCollision({
        distributor_master_collision: { distributor_id: 'x', distributor_name: '' },
      })
    ).toBeNull();
  });
});

describe('contextPossibleDuplicateOf', () => {
  it('parses object hints with scores', () => {
    const hints = contextPossibleDuplicateOf({
      possible_duplicate_of: [{ normalized_key: 'acme2', similarity_score: 0.91 }],
    });
    expect(hints).toEqual([
      { normalized_key: 'acme2', similarity_score: 0.91, match_basis: undefined },
    ]);
  });

  it('parses match_basis when present', () => {
    const hints = contextPossibleDuplicateOf({
      possible_duplicate_of: [
        { normalized_key: 'peer', similarity_score: 1.0, match_basis: 'source_customer_exact' },
      ],
    });
    expect(hints[0]?.match_basis).toBe('source_customer_exact');
  });
});

describe('classifyDuplicateSameEntityCase', () => {
  it('returns greenfield when both suggestions are null', () => {
    expect(classifyDuplicateSameEntityCase(null, null)).toBe('greenfield');
  });

  it('returns conflict when suggestions differ', () => {
    expect(classifyDuplicateSameEntityCase(10, 20)).toBe('conflict');
  });

  it('returns suggested when one side has a customer id', () => {
    expect(classifyDuplicateSameEntityCase(null, 55)).toBe('suggested');
    expect(suggestedCustomerIdForDuplicateSameEntity(null, 55)).toBe(55);
  });
});

describe('duplicate peer hint filtering (same entity)', () => {
  it('excludes self-referential normalized_key from peer selection', () => {
    const hints = [
      { normalized_key: 'axiom systems africa pty ltd', similarity_score: 1.0 },
      { normalized_key: 'axiom systems africa', similarity_score: 1.0 },
    ];
    const own = 'axiom systems africa pty ltd';
    const peerHints = hints.filter((h) => h.normalized_key.trim() !== own.trim());
    expect(peerHints).toHaveLength(1);
    expect(peerHints[0]?.normalized_key).toBe('axiom systems africa');
  });
});
