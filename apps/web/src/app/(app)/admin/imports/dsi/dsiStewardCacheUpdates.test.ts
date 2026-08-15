import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';

import { DSI_STEWARD_CONFIG } from './dsiSteward.config';
import type { DsiCandidateRow } from './dsi-mapping-steward-panel';
import {
  evictCandidatesFromResolutionPlanCache,
  patchCandidateStatusInDsiCache,
  removeCandidatesFromDsiCache,
  restoreDsiCandidatesCache,
  snapshotDsiCandidatesCache,
} from './dsiStewardCacheUpdates';

function sampleRow(id: number): DsiCandidateRow {
  return {
    id,
    import_job_id: 43,
    source_definition_id: null,
    entity_type: 'customer_dealer_token',
    normalized_key: `token-${id}`,
    dealer_group_token: null,
    row_count: 1,
    total_units: null,
    total_reported_value: null,
    sample_raw_values: null,
    suggested_entity_id: null,
    match_reason: null,
    confidence_score: null,
    status: 'needs_review',
    context: null,
  };
}

describe('dsiStewardCacheUpdates', () => {
  it('removeCandidatesFromDsiCache drops rows and decrements total', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const importJobId = 43;
    const queryKey = DSI_STEWARD_CONFIG.candidatesPageQueryKey(importJobId, 0, 1000, {
      entity: 'customer',
      party: '',
      verifyNameOnly: false,
      specialCategoryOnly: false,
      duplicateUnresolvedOnly: false,
      queue: 'all',
    });
    qc.setQueryData(queryKey, {
      items: [sampleRow(1), sampleRow(2), sampleRow(3)],
      total: 10,
    });

    removeCandidatesFromDsiCache(qc, importJobId, [2]);

    const page = qc.getQueryData<{ items: DsiCandidateRow[]; total: number }>(queryKey);
    expect(page?.items.map((r) => r.id)).toEqual([1, 3]);
    expect(page?.total).toBe(9);
  });

  it('restoreDsiCandidatesCache rolls back removeCandidatesFromDsiCache', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const importJobId = 43;
    const queryKey = DSI_STEWARD_CONFIG.candidatesPageQueryKey(importJobId, 0, 1000, {
      entity: 'customer',
      party: '',
      verifyNameOnly: false,
      specialCategoryOnly: false,
      duplicateUnresolvedOnly: false,
      queue: 'all',
    });
    const before = { items: [sampleRow(1), sampleRow(2)], total: 5 };
    qc.setQueryData(queryKey, before);

    const snapshot = removeCandidatesFromDsiCache(qc, importJobId, [1]);
    restoreDsiCandidatesCache(qc, snapshot);

    expect(qc.getQueryData(queryKey)).toEqual(before);
  });

  it('patchCandidateStatusInDsiCache updates status in place', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const importJobId = 43;
    const queryKey = DSI_STEWARD_CONFIG.candidatesPageQueryKey(importJobId, 0, 1000, {
      entity: 'customer',
      party: '',
      verifyNameOnly: false,
      specialCategoryOnly: false,
      duplicateUnresolvedOnly: false,
      queue: 'all',
    });
    qc.setQueryData(queryKey, { items: [sampleRow(7)], total: 1 });

    patchCandidateStatusInDsiCache(qc, importJobId, 7, 'acknowledged_unique');

    const page = qc.getQueryData<{ items: DsiCandidateRow[]; total: number }>(queryKey);
    expect(page?.items[0]?.status).toBe('acknowledged_unique');
    expect(page?.total).toBe(1);
  });

  it('evictCandidatesFromResolutionPlanCache removes plan rows and updates summary', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const importJobId = 43;
    const queryKey = DSI_STEWARD_CONFIG.resolutionSuggestionsQueryKey(importJobId, '1,2', '0', '0');
    qc.setQueryData(queryKey, {
      rows: [
        { candidate_id: 1, ready: true },
        { candidate_id: 2, ready: false },
        { candidate_id: 3, ready: true },
      ],
      summary: { total: 3, ready: 2, not_ready: 1 },
    });

    evictCandidatesFromResolutionPlanCache(qc, importJobId, [2]);

    const plan = qc.getQueryData<{
      rows: Array<{ candidate_id: number }>;
      summary: { total: number; ready: number; not_ready: number };
    }>(queryKey);
    expect(plan?.rows.map((r) => r.candidate_id)).toEqual([1, 3]);
    expect(plan?.summary).toEqual({ total: 2, ready: 2, not_ready: 0 });
  });

  it('snapshotDsiCandidatesCache captures paginated pages', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const importJobId = 43;
    const queryKey = DSI_STEWARD_CONFIG.candidatesPageQueryKey(importJobId, 0, 50, {
      entity: 'customer',
      party: '',
      verifyNameOnly: false,
      specialCategoryOnly: false,
      duplicateUnresolvedOnly: false,
      queue: 'all',
    });
    qc.setQueryData(queryKey, { items: [sampleRow(4)], total: 1 });

    const snapshot = snapshotDsiCandidatesCache(qc, importJobId);
    expect(snapshot.pages).toHaveLength(1);
    expect(snapshot.pages[0]?.data.items[0]?.id).toBe(4);
  });
});
