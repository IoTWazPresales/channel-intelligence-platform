'use client';

import { Alert, Paper, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

export type PortfolioIntelligence = {
  currency_compute: string;
  currency_display_secondary: string;
  fx_note: string;
  cases_in_scope: number;
  lines_included: number;
  lines_excluded_voided: number;
  totals: {
    support_usd: number;
    support_zar: number;
    estimate_qty: number;
    result_qty: number;
    delivery_rate: number | null;
    support_per_unit_sold_usd: number | null;
    support_per_unit_sold_zar: number | null;
  };
  by_customer: Array<{
    customer_id: number;
    customer_code: string | null;
    customer_name: string | null;
    support_usd: number;
    support_zar: number;
    delivery_rate: number | null;
  }>;
  by_bu: Array<{
    bu: string;
    support_usd: number;
    support_zar: number;
    delivery_rate: number | null;
  }>;
  by_promotion_type: Array<{
    promotion_type: string;
    support_usd: number;
    support_zar: number;
    delivery_rate: number | null;
  }>;
};

function fmtUsd(n: number | null | undefined): string {
  if (n == null) return '—';
  return n.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
}

function fmtZar(n: number | null | undefined): string {
  if (n == null) return '—';
  return `R ${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return '—';
  return `${(n * 100).toFixed(1)}%`;
}

export function CporPortfolioIntelligencePanel() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['cpor', 'intelligence', 'portfolio'],
    queryFn: ({ signal }) =>
      apiGet<PortfolioIntelligence>('/api/v1/cpor/intelligence/portfolio', { signal }),
  });

  if (isError) {
    return (
      <Alert severity="error" sx={{ mb: 2 }} data-testid="cpor-portfolio-intel-error">
        {(error as Error)?.message ?? 'Could not load portfolio intelligence.'}
      </Alert>
    );
  }

  const t = data?.totals;

  return (
    <Stack spacing={1.5} sx={{ mb: 2 }} data-testid="cpor-portfolio-intel">
      <Typography variant="subtitle2">Portfolio intelligence</Typography>
      <Typography variant="caption" color="text.secondary">
        Compute USD · display ZAR at each case FX · voided excluded · no claim-rate (collapses to delivery)
      </Typography>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} useFlexGap flexWrap="wrap">
        <Paper variant="outlined" sx={{ p: 2, flex: '1 1 180px' }}>
          <Typography variant="overline" color="text.secondary">
            Support spend
          </Typography>
          <Typography variant="h6">{isLoading ? '—' : fmtUsd(t?.support_usd)}</Typography>
          <Typography variant="body2" color="text.secondary">
            {isLoading ? '—' : fmtZar(t?.support_zar)}
          </Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 2, flex: '1 1 180px' }}>
          <Typography variant="overline" color="text.secondary">
            Delivery rate
          </Typography>
          <Typography variant="h6">{isLoading ? '—' : fmtPct(t?.delivery_rate)}</Typography>
          <Typography variant="body2" color="text.secondary">
            {isLoading
              ? '—'
              : `result ${t?.result_qty?.toLocaleString() ?? '—'} / est ${t?.estimate_qty?.toLocaleString() ?? '—'}`}
          </Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 2, flex: '1 1 180px' }}>
          <Typography variant="overline" color="text.secondary">
            Support / unit sold
          </Typography>
          <Typography variant="h6">
            {isLoading ? '—' : fmtUsd(t?.support_per_unit_sold_usd)}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {isLoading ? '—' : fmtZar(t?.support_per_unit_sold_zar)}
          </Typography>
        </Paper>
      </Stack>
      {!isLoading && data && data.by_bu.length > 0 ? (
        <Typography variant="caption" color="text.secondary" data-testid="cpor-portfolio-bu-summary">
          Top BU: {data.by_bu[0].bu} · {fmtUsd(data.by_bu[0].support_usd)} ({fmtZar(data.by_bu[0].support_zar)})
          {data.by_promotion_type[0]
            ? ` · Top promo: ${data.by_promotion_type[0].promotion_type}`
            : ''}
          {` · ${data.cases_in_scope} cases / ${data.lines_included} lines`}
        </Typography>
      ) : null}
    </Stack>
  );
}
