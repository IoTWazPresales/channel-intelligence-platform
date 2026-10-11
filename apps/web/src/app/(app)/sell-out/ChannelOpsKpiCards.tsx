'use client';

import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Alert, Box, Button, Collapse, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { apiGet } from '@/lib/api';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';

export type ChannelOpsSummary = {
  sell_out_this_quarter: {
    units: number;
    revenue: number;
    has_data?: boolean;
    period_start?: string;
    period_end?: string;
  };
  sell_out_prior_year_quarter: {
    units: number;
    revenue: number;
    period_start?: string;
    period_end?: string;
  };
  sell_out_yoy_pct: number | null;
  sell_out_data_vintage?: {
    max_transaction_date: string | null;
    current_quarter_has_data: boolean;
    as_of_date: string;
  };
  total_inventory_units: number;
  weeks_of_cover: number | null;
  replenishment_threshold_weeks?: number;
  replenishment_flag?: boolean;
  replenishment_pairs_below_threshold?: number;
  replenishment_pair_count?: number;
  distributors_reporting: number;
  distributors_expected: number;
  active_customers_this_period: number;
  active_customers_prior_period: number;
  has_velocity_data: boolean;
  has_forecast_data: boolean;
  has_reconciliation_data: boolean;
};

export function ChannelOpsKpiCards({ distributorId }: { distributorId?: number | null }) {
  const [aboutOpen, setAboutOpen] = useState(false);
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['channel-ops-summary', distributorId ?? null],
    queryFn: ({ signal }) => {
      const params = new URLSearchParams();
      if (distributorId != null) params.set('distributor_id', String(distributorId));
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
  const currentHasData = data?.sell_out_this_quarter?.has_data ?? data?.sell_out_data_vintage?.current_quarter_has_data;
  const vintage = data?.sell_out_data_vintage?.max_transaction_date;
  const cover = data?.weeks_of_cover;
  const coverSeverity = cover == null ? 'neutral' : cover < 2 ? 'bad' : cover < 4 ? 'warn' : 'neutral';
  const yoyText =
    currentHasData === false
      ? 'YoY n/a (no current-quarter coverage)'
      : yoy == null
        ? 'YoY n/a'
        : `${(yoy * 100).toFixed(1)}%`;

  return (
    <>
    <HeadlineStrip>
      <HeadlineFigure
        testId="channel-ops-sellout-kpi"
        label="Sell-out this quarter"
        state={isLoading ? 'loading' : currentHasData === false ? 'empty' : 'ready'}
        stateNote={
          currentHasData === false
            ? vintage
              ? `Vintage ${vintage}`
              : 'No sell-out in this calendar quarter'
            : undefined
        }
        value={
          currentHasData === false
            ? 'No data'
            : (data?.sell_out_this_quarter.units.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? '—')
        }
        unit="units"
        caption={
          currentHasData === false
            ? undefined
            : `Revenue ${data?.sell_out_this_quarter.revenue.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? '—'}`
        }
        delta={
          yoy == null || currentHasData === false
            ? { text: yoyText, direction: 'flat', goodWhen: 'neutral' }
            : { text: yoyText, direction: yoy > 0 ? 'up' : yoy < 0 ? 'down' : 'flat', goodWhen: 'up' }
        }
      />
      <HeadlineFigure
        label="Channel stock"
        state={isLoading ? 'loading' : 'ready'}
        value={data?.total_inventory_units.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? '—'}
        unit="units"
        caption={cover != null ? `${cover.toFixed(1)} weeks of cover` : 'n/a weeks of cover'}
        severity={coverSeverity}
      />
      <HeadlineFigure
        testId="channel-ops-replenishment"
        label="Replenish flag"
        state={isLoading ? 'loading' : data?.replenishment_pairs_below_threshold == null ? 'empty' : 'ready'}
        stateNote={
          !isLoading && data?.replenishment_pairs_below_threshold == null ? 'Reorder point not available' : undefined
        }
        value={data?.replenishment_pairs_below_threshold ?? '—'}
        unit="pairs"
        caption={
          data?.replenishment_pairs_below_threshold == null
            ? undefined
            : `Below ${data.replenishment_threshold_weeks ?? 4} weeks${
                data.replenishment_flag ? ' · portfolio below threshold' : ''
              }. A flag, not a buy recommendation.`
        }
        severity={
          (data?.replenishment_pairs_below_threshold ?? 0) > 0 || data?.replenishment_flag ? 'warn' : 'neutral'
        }
      />
      <HeadlineFigure
        label="Reporting"
        state={isLoading ? 'loading' : 'ready'}
        value={`${data?.distributors_reporting ?? 0} of ${data?.distributors_expected ?? 0}`}
        caption="Distributors in the last 35 days"
      />
      <HeadlineFigure
        label="Customers"
        state={isLoading ? 'loading' : 'ready'}
        value={data?.active_customers_this_period ?? '—'}
        caption={`Prior period ${data?.active_customers_prior_period ?? 0}`}
      />
    </HeadlineStrip>
    <Button
      size="small"
      variant="text"
      onClick={() => setAboutOpen((open) => !open)}
      aria-expanded={aboutOpen}
      endIcon={<ExpandMoreIcon sx={{ transform: aboutOpen ? 'rotate(180deg)' : 'none', transition: 'transform 120ms' }} />}
      sx={{ px: 0.5, mt: 0.5 }}
      data-testid="channel-ops-about-figure"
    >
      About this figure
    </Button>
    <Collapse in={aboutOpen}>
      <Box sx={{ mt: 0.5, mb: 1, p: 1.5, borderRadius: 1, bgcolor: 'action.hover' }} data-testid="channel-ops-about">
        <Typography variant="body2">
          Sell-out this quarter is units sold by distributors in the current calendar quarter. Revenue sits beside it. The change compares that quarter with the same quarter last year. If this quarter has no sales yet, the change is left blank.
        </Typography>
        <Typography variant="body2" sx={{ mt: 1 }}>
          Channel stock is units on hand. Weeks of cover is that stock divided by the weekly selling pace. Under 2 weeks is a problem. Under 4 weeks is a watch.
        </Typography>
        <Typography variant="body2" sx={{ mt: 1 }}>
          The replenishment line counts distributor and product pairs under the reorder point, 4 weeks unless a different point is set. It is a flag, not a buy recommendation. Reporting is how many distributors sent data in the last 35 days. Customers is how many bought this period, with the prior period beside it.
        </Typography>
      </Box>
    </Collapse>
    </>
  );
}

export function useChannelOpsSummary(distributorId?: number | null) {
  return useQuery({
    queryKey: ['channel-ops-summary', distributorId ?? null],
    queryFn: ({ signal }) => {
      const params = new URLSearchParams();
      if (distributorId != null) params.set('distributor_id', String(distributorId));
      const q = params.toString();
      return apiGet<ChannelOpsSummary>(`/api/v1/channel-ops/summary${q ? `?${q}` : ''}`, { signal });
    },
  });
}
