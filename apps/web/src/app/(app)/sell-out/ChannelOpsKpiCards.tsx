'use client';

import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import TrendingFlatIcon from '@mui/icons-material/TrendingFlat';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import { Alert, Paper, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

import type { PeriodGrain } from './intelDepth';

export type ChannelOpsSummary = {
  period_grain?: string;
  period_start?: string;
  period_end?: string;
  business_unit?: string | null;
  business_unit_applies_to?: string[];
  sell_out_this_quarter: { units: number; revenue: number };
  sell_out_prior_year_quarter: { units: number; revenue: number };
  sell_out_yoy_pct: number | null;
  total_inventory_units: number;
  weeks_of_cover: number | null;
  distributors_reporting: number;
  distributors_expected: number;
  active_customers_this_period: number;
  active_customers_prior_period: number;
  has_velocity_data: boolean;
  has_forecast_data: boolean;
  has_reconciliation_data: boolean;
};

function summaryParams(opts: {
  distributorId?: number | null;
  businessUnit?: string | null;
  periodGrain?: PeriodGrain;
  weeks?: number;
}) {
  const params = new URLSearchParams();
  if (opts.distributorId != null) params.set('distributor_id', String(opts.distributorId));
  if (opts.businessUnit) params.set('business_unit', opts.businessUnit);
  if (opts.periodGrain) params.set('period_grain', opts.periodGrain);
  if (opts.weeks != null) params.set('weeks', String(opts.weeks));
  return params;
}

export function ChannelOpsKpiCards({
  distributorId,
  businessUnit,
  periodGrain = 'quarter',
  weeks = 13,
}: {
  distributorId?: number | null;
  businessUnit?: string | null;
  periodGrain?: PeriodGrain;
  weeks?: number;
}) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['channel-ops-summary', distributorId ?? null, businessUnit ?? null, periodGrain, weeks],
    queryFn: ({ signal }) => {
      const params = summaryParams({ distributorId, businessUnit, periodGrain, weeks });
      const q = params.toString();
      return apiGet<ChannelOpsSummary>(`/api/v1/channel-ops/summary${q ? `?${q}` : ''}`, { signal });
    },
  });

  if (isError) {
    return (
      <Alert severity="error" sx={{ mb: 2 }}>
        {(error as Error)?.message ?? 'Could not load channel summary.'}
      </Alert>
    );
  }

  const yoy = data?.sell_out_yoy_pct;
  const TrendIcon =
    yoy == null ? TrendingFlatIcon : yoy > 0 ? TrendingUpIcon : yoy < 0 ? TrendingDownIcon : TrendingFlatIcon;
  const periodLabel =
    periodGrain === 'year' ? 'Sell-out YTD' : periodGrain === 'rolling_weeks' ? `Sell-out ${weeks}w` : 'Sell-out QoQ';
  const buPartial =
    Boolean(businessUnit) &&
    Array.isArray(data?.business_unit_applies_to) &&
    !data.business_unit_applies_to.includes('all');

  return (
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
      <Paper variant="outlined" sx={{ p: 2, flex: '1 1 200px' }}>
        <Typography variant="overline" color="text.secondary">
          {periodLabel}
          {businessUnit ? ` · ${businessUnit}` : ''}
        </Typography>
        <Typography variant="h5">
          {isLoading ? '—' : data?.sell_out_this_quarter.units.toLocaleString(undefined, { maximumFractionDigits: 0 })}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {isLoading
            ? '—'
            : `Revenue ${data?.sell_out_this_quarter.revenue.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
        </Typography>
        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.5 }}>
          <TrendIcon fontSize="small" color={yoy != null && yoy > 0 ? 'success' : 'inherit'} />
          <Typography variant="caption" color="text.secondary">
            {isLoading ? '…' : yoy == null ? 'Prior period n/a' : `vs prior ${(yoy * 100).toFixed(1)}%`}
          </Typography>
        </Stack>
      </Paper>
      <Paper variant="outlined" sx={{ p: 2, flex: '1 1 200px' }}>
        <Typography variant="overline" color="text.secondary">
          Channel stock{buPartial ? ' · all BUs' : ''}
        </Typography>
        <Typography variant="h5">
          {isLoading ? '—' : data?.total_inventory_units.toLocaleString(undefined, { maximumFractionDigits: 0 })}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {isLoading
            ? '—'
            : data?.weeks_of_cover != null
              ? `${data.weeks_of_cover.toFixed(1)} weeks of cover`
              : 'n/a weeks of cover'}
        </Typography>
      </Paper>
      <Paper variant="outlined" sx={{ p: 2, flex: '1 1 200px' }}>
        <Typography variant="overline" color="text.secondary">
          Reporting{buPartial ? ' · all BUs' : ''}
        </Typography>
        <Typography variant="h5">
          {isLoading
            ? '—'
            : `${data?.distributors_reporting ?? 0} of ${data?.distributors_expected ?? 0}`}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Distributors (35d)
        </Typography>
      </Paper>
      <Paper variant="outlined" sx={{ p: 2, flex: '1 1 200px' }}>
        <Typography variant="overline" color="text.secondary">
          Customers{buPartial ? ' · all BUs' : ''}
        </Typography>
        <Typography variant="h5">
          {isLoading ? '—' : data?.active_customers_this_period ?? '—'}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {isLoading
            ? '—'
            : `Prior period ${data?.active_customers_prior_period ?? 0}`}
        </Typography>
      </Paper>
    </Stack>
  );
}

export function useChannelOpsSummary(
  distributorId?: number | null,
  businessUnit?: string | null,
  periodGrain: PeriodGrain = 'quarter',
  weeks = 13,
) {
  return useQuery({
    queryKey: ['channel-ops-summary', distributorId ?? null, businessUnit ?? null, periodGrain, weeks],
    queryFn: ({ signal }) => {
      const params = summaryParams({ distributorId, businessUnit, periodGrain, weeks });
      const q = params.toString();
      return apiGet<ChannelOpsSummary>(`/api/v1/channel-ops/summary${q ? `?${q}` : ''}`, { signal });
    },
  });
}
