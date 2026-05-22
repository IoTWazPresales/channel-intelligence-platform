'use client';

import { useQueries, useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

import { buildDsiCandidatesListUrl, type DsiMappingCandidatesPageResponse } from './dsiCandidatesQuery';
import {
  DSI_ENTITY_CANDIDATE_TABS,
  defaultDsiStewardFiltersForTab,
  type DsiEntityTabId,
} from './dsiEntityTabs';
import { DSI_STEWARD_CONFIG } from './dsiSteward.config';
import type { DsiUnresolvedGeoRowDto } from './dsiSteward.types';
import { countUnresolvedGeoTokens } from './dsiUnresolvedGeoCount';

export type DsiEntityTabCounts = Record<DsiEntityTabId, { total: number | null; needsWork: number | null }>;

const emptyCounts = (): DsiEntityTabCounts => ({
  distributor: { total: null, needsWork: null },
  customer: { total: null, needsWork: null },
  product: { total: null, needsWork: null },
  region_channel: { total: null, needsWork: null },
});

export function useDsiEntityTabCounts(importJobId: number, enabled: boolean) {
  const entityQueries = useQueries({
    queries: DSI_ENTITY_CANDIDATE_TABS.flatMap((tab) => {
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

  const geoQuery = useQuery({
    queryKey: DSI_STEWARD_CONFIG.unresolvedGeoTokensQueryKey(importJobId),
    enabled: enabled && importJobId > 0,
    refetchOnWindowFocus: false,
    queryFn: ({ signal }) =>
      apiGet<{
        import_job_id: number;
        channels: DsiUnresolvedGeoRowDto[];
        regions: DsiUnresolvedGeoRowDto[];
      }>(`/api/v1/mappings/import-jobs/${importJobId}/dsi-unresolved-geo-tokens`, { signal }),
  });

  const counts = emptyCounts();
  const openByTab: Record<DsiEntityTabId, number> = {
    distributor: 0,
    customer: 0,
    product: 0,
    region_channel: 0,
  };

  DSI_ENTITY_CANDIDATE_TABS.forEach((tab, tabIndex) => {
    const openQ = entityQueries[tabIndex * 2];
    const needsQ = entityQueries[tabIndex * 2 + 1];
    counts[tab.id] = {
      total: openQ.data?.total ?? (openQ.isPending ? null : 0),
      needsWork: needsQ.data?.total ?? (needsQ.isPending ? null : 0),
    };
    openByTab[tab.id] = openQ.data?.total ?? 0;
  });

  const geoTotal = geoQuery.isSuccess
    ? countUnresolvedGeoTokens(geoQuery.data)
    : geoQuery.isPending
      ? null
      : 0;
  counts.region_channel = {
    total: geoTotal,
    needsWork: geoTotal,
  };
  openByTab.region_channel = geoTotal ?? 0;

  const isLoading = entityQueries.some((q) => q.isLoading) || geoQuery.isLoading;

  return { counts, openByTab, isLoading, unresolvedGeoQuery: geoQuery };
}
