import { describe, expect, it } from 'vitest';

import {
  STEWARD_ENTITY_CUST,
  STEWARD_ENTITY_DIST,
  defaultStewardCandidateFilterState,
  filterStewardCandidates,
  stewardCandidateMatchesFilters,
  stewardRowNeedsReview,
  stewardRowNoMatch,
  stewardRowProvisionalPath,
  stewardRowReadyToMap,
  type StewardCandidateFilterState,
  type StewardFilterRow,
} from './shipmentEntityStewardFilters';

function row(p: Partial<StewardFilterRow> & Pick<StewardFilterRow, 'id' | 'entity_type'>): StewardFilterRow {
  return {
    suggested_action: null,
    status: 'needs_review',
    match_reason: null,
    context: null,
    ...p,
  };
}

describe('shipmentEntityStewardFilters', () => {
  it('classifies needs_review like the Match column', () => {
    expect(stewardRowNeedsReview(row({ id: 1, entity_type: STEWARD_ENTITY_CUST, suggested_action: 'needs_review' }))).toBe(
      true
    );
    expect(
      stewardRowNeedsReview(
        row({ id: 2, entity_type: STEWARD_ENTITY_CUST, suggested_action: '', status: 'needs_review' })
      )
    ).toBe(true);
    expect(
      stewardRowNeedsReview(
        row({ id: 3, entity_type: STEWARD_ENTITY_CUST, suggested_action: 'map_customer', status: 'needs_review' })
      )
    ).toBe(false);
  });

  it('classifies ready-to-map and provisional paths', () => {
    expect(stewardRowReadyToMap(row({ id: 1, entity_type: STEWARD_ENTITY_CUST, suggested_action: 'map_customer' }))).toBe(
      true
    );
    expect(
      stewardRowProvisionalPath(
        row({ id: 2, entity_type: STEWARD_ENTITY_DIST, suggested_action: 'create_provisional_distributor' })
      )
    ).toBe(true);
  });

  it('no_match includes no_alias_or_exact_dim_match and empty distributor match_reason', () => {
    expect(
      stewardRowNoMatch(
        row({
          id: 1,
          entity_type: STEWARD_ENTITY_CUST,
          match_reason: 'no_alias_or_exact_dim_match',
        })
      )
    ).toBe(true);
    expect(stewardRowNoMatch(row({ id: 2, entity_type: STEWARD_ENTITY_DIST, match_reason: '' }))).toBe(true);
    expect(
      stewardRowNoMatch(row({ id: 3, entity_type: STEWARD_ENTITY_DIST, match_reason: 'some_other_reason' }))
    ).toBe(false);
  });

  it('filters by entity and party (distributor-only)', () => {
    const rows: StewardFilterRow[] = [
      row({
        id: 1,
        entity_type: STEWARD_ENTITY_DIST,
        context: { party: 'bill_to' },
        suggested_action: 'create_provisional_distributor',
        match_reason: 'no_alias_or_exact_dim_match',
      }),
      row({
        id: 2,
        entity_type: STEWARD_ENTITY_DIST,
        context: { party: 'ship_to' },
        suggested_action: 'create_provisional_distributor',
        match_reason: 'no_alias_or_exact_dim_match',
      }),
      row({
        id: 3,
        entity_type: STEWARD_ENTITY_CUST,
        context: null,
        suggested_action: 'create_provisional_customer',
        match_reason: 'no_alias_or_exact_dim_match',
      }),
    ];
    const partyBill: StewardCandidateFilterState = {
      ...defaultStewardCandidateFilterState(),
      party: 'bill_to',
    };
    expect(filterStewardCandidates(rows, partyBill).map((r) => r.id)).toEqual([1]);

    const custOnly: StewardCandidateFilterState = {
      ...defaultStewardCandidateFilterState(),
      entity: 'customer',
    };
    expect(filterStewardCandidates(rows, custOnly).map((r) => r.id)).toEqual([3]);
  });

  it('verify-name toggle keeps distributors visible', () => {
    const rows: StewardFilterRow[] = [
      row({
        id: 1,
        entity_type: STEWARD_ENTITY_DIST,
        suggested_action: 'map_distributor',
        match_reason: 'x',
        context: { party: 'bill_to' },
      }),
      row({
        id: 2,
        entity_type: STEWARD_ENTITY_CUST,
        suggested_action: 'map_customer',
        match_reason: 'no_alias_or_exact_dim_match',
        context: { needs_name_review: true },
      }),
      row({
        id: 3,
        entity_type: STEWARD_ENTITY_CUST,
        suggested_action: 'map_customer',
        match_reason: 'no_alias_or_exact_dim_match',
        context: { needs_name_review: false },
      }),
    ];
    const s: StewardCandidateFilterState = {
      ...defaultStewardCandidateFilterState(),
      verifyNameOnly: true,
    };
    expect(filterStewardCandidates(rows, s).map((r) => r.id).sort()).toEqual([1, 2]);
  });

  it('combines special-category and duplicate toggles with AND semantics', () => {
    const r: StewardFilterRow = row({
      id: 1,
      entity_type: STEWARD_ENTITY_CUST,
      suggested_action: 'needs_review',
      match_reason: 'x',
      context: { special_category: 'noise_only', possible_duplicate_of: ['A'] },
    });
    expect(stewardCandidateMatchesFilters(r, { ...defaultStewardCandidateFilterState(), specialCategoryOnly: true })).toBe(
      true
    );
    expect(
      stewardCandidateMatchesFilters(r, {
        ...defaultStewardCandidateFilterState(),
        specialCategoryOnly: true,
        possibleDuplicatesOnly: true,
      })
    ).toBe(true);
    expect(
      stewardCandidateMatchesFilters(
        { ...r, context: { special_category: 'noise_only' } },
        {
          ...defaultStewardCandidateFilterState(),
          specialCategoryOnly: true,
          possibleDuplicatesOnly: true,
        }
      )
    ).toBe(false);
  });
});
