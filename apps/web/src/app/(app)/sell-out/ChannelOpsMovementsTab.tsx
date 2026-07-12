'use client';

import { Alert, Box, Stack, TextField, Typography } from '@mui/material';
import type { ColDef, GridOptions } from 'ag-grid-community';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { MasterDataGridShell } from '@/components/masterGrid/MasterDataGridShell';
import type { MasterColumnPickerGroup } from '@/components/masterGrid/MasterColumnPickerDialog';
import { apiGet } from '@/lib/api';

import { depthAtLeast, type IntelDepth } from './intelDepth';

type MovementRow = {
  id: string;
  product_id: number | null;
  sku: string | null;
  product_name: string | null;
  order_no: string | null;
  delivery_no: string | null;
  ship_date: string | null;
  units_shipped: number | null;
  line_state: string;
  distributor_name: string | null;
};

const PAGE_SIZE_OPTIONS = [25, 50, 100];
const DEFAULT_PAGE_SIZE = 50;
const GRID_STATE_KEY = 'cip.channel-ops.movements.shell.grid.v1';

const COLUMN_GROUPS: MasterColumnPickerGroup[] = [
  {
    label: 'Core',
    fields: [
      'ship_date',
      'distributor_name',
      'product_name',
      'sku',
      'product_id',
      'order_no',
      'delivery_no',
      'units_shipped',
      'line_state',
    ],
  },
];

const DEFAULT_HIDDEN_MOVEMENT_FIELDS = ['product_id'] as const;

export function ChannelOpsMovementsTab({
  depth,
  distributorId,
}: {
  depth: IntelDepth;
  distributorId?: number | null;
}) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const distId = distributorId ?? null;

  useEffect(() => {
    setPage(1);
  }, [distId, dateFrom, dateTo]);

  const q = useQuery({
    queryKey: ['channel-ops-movements', distId, page, pageSize, dateFrom, dateTo],
    queryFn: ({ signal }) => {
      const params = new URLSearchParams({
        distributor_id: String(distId),
        page: String(page),
        page_size: String(pageSize),
      });
      if (dateFrom) params.set('date_from', dateFrom);
      if (dateTo) params.set('date_to', dateTo);
      return apiGet<{ items: Omit<MovementRow, 'id'>[]; total: number; page: number; page_size: number }>(
        `/api/v1/channel-ops/movements?${params}`,
        { signal },
      );
    },
    enabled: distId != null,
  });

  const rows: MovementRow[] = useMemo(
    () =>
      (q.data?.items ?? []).map((r, i) => ({
        ...r,
        id: `${r.order_no ?? ''}|${r.delivery_no ?? ''}|${r.product_id ?? ''}|${r.ship_date ?? ''}|${i}`,
      })),
    [q.data?.items],
  );

  const productTotals = useMemo(() => {
    if (!depthAtLeast(depth, 'strategic') || !rows.length) return [];
    const map = new Map<number, { sku: string; name: string; inbound: number }>();
    for (const r of rows) {
      if (r.product_id == null) continue;
      const cur = map.get(r.product_id) ?? {
        sku: r.sku ?? '—',
        name: r.product_name ?? '—',
        inbound: 0,
      };
      cur.inbound += r.units_shipped ?? 0;
      map.set(r.product_id, cur);
    }
    return [...map.entries()].map(([productId, v]) => ({ productId, ...v }));
  }, [rows, depth]);

  const columnDefs = useMemo<ColDef<MovementRow>[]>(
    () => [
      { field: 'ship_date', headerName: 'Ship date', width: 120 },
      { field: 'distributor_name', headerName: 'Distributor', width: 140 },
      { field: 'product_name', headerName: 'Product', flex: 1, minWidth: 160 },
      { field: 'sku', headerName: 'SKU', width: 120 },
      {
        field: 'product_id',
        headerName: 'Product ID',
        width: 100,
        type: 'numericColumn',
        hide: true,
        valueFormatter: (p) => (p.value == null ? '—' : String(p.value)),
      },
      { field: 'order_no', headerName: 'Order no', width: 120 },
      { field: 'delivery_no', headerName: 'Delivery no', width: 120 },
      {
        field: 'units_shipped',
        headerName: 'Units',
        width: 100,
        type: 'numericColumn',
        valueFormatter: (p) => (p.value == null ? '—' : Number(p.value).toLocaleString()),
      },
      { field: 'line_state', headerName: 'Status', width: 120 },
    ],
    [],
  );

  const gridOptions = useMemo<GridOptions<MovementRow>>(
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
      <Alert severity="info" data-testid="movements-distributor-required">
        Select a distributor above to view inbound shipment movements. Movements read shipment evidence for that
        distributor only.
      </Alert>
    );
  }

  return (
    <Box>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          type="date"
          label="Ship date from"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          InputLabelProps={{ shrink: true }}
          inputProps={{ 'data-testid': 'movements-date-from' }}
        />
        <TextField
          size="small"
          type="date"
          label="Ship date to"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          InputLabelProps={{ shrink: true }}
          inputProps={{ 'data-testid': 'movements-date-to' }}
        />
      </Stack>
      <MasterDataGridShell
        entityKey="channel-ops-movements"
        rows={rows}
        columnDefs={columnDefs}
        total={q.data?.total ?? 0}
        isLoading={q.isLoading}
        isError={q.isError}
        error={(q.error as Error) ?? null}
        onRetry={() => void q.refetch()}
        empty={{
          title: 'No movements',
          description: `No shipment evidence lines for this distributor${
            dateFrom || dateTo ? ' in the selected date range' : ''
          }. Check inbound shipment imports or widen the dates.`,
        }}
        url={{ page, pageSize, q: '', sortBy: 'ship_date', sortDir: 'desc' }}
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
        defaultSortBy="ship_date"
        defaultSortDir="desc"
        pageSizeOptions={PAGE_SIZE_OPTIONS}
        enableEmptyUrlSeed={false}
        gridStateStorageKey={GRID_STATE_KEY}
        defaultInitiallyHiddenFields={[...DEFAULT_HIDDEN_MOVEMENT_FIELDS]}
        columnPickerTitle="Movements columns"
        columnPickerGroups={COLUMN_GROUPS}
        gridOptions={gridOptions}
        bulkSelectionEnabled={false}
        onRefresh={() => void q.refetch()}
        refreshBusy={q.isFetching}
      />
      {depthAtLeast(depth, 'strategic') && productTotals.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2" gutterBottom>
            Inbound totals by product (current page only — not full filter set)
          </Typography>
          <Stack spacing={0.5}>
            {productTotals.map((r) => (
              <Typography key={r.productId} variant="body2">
                {r.sku} — {r.name}: {r.inbound.toLocaleString()}
              </Typography>
            ))}
          </Stack>
        </Box>
      )}
    </Box>
  );
}
