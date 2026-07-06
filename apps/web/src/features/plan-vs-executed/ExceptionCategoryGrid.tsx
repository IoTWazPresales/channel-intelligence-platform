'use client';

import { Box, Link as MuiLink, Stack, Typography } from '@mui/material';
import type { ColDef, GridOptions, ICellRendererParams, RowClickedEvent } from 'ag-grid-community';
import Link from 'next/link';
import { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';

export type ExceptionRow = {
  key: string | number;
  label: string;
  entity_primary?: string;
  entity_secondary?: string | null;
  label_fallback?: boolean;
  units: number;
  value_plan: number;
  value_cost?: number;
  line_count?: number;
  customer_id?: number | null;
  product_id?: number | null;
  sales_model?: string | null;
  business_unit_label?: string | null;
};

export type ExceptionCategory =
  | 'short_ships'
  | 'over_ships'
  | 'unplanned_intake'
  | 'no_po_blind_spots';

export const EXCEPTION_CATEGORY_LABELS: Record<ExceptionCategory, string> = {
  short_ships: 'Short-ships',
  over_ships: 'Over-ships / deal-stock',
  unplanned_intake: 'Unplanned intake',
  no_po_blind_spots: 'No-PO blind spots',
};

function fmtUnits(n: number): string {
  return new Intl.NumberFormat().format(Math.round(n));
}

function fmtValue(n: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(n);
}

function EntityCell({ data }: { data?: ExceptionRow }) {
  if (!data) return null;
  const primary = data.entity_primary ?? data.label;
  const secondary = data.entity_secondary;
  return (
    <Stack spacing={0.25} sx={{ py: 0.5, lineHeight: 1.3 }}>
      <Typography variant="body2" sx={{ fontWeight: 500 }}>
        {primary}
        {data.label_fallback ? (
          <Typography component="span" variant="caption" color="text.disabled" sx={{ ml: 0.75 }}>
            (no description)
          </Typography>
        ) : null}
      </Typography>
      {secondary ? (
        <Typography variant="caption" color="text.secondary">
          {secondary}
        </Typography>
      ) : null}
    </Stack>
  );
}

export function buildPoManagementHref(opts: {
  period: string;
  businessUnit?: string | null;
  customerId?: number | null;
}): string {
  const p = new URLSearchParams();
  p.set('period', opts.period);
  if (opts.businessUnit) p.set('business_unit', opts.businessUnit);
  if (opts.customerId != null) p.set('customer_id', String(opts.customerId));
  return `/admin/po-management?${p.toString()}`;
}

export function ExceptionCategoryGrid({
  rows,
  rankBy,
  category,
  periodForLink,
  defaultBusinessUnit,
  fxPartial,
  onRowClick,
}: {
  rows: ExceptionRow[];
  rankBy: 'units' | 'value';
  category: ExceptionCategory;
  periodForLink: string;
  defaultBusinessUnit?: string | null;
  fxPartial?: boolean;
  onRowClick?: (row: ExceptionRow) => void;
}) {
  const showPoLink = category === 'short_ships' || category === 'no_po_blind_spots';
  const showLines = category === 'no_po_blind_spots';
  const fxNote = fxPartial ? ' · FX partial' : '';

  const columnDefs = useMemo<ColDef<ExceptionRow>[]>(
    () => [
      {
        colId: 'entity',
        headerName: 'Entity',
        flex: 1,
        minWidth: 220,
        sortable: true,
        comparator: (_a, _b, nodeA, nodeB) => {
          const la = (nodeA.data?.entity_primary ?? nodeA.data?.label ?? '').toLowerCase();
          const lb = (nodeB.data?.entity_primary ?? nodeB.data?.label ?? '').toLowerCase();
          return la.localeCompare(lb);
        },
        cellRenderer: (p: ICellRendererParams<ExceptionRow>) => <EntityCell data={p.data} />,
      },
      {
        field: 'units',
        headerName: 'Units',
        width: 110,
        sortable: true,
        valueFormatter: (p) => fmtUnits(Number(p.value ?? 0)),
      },
      {
        field: 'value_plan',
        headerName: `Value (plan)${fxNote}`,
        width: 130,
        sortable: true,
        valueFormatter: (p) => fmtValue(Number(p.value ?? 0)),
      },
      {
        field: 'value_cost',
        headerName: 'Value (cost)',
        width: 120,
        sortable: true,
        valueFormatter: (p) => fmtValue(Number(p.value ?? 0)),
      },
      {
        field: 'line_count',
        headerName: 'Lines',
        width: 90,
        hide: !showLines,
        sortable: true,
      },
      {
        colId: 'po_action',
        headerName: 'Action',
        width: 120,
        hide: !showPoLink,
        cellRenderer: (p: ICellRendererParams<ExceptionRow>) => {
          const row = p.data;
          if (!row || !periodForLink) return null;
          const bu = row.business_unit_label || defaultBusinessUnit || '';
          const href = buildPoManagementHref({
            period: periodForLink,
            businessUnit: bu || undefined,
            customerId: row.customer_id ?? undefined,
          });
          return (
            <MuiLink component={Link} href={href} underline="hover" variant="body2" onClick={(e) => e.stopPropagation()}>
              PO Mgmt
            </MuiLink>
          );
        },
      },
    ],
    [showPoLink, showLines, periodForLink, defaultBusinessUnit, fxNote],
  );

  const gridOptions = useMemo<GridOptions<ExceptionRow>>(
    () => ({
      pagination: true,
      paginationPageSize: 15,
      domLayout: 'autoHeight',
      defaultColDef: { resizable: true },
      onRowClicked: (e: RowClickedEvent<ExceptionRow>) => {
        if (e.data && onRowClick) onRowClick(e.data);
      },
      rowStyle: onRowClick ? { cursor: 'pointer' } : undefined,
    }),
    [onRowClick],
  );

  if (!rows.length) {
    return (
      <Box sx={{ py: 2 }}>
        <Typography variant="body2" color="text.secondary">
          None in range for {EXCEPTION_CATEGORY_LABELS[category].toLowerCase()}.
        </Typography>
      </Box>
    );
  }

  return (
    <EnterpriseDataGrid
      rowData={rows}
      columnDefs={columnDefs}
      height={Math.min(520, 120 + rows.length * 42)}
      gridOptions={gridOptions}
    />
  );
}
