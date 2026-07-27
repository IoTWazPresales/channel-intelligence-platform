import { describe, expect, it } from 'vitest';

import { contextPossibleDuplicateOf } from './dsiStewardCandidateFilterLogic';
import {
  buildDuplicateClusterIndex,
  detectSuffixTokenFamily,
  duplicateClusterMembersForKey,
} from './dsiDuplicateCluster';

describe('contextPossibleDuplicateOf (cluster fixture)', () => {
  it('parses hint objects for cluster edges', () => {
    const hints = contextPossibleDuplicateOf({
      possible_duplicate_of: [{ normalized_key: 'acme2', similarity_score: 0.95 }],
    });
    expect(hints).toHaveLength(1);
  });
});

describe('buildDuplicateClusterIndex', () => {
  it('connects transitive duplicate hints on the page', () => {
    const index = buildDuplicateClusterIndex([
      {
        entity_type: 'customer_dealer_token',
        normalized_key: 'acme',
        context: { possible_duplicate_of: [{ normalized_key: 'acme2', similarity_score: 0.95 }] },
      },
      {
        entity_type: 'customer_dealer_token',
        normalized_key: 'acme2',
        context: { possible_duplicate_of: [{ normalized_key: 'acme3', similarity_score: 0.95 }] },
      },
      {
        entity_type: 'customer_dealer_token',
        normalized_key: 'acme3',
        context: { possible_duplicate_of: [] },
      },
    ]);
    expect(duplicateClusterMembersForKey(index, 'acme').sort()).toEqual(['acme', 'acme2', 'acme3']);
  });
});

describe('detectSuffixTokenFamily', () => {
  it('groups short-suffix variants with shared prefix', () => {
    const keys = [
      'client divers cash cam',
      'client divers cash cdi',
      'client divers cash cfd',
      'client divers cash cma',
    ];
    const family = detectSuffixTokenFamily('client divers cash cam', keys);
    expect(family).not.toBeNull();
    expect(family?.length).toBeGreaterThanOrEqual(3);
  });

  it('returns null for unrelated tokens', () => {
    expect(detectSuffixTokenFamily('acme retail', ['beta wholesale'])).toBeNull();
  });
});
