'use client';

import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { STEWARD_CANDIDATE_PAGE_SIZE_OPTIONS, type StewardCandidatePageSize } from '@/features/import-steward/stewardCandidatesQuery';

import { fetchCporHistoricalCandidates } from './cporHistoricalImportApi';
import {
  CPOR_HISTORICAL_STEWARD_CONFIG,
  type CporCandidatesPageResponse,
  type CporEntityTabId,
  type CporPlanClass,
} from './cporHistoricalSteward.config';

export { STEWARD_CANDIDATE_PAGE_SIZE_OPTIONS };

/**
 * Server-paginated CPOR historical candidates for one entity tab (Unit C, S12).
 *
 * Simpler than {@link import('@/features/import-steward/useDsiCandidatesPage').useDsiCandidatesPage}:
 * the queue/plan_class chip filters server-side (S9 collision fix — no truncated-page client
 * slicing), so no DSI-style full-load escape hatch is needed here.
 */
export function useCporCandidatesPage(
  importJobId: number,
  entity: CporEntityTabId,
  planClass: CporPlanClass | null,
  options?: { enabled?: boolean }
) {
  const queryEnabled = options?.enabled !== false && importJobId > 0;
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState<StewardCandidatePageSize>(100);
  const skip = page * pageSize;

  useEffect(() => {
    setPage(0);
  }, [entity, planClass]);

  const queryKey = useMemo(
    () =>
      CPOR_HISTORICAL_STEWARD_CONFIG.candidatesPageQueryKey(importJobId, entity, skip, pageSize, planClass),
    [importJobId, entity, skip, pageSize, planClass]
  );

  const query = useQuery<CporCandidatesPageResponse>({
    queryKey,
    enabled: queryEnabled,
    refetchOnWindowFocus: false,
    placeholderData: (previousData, previousQuery) => {
      if (!previousData || !previousQuery) return undefined;
      const prevKey = previousQuery.queryKey as unknown as readonly unknown[];
      // Query key shape: [..., 'page', entity, skip, limit, planClass]. Keep placeholder only
      // when entity/planClass are unchanged — avoids a cross-tab / cross-queue data flash.
      if (prevKey[5] !== entity || prevKey[8] !== (planClass ?? 'all')) return undefined;
      return previousData;
    },
    queryFn: ({ signal }) =>
      fetchCporHistoricalCandidates(importJobId, entity, { skip, limit: pageSize, planClass }, signal),
  });

  const total = query.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    if (query.isFetching) return;
    if (page > 0 && page >= pageCount) {
      setPage(Math.max(0, pageCount - 1));
    }
  }, [page, pageCount, query.isFetching]);

  const setPageSizeAndReset = useCallback((size: StewardCandidatePageSize) => {
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
    counts: query.data?.counts,
    planClassCounts: query.data?.plan_class_counts,
  };
}
