import { apiGet } from '@/lib/api';

import type { AdministrationOverview } from './types';

export const administrationOverviewQueryKey = ['administration', 'overview'] as const;

/** Shared by AdminChrome, AdminOverview and nav warm-up (administration domain). */
export function administrationOverviewQueryOptions() {
  return {
    queryKey: administrationOverviewQueryKey,
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      apiGet<AdministrationOverview>('/api/v1/administration/overview', { signal }),
    staleTime: 30_000,
  };
}