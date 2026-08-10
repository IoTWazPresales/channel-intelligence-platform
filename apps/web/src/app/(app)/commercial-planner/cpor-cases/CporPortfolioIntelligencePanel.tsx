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
  incremental_unit_cost?: {
    cases_ok: number;
    cases_flagged: number;
    cases_evaluated: number;
    avg_cost_per_incremental_unit_usd: number | null;
    note?: string;
  };
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
        Compute USD · display ZAR at each case FX · voided excluded · no claim-rate (no distinct
        owed vs computed support; paid is payment recon — separate)
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
        <Paper variant="outlined" sx={{ p: 2, flex: '1 1 180px' }} data-testid="cpor-incremental-unit-cost">
          <Typography variant="overline" color="text.secondary">
            Cost / incremental unit
          </Typography>
          <Typography variant="h6">
            {isLoading
              ? '—'
              : fmtUsd(data?.incremental_unit_cost?.avg_cost_per_incremental_unit_usd)}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {isLoading
              ? '—'
              : `${data?.incremental_unit_cost?.cases_ok ?? 0} ok / ${data?.incremental_unit_cost?.cases_flagged ?? 0} flagged (baseline)`}
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

      <CporSupportBiasSection />
      <CporSupportNormsSection />
    </Stack>
  );
}

type SupportBiasPayload = {
  reservation_source: string;
  cases_in_scope: number;
  missing_sku_lines: number;
  planned_lines_included: number;
  totals: {
    planned_usd: number | null;
    actual_usd: number;
    bias_pct: number | null;
    flags: string[];
  };
  sku_assumption_seed_hint?: string;
};

function CporSupportBiasSection() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['cpor', 'intelligence', 'support-bias'],
    queryFn: ({ signal }) =>
      apiGet<SupportBiasPayload>('/api/v1/cpor/intelligence/support-bias?limit_cases=100', { signal }),
  });

  if (isError) {
    return (
      <Alert severity="warning" data-testid="cpor-support-bias-error">
        Support bias unavailable.
      </Alert>
    );
  }

  const t = data?.totals;
  const missingLines = (data?.missing_sku_lines ?? 0) > 0;
  const plannedMissing = t?.planned_usd == null;

  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid="cpor-support-bias">
      <Typography variant="subtitle2">Support bias (A1-09)</Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
        Planned campaign reservation (derived_from_profit / SKU reserve) vs actual CPOR support USD · not
        claim or paid
      </Typography>
      {isLoading ? (
        <Typography variant="body2">Loading…</Typography>
      ) : (
        <Stack spacing={0.5}>
          <Typography variant="body2" data-testid="cpor-support-bias-planned">
            Planned: {fmtUsd(t?.planned_usd ?? null)}
            {plannedMissing ? ' (seed SKU economics to compute)' : ''}
          </Typography>
          <Typography variant="body2" data-testid="cpor-support-bias-actual">
            Actual: {fmtUsd(t?.actual_usd)}
          </Typography>
          <Typography variant="body2" data-testid="cpor-support-bias-pct">
            Bias:{' '}
            {t?.bias_pct != null
              ? `${(t.bias_pct * 100).toFixed(1)}% (actual − planned) / planned`
              : '—'}
          </Typography>
          {missingLines ? (
            <Alert severity="info" data-testid="cpor-support-bias-missing-sku">
              Missing SKU assumptions on {data?.missing_sku_lines ?? 0} lines. Seed via Commercial Planner
              SKU economics or product admin — never silent zero.
            </Alert>
          ) : null}
        </Stack>
      )}
    </Paper>
  );
}

type NormsPayload = {
  trailing_quarters: number;
  window_quarters: string[];
  anchor_quarter: string | null;
  window_source?: string;
  env_override_active?: boolean;
  tenant_profile_default?: number;
  by_customer: Array<{
    customer_id: number;
    customer_code: string | null;
    customer_name: string | null;
    quarters_present: number;
    absolute_support_usd_avg: number;
    absolute_support_zar_avg: number;
    absolute_support_usd_total: number;
    support_pct_of_srp_avg: number | null;
  }>;
};

function CporSupportNormsSection() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['cpor', 'intelligence', 'norms'],
    queryFn: ({ signal }) => apiGet<NormsPayload>('/api/v1/cpor/intelligence/norms', { signal }),
  });

  if (isError) {
    return (
      <Alert severity="warning" data-testid="cpor-norms-error">
        Support norms unavailable.
      </Alert>
    );
  }

  const top = data?.by_customer?.slice(0, 5) ?? [];

  return (
    <Stack spacing={0.75} data-testid="cpor-support-norms" sx={{ mt: 1 }}>
      <Typography variant="subtitle2">Support norms (trailing {data?.trailing_quarters ?? 4}Q)</Typography>
      <Typography variant="caption" color="text.secondary" data-testid="cpor-norms-window-source">
        Absolute USD/ZAR · % = support_unit / SRP · window {data?.window_quarters?.join(' · ') ?? '…'}
        {data?.anchor_quarter ? ` · anchor ${data.anchor_quarter}` : ''}
        {data?.window_source
          ? ` · source ${data.window_source}${data.env_override_active ? ' (env override)' : ''}`
          : ''}
      </Typography>
      {isLoading ? (
        <Typography variant="body2">Loading norms…</Typography>
      ) : (
        <Stack spacing={0.5}>
          {top.map((c) => (
            <Typography key={c.customer_id} variant="body2" data-testid={`cpor-norm-row-${c.customer_id}`}>
              {c.customer_code ?? c.customer_id} — {c.customer_name ?? '—'} · avg{' '}
              {fmtUsd(c.absolute_support_usd_avg)} ({fmtZar(c.absolute_support_zar_avg)}) ·{' '}
              {c.support_pct_of_srp_avg != null
                ? `${(c.support_pct_of_srp_avg * 100).toFixed(1)}% of SRP`
                : 'SRP % n/a'}{' '}
              · {c.quarters_present}Q present
            </Typography>
          ))}
          {!top.length ? (
            <Typography variant="body2" color="text.secondary">
              No trailing-quarter support yet.
            </Typography>
          ) : null}
        </Stack>
      )}
    </Stack>
  );
}
