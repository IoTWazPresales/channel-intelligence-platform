'use client';

import { Alert, Chip, Stack, Typography } from '@mui/material';
import type { ColDef } from 'ag-grid-community';
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { apiGet } from '@/lib/api';

export type PromoLoadLine = {
  product_id: number;
  product_sku: string | null;
  product_name: string | null;
  estimate_qty: number;
  result_qty: number | null;
  srp: number | null;
  support_unit: number | null;
  expected_shelf_price: number | null;
  cst_units: number;
  cst_near_miss_units: number;
  cst_unit_sell_price_wtd: number | null;
  bucket: string;
  flags: string[];
};

export type PromoLoadPayload = {
  case_id: number;
  customer_id: number;
  window_start: string | null;
  window_end: string | null;
  cst_available: boolean;
  data_unavailable: boolean;
  reason: string | null;
  price_tolerance: number;
  lines: PromoLoadLine[];
  summary: Record<string, number>;
  cst_vintage: { max_period_start_date: string | null };
  import_steward_hint?: string;
};

export function CporPromoLoadPanel({ caseId }: { caseId: number }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['cpor', 'promo-load-recon', caseId],
    queryFn: ({ signal }) =>
      apiGet<PromoLoadPayload>(`/api/v1/cpor/cases/${caseId}/promo-load-recon`, { signal }),
    enabled: caseId > 0,
  });

  const cols = useMemo<ColDef<PromoLoadLine>[]>(
    () => [
      { field: 'product_sku', headerName: 'SKU', flex: 1 },
      { field: 'product_name', headerName: 'Product', flex: 1.5 },
      { field: 'estimate_qty', headerName: 'Est qty', width: 100 },
      { field: 'cst_units', headerName: 'CST units', width: 110 },
      { field: 'expected_shelf_price', headerName: 'Expected', width: 110 },
      { field: 'cst_unit_sell_price_wtd', headerName: 'CST price', width: 110 },
      { field: 'bucket', headerName: 'Bucket', width: 140 },
    ],
    [],
  );

  if (isError) {
    return (
      <Alert severity="error" data-testid="cpor-promo-load-error">
        {(error as Error)?.message ?? 'Promo load recon failed'}
      </Alert>
    );
  }

  if (isLoading) {
    return <Typography variant="body2">Loading promo load…</Typography>;
  }

  if (!data) return null;

  if (data.data_unavailable && data.reason === 'no_cst') {
    return (
      <Alert severity="info" data-testid="cpor-promo-load-no-cst">
        No customer sell-through (CST) facts for this customer. Import via{' '}
        {data.import_steward_hint ?? 'CST import steward'} — DSI sell-out is not promo-load evidence.
      </Alert>
    );
  }

  const s = data.summary;

  return (
    <Stack spacing={1.5} data-testid="cpor-promo-load">
      <Typography variant="body2" color="text.secondary">
        Case-scoped CST vs approved terms (units / price / window). Settlement claim recon stays on the
        Settlement tab. Price tolerance {(data.price_tolerance * 100).toFixed(0)}%.
      </Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Chip size="small" label={`ok ${s.ok ?? 0}`} data-testid="cpor-promo-load-ok" />
        <Chip size="small" label={`missing ${s.missing_load ?? 0}`} data-testid="cpor-promo-load-missing" />
        <Chip size="small" label={`wrong window ${s.wrong_window ?? 0}`} />
        <Chip size="small" label={`wrong price ${s.wrong_price ?? 0}`} />
        <Chip size="small" label={`price unknown ${s.price_unknown ?? 0}`} />
      </Stack>
      {data.cst_vintage.max_period_start_date ? (
        <Typography variant="caption" color="text.secondary">
          CST vintage max period {data.cst_vintage.max_period_start_date}
        </Typography>
      ) : null}
      <EnterpriseDataGrid
        rowData={data.lines}
        columnDefs={cols}
        height={360}
        gridOptions={{ getRowId: (p) => String(p.data.product_id) }}
      />
    </Stack>
  );
}
