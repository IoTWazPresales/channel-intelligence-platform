'use client';

import {
  Alert,
  Box,
  Button,
  FormControlLabel,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import type { ColDef } from 'ag-grid-community';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { OPS_LIST_GRID_PAGINATION } from '@/features/shell/opsListGridPagination';
import { apiGet, apiPost, apiPut } from '@/lib/api';

export type StockGapRow = {
  id: number;
  customer_id: number;
  customer_code: string;
  customer_name: string;
  product_id: number;
  sku: string;
  product_name: string;
  period_grain: 'day' | 'week' | 'month';
  period_start_date: string;
  period_end_date: string;
  period_week: number | null;
  period_year: number | null;
  reported_on_hand: number | null;
  previous_on_hand: number | null;
  previous_period_end_date: string | null;
  receipts_units: number | null;
  units_sold: number | null;
  expected_on_hand: number | null;
  gap_units: number | null;
  in_transit_units: number | null;
  on_order_units: number | null;
  status: 'compared' | 'first_report';
  highlighted: boolean;
  reason: string;
};

export type StockGapResponse = {
  threshold_units: number;
  counts: { compared: number; highlighted: number; first_report: number };
  rows: StockGapRow[];
};

const units = (v: number | null | undefined) =>
  v == null ? '—' : v.toLocaleString(undefined, { maximumFractionDigits: 2 });

export function formatGap(v: number | null | undefined): string {
  if (v == null) return '—';
  if (v === 0) return '0';
  const text = Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
  return v > 0 ? `+${text}` : `−${text}`;
}

export function periodLabel(r: Pick<StockGapRow, 'period_grain' | 'period_start_date' | 'period_week' | 'period_year'>) {
  if (r.period_grain === 'day') return r.period_start_date;
  if (r.period_grain === 'month') return r.period_start_date.slice(0, 7);
  if (r.period_week != null && r.period_year != null) return `Week ${r.period_week}, ${r.period_year}`;
  return `Week from ${r.period_start_date}`;
}

export function CstStockGapSection() {
  const qc = useQueryClient();
  const [highlightedOnly, setHighlightedOnly] = useState(false);
  const [thresholdDraft, setThresholdDraft] = useState('');

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['cst-steward', 'stock-gap', highlightedOnly],
    queryFn: ({ signal }) =>
      apiGet<StockGapResponse>(`/api/v1/cst-steward/stock-gap${highlightedOnly ? '?highlighted_only=true' : ''}`, {
        signal,
      }),
  });

  useEffect(() => {
    if (data && thresholdDraft === '') setThresholdDraft(String(data.threshold_units));
  }, [data, thresholdDraft]);

  const thresholdValue = Number(thresholdDraft);
  const thresholdValid = thresholdDraft.trim() !== '' && Number.isFinite(thresholdValue) && thresholdValue > 0;

  const saveThreshold = useMutation({
    mutationFn: () =>
      apiPut<{ threshold_units: number }>('/api/v1/cst-steward/stock-gap/settings', { highlight_units: thresholdValue }),
    onSuccess: async (res) => {
      setThresholdDraft(String(res.threshold_units));
      await qc.invalidateQueries({ queryKey: ['cst-steward', 'stock-gap'] });
    },
  });

  const recompute = useMutation({
    mutationFn: () => apiPost<{ customers: number; positions: number }>('/api/v1/cst-steward/stock-gap/recompute', {}),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['cst-steward', 'stock-gap'] });
    },
  });

  const cols = useMemo<ColDef<StockGapRow>[]>(
    () => [
      {
        headerName: 'Flag',
        width: 130,
        valueGetter: (p) =>
          p.data?.status === 'first_report' ? 'First report' : p.data?.highlighted ? 'Over threshold' : '',
      },
      { field: 'customer_name', headerName: 'Customer', flex: 1, minWidth: 160 },
      { field: 'customer_code', headerName: 'Customer code', width: 130 },
      { field: 'sku', headerName: 'SKU', width: 140 },
      { field: 'product_name', headerName: 'Product', flex: 1, minWidth: 160 },
      { headerName: 'Report period', width: 150, valueGetter: (p) => (p.data ? periodLabel(p.data) : '') },
      {
        field: 'reported_on_hand',
        headerName: 'Reported on-hand',
        width: 140,
        type: 'numericColumn',
        valueFormatter: (p) => units(p.value),
      },
      {
        field: 'expected_on_hand',
        headerName: 'Expected position',
        width: 140,
        type: 'numericColumn',
        valueFormatter: (p) => units(p.value),
      },
      {
        field: 'gap_units',
        headerName: 'Gap (units)',
        width: 120,
        type: 'numericColumn',
        valueFormatter: (p) => formatGap(p.value),
        cellClassRules: { 'cip-gap-flag': (p) => Boolean(p.data?.highlighted) },
      },
      {
        field: 'previous_on_hand',
        headerName: 'Previous on-hand',
        width: 140,
        type: 'numericColumn',
        valueFormatter: (p) => units(p.value),
      },
      {
        field: 'receipts_units',
        headerName: 'Delivered (POD, matched)',
        width: 180,
        type: 'numericColumn',
        valueFormatter: (p) => units(p.value),
      },
      {
        field: 'units_sold',
        headerName: 'Units sold since',
        width: 140,
        type: 'numericColumn',
        valueFormatter: (p) => units(p.value),
      },
      {
        field: 'in_transit_units',
        headerName: 'In transit',
        width: 110,
        type: 'numericColumn',
        valueFormatter: (p) => units(p.value),
      },
      {
        field: 'on_order_units',
        headerName: 'On order',
        width: 110,
        type: 'numericColumn',
        valueFormatter: (p) => units(p.value),
      },
      { field: 'reason', headerName: 'What it can mean', flex: 2, minWidth: 280, wrapText: true, autoHeight: true },
    ],
    [],
  );

  const counts = data?.counts;

  return (
    <Stack spacing={1.5} data-testid="cst-stock-gap">
      <Typography variant="body2" color="text.secondary">
        The customer&apos;s reported on-hand is the stock position. Expected position = previous reported on-hand +
        deliveries with a proof-of-delivery date already matched to this customer − units sold since. The gap is
        reported on-hand minus expected. Neither number is changed. In transit and on order are shown beside on-hand
        and never added into it.
      </Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }}>
        <TextField
          size="small"
          type="number"
          label="Highlight at a gap of (units)"
          value={thresholdDraft}
          onChange={(e) => setThresholdDraft(e.target.value)}
          error={thresholdDraft !== '' && !thresholdValid}
          helperText={thresholdDraft !== '' && !thresholdValid ? 'Enter more than 0 units' : 'Absolute units, either direction'}
          inputProps={{ min: 0, step: 1, 'data-testid': 'cst-stock-gap-threshold' }}
          sx={{ width: 240 }}
        />
        <Button
          variant="outlined"
          onClick={() => saveThreshold.mutate()}
          disabled={!thresholdValid || saveThreshold.isPending || thresholdValue === data?.threshold_units}
          data-testid="cst-stock-gap-threshold-save"
        >
          {saveThreshold.isPending ? 'Saving…' : 'Save threshold'}
        </Button>
        <FormControlLabel
          control={
            <Switch
              checked={highlightedOnly}
              onChange={(e) => setHighlightedOnly(e.target.checked)}
              inputProps={{ 'aria-label': 'Show highlighted rows only' }}
            />
          }
          label="Highlighted only"
        />
        <Box sx={{ flex: 1 }} />
        <Button
          variant="outlined"
          onClick={() => recompute.mutate()}
          disabled={recompute.isPending}
          data-testid="cst-stock-gap-recompute"
        >
          {recompute.isPending ? 'Recomputing…' : 'Recompute'}
        </Button>
      </Stack>
      {counts ? (
        <Typography variant="body2" data-testid="cst-stock-gap-counts">
          {counts.compared} compared · {counts.highlighted} at or over {units(data?.threshold_units)} units ·{' '}
          {counts.first_report} first report{counts.first_report === 1 ? '' : 's'} (nothing to compare yet)
        </Typography>
      ) : null}
      {saveThreshold.isError ? <Alert severity="error">{String((saveThreshold.error as Error)?.message)}</Alert> : null}
      {recompute.isError ? <Alert severity="error">{String((recompute.error as Error)?.message)}</Alert> : null}
      {recompute.isSuccess ? (
        <Alert severity="success">
          Recomputed {recompute.data.positions} position{recompute.data.positions === 1 ? '' : 's'} for{' '}
          {recompute.data.customers} customer{recompute.data.customers === 1 ? '' : 's'}.
        </Alert>
      ) : null}
      <ModuleDataSection
        isLoading={isLoading}
        isError={isError}
        error={isError ? new Error(String((error as Error)?.message)) : null}
        onRetry={() => void refetch()}
        isEmpty={(data?.rows ?? []).length === 0}
        empty={{
          title: highlightedOnly ? 'No gap at or over the threshold' : 'No stock positions yet',
          description: highlightedOnly
            ? 'Every compared report is within the threshold. Turn off Highlighted only to see all rows.'
            : 'Positions appear after a customer sell-through report with an on-hand column is applied.',
        }}
      >
        <Box
          sx={{
            '& .cip-gap-flag': {
              backgroundColor: (t) => alpha(t.palette.warning.main, 0.22),
              fontWeight: 700,
            },
          }}
        >
          <EnterpriseDataGrid
            rowData={data?.rows ?? []}
            columnDefs={cols}
            height={520}
            gridOptions={{
              getRowId: (p) => String(p.data!.id),
              ...OPS_LIST_GRID_PAGINATION,
            }}
          />
        </Box>
      </ModuleDataSection>
    </Stack>
  );
}
