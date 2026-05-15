'use client';

import {
  Alert,
  Box,
  Chip,
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

type CountBucket = { key: string; count: number };

type ShippingSummary = {
  total_lines: number;
  by_line_state: CountBucket[];
  by_status: CountBucket[];
  by_product_resolution_status: CountBucket[];
};

type ShippingLine = {
  id: number;
  import_job_id: number | null;
  source_key: string;
  line_state: string;
  status: string;
  report_type?: string | null;
  product_resolution_status?: string | null;
  distributor_resolution_status?: string | null;
  customer_resolution_status?: string | null;
  product_sku?: string | null;
  product_name?: string | null;
  distributor_code?: string | null;
  distributor_name?: string | null;
  item_code?: string | null;
  eta_date?: string | null;
  promise_date?: string | null;
  pod_date?: string | null;
};

type LinesResponse = { total: number; skip: number; limit: number; items: ShippingLine[] };

function fmtShortDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function CountTile({ title, buckets }: { title: string; buckets: CountBucket[] }) {
  if (!buckets.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        No rows in this bucket.
      </Typography>
    );
  }
  return (
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      {buckets.map((b) => (
        <Chip key={`${title}-${b.key}`} label={`${b.key}: ${b.count}`} size="small" variant="outlined" />
      ))}
    </Stack>
  );
}

export default function ShippingEvidencePage() {
  const [lineState, setLineState] = useState<string>('');
  const [productStatus, setProductStatus] = useState<string>('');
  const [cargoStatus, setCargoStatus] = useState<string>('');

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['shipping-summary'],
    queryFn: ({ signal }) => apiGet<ShippingSummary>('/api/v1/shipping/summary', { signal }),
  });

  const queryKey = useMemo(
    () => ['shipping-lines', lineState, productStatus, cargoStatus] as const,
    [lineState, productStatus, cargoStatus]
  );

  const { data: lines, isLoading: linesLoading } = useQuery({
    queryKey,
    queryFn: ({ signal }) => {
      const params = new URLSearchParams();
      params.set('limit', '50');
      if (lineState) params.set('line_state', lineState);
      if (productStatus) params.set('product_resolution_status', productStatus);
      if (cargoStatus) params.set('status', cargoStatus);
      return apiGet<LinesResponse>(`/api/v1/shipping/lines?${params.toString()}`, { signal });
    },
  });

  return (
    <>
      <PageHeader crumbs={[{ label: 'Shipping evidence' }]} title="Inbound shipments (facts)" />
      <Alert severity="info" sx={{ mb: 2 }}>
        Truth layer from <strong>fact_inbound_shipment</strong> (populated when an inbound import job is applied).
        Steward raw imports under <strong>Admin → Shipment evidence</strong>.
      </Alert>
      {summaryLoading ? (
        <Typography color="text.secondary">Loading summary…</Typography>
      ) : (
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
          <Paper sx={{ p: 2, flex: 1 }}>
            <Typography variant="subtitle2" color="text.secondary">
              Total fact rows
            </Typography>
            <Typography variant="h5">{summary?.total_lines ?? '—'}</Typography>
          </Paper>
          <Paper sx={{ p: 2, flex: 2 }}>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              By line state
            </Typography>
            <CountTile title="line_state" buckets={summary?.by_line_state ?? []} />
          </Paper>
          <Paper sx={{ p: 2, flex: 2 }}>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              By cargo status
            </Typography>
            <CountTile title="status" buckets={summary?.by_status ?? []} />
          </Paper>
          <Paper sx={{ p: 2, flex: 2 }}>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              By product resolution
            </Typography>
            <CountTile title="product_resolution" buckets={summary?.by_product_resolution_status ?? []} />
          </Paper>
        </Stack>
      )}

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel id="flt-line-state">Line state</InputLabel>
          <Select
            labelId="flt-line-state"
            label="Line state"
            value={lineState}
            onChange={(e) => setLineState(String(e.target.value))}
          >
            <MenuItem value="">(any)</MenuItem>
            {(summary?.by_line_state ?? []).map((b) => (
              <MenuItem key={b.key} value={b.key}>
                {b.key}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel id="flt-cargo">Cargo status</InputLabel>
          <Select
            labelId="flt-cargo"
            label="Cargo status"
            value={cargoStatus}
            onChange={(e) => setCargoStatus(String(e.target.value))}
          >
            <MenuItem value="">(any)</MenuItem>
            {(summary?.by_status ?? []).map((b) => (
              <MenuItem key={b.key} value={b.key}>
                {b.key}
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
            {(summary?.by_product_resolution_status ?? []).map((b) => (
              <MenuItem key={b.key} value={b.key}>
                {b.key}
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
                <TableCell>Line / cargo</TableCell>
                <TableCell>Report</TableCell>
                <TableCell>Distributor</TableCell>
                <TableCell>Product</TableCell>
                <TableCell>ETA</TableCell>
                <TableCell>Promise</TableCell>
                <TableCell>POD</TableCell>
                <TableCell>Product res.</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(lines?.items ?? []).map((row) => (
                <TableRow key={row.id}>
                  <TableCell>{row.id}</TableCell>
                  <TableCell>{row.import_job_id ?? '—'}</TableCell>
                  <TableCell>
                    <Typography variant="body2">{row.line_state}</Typography>
                    <Typography variant="caption" color="text.secondary" display="block">
                      {row.status}
                    </Typography>
                  </TableCell>
                  <TableCell>{row.report_type ?? '—'}</TableCell>
                  <TableCell>
                    <Typography variant="body2">{row.distributor_name ?? row.distributor_code ?? '—'}</Typography>
                    {row.distributor_code && row.distributor_name ? (
                      <Typography variant="caption" color="text.secondary" display="block">
                        {row.distributor_code}
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">{row.product_name ?? row.product_sku ?? row.item_code ?? '—'}</Typography>
                    {row.product_sku && row.product_name ? (
                      <Typography variant="caption" color="text.secondary" display="block">
                        SKU {row.product_sku}
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell>{fmtShortDate(row.eta_date)}</TableCell>
                  <TableCell>{fmtShortDate(row.promise_date)}</TableCell>
                  <TableCell>{fmtShortDate(row.pod_date)}</TableCell>
                  <TableCell>{row.product_resolution_status ?? '—'}</TableCell>
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
