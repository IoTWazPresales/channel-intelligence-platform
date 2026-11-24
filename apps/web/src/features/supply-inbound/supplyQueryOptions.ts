import { apiGet } from '@/lib/api';

import type { SupplyOverview } from './types';

export const supplyOverviewQueryKey = ['supply', 'overview'] as const;

/** Shared by SupplyChrome and background nav warm-up (same cache key). */
export function supplyOverviewQueryOptions() {
  return {
    queryKey: supplyOverviewQueryKey,
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      apiGet<SupplyOverview>('/api/v1/supply/overview', { signal }),
    staleTime: 30_000,
  };
}