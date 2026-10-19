'use client';

import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { Box, Chip, Stack, Typography } from '@mui/material';
import { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { Sparkline } from '@/features/workbench-ui/charts';
import { StatusChip } from '@/features/workbench-ui/controls';
import { useFactGridChrome } from '@/features/workbench-ui/gridFind';

import type { ProblemReason, ProblemRow, SellThroughOverview } from './sellThroughTypes';

export const REASON_ORDER: ProblemReason[] = ['out_of_stock', 'needs_replen', 'dropped', 'aged', 'stopped'];
export const REASON_LABEL: Record<ProblemReason, string> = {
  out_of_stock: 'Out of stock',
  needs_replen: 'Needs replenishing',
  dropped: 'Sales dropped',
  aged: 'Aged stock',
  stopped: 'No recent sales',
};
const REASON_TONE: Record<ProblemReason, 'danger' | 'warning' | 'info' | 'neutral'> = {
  out_of_stock: 'danger',
  needs_replen: 'warning',
  dropped: 'warning',
  aged: 'info',
  stopped: 'neutral',
};

const num = (v: number | null | undefined, digits = 0) =>
  v == null ? '—' : v.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 });

/**
 * SKUs needing attention, per customer (Warren 2026-10-19): restock (out of stock while selling,
 * low cover with a suggested quantity) and slowing or stuck (a selling streak that dropped, stock not
 * moving, no recent sales). Each row says why in words and shows its 26-week sales line.
 */
export function SellThroughProblemsTable({
  problems,
  reason,
  onReason,
  onOpen,
}: {
  problems: SellThroughOverview['problems'];
  reason: ProblemReason | null;
  onReason: (r: ProblemReason | null) => void;
  /** Opens the product detail panel for a row. */
  onOpen?: (row: ProblemRow) => void;
}) {
  const gridChrome = useFactGridChrome('sell-through.problems');
  const rows = useMemo(
    () => (reason ? problems.rows.filter((r) => r.reason === reason) : problems.rows),
    [problems.rows, reason],
  );

  const cols = useMemo<ColDef<ProblemRow>[]>(
    () => [
      {
        field: 'reason',
        headerName: 'Why',
        width: 190,
        cellRenderer: (p: ICellRendererParams<ProblemRow>) =>
          p.data ? <StatusChip label={p.data.reason_label} tone={REASON_TONE[p.data.reason]} /> : null,
      },
      { field: 'customer_name', headerName: 'Customer', width: 170 },
      { field: 'product', headerName: 'Product', flex: 1.2, minWidth: 220 },
      { field: 'detail', headerName: 'What we see', flex: 1.4, minWidth: 260 },
      {
        headerName: 'Last 26 weeks',
        width: 150,
        sortable: false,
        cellRenderer: (p: ICellRendererParams<ProblemRow>) =>
          p.data ? (
            <Box sx={{ pt: 0.25 }}>
              <Sparkline
                values={p.data.weekly_units}
                height={22}
                tone={REASON_TONE[p.data.reason] === 'danger' ? 'danger' : 'primary'}
                label={`Weekly units, 26 weeks to ${p.data.judged_to}`}
              />
            </Box>
          ) : null,
      },
      { field: 'stock_on_hand', headerName: 'Stock', width: 95, type: 'numericColumn', valueFormatter: (p) => num(p.value) },
      {
        field: 'stock_date',
        headerName: 'Stock reported',
        width: 140,
        valueFormatter: (p) =>
          p.value ? `${p.value}${p.data?.stock_age_days != null && p.data.stock_age_days > 35 ? ` (${p.data.stock_age_days}d old)` : ''}` : '—',
      },
      {
        headerName: 'Stores with stock',
        width: 170,
        valueGetter: (p) =>
          (p.data?.stock_sites ?? []).map((x) => `${x.site} ${num(x.soh)}`).join(', ') || '—',
      },
      { field: 'on_order', headerName: 'On order', width: 100, type: 'numericColumn', valueFormatter: (p) => num(p.value) },
      { field: 'rate_recent', headerName: 'Per week now', width: 120, type: 'numericColumn', valueFormatter: (p) => num(p.value, 1) },
      { field: 'rate_before', headerName: 'Per week before', width: 130, type: 'numericColumn', valueFormatter: (p) => num(p.value, 1) },
      { field: 'weeks_of_cover', headerName: 'Weeks of cover', width: 130, type: 'numericColumn', valueFormatter: (p) => num(p.value, 1) },
      {
        field: 'suggested_qty',
        headerName: 'Suggested order',
        width: 140,
        type: 'numericColumn',
        valueFormatter: (p) => num(p.value),
        cellStyle: { fontWeight: 600 },
      },
      { field: 'sku', headerName: 'SKU', width: 150, hide: true },
      { field: 'business_unit', headerName: 'BU', width: 90, hide: true },
      { field: 'category', headerName: 'Category', width: 120, hide: true },
      { field: 'lifecycle', headerName: 'Lifecycle', width: 110, hide: true },
      { field: 'judged_to', headerName: 'Judged to', width: 110, hide: true },
    ],
    [],
  );

  return (
    <Stack spacing={1} data-testid="sellthrough-problems">
      <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap alignItems="center">
        <Chip
          size="small"
          label={`All ${problems.total.toLocaleString()}`}
          variant={reason == null ? 'filled' : 'outlined'}
          color={reason == null ? 'primary' : 'default'}
          onClick={() => onReason(null)}
        />
        {REASON_ORDER.map((r) => (
          <Chip
            key={r}
            size="small"
            data-testid={`sellthrough-problem-chip-${r}`}
            label={`${REASON_LABEL[r]} ${(problems.counts[r] ?? 0).toLocaleString()}`}
            variant={reason === r ? 'filled' : 'outlined'}
            color={reason === r ? (REASON_TONE[r] === 'danger' ? 'error' : REASON_TONE[r] === 'warning' ? 'warning' : 'primary') : 'default'}
            disabled={!problems.counts[r]}
            onClick={() => onReason(reason === r ? null : r)}
          />
        ))}
        <Box sx={{ flex: 1 }} />
        {gridChrome.filters}
        {gridChrome.trailing}
      </Stack>
      {problems.total > problems.rows.length ? (
        <Typography variant="caption" color="text.secondary">
          Showing the first {problems.rows.length.toLocaleString()} of {problems.total.toLocaleString()}, most urgent first.
          Narrow the filters to see the rest.
        </Typography>
      ) : null}
      {rows.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
          Nothing needs attention for these filters.
        </Typography>
      ) : (
        <EnterpriseDataGrid
          ref={gridChrome.gridRef}
          quickFilterText={gridChrome.query}
          rowData={rows}
          columnDefs={cols}
          height={Math.min(520, 56 + rows.length * 36)}
          gridOptions={{
            getRowId: (p) => `${p.data.customer_id}-${p.data.product_id}`,
            onRowClicked: (e) => {
              if (e.data) onOpen?.(e.data);
            },
          }}
        />
      )}

    </Stack>
  );
}
