'use client';

import {
  Alert,
  Box,
  Paper,
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
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

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

  useEffect(() => {
    setPage(0);
  }, [distId, dateFrom, dateTo]);

  const { data, isLoading, isError, error } = useQuery({
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
        { signal }
      );
    },
    enabled: distId != null,
  });

  const productTotals = useMemo(() => {
    if (!depthAtLeast(depth, 'strategic') || !data?.items?.length) return [];
    const map = new Map<number, { sku: string; name: string; inbound: number }>();
    for (const r of data.items) {
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
  }, [data?.items, depth]);

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
      {isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {(error as Error)?.message ?? 'Failed to load movements.'}
        </Alert>
      )}
      <Paper variant="outlined">
        <Box sx={{ p: 2 }}>
          {data != null && data.total > 0 ? (
            <TablePagination
              component="div"
              count={data.total}
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
              sx={{ borderBottom: 1, borderColor: 'divider', mb: 1 }}
            />
          ) : null}
          {isLoading ? (
            <Typography variant="body2">Loading…</Typography>
          ) : (data?.items ?? []).length === 0 ? (
            <Alert severity="info">
              No shipment evidence lines for this distributor
              {dateFrom || dateTo ? ' in the selected date range' : ''}. Check inbound shipment imports or widen
              the dates.
            </Alert>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Ship date</TableCell>
                  <TableCell>Product</TableCell>
                  <TableCell>SKU</TableCell>
                  <TableCell>Order no</TableCell>
                  <TableCell>Delivery no</TableCell>
                  <TableCell align="right">Units</TableCell>
                  <TableCell>Status</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data?.items.map((r, i) => (
                  <TableRow key={`${r.order_no}-${i}`}>
                    <TableCell>{r.ship_date ?? '—'}</TableCell>
                    <TableCell>{r.product_name ?? '—'}</TableCell>
                    <TableCell>{r.sku ?? '—'}</TableCell>
                    <TableCell>{r.order_no ?? '—'}</TableCell>
                    <TableCell>{r.delivery_no ?? '—'}</TableCell>
                    <TableCell align="right">
                      {r.units_shipped != null ? r.units_shipped.toLocaleString() : '—'}
                    </TableCell>
                    <TableCell>{r.line_state}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Box>
      </Paper>
      {depthAtLeast(depth, 'strategic') && productTotals.length > 0 && (
        <Paper variant="outlined" sx={{ mt: 2, p: 2 }}>
          <Typography variant="subtitle2" gutterBottom>
            Inbound totals by product (filtered page)
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
        </Paper>
      )}
    </Box>
  );
}
