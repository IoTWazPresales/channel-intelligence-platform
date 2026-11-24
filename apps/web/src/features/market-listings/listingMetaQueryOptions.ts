import { apiGet } from '@/lib/api';

type ListingMeta = {
  sites?: { site_key: string; display_name: string; configured: boolean }[];
};

export const listingCaptureMetaQueryKey = ['listing-capture', 'meta'] as const;

/** Light market-domain warm-up (skipped: listings grid and intelligence — heavy reads). */
export function listingCaptureMetaQueryOptions() {
  return {
    queryKey: listingCaptureMetaQueryKey,
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      apiGet<ListingMeta>('/api/v1/listing-capture/meta', { signal }),
    staleTime: 60_000,
  };
}