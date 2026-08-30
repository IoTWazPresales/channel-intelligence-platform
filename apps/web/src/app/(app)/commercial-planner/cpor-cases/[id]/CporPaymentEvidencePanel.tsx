'use client';

import { Alert, Chip, Stack, Typography } from '@mui/material';
import type { ColDef } from 'ag-grid-community';
import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { apiGet } from '@/lib/api';

type PayRow = {
  id: number;
  credit_note_id: string | null;
  case_status_raw: string | null;
  payment_status: string | null;
  payment_date: string | null;
  amount: number | null;
  currency_code: string;
  customer_token: string | null;
  distributor_token: string | null;
  description: string | null;
};

type ReconExplanation = { field: string; source: string; rule: string };

type PaymentRecon = {
  case_id: number;
  case_code: string | null;
  currency_code: string;
  owed_amount: number | null;
  paid_amount: number | null;
  outstanding_amount: number | null;
  owed_amount_file: number | null;
  paid_other_currency_amount: number | null;
  paid_other_currencies: string[];
  last_payment_date: string | null;
  credit_note_ids: string[];
  recon_status: string;
  flags: string[];
  explanations: ReconExplanation[];
  paid_row_count: number;
  pending_row_count: number;
  payment_evidence_count: number;
};

function money(v: number | null | undefined): string {
  if (v == null) return '—';
  return Number(v).toFixed(2);
}

export function CporPaymentEvidencePanel({ caseId }: { caseId: number }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['cpor', 'case', caseId, 'payment-evidence'],
    queryFn: ({ signal }) =>
      apiGet<{ items: PayRow[]; total: number }>(
        `/api/v1/cpor/cases/${caseId}/payment-evidence`,
        { signal },
      ),
  });

  const reconQ = useQuery({
    queryKey: ['cpor', 'case', caseId, 'payment-recon'],
    queryFn: ({ signal }) =>
      apiGet<PaymentRecon>(`/api/v1/cpor/cases/${caseId}/payment-recon`, { signal }),
    enabled: caseId > 0,
  });

  const columnDefs = useMemo<ColDef<PayRow>[]>(
    () => [
      { field: 'credit_note_id', headerName: 'CN / deduction', width: 130 },
      {
        field: 'payment_status',
        headerName: 'Payment',
        width: 120,
        cellRenderer: (p: { value?: string }) =>
          p.value ? <Chip size="small" label={p.value} /> : null,
      },
      { field: 'payment_date', headerName: 'Date', width: 110 },
      {
        field: 'amount',
        headerName: 'Amount',
        width: 110,
        valueFormatter: (p) => (p.value == null ? '' : Number(p.value).toFixed(2)),
      },
      { field: 'currency_code', headerName: 'CCY', width: 70 },
      { field: 'case_status_raw', headerName: 'File case status', width: 130 },
      { field: 'customer_token', headerName: 'Customer token', flex: 1, minWidth: 140 },
      { field: 'distributor_token', headerName: 'Distributor token', width: 140 },
      { field: 'description', headerName: 'Description', flex: 1, minWidth: 160 },
    ],
    [],
  );

  const recon = reconQ.data;

  return (
    <Stack spacing={1} data-testid="cpor-payment-evidence-panel">
      <Typography variant="h6">Payments / recon</Typography>
      <Typography variant="body2" color="text.secondary">
        Owed is approved case support (line ttl_support). Paid is mapped payment/CN evidence
        with status paid, processed, or closed. File case status does not overwrite CIP workflow.
      </Typography>
      {reconQ.isError ? (
        <Alert severity="error" data-testid="cpor-payment-recon-error">
          {String((reconQ.error as Error).message)}
        </Alert>
      ) : null}
      {recon ? (
        <Stack spacing={1} data-testid="cpor-payment-recon">
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip
              size="small"
              label={`Owed ${money(recon.owed_amount)} ${recon.currency_code}`}
              data-testid="cpor-recon-owed"
            />
            <Chip
              size="small"
              color="info"
              label={`Paid ${money(recon.paid_amount)} ${recon.currency_code}`}
              data-testid="cpor-recon-paid"
            />
            <Chip
              size="small"
              color={
                recon.recon_status === 'cleared'
                  ? 'success'
                  : recon.recon_status === 'overpaid' || recon.recon_status === 'fx_undeclared'
                    ? 'warning'
                    : 'default'
              }
              label={`Outstanding ${money(recon.outstanding_amount)} ${recon.currency_code}`}
              data-testid="cpor-recon-outstanding"
            />
            <Chip size="small" variant="outlined" label={recon.recon_status} data-testid="cpor-recon-status" />
            {recon.owed_amount_file != null ? (
              <Chip
                size="small"
                variant="outlined"
                label={`File owed ${money(recon.owed_amount_file)}`}
                data-testid="cpor-recon-owed-file"
              />
            ) : null}
            {recon.paid_other_currency_amount != null ? (
              <Chip
                size="small"
                color="warning"
                label={`Other CCY paid ${money(recon.paid_other_currency_amount)} (${recon.paid_other_currencies.join(', ')}) — not converted`}
                data-testid="cpor-recon-fx"
              />
            ) : null}
            {recon.flags.map((f) => (
              <Chip key={f} size="small" color="warning" variant="outlined" label={f} />
            ))}
          </Stack>
          <Typography variant="caption" color="text.secondary" data-testid="cpor-recon-explain">
            {(recon.explanations || []).map((e) => `${e.field}: ${e.rule}`).join(' · ')}
          </Typography>
          {recon.credit_note_ids.length ? (
            <Typography variant="caption" color="text.secondary">
              CN ids: {recon.credit_note_ids.join(', ')}
              {recon.last_payment_date ? ` · last paid ${recon.last_payment_date}` : ''}
            </Typography>
          ) : null}
        </Stack>
      ) : null}
      {isError ? <Alert severity="error">{String((error as Error).message)}</Alert> : null}
      {!isLoading && (data?.total ?? 0) === 0 ? (
        <Alert severity="info">
          No payment / CN evidence for this case. Import via{' '}
          <strong>Import payment / CN</strong> on the cases list.
        </Alert>
      ) : (
        <EnterpriseDataGrid
          rowData={data?.items ?? []}
          columnDefs={columnDefs}
          height={280}
          gridOptions={{ getRowId: (p) => String(p.data.id), loading: isLoading }}
        />
      )}
    </Stack>
  );
}
