'use client';

import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

import type { StewardCandidateFilterState } from '@/features/import-steward/stewardCandidateFilterLogic';
import { defaultStewardCandidateFilterState } from '@/features/import-steward/stewardCandidateFilterLogic';
import { SHIPMENT_STEWARD_CONFIG } from './shipmentSteward.config';
import {
  buildShipmentCandidatesListUrl,
  SHIPMENT_CANDIDATE_FULL_LOAD_LIMIT,
  type ShipmentMappingCandidatesPageResponse,
  type StewardCandidatePageSize,
} from './shipmentCandidatesQuery';
import { stewardQueueFilterRequiresFullLoad } from '@/features/import-steward/stewardCandidateFilterLogic';
import { useCallback, useEffect, useMemo, useState } from 'react';

export function useShipmentCandidatesPage(
  importJobId: number,
  stewardFilters: StewardCandidateFilterState = defaultStewardCandidateFilterState(),
  options?: { enabled?: boolean; tabKey?: string }
) {
  const queryEnabled = options?.enabled !== false && importJobId > 0;
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState<StewardCandidatePageSize>(100);
  const clientQueueFilterActive = stewardQueueFilterRequiresFullLoad(stewardFilters);
  const skip = page * pageSize;
  const fetchSkip = clientQueueFilterActive ? 0 : skip;
  const fetchLimit = clientQueueFilterActive ? SHIPMENT_CANDIDATE_FULL_LOAD_LIMIT : pageSize;

  const serverFilterSlice = useMemo(
    () => ({
      entity: stewardFilters.entity,
      party: stewardFilters.party,
      verifyNameOnly: stewardFilters.verifyNameOnly,
      specialCategoryOnly: stewardFilters.specialCategoryOnly,
      duplicateUnresolvedOnly: stewardFilters.duplicateUnresolvedOnly,
      queue: stewardFilters.queue,
    }),
    [
      stewardFilters.entity,
      stewardFilters.party,
      stewardFilters.verifyNameOnly,
      stewardFilters.specialCategoryOnly,
      stewardFilters.duplicateUnresolvedOnly,
      stewardFilters.queue,
    ]
  );

  useEffect(() => {
    setPage(0);
  }, [options?.tabKey, ...Object.values(serverFilterSlice)]);

  const queryKey = useMemo(
    () => SHIPMENT_STEWARD_CONFIG.candidatesPageQueryKey(importJobId, fetchSkip, fetchLimit, serverFilterSlice),
    [importJobId, fetchSkip, fetchLimit, serverFilterSlice]
  );

  const query = useQuery({
    queryKey,
    enabled: queryEnabled,
    refetchOnWindowFocus: false,
    queryFn: ({ signal }) =>
      apiGet<ShipmentMappingCandidatesPageResponse>(
        buildShipmentCandidatesListUrl(importJobId, fetchSkip, fetchLimit, stewardFilters),
        { signal }
      ),
  });

  const serverTotal = query.data?.total ?? 0;
  const pageCount = clientQueueFilterActive ? 1 : Math.max(1, Math.ceil(serverTotal / pageSize));

  useEffect(() => {
    if (query.isFetching || clientQueueFilterActive) return;
    if (page > 0 && page >= pageCount) setPage(Math.max(0, pageCount - 1));
  }, [page, pageCount, query.isFetching, clientQueueFilterActive]);

  const setPageSizeAndReset = useCallback((size: StewardCandidatePageSize) => {
    setPageSize(size);
    setPage(0);
  }, []);

  return {
    query,
    candidates: query.data?.items ?? [],
    total: serverTotal,
    page,
    setPage,
    pageSize,
    setPageSize: setPageSizeAndReset,
    pageCount,
    skip: fetchSkip,
    clientQueueFilterActive,
  };
}
