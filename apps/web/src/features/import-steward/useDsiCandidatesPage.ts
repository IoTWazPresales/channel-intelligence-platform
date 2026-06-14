'use client';

import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { apiGet } from '@/lib/api';

import { DSI_STEWARD_CONFIG } from './dsiSteward.config';
import {
  buildDsiCandidatesListUrl,
  type DsiCandidatePageSize,
  type DsiMappingCandidatesPageResponse,
} from './dsiCandidatesQuery';
import type { DsiStewardCandidateFilterState } from './dsiStewardCandidateFilterLogic';
import { keepDsiCandidatesPageDataIfSameEntity } from './dsiCandidatesPagePlaceholder';
import { defaultDsiStewardCandidateFilterState } from './dsiStewardCandidateFilterLogic';

export function useDsiCandidatesPage(
  importJobId: number,
  stewardFilters: DsiStewardCandidateFilterState = defaultDsiStewardCandidateFilterState(),
  options?: { enabled?: boolean; tabKey?: string }
) {
  const queryEnabled = options?.enabled !== false && importJobId > 0;
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState<DsiCandidatePageSize>(100);

  const skip = page * pageSize;

  const serverFilterSlice = useMemo(
    () => ({
      entity: stewardFilters.entity,
      party: stewardFilters.party,
      verifyNameOnly: stewardFilters.verifyNameOnly,
      specialCategoryOnly: stewardFilters.specialCategoryOnly,
      duplicateUnresolvedOnly: stewardFilters.duplicateUnresolvedOnly,
    }),
    [
      stewardFilters.entity,
      stewardFilters.party,
      stewardFilters.verifyNameOnly,
      stewardFilters.specialCategoryOnly,
      stewardFilters.duplicateUnresolvedOnly,
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
  ]);

  const queryKey = useMemo(
    () => DSI_STEWARD_CONFIG.candidatesPageQueryKey(importJobId, skip, pageSize, serverFilterSlice),
    [importJobId, skip, pageSize, serverFilterSlice]
  );

  const query = useQuery({
    queryKey,
    enabled: queryEnabled,
    refetchOnWindowFocus: false,
    placeholderData: (previousData, previousQuery) =>
      keepDsiCandidatesPageDataIfSameEntity(previousData, previousQuery, serverFilterSlice.entity),
    queryFn: ({ signal }) =>
      apiGet<DsiMappingCandidatesPageResponse>(
        buildDsiCandidatesListUrl(importJobId, skip, pageSize, stewardFilters),
        { signal }
      ),
  });

  const total = query.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    if (query.isFetching) return;
    if (page > 0 && page >= pageCount) {
      setPage(Math.max(0, pageCount - 1));
    }
  }, [page, pageCount, query.isFetching]);

  const setPageSizeAndReset = useCallback((size: DsiCandidatePageSize) => {
    setPageSize(size);
    setPage(0);
  }, []);

  return {
    query,
    candidates: query.data?.items ?? [],
    total,
    page,
    setPage,
    pageSize,
    setPageSize: setPageSizeAndReset,
    pageCount,
    skip,
  };
}
