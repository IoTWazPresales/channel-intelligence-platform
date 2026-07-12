'use client';

import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import { Alert, Box, TablePagination } from '@mui/material';
import type { ColDef, GridOptions, ICellRendererParams } from 'ag-grid-community';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { gridRowMetrics, paginatedGridHeight } from '@/features/plan-vs-executed/gridPagination';
import { apiGet } from '@/lib/api';

import { depthAtLeast, type IntelDepth } from './intelDepth';

type InvRow = {
  distributor_id: number;
  distributor_name: string | null;
  product_id: number;
  sku: string | null;
  product_name: string | null;
  snapshot_date?: string | null;
  reported_soh: number;
  sell_out_since?: number;
  landed_since?: number;
  derived_stock?: number;
  calculated_soh: number | null;
  variance_units: number | null;
  variance_pct: number | null;
  reconciliation_status: string | null;
  velocity_52wk: number | null;
  weeks_of_cover: number | null;
  computed_through_date: string | null;
  reorder_signal: boolean;
};

const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;
const DEFAULT_PAGE_SIZE = 50;

function fmtNum(n: number | null | undefined): string {
  if (n == null) return '—';
  return n.toLocaleString();
}

export function ChannelOpsInventoryTab({
  depth,
  distributorId,
}: {
  depth: IntelDepth;
  distributorId?: number | null;
}) {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const distId = distributorId ?? null;
  const { rowHeight, headerHeight } = gridRowMetrics('comfortable');

  useEffect(() => {
    setPage(0);
  }, [distId]);

  const q = useQuery({
    queryKey: ['channel-ops-inventory', distId, page, pageSize],
    queryFn: ({ signal }) =>
      apiGet<{
        items: InvRow[];
        total: number;
        page: number;
        page_size: number;
        truncated?: boolean;
        true_total?: number;
      }>(
        `/api/v1/channel-ops/inventory?distributor_id=${distId}&page=${page + 1}&page_size=${pageSize}`,
        { signal },
      ),
    enabled: distId != null,
  });

  const columnDefs = useMemo<ColDef<InvRow>[]>(() => {
    const cols: ColDef<InvRow>[] = [
      { field: 'product_name', headerName: 'Product', flex: 1, minWidth: 160 },
      { field: 'sku', headerName: 'SKU', width: 120 },
      {
        field: 'reported_soh',
        headerName: 'Reported SOH',
        width: 120,
        type: 'numericColumn',
        valueFormatter: (p) => fmtNum(p.value as number),
      },
      {
        colId: 'derived_stock',
        headerName: 'Derived stock',
        width: 120,
        type: 'numericColumn',
        valueGetter: (p) => p.data?.derived_stock ?? p.data?.reported_soh ?? null,
        valueFormatter: (p) => fmtNum(p.value as number | null),
      },
    ];
    if (depthAtLeast(depth, 'operational')) {
      cols.push(
        {
          field: 'calculated_soh',
          headerName: 'Calculated SOH',
          width: 130,
          type: 'numericColumn',
          valueFormatter: (p) => fmtNum(p.value as number | null),
        },
        {
          field: 'variance_units',
          headerName: 'Variance',
          width: 110,
          type: 'numericColumn',
          valueFormatter: (p) => fmtNum(p.value as number | null),
        },
        { field: 'reconciliation_status', headerName: 'Recon status', width: 130 },
      );
    }
    if (depthAtLeast(depth, 'strategic')) {
      cols.push(
        {
          field: 'velocity_52wk',
          headerName: 'Velocity 52wk',
          width: 120,
          type: 'numericColumn',
          valueFormatter: (p) =>
            p.value == null ? '—' : Number(p.value).toFixed(2),
        },
        {
          field: 'weeks_of_cover',
          headerName: 'Weeks of cover',
          width: 130,
          type: 'numericColumn',
          valueFormatter: (p) =>
            p.value == null ? 'n/a' : Number(p.value).toFixed(1),
        },
      );
    }
    if (depthAtLeast(depth, 'forecast')) {
      cols.push({
        field: 'reorder_signal',
        headerName: 'Reorder',
        width: 100,
        cellRenderer: (p: ICellRendererParams<InvRow>) =>
          p.data?.reorder_signal ? (
            <WarningAmberIcon color="warning" fontSize="small" titleAccess="Reorder signal" />
          ) : (
            '—'
          ),
      });
    }
    return cols;
  }, [depth]);

  const gridOptions = useMemo<GridOptions<InvRow>>(
    () => ({
      pagination: false,
      suppressPaginationPanel: true,
      getRowId: (p) => String(p.data.product_id),
      rowHeight,
      headerHeight,
      defaultColDef: { resizable: true, sortable: true },
    }),
    [rowHeight, headerHeight],
  );

  if (distId == null) {
    return (
      <Alert severity="info" data-testid="inventory-distributor-required">
        Select a distributor above to load inventory. Inventory is computed per distributor from the latest DSI
        snapshot (derived stock) — there is no all-distributor inventory grid yet.
      </Alert>
    );
  }

  const items = q.data?.items ?? [];
  const total = q.data?.total ?? 0;

  return (
    <Box>
      {q.data?.truncated ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Soft cap: paging the first {total.toLocaleString()} of{' '}
          {(q.data.true_total ?? total).toLocaleString()} products for this distributor.
        </Alert>
      ) : null}
      <ModuleGridToolbar onRefresh={() => void q.refetch()} busy={q.isFetching} />
      <ModuleDataSection
        isLoading={q.isLoading}
        isError={q.isError}
        error={(q.error as Error) ?? null}
        onRetry={() => void q.refetch()}
        isEmpty={items.length === 0}
        empty={{
          title: 'No inventory rows',
          description:
            'No distributor inventory rows for this selection. Confirm DSI inventory snapshots exist for this distributor (Admin → Imports), or try another distributor.',
        }}
      >
        <EnterpriseDataGrid
          rowData={items}
          columnDefs={columnDefs}
          height={paginatedGridHeight(Math.min(pageSize, Math.max(items.length, 1)), {
            rowHeight,
            headerHeight,
          })}
          gridOptions={gridOptions}
        />
        <TablePagination
          component="div"
          count={total}
          page={page}
          onPageChange={(_e, nextPage) => setPage(nextPage)}
          rowsPerPage={pageSize}
          onRowsPerPageChange={(e) => {
            setPageSize(Number(e.target.value));
            setPage(0);
          }}
          rowsPerPageOptions={[...PAGE_SIZE_OPTIONS]}
          labelDisplayedRows={({ from, to, count }) =>
            `${from}–${to} of ${count !== -1 ? count.toLocaleString() : `more than ${to}`}`
          }
        />
      </ModuleDataSection>
    </Box>
  );
}
