'use client';

import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import { Alert, Box } from '@mui/material';
import type { ColDef, GridOptions, ICellRendererParams } from 'ag-grid-community';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { MasterDataGridShell } from '@/components/masterGrid/MasterDataGridShell';
import type { MasterColumnPickerGroup } from '@/components/masterGrid/MasterColumnPickerDialog';
import { apiGet } from '@/lib/api';

import { depthAtLeast, type IntelDepth } from './intelDepth';

type InvRow = {
  id: number;
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

const PAGE_SIZE_OPTIONS = [25, 50, 100];
const DEFAULT_PAGE_SIZE = 50;
const GRID_STATE_KEY = 'cip.channel-ops.inventory.shell.grid.v1';

const COLUMN_GROUPS: MasterColumnPickerGroup[] = [
  {
    label: 'Core',
    fields: ['product_name', 'sku', 'reported_soh', 'reconciliation_status'],
  },
  {
    label: 'Stock',
    fields: ['derived_stock', 'calculated_soh', 'variance_units', 'computed_through_date'],
  },
  {
    label: 'Cover',
    fields: ['velocity_52wk', 'weeks_of_cover', 'reorder_signal'],
  },
];

const DEFAULT_HIDDEN_INVENTORY_FIELDS = ['computed_through_date'] as const;

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
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const distId = distributorId ?? null;

  useEffect(() => {
    setPage(1);
  }, [distId]);

  const q = useQuery({
    queryKey: ['channel-ops-inventory', distId, page, pageSize],
    queryFn: ({ signal }) =>
      apiGet<{
        items: Omit<InvRow, 'id'>[];
        total: number;
        page: number;
        page_size: number;
        truncated?: boolean;
        true_total?: number;
      }>(
        `/api/v1/channel-ops/inventory?distributor_id=${distId}&page=${page}&page_size=${pageSize}`,
        { signal },
      ),
    enabled: distId != null,
  });

  const rows: InvRow[] = useMemo(
    () => (q.data?.items ?? []).map((r) => ({ ...r, id: r.product_id })),
    [q.data?.items],
  );

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
        field: 'derived_stock',
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
        {
          field: 'computed_through_date',
          headerName: 'Computed through',
          width: 130,
          hide: true,
          valueFormatter: (p) => (p.value ? String(p.value) : '—'),
        },
      );
    }
    if (depthAtLeast(depth, 'strategic')) {
      cols.push(
        {
          field: 'velocity_52wk',
          headerName: 'Velocity 52wk',
          width: 120,
          type: 'numericColumn',
          valueFormatter: (p) => (p.value == null ? '—' : Number(p.value).toFixed(2)),
        },
        {
          field: 'weeks_of_cover',
          headerName: 'Weeks of cover',
          width: 130,
          type: 'numericColumn',
          valueFormatter: (p) => (p.value == null ? 'n/a' : Number(p.value).toFixed(1)),
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
      getRowId: (p) => String(p.data.id),
      defaultColDef: { resizable: true, sortable: true },
    }),
    [],
  );

  if (distId == null) {
    return (
      <Alert severity="info" data-testid="inventory-distributor-required">
        Select a distributor above to load inventory. Inventory is computed per distributor from the latest DSI
        snapshot (derived stock) — there is no all-distributor inventory grid yet.
      </Alert>
    );
  }

  return (
    <Box>
      {q.data?.truncated ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Soft cap: paging the first {(q.data.total ?? 0).toLocaleString()} of{' '}
          {(q.data.true_total ?? q.data.total).toLocaleString()} products for this distributor.
        </Alert>
      ) : null}
      <MasterDataGridShell
        entityKey="channel-ops-inventory"
        rows={rows}
        columnDefs={columnDefs}
        total={q.data?.total ?? 0}
        isLoading={q.isLoading}
        isError={q.isError}
        error={(q.error as Error) ?? null}
        onRetry={() => void q.refetch()}
        empty={{
          title: 'No inventory rows',
          description:
            'No distributor inventory rows for this selection. Confirm DSI inventory snapshots exist for this distributor (Admin → Imports), or try another distributor.',
        }}
        url={{ page, pageSize, q: '', sortBy: 'sku', sortDir: 'asc' }}
        onUrlChange={(patch, resetPage) => {
          if (patch.page_size != null) {
            setPageSize(Number(patch.page_size) || DEFAULT_PAGE_SIZE);
            setPage(1);
            return;
          }
          if (resetPage) setPage(1);
          if (patch.page != null) setPage(Math.max(1, Number(patch.page) || 1));
        }}
        defaultPageSize={DEFAULT_PAGE_SIZE}
        defaultSortBy="sku"
        defaultSortDir="asc"
        pageSizeOptions={PAGE_SIZE_OPTIONS}
        enableEmptyUrlSeed={false}
        gridStateStorageKey={GRID_STATE_KEY}
        defaultInitiallyHiddenFields={[...DEFAULT_HIDDEN_INVENTORY_FIELDS]}
        columnPickerTitle="Inventory columns"
        columnPickerGroups={COLUMN_GROUPS}
        gridOptions={gridOptions}
        bulkSelectionEnabled={false}
        onRefresh={() => void q.refetch()}
        refreshBusy={q.isFetching}
      />
    </Box>
  );
}
