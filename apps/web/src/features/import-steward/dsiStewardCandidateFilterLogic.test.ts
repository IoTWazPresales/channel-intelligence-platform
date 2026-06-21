import { describe, expect, it } from 'vitest';

import type { DsiCandidateRow } from './dsi-mapping-steward-panel';
import {
  classifyDuplicateSameEntityCase,
  contextDistributorMasterCollision,
  contextPossibleDuplicateOf,
  defaultDsiStewardCandidateFilterState,
  filterDsiStewardCandidates,
  paginateDsiStewardCandidateRows,
  stewardQueueFilterRequiresFullLoad,
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

describe('product match status queue filters', () => {
  const plan = new Map<number, Record<string, unknown>>();

  function productRow(
    id: number,
    context: Record<string, unknown>,
    matchReason: string | null = null
  ): DsiCandidateRow {
    return {
      id,
      import_job_id: 43,
      source_definition_id: null,
      entity_type: 'product_identifier',
      normalized_key: `token-${id}`,
      dealer_group_token: null,
      row_count: 1,
      total_units: null,
      total_reported_value: null,
      sample_raw_values: [`SKU-${id}`],
      suggested_entity_id: null,
      match_reason: matchReason,
      confidence_score: null,
      status: 'open',
      context,
    };
  }

  it('no_match is strict product_match_status for products', () => {
    const rows = [
      productRow(1, { product_match_status: 'no_match' }),
      productRow(2, { product_match_status: 'ambiguous_eligible' }),
      productRow(3, { product_match_status: 'ambiguous_eligible' }, null),
    ];
    const filters = { ...defaultDsiStewardCandidateFilterState(), entity: 'product' as const, queue: 'no_match' as const };
    expect(filterDsiStewardCandidates(rows, filters, plan).map((r) => r.id)).toEqual([1]);
  });

  it('ambiguous_eligible chip filters only ambiguous_eligible products', () => {
    const rows = [
      productRow(1, { product_match_status: 'no_match' }),
      productRow(2, { product_match_status: 'ambiguous_eligible' }),
      productRow(3, { product_match_status: 'ambiguous_eligible' }),
    ];
    const filters = {
      ...defaultDsiStewardCandidateFilterState(),
      entity: 'product' as const,
      queue: 'ambiguous_eligible' as const,
    };
    expect(filterDsiStewardCandidates(rows, filters, plan).map((r) => r.id)).toEqual([2, 3]);
  });

  it('empty product match_reason without status is not no_match', () => {
    const rows = [productRow(9, {}, null)];
    const filters = { ...defaultDsiStewardCandidateFilterState(), entity: 'product' as const, queue: 'no_match' as const };
    expect(filterDsiStewardCandidates(rows, filters, plan)).toHaveLength(0);
  });

  it('distributor no_match keeps legacy match_reason heuristic', () => {
    const row: DsiCandidateRow = {
      ...productRow(1, {}),
      id: 10,
      entity_type: 'distributor_token',
      context: null,
      match_reason: null,
    };
    const filters = {
      ...defaultDsiStewardCandidateFilterState(),
      entity: 'distributor' as const,
      queue: 'no_match' as const,
    };
    expect(filterDsiStewardCandidates([row], filters, plan)).toHaveLength(1);
  });
});

describe('steward queue filter full-load + client pagination', () => {
  const plan = new Map<number, Record<string, unknown>>();

  function productRow(id: number, context: Record<string, unknown>): DsiCandidateRow {
    return {
      id,
      import_job_id: 43,
      source_definition_id: null,
      entity_type: 'product_identifier',
      normalized_key: `token-${id}`,
      dealer_group_token: null,
      row_count: 1,
      total_units: null,
      total_reported_value: null,
      sample_raw_values: [`SKU-${id}`],
      suggested_entity_id: null,
      match_reason: null,
      confidence_score: null,
      status: 'open',
      context,
    };
  }

  it('stewardQueueFilterRequiresFullLoad when Plan/match queue is not all', () => {
    expect(stewardQueueFilterRequiresFullLoad(defaultDsiStewardCandidateFilterState())).toBe(false);
    expect(
      stewardQueueFilterRequiresFullLoad({
        ...defaultDsiStewardCandidateFilterState(),
        queue: 'ambiguous_eligible',
      })
    ).toBe(true);
  });

  it('ambiguous filter on full tab set returns all matches beyond first server page', () => {
    const rows = [
      ...Array.from({ length: 482 }, (_, i) =>
        productRow(i + 1, { product_match_status: 'no_match' })
      ),
      ...Array.from({ length: 63 }, (_, i) =>
        productRow(500 + i, { product_match_status: 'ambiguous_eligible' })
      ),
    ];
    const filters = {
      ...defaultDsiStewardCandidateFilterState(),
      entity: 'product' as const,
      queue: 'ambiguous_eligible' as const,
    };
    const filtered = filterDsiStewardCandidates(rows, filters, plan);
    expect(filtered).toHaveLength(63);
    const page0 = paginateDsiStewardCandidateRows(filtered, 0, 100);
    expect(page0).toHaveLength(63);
    expect(page0.every((r) => r.context?.product_match_status === 'ambiguous_eligible')).toBe(true);
  });

  it('no_match filter on full tab set returns all no_match rows at default page size', () => {
    const rows = [
      ...Array.from({ length: 482 }, (_, i) =>
        productRow(i + 1, { product_match_status: 'no_match' })
      ),
      ...Array.from({ length: 63 }, (_, i) =>
        productRow(500 + i, { product_match_status: 'ambiguous_eligible' })
      ),
    ];
    const filters = {
      ...defaultDsiStewardCandidateFilterState(),
      entity: 'product' as const,
      queue: 'no_match' as const,
    };
    const filtered = filterDsiStewardCandidates(rows, filters, plan);
    expect(filtered).toHaveLength(482);
    expect(paginateDsiStewardCandidateRows(filtered, 0, 100)).toHaveLength(100);
    expect(paginateDsiStewardCandidateRows(filtered, 1, 100)).toHaveLength(100);
    expect(paginateDsiStewardCandidateRows(filtered, 4, 100)).toHaveLength(82);
  });
});
