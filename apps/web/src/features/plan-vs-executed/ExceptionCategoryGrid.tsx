'use client';

import { Box, Link as MuiLink, Typography } from '@mui/material';
import type { ColDef, GridOptions, RowClickedEvent } from 'ag-grid-community';
import Link from 'next/link';
import { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';

export type ExceptionRow = {
  key: string | number;
  label: string;
  units: number;
  value_plan: number;
  line_count?: number;
  customer_id?: number | null;
  product_id?: number | null;
  sales_model?: string | null;
  business_unit_label?: string | null;
};

function fmtUnits(n: number): string {
  return new Intl.NumberFormat().format(Math.round(n));
}

function fmtValue(n: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(n);
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
  title,
  rows,
  rankBy,
  category,
  periodForLink,
  defaultBusinessUnit,
  onRowClick,
}: {
  title: string;
  rows: ExceptionRow[];
  rankBy: 'units' | 'value';
  category: 'short_ships' | 'over_ships' | 'unplanned_intake' | 'no_po_blind_spots';
  periodForLink: string;
  defaultBusinessUnit?: string | null;
  onRowClick?: (row: ExceptionRow) => void;
}) {
  const showPoLink = category === 'short_ships' || category === 'no_po_blind_spots';

  const columnDefs = useMemo<ColDef<ExceptionRow>[]>(
    () => [
      { field: 'label', headerName: 'Entity', flex: 1, minWidth: 140 },
      {
        headerName: rankBy === 'value' ? 'Value (plan)' : 'Units',
        width: 110,
        valueGetter: (p) => (rankBy === 'value' ? p.data?.value_plan : p.data?.units),
        valueFormatter: (p) =>
          rankBy === 'value' ? fmtValue(Number(p.value ?? 0)) : fmtUnits(Number(p.value ?? 0)),
      },
      {
        field: 'line_count',
        headerName: 'Lines',
        width: 80,
        hide: category !== 'no_po_blind_spots',
      },
      {
        colId: 'po_action',
        headerName: 'Action',
        width: 120,
        hide: !showPoLink,
        cellRenderer: (p: { data?: ExceptionRow }) => {
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
    [rankBy, category, showPoLink, periodForLink, defaultBusinessUnit],
  );

  const gridOptions = useMemo<GridOptions<ExceptionRow>>(
    () => ({
      pagination: true,
      paginationPageSize: 8,
      domLayout: 'autoHeight',
      onRowClicked: (e: RowClickedEvent<ExceptionRow>) => {
        if (e.data && onRowClick) onRowClick(e.data);
      },
      rowStyle: onRowClick ? { cursor: 'pointer' } : undefined,
    }),
    [onRowClick],
  );

  if (!rows.length) {
    return (
      <Box sx={{ minWidth: 280, flex: 1 }}>
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          {title}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          None in range
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ minWidth: 280, flex: 1 }}>
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        {title}
      </Typography>
      <EnterpriseDataGrid
        rowData={rows}
        columnDefs={columnDefs}
        height={280}
        gridOptions={gridOptions}
      />
    </Box>
  );
}
