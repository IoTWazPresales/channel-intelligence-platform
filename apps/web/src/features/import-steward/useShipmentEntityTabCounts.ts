'use client';

import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

import { SHIPMENT_STEWARD_CONFIG } from './shipmentSteward.config';
import { SHIPMENT_ENTITY_TAB_DEFS, type ShipmentEntityTabId } from './shipmentEntityTabs';

export type { ShipmentEntityTabId };
export const SHIPMENT_ENTITY_TABS = SHIPMENT_ENTITY_TAB_DEFS;

type TabCountsApiResponse = {
  import_job_id: number;
  counts: Record<string, { open: number; needs_work: number; needs_review: number }>;
};

export function useShipmentEntityTabCounts(importJobId: number, enabled: boolean) {
  const tabCountsQuery = useQuery({
    queryKey: SHIPMENT_STEWARD_CONFIG.candidateTabCountsQueryKey(importJobId),
    enabled: enabled && importJobId > 0,
    refetchOnWindowFocus: false,
    queryFn: ({ signal }) =>
      apiGet<TabCountsApiResponse>(
        `/api/v1/shipment-evidence/import-jobs/${importJobId}/mapping-candidates/tab-counts`,
        { signal }
      ),
  });

  const counts: Record<ShipmentEntityTabId, { total: number | null; needsWork: number | null }> = {
    distributor: { total: null, needsWork: null },
    customer: { total: null, needsWork: null },
  };
  const openByTab: Record<ShipmentEntityTabId, number> = { distributor: 0, customer: 0 };

  if (tabCountsQuery.isSuccess && tabCountsQuery.data?.counts) {
    for (const tab of SHIPMENT_ENTITY_TABS) {
      const row = tabCountsQuery.data.counts[tab.id];
      counts[tab.id] = { total: row?.open ?? 0, needsWork: row?.needs_work ?? row?.open ?? 0 };
      openByTab[tab.id] = row?.open ?? 0;
    }
  }

  return { counts, openByTab, tabCountsQuery };
}
