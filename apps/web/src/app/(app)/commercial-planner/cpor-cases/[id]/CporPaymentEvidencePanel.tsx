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

export function CporPaymentEvidencePanel({ caseId }: { caseId: number }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['cpor', 'case', caseId, 'payment-evidence'],
    queryFn: ({ signal }) =>
      apiGet<{ items: PayRow[]; total: number }>(
        `/api/v1/cpor/cases/${caseId}/payment-evidence`,
        { signal },
      ),
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

  return (
    <Stack spacing={1} data-testid="cpor-payment-evidence-panel">
      <Typography variant="h6">Payments / credit notes</Typography>
      <Typography variant="body2" color="text.secondary">
        Evidence only — file case status does not overwrite CIP case workflow status.
      </Typography>
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
