'use client';

import {
  Alert,
  Autocomplete,
  Box,
  Chip,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { PageHeader } from '@/components/PageHeader';
import { apiGet } from '@/lib/api';

type SmartPresetId =
  | ''
  | 'fastest_movers'
  | 'customers_increased_volume'
  | 'customers_dropped_off'
  | 'zero_sellout_products';

type SelloutSummary = {
  total_rows: number;
  total_units: number;
  total_revenue: number;
  latest_period_start: string | null;
};

type SelloutLine = {
  id: number;
  product_sku: string | null;
  product_name: string | null;
  customer_code: string | null;
  customer_name: string | null;
  distributor_code: string | null;
  period_start: string;
  units: number;
  revenue: number;
  currency_code: string | null;
};

type LinesResponse = { total: number; skip: number; limit: number; items: SelloutLine[] };

type DistHit = { id: number; distributor_code: string; distributor_name: string };
type CustHit = { id: number; customer_code: string; customer_name: string };

type ZeroProduct = { product_id: number; sku: string; name: string };

export default function SellOutPage() {
  const [smartPreset, setSmartPreset] = useState<SmartPresetId>('');
  const [distributorPick, setDistributorPick] = useState<DistHit | null>(null);
  const [customerPick, setCustomerPick] = useState<CustHit | null>(null);
  const [search, setSearch] = useState('');

  const { data: summary } = useQuery({
    queryKey: ['sellout-commercial-summary'],
    queryFn: ({ signal }) => apiGet<SelloutSummary>('/api/v1/sellout/commercial-summary', { signal }),
  });

  const { data: filterOptions } = useQuery({
    queryKey: ['sellout-filter-options'],
    queryFn: ({ signal }) =>
      apiGet<{ distributors: DistHit[]; customers: CustHit[] }>('/api/v1/sellout/filter-options', { signal }),
  });

  const distOptions = filterOptions?.distributors ?? [];
  const custOptions = filterOptions?.customers ?? [];

  const linesQueryKey = useMemo(
    () =>
      [
        'sellout-commercial-lines',
        smartPreset,
        distributorPick?.id ?? null,
        customerPick?.id ?? null,
        search,
      ] as const,
    [smartPreset, distributorPick?.id, customerPick?.id, search]
  );

  const { data: lines, isLoading: linesLoading } = useQuery({
    queryKey: linesQueryKey,
    queryFn: ({ signal }) => {
      const params = new URLSearchParams();
      params.set('limit', '50');
      if (distributorPick != null) params.set('distributor_id', String(distributorPick.id));
      if (customerPick != null) params.set('customer_id', String(customerPick.id));
      if (search.trim()) params.set('product_search', search.trim());
      if (smartPreset && smartPreset !== 'zero_sellout_products') {
        params.set('smart_view', smartPreset);
      }
      return apiGet<LinesResponse>(`/api/v1/sellout/commercial-lines?${params.toString()}`, { signal });
    },
    enabled: smartPreset !== 'zero_sellout_products',
  });

  const { data: zeroProducts, isLoading: zeroLoading } = useQuery({
    queryKey: ['sellout-zero-products'],
    queryFn: ({ signal }) =>
      apiGet<{ items: ZeroProduct[] }>('/api/v1/sellout/zero-sellout-products?lookback_days=365&limit=80', { signal }),
    enabled: smartPreset === 'zero_sellout_products',
  });

  return (
    <>
      <PageHeader crumbs={[{ label: 'Sell-out' }]} title="Sell-out" />
      <Alert severity="info" sx={{ mb: 2 }}>
        Commercial view over <strong>fact_sales_sellout</strong> (populated when DSI import jobs are applied). Use{' '}
        <strong>Admin → Imports</strong> for distributor sales &amp; inventory loads.
      </Alert>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <Paper variant="outlined" sx={{ p: 2, flex: '1 1 200px' }}>
          <Typography variant="overline" color="text.secondary">
            Fact rows
          </Typography>
          <Typography variant="h5">{summary?.total_rows ?? '—'}</Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 2, flex: '1 1 200px' }}>
          <Typography variant="overline" color="text.secondary">
            Units (all time)
          </Typography>
          <Typography variant="h5">
            {summary != null ? summary.total_units.toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—'}
          </Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 2, flex: '1 1 200px' }}>
          <Typography variant="overline" color="text.secondary">
            Revenue (all time)
          </Typography>
          <Typography variant="h5">
            {summary != null ? summary.total_revenue.toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—'}
          </Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 2, flex: '1 1 200px' }}>
          <Typography variant="overline" color="text.secondary">
            Latest period
          </Typography>
          <Typography variant="h6">{summary?.latest_period_start ?? '—'}</Typography>
        </Paper>
      </Stack>

      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.5 }}>
        Smart views
      </Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }} alignItems="center">
        <Chip
          label="Fastest movers (by product)"
          size="small"
          variant={smartPreset === 'fastest_movers' ? 'filled' : 'outlined'}
          color={smartPreset === 'fastest_movers' ? 'primary' : 'default'}
          onClick={() => setSmartPreset(smartPreset === 'fastest_movers' ? '' : 'fastest_movers')}
        />
        <Chip
          label="Customers who increased volume"
          size="small"
          variant={smartPreset === 'customers_increased_volume' ? 'filled' : 'outlined'}
          color={smartPreset === 'customers_increased_volume' ? 'primary' : 'default'}
          onClick={() =>
            setSmartPreset(smartPreset === 'customers_increased_volume' ? '' : 'customers_increased_volume')
          }
        />
        <Chip
          label="Customers who dropped off"
          size="small"
          variant={smartPreset === 'customers_dropped_off' ? 'filled' : 'outlined'}
          color={smartPreset === 'customers_dropped_off' ? 'primary' : 'default'}
          onClick={() => setSmartPreset(smartPreset === 'customers_dropped_off' ? '' : 'customers_dropped_off')}
        />
        <Chip
          label="Products with zero sell-out"
          size="small"
          variant={smartPreset === 'zero_sellout_products' ? 'filled' : 'outlined'}
          color={smartPreset === 'zero_sellout_products' ? 'primary' : 'default'}
          onClick={() => setSmartPreset(smartPreset === 'zero_sellout_products' ? '' : 'zero_sellout_products')}
        />
      </Stack>

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          label="Search SKU / product / customer"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ minWidth: 260, flex: 1 }}
          disabled={smartPreset === 'zero_sellout_products'}
        />
        <Autocomplete
          sx={{ minWidth: 280, flex: 1 }}
          size="small"
          loading={!filterOptions}
          options={distOptions}
          value={distributorPick}
          onChange={(_e, v) => setDistributorPick(v)}
          disabled={smartPreset === 'zero_sellout_products'}
          getOptionLabel={(o) => `${o.distributor_name} (${o.distributor_code})`}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={(params) => (
            <TextField {...params} label="Distributor" placeholder="All distributors" />
          )}
        />
        <Autocomplete
          sx={{ minWidth: 260, flex: 1 }}
          size="small"
          loading={!filterOptions}
          options={custOptions}
          value={customerPick}
          onChange={(_e, v) => setCustomerPick(v)}
          disabled={smartPreset === 'zero_sellout_products'}
          getOptionLabel={(o) => `${o.customer_name} (${o.customer_code})`}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={(params) => (
            <TextField {...params} label="Customer" placeholder="All customers" />
          )}
        />
      </Stack>

      {smartPreset === 'zero_sellout_products' ? (
        <Paper variant="outlined">
          <Box sx={{ p: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              Active products with no sell-out in the last 365 days
            </Typography>
            {zeroLoading ? (
              <Typography variant="body2">Loading…</Typography>
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>SKU</TableCell>
                    <TableCell>Name</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(zeroProducts?.items ?? []).map((p) => (
                    <TableRow key={p.product_id}>
                      <TableCell>{p.sku}</TableCell>
                      <TableCell>{p.name}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Box>
        </Paper>
      ) : (
        <Paper variant="outlined">
          <Box sx={{ p: 2 }}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {lines != null ? `${lines.total.toLocaleString()} matching rows · showing ${lines.items.length}` : null}
            </Typography>
            {linesLoading ? (
              <Typography variant="body2">Loading…</Typography>
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Period</TableCell>
                    <TableCell>SKU</TableCell>
                    <TableCell>Customer</TableCell>
                    <TableCell>Distributor</TableCell>
                    <TableCell align="right">Units</TableCell>
                    <TableCell align="right">Revenue</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(lines?.items ?? []).map((r) => (
                    <TableRow key={r.id}>
                      <TableCell>{r.period_start}</TableCell>
                      <TableCell>{r.product_sku}</TableCell>
                      <TableCell>
                        {r.customer_name} ({r.customer_code})
                      </TableCell>
                      <TableCell>{r.distributor_code ?? '—'}</TableCell>
                      <TableCell align="right">{r.units.toLocaleString()}</TableCell>
                      <TableCell align="right">{r.revenue.toLocaleString()}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Box>
        </Paper>
      )}
    </>
  );
}
