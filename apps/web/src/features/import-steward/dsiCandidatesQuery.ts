'use client';

import type { DsiCandidateRow } from './dsi-mapping-steward-panel';
import type { DsiStewardCandidateFilterState } from './dsiStewardCandidateFilterLogic';
import { dsiStewardFiltersAreDefault } from './dsiStewardCandidateFilterLogic';

export const DSI_CANDIDATE_PAGE_SIZE_OPTIONS = [100, 250, 500, 1000] as const;
export type DsiCandidatePageSize = (typeof DSI_CANDIDATE_PAGE_SIZE_OPTIONS)[number];

/** Max server page size — used when Plan/match queue filter requires a full tab load. */
export const DSI_CANDIDATE_FULL_LOAD_LIMIT = 1000 as const;

export type DsiMappingCandidatesPageResponse = {
  items: DsiCandidateRow[];
  total: number;
  skip: number;
  limit: number;
};

export type DsiCandidateListStatus = 'open' | 'needs_review' | 'terminal' | 'all';

export function serverFilterParamsFromStewardState(
  filters: DsiStewardCandidateFilterState,
  options?: { status?: DsiCandidateListStatus }
): Record<string, string | boolean> {
  const params: Record<string, string | boolean> = {
    status: options?.status ?? 'open',
  };
  if (filters.entity !== 'all') {
    params.entity = filters.entity;
  }
  if (filters.party !== 'all') {
    params.party = filters.party;
  }
  if (filters.verifyNameOnly) {
    params.verify_name_only = true;
  }
  if (filters.specialCategoryOnly) {
    params.special_category_only = true;
  }
  if (filters.duplicateUnresolvedOnly) {
    params.duplicate_unresolved_only = true;
  }
  return params;
}

export function buildDsiCandidatesListUrl(
  importJobId: number,
  skip: number,
  limit: number,
  filters: DsiStewardCandidateFilterState,
  options?: { status?: DsiCandidateListStatus }
): string {
  const q = new URLSearchParams();
  q.set('skip', String(skip));
  q.set('limit', String(limit));
  const fp = serverFilterParamsFromStewardState(filters, options);
  for (const [k, v] of Object.entries(fp)) {
    if (typeof v === 'boolean') {
      if (v) q.set(k, 'true');
    } else if (v) {
      q.set(k, String(v));
    }
  }
  return `/api/v1/mappings/import-jobs/${importJobId}/distributor-si-candidates?${q.toString()}`;
}

export function stewardFiltersAffectServerQuery(filters: DsiStewardCandidateFilterState): boolean {
  return !dsiStewardFiltersAreDefault(filters) || filters.entity !== 'all' || filters.party !== 'all';
}
