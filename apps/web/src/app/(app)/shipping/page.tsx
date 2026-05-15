'use client';

import {
  Alert,
  Box,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { PageHeader } from '@/components/PageHeader';
import { apiGet } from '@/lib/api';

type ShippingSummary = {
  total_lines: number;
  by_line_state: Record<string, number>;
  by_product_resolution_status: Record<string, number>;
};

type ShippingLine = {
  id: number;
  import_job_id: number;
  line_state: string;
  report_type?: string | null;
  product_resolution_status?: string | null;
  distributor_resolution_status?: string | null;
  customer_resolution_status?: string | null;
  product_sku?: string | null;
  distributor_code?: string | null;
  item_code?: string | null;
  bill_to_raw?: string | null;
  ship_to_raw?: string | null;
};

type LinesResponse = { total: number; skip: number; limit: number; items: ShippingLine[] };

export default function ShippingEvidencePage() {
  const [lineState, setLineState] = useState<string>('');
  const [productStatus, setProductStatus] = useState<string>('');

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['shipping-summary'],
    queryFn: ({ signal }) => apiGet<ShippingSummary>('/api/v1/shipping/summary', { signal }),
  });

  const queryKey = useMemo(
    () => ['shipping-lines', lineState, productStatus] as const,
    [lineState, productStatus]
  );

  const { data: lines, isLoading: linesLoading } = useQuery({
    queryKey,
    queryFn: ({ signal }) => {
      const params = new URLSearchParams();
      params.set('limit', '50');
      if (lineState) params.set('line_state', lineState);
      if (productStatus) params.set('product_resolution_status', productStatus);
      return apiGet<LinesResponse>(`/api/v1/shipping/lines?${params.toString()}`, { signal });
    },
  });

  return (
    <>
      <PageHeader crumbs={[{ label: 'Shipping evidence' }]} title="Shipping evidence" />
      <Alert severity="info" sx={{ mb: 2 }}>
        Read-only view of canonical shipment evidence lines. Admin tools for stewarding imports live under{' '}
        <strong>Admin → Shipment evidence</strong>.
      </Alert>
      {summaryLoading ? (
        <Typography color="text.secondary">Loading summary…</Typography>
      ) : (
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
          <Paper sx={{ p: 2, flex: 1 }}>
            <Typography variant="subtitle2" color="text.secondary">
              Total lines
            </Typography>
            <Typography variant="h5">{summary?.total_lines ?? '—'}</Typography>
          </Paper>
          <Paper sx={{ p: 2, flex: 2 }}>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              By line state
            </Typography>
            <Typography variant="body2" component="pre" sx={{ whiteSpace: 'pre-wrap', m: 0 }}>
              {JSON.stringify(summary?.by_line_state ?? {}, null, 2)}
            </Typography>
          </Paper>
          <Paper sx={{ p: 2, flex: 2 }}>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              By product resolution
            </Typography>
            <Typography variant="body2" component="pre" sx={{ whiteSpace: 'pre-wrap', m: 0 }}>
              {JSON.stringify(summary?.by_product_resolution_status ?? {}, null, 2)}
            </Typography>
          </Paper>
        </Stack>
      )}

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel id="flt-line-state">Line state</InputLabel>
          <Select
            labelId="flt-line-state"
            label="Line state"
            value={lineState}
            onChange={(e) => setLineState(String(e.target.value))}
          >
            <MenuItem value="">(any)</MenuItem>
            {Object.keys(summary?.by_line_state ?? {}).map((k) => (
              <MenuItem key={k} value={k}>
                {k}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 240 }}>
          <InputLabel id="flt-prod">Product resolution</InputLabel>
          <Select
            labelId="flt-prod"
            label="Product resolution"
            value={productStatus}
            onChange={(e) => setProductStatus(String(e.target.value))}
          >
            <MenuItem value="">(any)</MenuItem>
            {Object.keys(summary?.by_product_resolution_status ?? {}).map((k) => (
              <MenuItem key={k} value={k}>
                {k}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Stack>

      <Box sx={{ overflowX: 'auto' }}>
        {linesLoading ? (
          <Typography color="text.secondary">Loading rows…</Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>ID</TableCell>
                <TableCell>Job</TableCell>
                <TableCell>Line state</TableCell>
                <TableCell>Report</TableCell>
                <TableCell>Distributor</TableCell>
                <TableCell>SKU</TableCell>
                <TableCell>Product res.</TableCell>
                <TableCell>Dist. res.</TableCell>
                <TableCell>Customer res.</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(lines?.items ?? []).map((row) => (
                <TableRow key={row.id}>
                  <TableCell>{row.id}</TableCell>
                  <TableCell>{row.import_job_id}</TableCell>
                  <TableCell>{row.line_state}</TableCell>
                  <TableCell>{row.report_type ?? '—'}</TableCell>
                  <TableCell>{row.distributor_code ?? '—'}</TableCell>
                  <TableCell>{row.product_sku ?? row.item_code ?? '—'}</TableCell>
                  <TableCell>{row.product_resolution_status ?? '—'}</TableCell>
                  <TableCell>{row.distributor_resolution_status ?? '—'}</TableCell>
                  <TableCell>{row.customer_resolution_status ?? '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {lines && !linesLoading ? (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            Showing {lines.items.length} of {lines.total} (skip {lines.skip}, limit {lines.limit})
          </Typography>
        ) : null}
      </Box>
    </>
  );
}
