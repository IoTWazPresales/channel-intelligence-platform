'use client';

import {
  Alert,
  Box,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import type { ColDef, GridOptions } from 'ag-grid-community';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { gridRowMetrics, paginatedGridHeight } from '@/features/plan-vs-executed/gridPagination';
import { apiGet } from '@/lib/api';

import { depthAtLeast, type IntelDepth } from './intelDepth';

type MovementRow = {
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

const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;
const DEFAULT_PAGE_SIZE = 50;

export function ChannelOpsMovementsTab({
  depth,
  distributorId,
}: {
  depth: IntelDepth;
  distributorId?: number | null;
}) {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const distId = distributorId ?? null;
  const { rowHeight, headerHeight } = gridRowMetrics('comfortable');

  useEffect(() => {
    setPage(0);
  }, [distId, dateFrom, dateTo]);

  const q = useQuery({
    queryKey: ['channel-ops-movements', distId, page, pageSize, dateFrom, dateTo],
    queryFn: ({ signal }) => {
      const params = new URLSearchParams({
        distributor_id: String(distId),
        page: String(page + 1),
        page_size: String(pageSize),
      });
      if (dateFrom) params.set('date_from', dateFrom);
      if (dateTo) params.set('date_to', dateTo);
      return apiGet<{ items: MovementRow[]; total: number; page: number; page_size: number }>(
        `/api/v1/channel-ops/movements?${params}`,
        { signal },
      );
    },
    enabled: distId != null,
  });

  const productTotals = useMemo(() => {
    if (!depthAtLeast(depth, 'strategic') || !q.data?.items?.length) return [];
    const map = new Map<number, { sku: string; name: string; inbound: number }>();
    for (const r of q.data.items) {
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
  }, [q.data?.items, depth]);

  const columnDefs = useMemo<ColDef<MovementRow>[]>(
    () => [
      { field: 'ship_date', headerName: 'Ship date', width: 120 },
      { field: 'product_name', headerName: 'Product', flex: 1, minWidth: 160 },
      { field: 'sku', headerName: 'SKU', width: 120 },
      { field: 'order_no', headerName: 'Order no', width: 120 },
      { field: 'delivery_no', headerName: 'Delivery no', width: 120 },
      {
        field: 'units_shipped',
        headerName: 'Units',
        width: 100,
        type: 'numericColumn',
        valueFormatter: (p) =>
          p.value == null ? '—' : Number(p.value).toLocaleString(),
      },
      { field: 'line_state', headerName: 'Status', width: 120 },
    ],
    [],
  );

  const gridOptions = useMemo<GridOptions<MovementRow>>(
    () => ({
      pagination: false,
      suppressPaginationPanel: true,
      getRowId: (p) =>
        `${p.data.order_no ?? ''}|${p.data.delivery_no ?? ''}|${p.data.product_id ?? ''}|${p.data.ship_date ?? ''}|${p.rowIndex}`,
      rowHeight,
      headerHeight,
      defaultColDef: { resizable: true, sortable: true },
    }),
    [rowHeight, headerHeight],
  );

  if (distId == null) {
    return (
      <Alert severity="info" data-testid="movements-distributor-required">
        Select a distributor above to view inbound shipment movements. Movements read shipment evidence for that
        distributor only.
      </Alert>
    );
  }

  const items = q.data?.items ?? [];
  const total = q.data?.total ?? 0;

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
      <ModuleGridToolbar onRefresh={() => void q.refetch()} busy={q.isFetching} />
      <ModuleDataSection
        isLoading={q.isLoading}
        isError={q.isError}
        error={(q.error as Error) ?? null}
        onRetry={() => void q.refetch()}
        isEmpty={items.length === 0}
        empty={{
          title: 'No movements',
          description: `No shipment evidence lines for this distributor${
            dateFrom || dateTo ? ' in the selected date range' : ''
          }. Check inbound shipment imports or widen the dates.`,
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
      {depthAtLeast(depth, 'strategic') && productTotals.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2" gutterBottom>
            Inbound totals by product (current page only — not full filter set)
          </Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>SKU</TableCell>
                <TableCell>Product</TableCell>
                <TableCell align="right">Inbound units</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {productTotals.map((r) => (
                <TableRow key={r.productId}>
                  <TableCell>{r.sku}</TableCell>
                  <TableCell>{r.name}</TableCell>
                  <TableCell align="right">{r.inbound.toLocaleString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      )}
    </Box>
  );
}
