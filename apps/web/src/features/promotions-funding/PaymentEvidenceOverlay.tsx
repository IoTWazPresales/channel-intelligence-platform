'use client';

import { Alert, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { fmtCompact, fmtInt, fmtPct } from '@/features/promotions-funding/format';
import { evidenceBasisLabel } from '@/features/promotions-funding/evidenceBasis';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';
import { apiGet } from '@/lib/api';

export type PaymentEvidenceOverlay = {
  row_count: number;
  distinct_file_case_codes: number;
  cip_case_count: number;
  matched_cip_case_count: number;
  unmatched_cip_case_count: number;
  unmatched_file_case_count: number;
  unmatched_file_attested_count?: number;
  unmatched_file_attested_amount_by_currency?: Record<string, number>;
  unmatched_file_amount_note?: string;
  unmatched_file_rows?: Array<{
    id: number;
    external_case_code: string;
    case_id: number | null;
    payment_status: string | null;
    amount: number | null;
    currency_code: string | null;
    customer_token: string | null;
    evidence_basis: string;
  }>;
  match_rate: number | null;
  pending_row_count: number;
  pending_with_comment_count: number;
  pending_rows: Array<{
    id: number;
    external_case_code: string;
    payment_status: string | null;
    latest_comment: string | null;
    case_id: number | null;
    currency_code: string | null;
  }>;
  unmatched_cip_sample: string[];
  unmatched_file_sample: string[];
  unmatched_cip_note?: string;
  paid_note: string;
  not_claim_evidence: boolean;
  match_rule: string;
};

export function PaymentEvidenceOverlayPanel() {
  const { data, isError, error } = useQuery({
    queryKey: ['cpor', 'payment', 'overlay'],
    queryFn: ({ signal }) =>
      apiGet<PaymentEvidenceOverlay>('/api/v1/cpor/payment-evidence/overlay', { signal }),
    staleTime: 15_000,
  });

  const disputed = useMemo(
    () => (data?.pending_rows ?? []).filter((r) => (r.latest_comment || '').trim()),
    [data],
  );

  return (
    <Stack spacing={2} data-testid="cpor-payment-overlay">
      {isError ? (
        <Alert severity="error">{error instanceof Error ? error.message : 'Overlay failed'}</Alert>
      ) : null}
      <HeadlineStrip columns={4}>
        <HeadlineFigure
          label="CIP cases in this file"
          value={data ? `${fmtInt(data.matched_cip_case_count)} / ${fmtInt(data.cip_case_count)}` : '—'}
          compact
          caption={data ? `Exact Case ID match ${fmtPct(data.match_rate)} — no fuzzy` : 'Exact Case ID'}
        />
        <HeadlineFigure
          label="Unmatched CIP cases"
          value={fmtInt(data?.unmatched_cip_case_count ?? null)}
          compact
          caption="Stay reviewable — not auto-created"
        />
        <HeadlineFigure
          label="Unmatched file cases"
          value={fmtInt(data?.unmatched_file_case_count ?? null)}
          compact
          caption={`${fmtInt(data?.unmatched_file_attested_count ?? null)} closed/paid source-attested · ${fmtInt(data?.distinct_file_case_codes ?? null)} distinct Case IDs`}
        />
        <HeadlineFigure
          label="Pending rows"
          value={fmtInt(data?.pending_row_count ?? null)}
          compact
          caption={`${fmtInt(data?.pending_with_comment_count ?? null)} carry Latest Comment (dispute text)`}
        />
      </HeadlineStrip>
      <Alert severity="warning" variant="outlined" data-testid="cpor-payment-paid-note">
        {data?.paid_note ??
          'Paid on the ZAR open book only sums same-currency linked evidence. USD pending-report rows do not move R0 paid.'}{' '}
        This is payment/CN status evidence, not per-SKU claim lines. Unmatched closed/paid Case IDs
        below are historical source attestation — not minted as cpor_case. Claim-sale ageing stays
        claim-line-only; uplift stays blocked.
      </Alert>
      <Panel
        title="Pending — Latest Comment"
        subtitle="To_Be_Applied / To_Be_Clarified / Processed (and blank status). Comment is the file Latest Comment column, not Subject."
      >
        {disputed.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {data ? 'No pending rows with Latest Comment yet.' : 'Loading…'}
          </Typography>
        ) : (
          <Stack spacing={0.25}>
            {disputed.map((r) => (
              <PanelRow
                key={r.id}
                severity={r.payment_status === 'to_be_clarified' ? 'warning' : 'neutral'}
                primary={`${r.external_case_code} · ${r.payment_status ?? 'blank'}`}
                secondary={r.latest_comment ?? ''}
                figure={r.case_id != null ? 'linked' : 'unlinked'}
              />
            ))}
          </Stack>
        )}
      </Panel>
      <Panel
        title="Unmatched historical Case IDs"
        subtitle="Persisted cpor_payment_evidence with nullable case_id. Exact Case ID only — not minted as cpor_case. Closed/paid is source_attested."
      >
        {(data?.unmatched_file_rows ?? []).length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {data ? 'No unmatched file Case IDs in applied evidence.' : 'Loading…'}
          </Typography>
        ) : (
          <Stack spacing={0.25} data-testid="cpor-unmatched-file-evidence">
            <Typography variant="caption" color="text.secondary" sx={{ px: 0.5, pb: 0.5 }}>
              {data?.unmatched_file_amount_note}
              {data?.unmatched_file_attested_amount_by_currency
                ? ` Attested CN/payment: ${Object.entries(data.unmatched_file_attested_amount_by_currency)
                    .map(([ccy, n]) => `${fmtCompact(n, ccy)}`)
                    .join(' · ')}`
                : ''}
            </Typography>
            {(data?.unmatched_file_rows ?? [])
              .filter((r) => r.evidence_basis === 'source_attested')
              .slice(0, 12)
              .map((r) => (
                <PanelRow
                  key={r.id}
                  severity="neutral"
                  primary={`${r.external_case_code} · ${evidenceBasisLabel(r.evidence_basis)}`}
                  secondary={`${r.customer_token ?? '—'} · ${r.payment_status ?? 'blank'}`}
                  figure={fmtCompact(r.amount, r.currency_code ?? 'USD')}
                />
              ))}
          </Stack>
        )}
      </Panel>
    </Stack>
  );
}
