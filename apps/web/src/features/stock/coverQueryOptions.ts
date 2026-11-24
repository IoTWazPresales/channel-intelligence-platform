import { apiGet } from '@/lib/api';

export type CoverDistributionWarm = {
  buckets?: { lt2?: number };
  pair_count?: number;
  cover_as_of_date?: string | null;
  data_unavailable?: boolean;
};

export const coverDistributionQueryKey = ['channel-ops', 'cover-distribution'] as const;

/** Primary inventory / stock lens read (CoverLensView). */
export function coverDistributionQueryOptions() {
  return {
    queryKey: coverDistributionQueryKey,
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      apiGet<CoverDistributionWarm>('/api/v1/channel-ops/cover-distribution', { signal }),
    staleTime: 60_000,
  };
}

/** StockChrome header uses a distinct key so the grid fetch is not blocked on chrome-only warm-up. */
export function stockChromeCoverQueryOptions() {
  return {
    queryKey: ['channel-ops', 'cover-distribution', 'stock-chrome'] as const,
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      apiGet<CoverDistributionWarm>('/api/v1/channel-ops/cover-distribution', { signal }),
    staleTime: 60_000,
  };
}