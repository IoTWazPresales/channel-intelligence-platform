'use client';

import {
  Alert,
  Autocomplete,
  Box,
  Chip,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { useLineIdentifierPreference } from '@/features/tenant/useLineIdentifierPreference';
import { apiGet } from '@/lib/api';

import { depthAtLeast, type IntelDepth } from './intelDepth';

type SmartPresetId = '' | 'fastest_movers' | 'slowest_movers' | 'new_this_period' | 'zero_sellout_products';

type SelloutSummary = {
  total_rows: number;
  total_units: number;
  total_revenue: number;
  latest_period_start: string | null;
};

type SelloutLine = {
  id: number;
  product_sku: string | null;
  product_sales_model_name: string | null;
  product_name: string | null;
  customer_code: string | null;
  customer_name: string | null;
  distributor_code: string | null;
  period_start: string;
  units: number;
  revenue: number;
  currency_code: string | null;
};

type ChannelSelloutLine = {
  date: string;
  distributor_name: string | null;
  customer_name: string | null;
  product_name: string | null;
  sku: string | null;
  sales_model_name: string | null;
  units: number;
  unit_price: number | null;
  revenue: number;
  prior_period_units: number | null;
};

type LinesResponse = { total: number; skip: number; limit: number; items: SelloutLine[] };
type ChannelLinesResponse = { total: number; page: number; page_size: number; items: ChannelSelloutLine[] };

type DistHit = { id: number; distributor_code: string; distributor_name: string };
type CustHit = { id: number; customer_code: string; customer_name: string };
type ZeroProduct = { product_id: number; sku: string; sales_model_name: string | null; name: string };

export function SellOutTab({ depth }: { depth: IntelDepth }) {
  const lineId = useLineIdentifierPreference();
  const [smartPreset, setSmartPreset] = useState<SmartPresetId>('');
  const [distributorPick, setDistributorPick] = useState<DistHit | null>(null);
  const [customerPick, setCustomerPick] = useState<CustHit | null>(null);
  const [search, setSearch] = useState('');
  const useChannelApi = depthAtLeast(depth, 'operational');

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

  const periodFrom = useMemo(() => {
    if (smartPreset !== 'new_this_period') return undefined;
    const d = new Date();
    d.setDate(d.getDate() - 90);
    return d.toISOString().slice(0, 10);
  }, [smartPreset]);

  const linesQueryKey = useMemo(
    () =>
      [
        useChannelApi ? 'channel-ops-sell-out' : 'sellout-commercial-lines',
        smartPreset,
        distributorPick?.id ?? null,
        customerPick?.id ?? null,
        search,
        periodFrom,
      ] as const,
    [useChannelApi, smartPreset, distributorPick?.id, customerPick?.id, search, periodFrom]
  );

  const { data: lines, isLoading: linesLoading, isError: linesError, error: linesErr } = useQuery({
    queryKey: linesQueryKey,
    queryFn: async ({ signal }) => {
      if (useChannelApi) {
        const params = new URLSearchParams({ page: '1', page_size: '50' });
        if (distributorPick != null) params.set('distributor_id', String(distributorPick.id));
        if (customerPick != null) params.set('customer_id', String(customerPick.id));
        if (periodFrom) params.set('date_from', periodFrom);
        const res = await apiGet<ChannelLinesResponse>(`/api/v1/channel-ops/sell-out?${params}`, { signal });
        let items = res.items;
        if (smartPreset === 'slowest_movers') {
          items = [...items].sort((a, b) => a.units - b.units);
        } else if (smartPreset === 'fastest_movers') {
          items = [...items].sort((a, b) => b.units - a.units);
        }
        return { total: res.total, skip: 0, limit: res.page_size, items, channel: true as const };
      }
      const params = new URLSearchParams();
      params.set('limit', '50');
      if (distributorPick != null) params.set('distributor_id', String(distributorPick.id));
      if (customerPick != null) params.set('customer_id', String(customerPick.id));
      if (search.trim()) params.set('product_search', search.trim());
      if (periodFrom) params.set('period_from', periodFrom);
      if (smartPreset && smartPreset !== 'zero_sellout_products' && smartPreset !== 'slowest_movers') {
        if (smartPreset === 'fastest_movers') params.set('smart_view', 'fastest_movers');
        if (smartPreset === 'new_this_period') params.set('smart_view', 'customers_increased_volume');
      }
      const res = await apiGet<LinesResponse>(`/api/v1/sellout/commercial-lines?${params}`, { signal });
      let items = res.items;
      if (smartPreset === 'slowest_movers') {
        items = [...items].sort((a, b) => a.units - b.units);
      }
      return { ...res, channel: false as const };
    },
    enabled: smartPreset !== 'zero_sellout_products',
  });

  const { data: zeroProducts, isLoading: zeroLoading } = useQuery({
    queryKey: ['sellout-zero-products'],
    queryFn: ({ signal }) =>
      apiGet<{ items: ZeroProduct[] }>('/api/v1/sellout/zero-sellout-products?lookback_days=365&limit=80', { signal }),
    enabled: smartPreset === 'zero_sellout_products',
  });

  const operational = depthAtLeast(depth, 'operational');
  const zeroCols = useMemo<ColDef<ZeroProduct>[]>(
    () => [
      {
        colId: 'line_identifier',
        headerName: lineId.header,
        minWidth: 120,
        valueGetter: (p) => lineId.value(p.data?.sku, p.data?.sales_model_name),
      },
      { field: 'name', headerName: 'Name', flex: 1, minWidth: 180 },
    ],
    [lineId],
  );
  const channelCols = useMemo<ColDef<ChannelSelloutLine>[]>(() => {
    const cols: ColDef<ChannelSelloutLine>[] = [
      { field: 'date', headerName: 'Date', minWidth: 110 },
      {
        colId: 'line_identifier',
        headerName: lineId.header,
        minWidth: 110,
        valueGetter: (p) => lineId.value(p.data?.sku, p.data?.sales_model_name),
      },
      { field: 'customer_name', headerName: 'Customer', flex: 1, minWidth: 140 },
      { field: 'distributor_name', headerName: 'Distributor', minWidth: 140, valueFormatter: (p) => p.value ?? '—' },
      {
        field: 'units',
        headerName: 'Units',
        type: 'numericColumn',
        minWidth: 90,
        valueFormatter: (p) => Number(p.value ?? 0).toLocaleString(),
      },
      {
        field: 'revenue',
        headerName: 'Revenue',
        type: 'numericColumn',
        minWidth: 110,
        valueFormatter: (p) => Number(p.value ?? 0).toLocaleString(),
      },
    ];
    if (operational) {
      cols.push(
        {
          field: 'prior_period_units',
          headerName: 'Prior period qty',
          type: 'numericColumn',
          minWidth: 130,
          valueFormatter: (p) => (p.value != null ? Number(p.value).toLocaleString() : '—'),
        },
        {
          headerName: 'Change %',
          type: 'numericColumn',
          minWidth: 100,
          valueGetter: (p) => {
            const cur = p.data?.units;
            const prior = p.data?.prior_period_units;
            if (cur == null || prior == null || prior <= 0) return null;
            return ((cur - prior) / prior) * 100;
          },
          valueFormatter: (p) => (p.value != null ? `${Number(p.value).toFixed(1)}%` : '—'),
        },
      );
    }
    return cols;
  }, [operational, lineId]);
  const factCols = useMemo<ColDef<SelloutLine>[]>(
    () => [
      { field: 'period_start', headerName: 'Period', minWidth: 110 },
      {
        colId: 'line_identifier',
        headerName: lineId.header,
        minWidth: 110,
        valueGetter: (p) => lineId.value(p.data?.product_sku, p.data?.product_sales_model_name),
      },
      {
        headerName: 'Customer',
        flex: 1,
        minWidth: 160,
        valueGetter: (p) =>
          p.data ? `${p.data.customer_name ?? ''} (${p.data.customer_code ?? ''})` : '—',
      },
      { field: 'distributor_code', headerName: 'Distributor', minWidth: 130, valueFormatter: (p) => p.value ?? '—' },
      {
        field: 'units',
        headerName: 'Units',
        type: 'numericColumn',
        minWidth: 90,
        valueFormatter: (p) => Number(p.value ?? 0).toLocaleString(),
      },
      {
        field: 'revenue',
        headerName: 'Revenue',
        type: 'numericColumn',
        minWidth: 110,
        valueFormatter: (p) => Number(p.value ?? 0).toLocaleString(),
      },
    ],
    [lineId],
  );

  return (
    <>
      <Alert severity="info" sx={{ mb: 2 }}>
        Commercial view over <strong>fact_sales_sellout</strong> (populated when DSI import jobs are applied). Use{' '}
        <strong>Data & Stewardship → Import Center</strong> for distributor sales &amp; inventory loads.
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
        {(
          [
            ['', 'All'],
            ['fastest_movers', 'Fastest movers'],
            ['slowest_movers', 'Slowest movers'],
            ['new_this_period', 'New this period'],
          ] as const
        ).map(([id, label]) => (
          <Chip
            key={id || 'all'}
            label={label}
            size="small"
            variant={smartPreset === id ? 'filled' : 'outlined'}
            color={smartPreset === id ? 'primary' : 'default'}
            onClick={() => setSmartPreset(id)}
          />
        ))}
      </Stack>

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          label="Search SKU / product / customer"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ minWidth: 260, flex: 1 }}
          disabled={smartPreset === 'zero_sellout_products' || useChannelApi}
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
          renderInput={(params) => <TextField {...params} label="Distributor" placeholder="All distributors" />}
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
          renderInput={(params) => <TextField {...params} label="Customer" placeholder="All customers" />}
        />
      </Stack>

      {smartPreset === 'zero_sellout_products' ? (
        <Paper variant="outlined">
          <Box sx={{ p: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              Active products with no sell-out in the last 365 days
            </Typography>
            <ModuleDataSection
              isLoading={zeroLoading}
              isEmpty={(zeroProducts?.items ?? []).length === 0}
              empty={{
                title: 'No zero-sell-out products',
                description: 'Every active product has at least one sell-out row in the lookback window.',
              }}
            >
              <EnterpriseDataGrid rowData={zeroProducts?.items ?? []} columnDefs={zeroCols} height={360} />
            </ModuleDataSection>
          </Box>
        </Paper>
      ) : (
        <Paper variant="outlined">
          <Box sx={{ p: 2 }}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {lines != null
                ? `${lines.total.toLocaleString()} matching rows · showing ${lines.items.length}`
                : null}
            </Typography>
            <ModuleDataSection
              isLoading={linesLoading}
              isError={Boolean(linesError)}
              error={linesError ? new Error((linesErr as Error)?.message ?? 'Failed to load sell-out lines.') : null}
              isEmpty={(lines?.items ?? []).length === 0}
              empty={{
                title: 'No sell-out rows match',
                description: 'Adjust the filters above, or import distributor sell-out via the Import Center.',
                primary: { label: 'Import Center', href: '/admin/imports?template=distributor_inventory' },
              }}
            >
              {lines?.channel ? (
                <EnterpriseDataGrid
                  rowData={lines.items as ChannelSelloutLine[]}
                  columnDefs={channelCols}
                  height={420}
                />
              ) : (
                <EnterpriseDataGrid
                  rowData={(lines?.items ?? []) as SelloutLine[]}
                  columnDefs={factCols}
                  height={420}
                />
              )}
            </ModuleDataSection>
          </Box>
        </Paper>
      )}
    </>
  );
}
