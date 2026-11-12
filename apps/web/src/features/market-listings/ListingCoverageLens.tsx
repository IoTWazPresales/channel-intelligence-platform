'use client';

import { Alert, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

type CoverageCustomer = {
  customer_id: number;
  customer_code: string;
  customer_name: string;
  reported: number;
  watched: number;
  awaiting_steward: number;
  failing: number;
  not_found: number;
  not_searched: number;
};

type CaptureHealth = {
  data_unavailable?: boolean;
  coverage?: {
    data_unavailable?: boolean;
    customers?: CoverageCustomer[];
  };
};

export function ListingCoverageLens() {
  const health = useQuery({
    queryKey: ['listing-capture', 'capture-health'],
    queryFn: ({ signal }) => apiGet<CaptureHealth>('/api/v1/listing-capture/capture-health', { signal }),
  });
  const coverage = health.data?.coverage;
  const rows = coverage?.customers ?? [];
  const unavailable = Boolean(health.data?.data_unavailable || coverage?.data_unavailable);

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="listing-coverage-lens">
      <Typography variant="body2" color="text.secondary">
        For each customer: products they reported, listings being watched, rows waiting on a steward, failing reads,
        products not found on the site, and products not searched yet.
      </Typography>
      {health.isError || unavailable ? (
        <Alert severity="warning">Coverage could not be loaded in full.</Alert>
      ) : null}
      {rows.length === 0 ? (
        <Typography variant="body2" data-testid="listing-coverage-empty">
          No reported products yet.
        </Typography>
      ) : (
        <Table size="small" data-testid="listing-coverage-table">
          <TableHead>
            <TableRow>
              <TableCell>Customer</TableCell>
              <TableCell align="right">Reported</TableCell>
              <TableCell align="right">Watched</TableCell>
              <TableCell align="right">Awaiting steward</TableCell>
              <TableCell align="right">Failing</TableCell>
              <TableCell align="right">Not found</TableCell>
              <TableCell align="right">Not searched</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.customer_id} data-testid={`listing-coverage-row-${row.customer_id}`}>
                <TableCell>{row.customer_name || row.customer_code || row.customer_id}</TableCell>
                <TableCell align="right">{row.reported}</TableCell>
                <TableCell align="right">{row.watched}</TableCell>
                <TableCell align="right">{row.awaiting_steward}</TableCell>
                <TableCell align="right">{row.failing}</TableCell>
                <TableCell align="right">{row.not_found}</TableCell>
                <TableCell align="right">{row.not_searched}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Stack>
  );
}
