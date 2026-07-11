'use client';

import {
  Alert,
  Autocomplete,
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

type DistHit = { id: number; distributor_code: string; distributor_name: string };

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

export function ChannelOpsMovementsTab({ depth }: { depth: IntelDepth }) {
  const [distributorPick, setDistributorPick] = useState<DistHit | null>(null);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const distId = distributorPick?.id;

  useEffect(() => {
    setPage(0);
  }, [distId]);

  const { data: filterOptions } = useQuery({
    queryKey: ['sellout-filter-options'],
    queryFn: ({ signal }) =>
      apiGet<{ distributors: DistHit[] }>('/api/v1/sellout/filter-options', { signal }),
  });

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['channel-ops-movements', distId, page, pageSize],
    queryFn: ({ signal }) =>
      apiGet<{ items: MovementRow[]; total: number; page: number; page_size: number }>(
        `/api/v1/channel-ops/movements?distributor_id=${distId}&page=${page + 1}&page_size=${pageSize}`,
        { signal }
      ),
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
      <Box>
        <Autocomplete
          sx={{ minWidth: 320, mb: 2 }}
          size="small"
          options={filterOptions?.distributors ?? []}
          value={distributorPick}
          onChange={(_e, v) => setDistributorPick(v)}
          getOptionLabel={(o) => `${o.distributor_name} (${o.distributor_code})`}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={(params) => <TextField {...params} label="Distributor" required />}
        />
        <Alert severity="info">Select a distributor to view inbound shipment movements.</Alert>
      </Box>
    );
  }

  return (
    <Box>
      <Autocomplete
        sx={{ minWidth: 320, mb: 2 }}
        size="small"
        options={filterOptions?.distributors ?? []}
        value={distributorPick}
        onChange={(_e, v) => setDistributorPick(v)}
        getOptionLabel={(o) => `${o.distributor_name} (${o.distributor_code})`}
        isOptionEqualToValue={(a, b) => a.id === b.id}
        renderInput={(params) => <TextField {...params} label="Distributor" required />}
      />
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
            <Typography variant="body2" color="text.secondary">
              No shipment evidence lines for this distributor.
            </Typography>
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
