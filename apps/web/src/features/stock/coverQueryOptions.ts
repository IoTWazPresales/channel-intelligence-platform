import type { UseQueryOptions } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

import type { CoverPairStatus } from './coverStatus';

export type CoverItem = {
  id: string;
  distributor_id: number;
  distributor_code: string;
  distributor_name: string;
  product_id: number;
  sku: string;
  sales_model_name?: string | null;
  product_name: string;
  family: string;
  weeks_of_cover: number | null;
  derived_stock: number;
  weekly_velocity: number | null;
  inbound_open: number;
  vintage_days: number;
  status: CoverPairStatus | null;
  lab_bucket: string | null;
  replenishment_flag: boolean;
  cover_as_of_date: string;
};

export type CoverDistribution = {
  data_unavailable?: boolean;
  pair_count: number;
  under_4w: number;
  mean_woc: number | null;
  buckets: Record<string, number>;
  lab_buckets?: { bucket: string; pairs: number }[];
  headlines?: {
    soh: number;
    network_cover: number | null;
    pairs: number;
    with_woc: number;
    distributor_count: number;
    breach: number;
    watch: number;
    excess: number;
  };
  items?: CoverItem[];
  cover_as_of_date?: string | null;
  weekly_flow?: {
    points: { week: string; week_start: string; sellOut: number; shipped: number }[];
    sell_out_through: string | null;
    shipped_through: string | null;
  };
  scopes?: {
    distributors: { id: number; code: string; name: string; pairs: number }[];
    families: { family: string; pairs: number }[];
  };
};

/** @deprecated Use CoverDistribution — kept for imports that expected the warm alias. */
export type CoverDistributionWarm = CoverDistribution;

export const coverDistributionQueryKey = ['channel-ops', 'cover-distribution'] as const;

const stockChromeCoverQueryKey = ['channel-ops', 'cover-distribution', 'stock-chrome'] as const;

export const COVER_DISTRIBUTION_STALE_MS = 60_000;

export function fetchCoverDistribution(signal: AbortSignal): Promise<CoverDistribution> {
  return apiGet<CoverDistribution>('/api/v1/channel-ops/cover-distribution', { signal });
}

/** Primary inventory / stock lens read (CoverLensView). */
export function coverDistributionQueryOptions(): UseQueryOptions<
  CoverDistribution,
  Error,
  CoverDistribution,
  typeof coverDistributionQueryKey
> {
  return {
    queryKey: coverDistributionQueryKey,
    queryFn: ({ signal }) => fetchCoverDistribution(signal),
    staleTime: COVER_DISTRIBUTION_STALE_MS,
  };
}

/** StockChrome header uses a distinct key so the grid fetch is not blocked on chrome-only warm-up. */
export function stockChromeCoverQueryOptions(): UseQueryOptions<
  CoverDistribution,
  Error,
  CoverDistribution,
  typeof stockChromeCoverQueryKey
> {
  return {
    queryKey: stockChromeCoverQueryKey,
    queryFn: ({ signal }) => fetchCoverDistribution(signal),
    staleTime: COVER_DISTRIBUTION_STALE_MS,
  };
}