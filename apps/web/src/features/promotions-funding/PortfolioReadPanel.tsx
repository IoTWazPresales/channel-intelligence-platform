'use client';

import { Box, Button, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useId, useState } from 'react';

import { ModuleDataSection } from '@/components/ModuleDataSection';
import { DualMoney } from '@/features/cpor/DualMoney';
import { fmtInt } from '@/features/promotions-funding/format';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';
import { apiGet } from '@/lib/api';

/** Subset of GET /cpor/intelligence/portfolio this panel reads. */
export type PortfolioIntelligence = {
  cases_in_scope: number;
  lines_included: number;
  evidence_basis_mix?: { claim_evidenced?: number; source_attested?: number; none?: number };
  totals: {
    support_usd: number;
    support_zar: number;
    estimate_qty: number;
    result_qty: number;
    delivery_rate: number | null;
    support_per_unit_sold_usd: number | null;
    support_per_unit_sold_zar: number | null;
  };
  claim_evidenced_only?: { cases_in_scope: number; delivery_rate: number | null };
  by_bu: Array<{ bu: string; support_usd: number; support_zar: number }>;
  by_promotion_type: Array<{ promotion_type: string; support_usd: number; support_zar: number }>;
};

type NormsPayload = {
  trailing_quarters: number;
  window_quarters: string[];
  anchor_quarter: string | null;
  window_source?: string;
  env_override_active?: boolean;
  attested_unmatched_file?: { case_count: number };
  by_customer: Array<{
    customer_id: number;
    customer_code: string | null;
    customer_name: string | null;
    quarters_present: number;
    absolute_support_usd_avg: number;
    absolute_support_zar_avg: number;
    support_pct_of_srp_avg: number | null;
  }>;
};

/** Delivery rate is always a ratio here (result ÷ estimate) and can exceed 1 — `fmtPct` guesses. */
function fmtRatio(v: number | null | undefined): string {
  return v == null || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(1)}%`;
}

/**
 * All-lifecycle portfolio read on the Case book lens (N-0044, operator decision D-c; placement is a
 * reversible default pending D-0032). Trimmed from the unmounted CporPortfolioIntelligencePanel:
 * the cost-per-incremental-unit tile is gone (A2-X is `do_not_build` in the semantic catalog) and
 * so is the support-bias block (the Promotion planner owns it, and forbids its ratio). Money goes
 * through DualMoney — local primary, the API's per-line booked USD sum secondary.
 *
 * Collapsed by default: the body (and its two queries) mounts only when opened.
 */
export function PortfolioReadPanel({ currencyCode }: { currencyCode: string }) {
  const [open, setOpen] = useState(false);
  const bodyId = useId();
  return (
    <Box data-testid="case-book-portfolio-read">
      <Panel
        title="Portfolio read — all non-superseded cases"
        subtitle="Every lifecycle stage including settled, intelligence-excluded cases left out. The open book above is a narrower scope."
        actions={
          <Button
            size="small"
            variant="text"
            aria-expanded={open}
            aria-controls={bodyId}
            onClick={() => setOpen((v) => !v)}
            data-testid="case-book-portfolio-toggle"
          >
            {open ? 'Hide' : 'Show'}
          </Button>
        }
      >
        <Box id={bodyId} hidden={!open}>
          {open ? <PortfolioReadBody currencyCode={currencyCode} /> : null}
        </Box>
      </Panel>
    </Box>
  );
}

function PortfolioReadBody({ currencyCode }: { currencyCode: string }) {
  // Same key as the FundingChrome delivery-rate meta, so this is normally a cache hit.
  const q = useQuery({
    queryKey: ['cpor', 'intelligence', 'portfolio'],
    queryFn: ({ signal }) => apiGet<PortfolioIntelligence>('/api/v1/cpor/intelligence/portfolio', { signal }),
  });
  const data = q.data;
  const t = data?.totals;
  const mix = data?.evidence_basis_mix;
  const claimOnly = data?.claim_evidenced_only;
  const topBu = data?.by_bu?.[0];
  const topPromo = data?.by_promotion_type?.[0];

  return (
    <Stack spacing={2}>
      <ModuleDataSection
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.isError ? new Error(String((q.error as Error)?.message ?? 'Could not load the portfolio read')) : null}
        onRetry={() => void q.refetch()}
        isEmpty={!data || data.cases_in_scope === 0}
        empty={{ title: 'No cases in scope', description: 'No non-superseded, non-excluded cases have lines yet.' }}
        loadingLabel="Loading portfolio read…"
      >
        <Stack spacing={1.5}>
          <Typography variant="caption" color="text.secondary" data-testid="case-book-portfolio-scope">
            {data?.cases_in_scope ?? 0} cases · {data?.lines_included ?? 0} lines · voided excluded · mixed evidence:
            claim {mix?.claim_evidenced ?? 0} · attested {mix?.source_attested ?? 0} · none {mix?.none ?? 0}
          </Typography>
          <HeadlineStrip columns={3}>
            <HeadlineFigure
              label="Support spend"
              value={
                <DualMoney
                  amount={t?.support_zar}
                  currencyCode={currencyCode}
                  usdAmount={t?.support_usd ?? null}
                  usdNote={t?.support_usd != null ? 'Σ per-line booked USD' : undefined}
                  missingRoe={t?.support_usd == null}
                  testId="portfolio-support"
                />
              }
              compact
              caption="Σ line ttl_support across all lifecycle stages"
            />
            <HeadlineFigure
              label="Delivery rate"
              value={fmtRatio(t?.delivery_rate)}
              compact
              caption={`Result ${fmtInt(t?.result_qty)} / est ${fmtInt(t?.estimate_qty)}${
                claimOnly && claimOnly.cases_in_scope > 0
                  ? ` · claim-evidenced only ${fmtRatio(claimOnly.delivery_rate)} over ${claimOnly.cases_in_scope} cases`
                  : ''
              }`}
            />
            <HeadlineFigure
              label="Support / unit sold"
              value={
                <DualMoney
                  amount={t?.support_per_unit_sold_zar}
                  currencyCode={currencyCode}
                  usdAmount={t?.support_per_unit_sold_usd ?? null}
                  usdNote={t?.support_per_unit_sold_usd != null ? 'booked USD per unit sold' : undefined}
                  missingRoe={t?.support_per_unit_sold_usd == null}
                  testId="portfolio-per-unit"
                />
              }
              compact
              caption="Support spend ÷ result units"
            />
          </HeadlineStrip>
          {topBu || topPromo ? (
            <Stack spacing={0.25} data-testid="case-book-portfolio-top">
              {topBu ? (
                <PanelRow
                  primary={`Top BU · ${topBu.bu}`}
                  secondary="Largest support spend by business unit"
                  figure={
                    <DualMoney
                      amount={topBu.support_zar}
                      currencyCode={currencyCode}
                      usdAmount={topBu.support_usd}
                      usdNote="Σ per-line booked USD"
                      testId="portfolio-top-bu"
                    />
                  }
                />
              ) : null}
              {topPromo ? (
                <PanelRow
                  primary={`Top promotion type · ${topPromo.promotion_type}`}
                  secondary="Largest support spend by mechanic"
                  figure={
                    <DualMoney
                      amount={topPromo.support_zar}
                      currencyCode={currencyCode}
                      usdAmount={topPromo.support_usd}
                      usdNote="Σ per-line booked USD"
                      testId="portfolio-top-promo"
                    />
                  }
                />
              ) : null}
            </Stack>
          ) : null}
        </Stack>
      </ModuleDataSection>
      <SupportNorms currencyCode={currencyCode} />
    </Stack>
  );
}

function SupportNorms({ currencyCode }: { currencyCode: string }) {
  const q = useQuery({
    queryKey: ['cpor', 'intelligence', 'norms'],
    queryFn: ({ signal }) => apiGet<NormsPayload>('/api/v1/cpor/intelligence/norms', { signal }),
  });
  const data = q.data;
  const top = data?.by_customer?.slice(0, 5) ?? [];

  return (
    <Box data-testid="case-book-portfolio-norms">
      <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
        Support norms by customer · trailing {data?.trailing_quarters ?? 4}Q
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
        % = support per unit ÷ SRP · window {data?.window_quarters?.join(' · ') ?? '…'}
        {data?.anchor_quarter ? ` · anchor ${data.anchor_quarter}` : ''}
        {data?.window_source ? ` · source ${data.window_source}${data.env_override_active ? ' (env override)' : ''}` : ''}
        {data?.attested_unmatched_file
          ? ` · ${data.attested_unmatched_file.case_count} attested Case IDs unmatched in the file (CN/payment, not ttl_support)`
          : ''}
      </Typography>
      <ModuleDataSection
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.isError ? new Error(String((q.error as Error)?.message ?? 'Support norms unavailable')) : null}
        onRetry={() => void q.refetch()}
        isEmpty={top.length === 0}
        empty={{ title: 'No trailing-quarter support yet', description: 'Norms appear once cases fall inside the window.' }}
        loadingLabel="Loading support norms…"
      >
        <Stack spacing={0.25}>
          {top.map((c) => (
            <PanelRow
              key={c.customer_id}
              primary={c.customer_name ?? c.customer_code ?? String(c.customer_id)}
              secondary={`${
                c.support_pct_of_srp_avg != null ? `${(c.support_pct_of_srp_avg * 100).toFixed(1)}% of SRP` : 'SRP % n/a'
              } · ${c.quarters_present}Q present`}
              figure={
                <DualMoney
                  amount={c.absolute_support_zar_avg}
                  currencyCode={currencyCode}
                  usdAmount={c.absolute_support_usd_avg}
                  usdNote="avg · booked USD"
                  testId={`portfolio-norm-${c.customer_id}`}
                />
              }
            />
          ))}
        </Stack>
      </ModuleDataSection>
    </Box>
  );
}
