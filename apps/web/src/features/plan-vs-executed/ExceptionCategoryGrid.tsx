'use client';

import { Box, Link as MuiLink, Tooltip, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import type { ColDef, GridOptions, ICellRendererParams, RowClickedEvent } from 'ag-grid-community';
import Link from 'next/link';
import { useCallback, useMemo } from 'react';

import { MasterDataGridShell } from '@/components/masterGrid/MasterDataGridShell';
import type { MasterColumnPickerGroup } from '@/components/masterGrid/MasterColumnPickerDialog';

import {
  ENTITY_LENS_HEADERS,
  gridRowMetrics,
  PAGINATED_GRID_PAGE_SIZE,
  VALUE_UNAVAILABLE_TOOLTIP,
  type ExceptionLens,
} from './gridPagination';
import { pageFromSkipLimit, skipFromPage, zeroBasedPageFromOffset } from '@/lib/skipLimitSearchParams';

export type ExceptionRow = {
  id?: string;
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

export type ExceptionGridRow = ExceptionRow & { id: string };

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

const GRID_STATE_KEY_BASE = 'cip.pve.exceptions.grid.v1';

function exceptionGridStateKey(category: ExceptionCategory): string {
  return `${GRID_STATE_KEY_BASE}.${category}`;
}

const EXCEPTION_COLUMN_GROUPS: MasterColumnPickerGroup[] = [
  { label: 'Entity', fields: ['label'] },
  { label: 'Units', fields: ['units'] },
  { label: 'Value', fields: ['value_plan', 'value_cost'] },
  { label: 'Other', fields: ['line_count', 'po_action'] },
];

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

function toGridRows(rows: ExceptionRow[]): ExceptionGridRow[] {
  return rows.map((row) => ({ ...row, id: row.id ?? String(row.key) }));
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

const NUMERIC_CELL_SX = { display: 'block', textAlign: 'right', width: '100%', lineHeight: 1.2 } as const;

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
        <Typography
          component="span"
          variant="body2"
          color="text.disabled"
          sx={{ ...NUMERIC_CELL_SX, cursor: 'help' }}
        >
          —
        </Typography>
      </Tooltip>
    );
  }
  return (
    <Typography component="span" variant="body2" sx={NUMERIC_CELL_SX}>
      {fmtValue(value)}
    </Typography>
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
  total,
  page,
  pageSize,
  pageSizeOptions,
  onPageChange,
  onPageSizeChange,
  lens,
  rankBy,
  category,
  periodForLink,
  defaultBusinessUnit,
  fxPartial,
  onRowClick,
}: {
  rows: ExceptionRow[];
  total: number;
  page: number;
  pageSize: number;
  pageSizeOptions?: readonly number[];
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
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
  // Clamp height to occupied rows (not full pageSize capacity).
  const visibleRows = Math.max(1, Math.min(rows.length || 1, pageSize));
  const gridHeight = headerHeight + rowHeight * visibleRows;
  // 0-based parent page ↔ 1-based shell via shared skip/limit bijection (skip = page * pageSize).
  const shellPage = pageFromSkipLimit(page * pageSize, pageSize);
  const gridRows = useMemo(() => toGridRows(rows), [rows]);

  const showPoLink = category === 'short_ships' || category === 'no_po_blind_spots';
  const showLines = category === 'no_po_blind_spots';
  const entityHeader = ENTITY_LENS_HEADERS[lens];

  const columnLabelByField = useMemo(
    () => ({
      label: entityHeader,
      units: 'Units',
      value_plan: 'Value (plan)',
      value_cost: 'Value (cost)',
      line_count: 'Lines',
      po_action: 'Action',
    }),
    [entityHeader],
  );

  const columnDefs = useMemo<ColDef<ExceptionGridRow>[]>(
    () => [
      {
        colId: 'entity',
        field: 'label',
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
        cellRenderer: (p: ICellRendererParams<ExceptionGridRow>) => (
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
        type: 'numericColumn',
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
        type: 'numericColumn',
        sortable: true,
        comparator: (_a, _b, nodeA, nodeB) => {
          const va = nodeA.data?.value_plan;
          const vb = nodeB.data?.value_plan;
          if (va == null && vb == null) return 0;
          if (va == null) return -1;
          if (vb == null) return 1;
          return va - vb;
        },
        cellRenderer: (p: ICellRendererParams<ExceptionGridRow>) => (
          <ValueCell value={p.data?.value_plan} fxPartial={fxPartial} />
        ),
      },
      {
        field: 'value_cost',
        headerName: 'Value (cost)',
        headerTooltip: 'Cost currency — unavailable where bridge missing',
        width: 130,
        type: 'numericColumn',
        sortable: true,
        comparator: (_a, _b, nodeA, nodeB) => {
          const va = nodeA.data?.value_cost;
          const vb = nodeB.data?.value_cost;
          if (va == null && vb == null) return 0;
          if (va == null) return -1;
          if (vb == null) return 1;
          return va - vb;
        },
        cellRenderer: (p: ICellRendererParams<ExceptionGridRow>) => (
          <ValueCell value={p.data?.value_cost} fxPartial={fxPartial} />
        ),
      },
      {
        field: 'line_count',
        headerName: 'Lines',
        width: 90,
        type: 'numericColumn',
        hide: !showLines,
        sortable: true,
      },
      {
        colId: 'po_action',
        field: 'po_action',
        headerName: 'Action',
        width: 120,
        hide: !showPoLink,
        cellRenderer: (p: ICellRendererParams<ExceptionGridRow>) => {
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

  const gridOptions = useMemo<GridOptions<ExceptionGridRow>>(
    () => ({
      pagination: false,
      suppressPaginationPanel: true,
      rowHeight,
      headerHeight,
      defaultColDef: { resizable: true },
      onRowClicked: (e: RowClickedEvent<ExceptionGridRow>) => {
        if (e.data && onRowClick) onRowClick(e.data);
      },
      rowStyle: onRowClick ? { cursor: 'pointer' } : undefined,
    }),
    [onRowClick, rowHeight, headerHeight],
  );

  const onShellUrlChange = useCallback(
    (patch: Record<string, string | null>, resetPage?: boolean) => {
      if (patch.page_size != null) {
        onPageSizeChange(Number(patch.page_size) || pageSize);
        return;
      }
      if (resetPage) {
        onPageChange(0);
        return;
      }
      if (patch.page != null) {
        const oneBased = Math.max(1, Number(patch.page) || 1);
        const skip = skipFromPage(oneBased, pageSize);
        onPageChange(zeroBasedPageFromOffset(skip, pageSize));
      }
    },
    [onPageChange, onPageSizeChange, pageSize],
  );

  if (!total) {
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
      <MasterDataGridShell
        entityKey={`pve-exceptions-${category}`}
        rows={gridRows}
        columnDefs={columnDefs}
        total={total}
        empty={{
          title: 'No exception rows on this page',
          description: `None in range for ${EXCEPTION_CATEGORY_LABELS[category].toLowerCase()}.`,
        }}
        url={{
          page: shellPage,
          pageSize,
          q: '',
          sortBy: rankBy === 'value' ? 'value_plan' : 'units',
          sortDir: 'desc',
        }}
        onUrlChange={onShellUrlChange}
        defaultPageSize={PAGINATED_GRID_PAGE_SIZE}
        defaultSortBy="units"
        defaultSortDir="desc"
        pageSizeOptions={[...(pageSizeOptions ?? [PAGINATED_GRID_PAGE_SIZE, 30, 50])]}
        enableEmptyUrlSeed={false}
        gridStateStorageKey={exceptionGridStateKey(category)}
        columnPickerTitle="Exception list columns"
        columnPickerGroups={EXCEPTION_COLUMN_GROUPS}
        columnLabelByField={columnLabelByField}
        gridHeight={gridHeight}
        gridOptions={gridOptions}
        bulkSelectionEnabled={false}
      />
    </Box>
  );
}
