'use client';

import { Alert, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { fmtInt, fmtPct } from '@/features/promotions-funding/format';
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
          caption={`${fmtInt(data?.distinct_file_case_codes ?? null)} distinct Case IDs in applied evidence`}
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
        This is payment/CN status evidence, not per-SKU claim lines — claim ageing and uplift stay
        blocked. Not a budget ledger.
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
    </Stack>
  );
}
