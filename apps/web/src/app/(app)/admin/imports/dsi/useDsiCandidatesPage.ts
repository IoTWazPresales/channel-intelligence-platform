'use client';

import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { apiGet } from '@/lib/api';

import { DSI_STEWARD_CONFIG } from './dsiSteward.config';
import {
  buildDsiCandidatesListUrl,
  STEWARD_CANDIDATE_FULL_LOAD_LIMIT,
  type StewardCandidatePageSize,
  type StewardMappingCandidatesPageResponse,
} from '@/features/import-steward/stewardCandidatesQuery';
import type { DsiStewardCandidateFilterState } from './dsiStewardCandidateFilterLogic';
import {
  defaultDsiStewardCandidateFilterState,
  stewardQueueFilterRequiresFullLoad,
} from './dsiStewardCandidateFilterLogic';
import { keepDsiCandidatesPageDataIfSameEntity } from './dsiCandidatesPagePlaceholder';

export function useDsiCandidatesPage(
  importJobId: number,
  stewardFilters: DsiStewardCandidateFilterState = defaultDsiStewardCandidateFilterState(),
  options?: { enabled?: boolean; tabKey?: string }
) {
  const queryEnabled = options?.enabled !== false && importJobId > 0;
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState<StewardCandidatePageSize>(100);

  const clientQueueFilterActive = stewardQueueFilterRequiresFullLoad(stewardFilters);

  const skip = page * pageSize;
  const fetchSkip = clientQueueFilterActive ? 0 : skip;
  const fetchLimit = clientQueueFilterActive ? STEWARD_CANDIDATE_FULL_LOAD_LIMIT : pageSize;

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
  }, [
    options?.tabKey,
    serverFilterSlice.entity,
    serverFilterSlice.party,
    serverFilterSlice.verifyNameOnly,
    serverFilterSlice.specialCategoryOnly,
    serverFilterSlice.duplicateUnresolvedOnly,
    serverFilterSlice.queue,
  ]);

  const queryKey = useMemo(
    () =>
      DSI_STEWARD_CONFIG.candidatesPageQueryKey(
        importJobId,
        fetchSkip,
        fetchLimit,
        serverFilterSlice
      ),
    [importJobId, fetchSkip, fetchLimit, serverFilterSlice]
  );

  const query = useQuery<StewardMappingCandidatesPageResponse>({
    queryKey,
    enabled: queryEnabled,
    refetchOnWindowFocus: false,
    placeholderData: (previousData, previousQuery) =>
      keepDsiCandidatesPageDataIfSameEntity(previousData, previousQuery, serverFilterSlice.entity),
    queryFn: ({ signal }) =>
      apiGet<StewardMappingCandidatesPageResponse>(
        buildDsiCandidatesListUrl(importJobId, fetchSkip, fetchLimit, stewardFilters),
        { signal }
      ),
  });

  const serverTotal = query.data?.total ?? 0;
  const pageCount = clientQueueFilterActive
    ? 1
    : Math.max(1, Math.ceil(serverTotal / pageSize));

  useEffect(() => {
    if (query.isFetching || clientQueueFilterActive) return;
    if (page > 0 && page >= pageCount) {
      setPage(Math.max(0, pageCount - 1));
    }
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
    skip: clientQueueFilterActive ? page * pageSize : skip,
    clientQueueFilterActive,
    fullLoadTruncated:
      clientQueueFilterActive && serverTotal > STEWARD_CANDIDATE_FULL_LOAD_LIMIT,
  };
}
