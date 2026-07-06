'use client';

import { Box, Link as MuiLink, Tooltip, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import type { ColDef, GridOptions, ICellRendererParams, RowClickedEvent } from 'ag-grid-community';
import Link from 'next/link';
import { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';

import {
  ENTITY_LENS_HEADERS,
  gridRowMetrics,
  PAGINATED_GRID_PAGE_SIZE,
  paginatedGridHeight,
  VALUE_UNAVAILABLE_TOOLTIP,
  type ExceptionLens,
} from './gridPagination';

export type ExceptionRow = {
  key: string | number;
  label: string;
  entity_primary?: string;
  entity_secondary?: string | null;
  label_fallback?: boolean;
  units: number;
  value_plan: number | null;
  value_cost?: number | null;
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

/** Single-line entity label — one field per column, no stacked sub-labels. */
export function formatEntityLine(primary: string, labelFallback?: boolean): string {
  if (!labelFallback) return primary;
  return `${primary} (no description)`;
}

function EntityCell({ primary, labelFallback }: { primary: string; labelFallback?: boolean }) {
  const line = formatEntityLine(primary, labelFallback);
  return (
    <Typography variant="body2" noWrap title={line} sx={{ lineHeight: 1.2 }}>
      {primary}
      {labelFallback ? (
        <Typography component="span" variant="body2" color="text.disabled" sx={{ ml: 0.5 }}>
          (no description)
        </Typography>
      ) : null}
    </Typography>
  );
}

function ValueCell({
  value,
  fxPartial,
}: {
  value: number | null | undefined;
  fxPartial?: boolean;
}) {
  if (value == null) {
    const tip = fxPartial
      ? `${VALUE_UNAVAILABLE_TOOLTIP} (FX partial in range)`
      : VALUE_UNAVAILABLE_TOOLTIP;
    return (
      <Tooltip title={tip}>
        <Typography component="span" variant="body2" color="text.disabled" sx={{ cursor: 'help' }}>
          —
        </Typography>
      </Tooltip>
    );
  }
  return <Typography component="span" variant="body2">{fmtValue(value)}</Typography>;
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
  lens,
  rankBy,
  category,
  periodForLink,
  defaultBusinessUnit,
  fxPartial,
  onRowClick,
}: {
  rows: ExceptionRow[];
  lens: ExceptionLens;
  rankBy: 'units' | 'value';
  category: ExceptionCategory;
  periodForLink: string;
  defaultBusinessUnit?: string | null;
  fxPartial?: boolean;
  onRowClick?: (row: ExceptionRow) => void;
}) {
  const theme = useTheme();
  const density = theme.density === 'compact' ? 'compact' : 'comfortable';
  const { rowHeight, headerHeight } = gridRowMetrics(density);
  const gridHeight = paginatedGridHeight(PAGINATED_GRID_PAGE_SIZE, { rowHeight, headerHeight });

  const showPoLink = category === 'short_ships' || category === 'no_po_blind_spots';
  const showLines = category === 'no_po_blind_spots';
  const entityHeader = ENTITY_LENS_HEADERS[lens];

  const columnDefs = useMemo<ColDef<ExceptionRow>[]>(
    () => [
      {
        colId: 'entity',
        headerName: entityHeader,
        flex: 1,
        minWidth: 200,
        sortable: true,
        comparator: (_a, _b, nodeA, nodeB) => {
          const la = (nodeA.data?.entity_primary ?? nodeA.data?.label ?? '').toLowerCase();
          const lb = (nodeB.data?.entity_primary ?? nodeB.data?.label ?? '').toLowerCase();
          return la.localeCompare(lb);
        },
        valueGetter: (p) =>
          formatEntityLine(p.data?.entity_primary ?? p.data?.label ?? '', p.data?.label_fallback),
        cellRenderer: (p: ICellRendererParams<ExceptionRow>) => (
          <EntityCell
            primary={p.data?.entity_primary ?? p.data?.label ?? ''}
            labelFallback={p.data?.label_fallback}
          />
        ),
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
        headerName: 'Value (plan)',
        headerTooltip: fxPartial
          ? 'Plan currency — FX partial; unavailable where bridge missing'
          : 'Plan currency — unavailable where bridge missing',
        width: 140,
        sortable: true,
        comparator: (_a, _b, nodeA, nodeB) => {
          const va = nodeA.data?.value_plan;
          const vb = nodeB.data?.value_plan;
          if (va == null && vb == null) return 0;
          if (va == null) return -1;
          if (vb == null) return 1;
          return va - vb;
        },
        cellRenderer: (p: ICellRendererParams<ExceptionRow>) => (
          <ValueCell value={p.data?.value_plan} fxPartial={fxPartial} />
        ),
      },
      {
        field: 'value_cost',
        headerName: 'Value (cost)',
        headerTooltip: 'Cost currency — unavailable where bridge missing',
        width: 130,
        sortable: true,
        comparator: (_a, _b, nodeA, nodeB) => {
          const va = nodeA.data?.value_cost;
          const vb = nodeB.data?.value_cost;
          if (va == null && vb == null) return 0;
          if (va == null) return -1;
          if (vb == null) return 1;
          return va - vb;
        },
        cellRenderer: (p: ICellRendererParams<ExceptionRow>) => (
          <ValueCell value={p.data?.value_cost} fxPartial={fxPartial} />
        ),
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
    [entityHeader, showPoLink, showLines, periodForLink, defaultBusinessUnit, fxPartial],
  );

  const gridOptions = useMemo<GridOptions<ExceptionRow>>(
    () => ({
      pagination: true,
      paginationPageSize: PAGINATED_GRID_PAGE_SIZE,
      suppressPaginationPanel: false,
      rowHeight,
      headerHeight,
      defaultColDef: { resizable: true },
      onRowClicked: (e: RowClickedEvent<ExceptionRow>) => {
        if (e.data && onRowClick) onRowClick(e.data);
      },
      rowStyle: onRowClick ? { cursor: 'pointer' } : undefined,
    }),
    [onRowClick, rowHeight, headerHeight],
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
    <Box data-testid="exception-category-grid" sx={{ width: '100%', overflow: 'visible' }}>
      <EnterpriseDataGrid
        rowData={rows}
        columnDefs={columnDefs}
        height={gridHeight}
        gridOptions={gridOptions}
      />
    </Box>
  );
}
