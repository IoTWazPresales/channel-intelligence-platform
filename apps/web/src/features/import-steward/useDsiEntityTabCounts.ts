'use client';

import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

import {
  DSI_ENTITY_CANDIDATE_TABS,
  type DsiEntityTabId,
} from './dsiEntityTabs';
import { DSI_STEWARD_CONFIG } from './dsiSteward.config';
import type { DsiUnresolvedGeoRowDto } from './dsiSteward.types';
import { countUnresolvedGeoTokens } from './dsiUnresolvedGeoCount';

export type DsiEntityTabCounts = Record<DsiEntityTabId, { total: number | null; needsWork: number | null }>;

type TabCountsApiResponse = {
  import_job_id: number;
  counts: Record<string, { open: number; needs_review: number }>;
};

const emptyCounts = (): DsiEntityTabCounts => ({
  distributor: { total: null, needsWork: null },
  customer: { total: null, needsWork: null },
  product: { total: null, needsWork: null },
  region_channel: { total: null, needsWork: null },
});

export function useDsiEntityTabCounts(importJobId: number, enabled: boolean) {
  const tabCountsQuery = useQuery({
    queryKey: DSI_STEWARD_CONFIG.candidateTabCountsQueryKey(importJobId),
    enabled: enabled && importJobId > 0,
    refetchOnWindowFocus: false,
    queryFn: ({ signal }) =>
      apiGet<TabCountsApiResponse>(
        `/api/v1/mappings/import-jobs/${importJobId}/distributor-si-candidates/tab-counts`,
        { signal }
      ),
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

  if (tabCountsQuery.isSuccess && tabCountsQuery.data?.counts) {
    for (const tab of DSI_ENTITY_CANDIDATE_TABS) {
      const row = tabCountsQuery.data.counts[tab.id];
      counts[tab.id] = {
        total: row?.open ?? 0,
        needsWork: row?.needs_review ?? 0,
      };
      openByTab[tab.id] = row?.open ?? 0;
    }
  } else if (tabCountsQuery.isPending) {
    for (const tab of DSI_ENTITY_CANDIDATE_TABS) {
      counts[tab.id] = { total: null, needsWork: null };
    }
  }

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

  const isLoading = tabCountsQuery.isLoading || geoQuery.isLoading;

  return { counts, openByTab, isLoading, unresolvedGeoQuery: geoQuery };
}
