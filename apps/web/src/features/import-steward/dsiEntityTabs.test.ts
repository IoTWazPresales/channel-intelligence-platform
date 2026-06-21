import { describe, expect, it } from 'vitest';

import { DSI_STEWARD_CONFIG } from './dsiSteward.config';
import {
  DSI_CANDIDATES_PAGE_ENTITY_QUERY_KEY_INDEX,
  keepDsiCandidatesPageDataIfSameEntity,
} from './dsiCandidatesPagePlaceholder';
import {
  defaultDsiStewardFiltersForTab,
  dsiStewardFiltersMatchTabDefault,
} from './dsiEntityTabs';
import { defaultDsiStewardCandidateFilterState } from './dsiStewardCandidateFilterLogic';

describe('keepDsiCandidatesPageDataIfSameEntity', () => {
  const previousData = { items: [{ id: 1 }], total: 1 };

  function queryKeyForEntity(entity: string) {
    return {
      queryKey: DSI_STEWARD_CONFIG.candidatesPageQueryKey(1, 0, 100, {
        entity,
        party: 'all',
        verifyNameOnly: false,
        specialCategoryOnly: false,
        duplicateUnresolvedOnly: false,
      }),
    };
  }

  it('drops placeholder when entity filter changed', () => {
    expect(
      keepDsiCandidatesPageDataIfSameEntity(
        previousData,
        queryKeyForEntity('product'),
        'customer'
      )
    ).toBeUndefined();
  });

  it('keeps placeholder when entity filter unchanged', () => {
    expect(
      keepDsiCandidatesPageDataIfSameEntity(
        previousData,
        queryKeyForEntity('customer'),
        'customer'
      )
    ).toBe(previousData);
  });

  it('uses the configured entity index in the query key', () => {
    const key = queryKeyForEntity('distributor').queryKey;
    expect(key[DSI_CANDIDATES_PAGE_ENTITY_QUERY_KEY_INDEX]).toBe('distributor');
  });
});

describe('dsiStewardFiltersMatchTabDefault', () => {
  it('customer tab default keeps entity customer', () => {
    const def = defaultDsiStewardFiltersForTab('customer');
    expect(def.entity).toBe('customer');
    expect(dsiStewardFiltersMatchTabDefault(def, 'customer')).toBe(true);
  });

  it('clearing queue on customer tab does not match global default', () => {
    const cleared = defaultDsiStewardCandidateFilterState();
    expect(cleared.entity).toBe('all');
    expect(dsiStewardFiltersMatchTabDefault(cleared, 'customer')).toBe(false);
  });

  it('refined filters on customer tab are not at tab default', () => {
    const refined = {
      ...defaultDsiStewardFiltersForTab('customer'),
      queue: 'needs_review' as const,
    };
    expect(dsiStewardFiltersMatchTabDefault(refined, 'customer')).toBe(false);
  });

  it('resetting refine filters on customer tab matches tab default', () => {
    const reset = defaultDsiStewardFiltersForTab('customer');
    expect(reset.entity).toBe('customer');
    expect(dsiStewardFiltersMatchTabDefault(reset, 'customer')).toBe(true);
  });
});
