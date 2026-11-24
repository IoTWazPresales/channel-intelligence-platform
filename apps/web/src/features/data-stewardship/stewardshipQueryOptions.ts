import { apiGet } from '@/lib/api';

import type { StewardshipSummary } from './types';

export const stewardshipSummaryQueryKey = ['imports', 'stewardship-summary'] as const;

/** Shared by DataChrome and nav warm-up. */
export function stewardshipSummaryQueryOptions() {
  return {
    queryKey: stewardshipSummaryQueryKey,
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      apiGet<StewardshipSummary>('/api/v1/imports/stewardship-summary', { signal }),
    staleTime: 30_000,
  };
}