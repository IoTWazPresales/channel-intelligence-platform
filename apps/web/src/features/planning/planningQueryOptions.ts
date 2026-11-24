import { apiGet } from '@/lib/api';

import type { PlanningOverview } from './types';

export const planningOverviewQueryKey = ['planning', 'overview'] as const;

/** Shared by PlanningChrome, PlanningOverview and nav warm-up. */
export function planningOverviewQueryOptions() {
  return {
    queryKey: planningOverviewQueryKey,
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      apiGet<PlanningOverview>('/api/v1/planning/overview', { signal }),
    staleTime: 30_000,
  };
}