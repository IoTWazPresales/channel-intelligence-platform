'use client';

import { useQuery } from '@tanstack/react-query';

import type { TimingAlert } from '@/features/market-listings/ActivationTimingAlerts';
import { apiGet } from '@/lib/api';

export type IntelligenceRow = {
  listing_id: number;
  customer_id: number;
  product_id: number | null;
  marketplace: string;
  url: string;
  observation_count: number;
  span_days: number | null;
  history_status: string;
  first_price: number | null;
  last_price: number | null;
  price_drift_pct: number | null;
  activation_status: string | null;
  activation_message?: string | null;
  case_price?: number | null;
  case_id?: number | null;
  last_availability?: string | null;
  last_promo_badge?: string | null;
  last_fetched?: string | null;
  buy_box_label?: string | null;
  buy_box_seller?: string | null;
  worklist: boolean;
};

export type IntelligencePayload = {
  items: IntelligenceRow[];
  listings?: number;
  activation_alert_days?: number;
  timing_alerts?: TimingAlert[];
  data_unavailable?: boolean;
};

/** One key for every reader: the page header, the lenses and the timing tab share one fetch. */
export const LISTING_INTELLIGENCE_KEY = ['listing-capture', 'intelligence'] as const;

/** The read is heavy on a large registry, so it stays fresh for a while and is never retried. */
export const LISTING_INTELLIGENCE_STALE_MS = 5 * 60_000;

/**
 * The listings intelligence read, shared by every component that needs it.
 *
 * Same query key, a long ``staleTime`` and no refetch on mount, focus or reconnect: switching
 * tabs reuses the cached result instead of calling the endpoint again. Mutations still refresh it
 * (they invalidate the ``listing-capture`` prefix). ``retry`` is off so a slow failure is not
 * repeated.
 */
export function useListingIntelligence() {
  const query = useQuery({
    queryKey: LISTING_INTELLIGENCE_KEY,
    queryFn: ({ signal }) =>
      apiGet<IntelligencePayload>('/api/v1/listing-capture/intelligence', { signal }),
    staleTime: LISTING_INTELLIGENCE_STALE_MS,
    retry: false,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  /** A failed call, or an answer the API itself marks as unavailable. */
  const failed = query.isError || Boolean(query.data?.data_unavailable);
  return {
    ...query,
    failed,
    /** No answer yet (first load). Never read this as "zero observations". */
    loading: query.isPending,
    ready: !query.isPending && !failed,
  };
}
