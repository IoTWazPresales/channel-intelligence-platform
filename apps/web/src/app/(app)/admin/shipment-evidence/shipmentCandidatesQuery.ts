'use client';

import type { StewardCandidateFilterState } from '@/features/import-steward/stewardCandidateFilterLogic';
import type { InboundEvidenceMappingCandidateRow } from './inboundEvidenceMappingCandidateWorkspaceColumns';

import { STEWARD_CANDIDATE_PAGE_SIZE_OPTIONS, type StewardCandidatePageSize } from '@/features/import-steward/stewardCandidatesQuery';

export type ShipmentMappingCandidatesPageResponse = {
  items: InboundEvidenceMappingCandidateRow[];
  total: number;
  skip: number;
  limit: number;
};

export const SHIPMENT_CANDIDATE_FULL_LOAD_LIMIT = 2000;

export { STEWARD_CANDIDATE_PAGE_SIZE_OPTIONS };

export function buildShipmentCandidatesListUrl(
  importJobId: number,
  skip: number,
  limit: number,
  filters: StewardCandidateFilterState
): string {
  const params = new URLSearchParams({
    skip: String(skip),
    limit: String(limit),
    entity: filters.entity,
    party: filters.party,
    status: 'open',
  });
  if (filters.verifyNameOnly) params.set('verify_name_only', 'true');
  if (filters.specialCategoryOnly) params.set('special_category_only', 'true');
  if (filters.duplicateUnresolvedOnly) params.set('duplicate_unresolved_only', 'true');
  return `/api/v1/shipment-evidence/import-jobs/${importJobId}/mapping-candidates/paginated?${params}`;
}

export type { StewardCandidatePageSize };
