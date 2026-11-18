'use client';

import { Alert, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

type StockNotListedRow = {
  customer_id: number;
  customer_code: string;
  customer_name: string;
  product_id: number;
  sku: string;
  product_name: string;
  stock_on_hand: number;
  stock_as_of: string | null;
  coverage: string;
  next_step: string;
};

type StockNotListed = {
  data_unavailable?: boolean;
  total?: number;
  truncated?: boolean;
  rows?: StockNotListedRow[];
};

const COVERAGE_LABEL: Record<string, string> = {
  awaiting_steward: 'Awaiting steward',
  failing: 'Failing',
  not_found: 'Not found',
  not_searched: 'Not searched',
};

/** Reported products in stock on the latest report that no watched listing covers. Read-only. */
export function StockNotListedWorklist() {
  const query = useQuery({
    queryKey: ['listing-capture', 'stock-not-listed'],
    queryFn: ({ signal }) => apiGet<StockNotListed>('/api/v1/listing-capture/stock-not-listed', { signal }),
  });
  const rows = Array.isArray(query.data?.rows) ? query.data.rows : [];
  const failed = query.isError || Boolean(query.data?.data_unavailable);

  return (
    <Stack spacing={1} data-testid="stock-not-listed">
      <Typography variant="subtitle2">In stock, not watched</Typography>
      <Typography variant="body2" color="text.secondary">
        Products with stock on each customer&apos;s latest report and no listing being watched, with the reason.
      </Typography>
      {failed ? (
        <Alert severity="warning" data-testid="stock-not-listed-error">
          This worklist could not be loaded.
        </Alert>
      ) : null}
      {query.isPending ? (
        <Typography variant="body2" color="text.secondary" data-testid="stock-not-listed-loading">
          Loading worklist…
        </Typography>
      ) : failed ? null : rows.length === 0 ? (
        <Typography variant="body2" data-testid="stock-not-listed-empty">
          Every stocked product has a watched listing.
        </Typography>
      ) : (
        <>
          {query.data?.truncated ? (
            <Typography variant="caption" color="text.secondary" data-testid="stock-not-listed-truncated">
              Showing {rows.length} of {query.data?.total} rows, highest stock first.
            </Typography>
          ) : null}
          <Table size="small" data-testid="stock-not-listed-table">
            <TableHead>
              <TableRow>
                <TableCell>Customer</TableCell>
                <TableCell>Product</TableCell>
                <TableCell align="right">Stock on hand</TableCell>
                <TableCell>As of</TableCell>
                <TableCell>Coverage</TableCell>
                <TableCell>Next step</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow
                  key={`${row.customer_id}-${row.product_id}`}
                  data-testid={`stock-not-listed-row-${row.customer_id}-${row.product_id}`}
                >
                  <TableCell>{row.customer_name || row.customer_code || row.customer_id}</TableCell>
                  <TableCell>{[row.sku, row.product_name].filter(Boolean).join(' · ') || row.product_id}</TableCell>
                  <TableCell align="right">{row.stock_on_hand}</TableCell>
                  <TableCell>{row.stock_as_of ?? '—'}</TableCell>
                  <TableCell>{COVERAGE_LABEL[row.coverage] ?? row.coverage}</TableCell>
                  <TableCell>{row.next_step}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </>
      )}
    </Stack>
  );
}
