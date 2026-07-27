'use client';

import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { apiGet } from '@/lib/api';
import {
  DSI_CANDIDATE_PAGE_SIZE_OPTIONS,
  type DsiCandidatePageSize,
} from '@/features/import-steward/dsiCandidatesQuery';

import {
  CST_IMPORT_STEWARD_CONFIG,
  type CstCandidatesPageResponse,
  type CstEntityTabId,
} from './cstImportSteward.config';

export { DSI_CANDIDATE_PAGE_SIZE_OPTIONS };

export function useCstCandidatesPage(
  importJobId: number,
  entity: CstEntityTabId,
  status: string,
  options?: { enabled?: boolean }
) {
  const queryEnabled = options?.enabled !== false && importJobId > 0;
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState<DsiCandidatePageSize>(100);
  const skip = page * pageSize;

  useEffect(() => {
    setPage(0);
  }, [entity, status]);

  const queryKey = useMemo(
    () => CST_IMPORT_STEWARD_CONFIG.candidatesPageQueryKey(importJobId, entity, status, skip, pageSize),
    [importJobId, entity, status, skip, pageSize]
  );

  const query = useQuery({
    queryKey,
    enabled: queryEnabled,
    refetchOnWindowFocus: false,
    queryFn: ({ signal }) => {
      const params = new URLSearchParams({
        skip: String(skip),
        limit: String(pageSize),
        entity,
        status,
      });
      return apiGet<CstCandidatesPageResponse>(
        `/api/v1/imports/jobs/${importJobId}/cst-candidates?${params}`,
        { signal }
      );
    },
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
