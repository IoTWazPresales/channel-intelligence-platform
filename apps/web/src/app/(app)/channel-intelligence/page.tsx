'use client';

import {
  Alert,
  Chip,
  Drawer,
  Stack,
  TextField,
  Typography,
  Box,
  Button,
} from '@mui/material';
import type { ColDef } from 'ag-grid-community';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { PageHeader } from '@/components/PageHeader';
import { apiGet } from '@/lib/api';

type IntelRow = {
  customer_id: number;
  product_id: number;
  site_label: string | null;
  data_state: string;
  reason: string | null;
  velocity_4wk: number | null;
  velocity_13wk: number | null;
  weeks_of_cover: number | null;
  weeks_of_cover_reason: string | null;
  aged_dead_stock: boolean;
  velocity_trend: string | null;
  factors: Record<string, unknown>;
  aged_factors?: Record<string, unknown>;
};

type IntelResponse = {
  items: IntelRow[];
  total: number;
  page: number;
  page_size: number;
  data_unavailable: boolean;
  grain_policy: string;
  message?: string;
  thresholds?: Record<string, unknown>;
};

export default function ChannelIntelligencePage() {
  const [customerId, setCustomerId] = useState('');
  const [productId, setProductId] = useState('');
  const [site, setSite] = useState('');
  const [selected, setSelected] = useState<IntelRow | null>(null);

  const params = new URLSearchParams();
  if (customerId.trim()) params.set('customer_id', customerId.trim());
  if (productId.trim()) params.set('product_id', productId.trim());
  if (site.trim()) params.set('site_label', site.trim());
  params.set('page_size', '200');

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['channel-intelligence', customerId, productId, site],
    queryFn: ({ signal }) =>
      apiGet<IntelResponse>(`/api/v1/channel-intelligence?${params.toString()}`, { signal }),
  });

  const cols = useMemo<ColDef<IntelRow>[]>(
    () => [
      { field: 'customer_id', headerName: 'Customer', width: 100 },
      { field: 'product_id', headerName: 'Product', width: 100 },
      { field: 'site_label', headerName: 'Site', flex: 1, minWidth: 120 },
      { field: 'data_state', headerName: 'State', width: 140 },
      {
        field: 'velocity_4wk',
        headerName: 'Vel 4wk',
        width: 100,
        valueFormatter: (p) => (p.value == null ? '—' : Number(p.value).toFixed(2)),
      },
      {
        field: 'velocity_13wk',
        headerName: 'Vel 13wk',
        width: 100,
        valueFormatter: (p) => (p.value == null ? '—' : Number(p.value).toFixed(2)),
      },
      {
        field: 'weeks_of_cover',
        headerName: 'WoC',
        width: 90,
        valueFormatter: (p) => (p.value == null ? 'n/a' : Number(p.value).toFixed(1)),
      },
      { field: 'velocity_trend', headerName: 'Trend', width: 90 },
      {
        headerName: 'Flags',
        width: 160,
        valueGetter: (p) => {
          const flags: string[] = [];
          if (p.data?.aged_dead_stock) flags.push('aged');
          if (p.data?.data_state === 'insufficient_data') flags.push('sparse');
          return flags.join(', ') || '—';
        },
      },
    ],
    [],
  );

  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Channel Intelligence' }, { label: 'CST velocity' }]}
        title="Channel intelligence (CST)"
        action={
          <Button size="small" variant="outlined" onClick={() => refetch()}>
            Refresh
          </Button>
        }
      />
      <Alert severity="info" sx={{ mb: 2 }}>
        Read-only over customer sell-through. Elasticity and competitor pricing are out of scope.
        Grain policy: {data?.grain_policy ?? '…'}. Sparse CST → insufficient_data (never false aged flags).
      </Alert>
      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap">
        <TextField
          size="small"
          label="Customer id"
          value={customerId}
          onChange={(e) => setCustomerId(e.target.value)}
          sx={{ width: 140 }}
        />
        <TextField
          size="small"
          label="Product id"
          value={productId}
          onChange={(e) => setProductId(e.target.value)}
          sx={{ width: 140 }}
        />
        <TextField
          size="small"
          label="Site label"
          value={site}
          onChange={(e) => setSite(e.target.value)}
          sx={{ width: 180 }}
        />
        <Chip size="small" label={`rows: ${data?.total ?? '…'}`} />
        {data?.data_unavailable ? <Chip size="small" color="warning" label="data unavailable" /> : null}
      </Stack>
      {isError ? <Alert severity="error">{String((error as Error)?.message)}</Alert> : null}
      {isLoading ? (
        <Typography>Loading…</Typography>
      ) : (
        <EnterpriseDataGrid
          rowData={data?.items ?? []}
          columnDefs={cols}
          height={520}
          gridOptions={{
            getRowId: (p) =>
              `${p.data.customer_id}-${p.data.product_id}-${p.data.site_label ?? ''}`,
            onRowClicked: (e) => setSelected(e.data ?? null),
          }}
        />
      )}
      <Drawer anchor="right" open={!!selected} onClose={() => setSelected(null)}>
        <Box sx={{ width: 360, p: 2 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            Factors
          </Typography>
          {selected ? (
            <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>
              {JSON.stringify(
                {
                  data_state: selected.data_state,
                  reason: selected.reason,
                  weeks_of_cover_reason: selected.weeks_of_cover_reason,
                  aged_factors: selected.aged_factors,
                  factors: selected.factors,
                },
                null,
                2,
              )}
            </pre>
          ) : null}
        </Box>
      </Drawer>
    </>
  );
}
