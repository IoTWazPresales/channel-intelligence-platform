'use client';

import { useQueries } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

import { buildDsiCandidatesListUrl, type DsiMappingCandidatesPageResponse } from './dsiCandidatesQuery';
import {
  DSI_ENTITY_TABS,
  defaultDsiStewardFiltersForTab,
  type DsiEntityTabId,
} from './dsiEntityTabs';

export type DsiEntityTabCounts = Record<DsiEntityTabId, { total: number | null; needsWork: number | null }>;

const emptyCounts = (): DsiEntityTabCounts => ({
  distributor: { total: null, needsWork: null },
  customer: { total: null, needsWork: null },
  product: { total: null, needsWork: null },
});

export function useDsiEntityTabCounts(importJobId: number, enabled: boolean) {
  const queries = useQueries({
    queries: DSI_ENTITY_TABS.flatMap((tab) => {
      const filters = defaultDsiStewardFiltersForTab(tab.id);
      return [
        {
          queryKey: ['distributor-si-candidates', importJobId, 'tab-count', tab.id, 'open'] as const,
          enabled: enabled && importJobId > 0,
          refetchOnWindowFocus: false,
          queryFn: ({ signal }: { signal: AbortSignal }) =>
            apiGet<DsiMappingCandidatesPageResponse>(
              buildDsiCandidatesListUrl(importJobId, 0, 1, filters, { status: 'open' }),
              { signal }
            ),
        },
        {
          queryKey: ['distributor-si-candidates', importJobId, 'tab-count', tab.id, 'needs_review'] as const,
          enabled: enabled && importJobId > 0,
          refetchOnWindowFocus: false,
          queryFn: ({ signal }: { signal: AbortSignal }) =>
            apiGet<DsiMappingCandidatesPageResponse>(
              buildDsiCandidatesListUrl(importJobId, 0, 1, filters, { status: 'needs_review' }),
              { signal }
            ),
        },
      ];
    }),
  });

  const counts = emptyCounts();
  const openByTab: Record<DsiEntityTabId, number> = {
    distributor: 0,
    customer: 0,
    product: 0,
  };

  DSI_ENTITY_TABS.forEach((tab, tabIndex) => {
    const openQ = queries[tabIndex * 2];
    const needsQ = queries[tabIndex * 2 + 1];
    counts[tab.id] = {
      total: openQ.data?.total ?? (openQ.isPending ? null : 0),
      needsWork: needsQ.data?.total ?? (needsQ.isPending ? null : 0),
    };
    openByTab[tab.id] = openQ.data?.total ?? 0;
  });

  const isLoading = queries.some((q) => q.isLoading);

  return { counts, openByTab, isLoading };
}
