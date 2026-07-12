'use client';

import {
  Alert,
  Autocomplete,
  Chip,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
  Paper,
} from '@mui/material';
import type { ColDef, GridOptions, ValueGetterParams } from 'ag-grid-community';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { gridRowMetrics, paginatedGridHeight } from '@/features/plan-vs-executed/gridPagination';
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
  business_unit?: string | null;
  units: number;
  unit_price: number | null;
  revenue: number;
  prior_period_units: number | null;
  product_spec_cpu?: string | null;
  product_spec_gpu?: string | null;
  product_spec_ram?: string | null;
  product_spec_storage?: string | null;
  product_spec_generation?: string | null;
  product_spec_chassis?: string | null;
};

type LinesResponse = { total: number; skip: number; limit: number; items: SelloutLine[] };
type ChannelLinesResponse = { total: number; page: number; page_size: number; items: ChannelSelloutLine[] };

type DistHit = { id: number; distributor_code: string; distributor_name: string };
type CustHit = { id: number; customer_code: string; customer_name: string };
type ZeroProduct = { product_id: number; sku: string; name: string };

const CHANNEL_PAGE_SIZE_OPTIONS = [25, 50, 100] as const;
const CHANNEL_DEFAULT_PAGE_SIZE = 50;

export function SellOutTab({
  depth,
  distributorId,
  businessUnit,
}: {
  depth: IntelDepth;
  distributorId?: number | null;
  businessUnit?: string | null;
}) {
  const [smartPreset, setSmartPreset] = useState<SmartPresetId>('');
  const [distributorPick, setDistributorPick] = useState<DistHit | null>(null);
  const [customerPick, setCustomerPick] = useState<CustHit | null>(null);
  const [search, setSearch] = useState('');
  const [specSearch, setSpecSearch] = useState('');
  const [channelPage, setChannelPage] = useState(0);
  const [channelPageSize, setChannelPageSize] = useState(CHANNEL_DEFAULT_PAGE_SIZE);
  const useChannelApi = depthAtLeast(depth, 'operational');
  const { rowHeight, headerHeight } = gridRowMetrics('comfortable');

  const summaryQ = useQuery({
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

  useEffect(() => {
    if (distributorId == null) {
      setDistributorPick(null);
      return;
    }
    const hit = distOptions.find((d) => d.id === distributorId) ?? null;
    setDistributorPick(hit);
  }, [distributorId, distOptions]);

  const periodFrom = useMemo(() => {
    if (smartPreset !== 'new_this_period') return undefined;
    const d = new Date();
    d.setDate(d.getDate() - 90);
    return d.toISOString().slice(0, 10);
  }, [smartPreset]);

  useEffect(() => {
    setChannelPage(0);
  }, [
    smartPreset,
    distributorPick?.id,
    customerPick?.id,
    periodFrom,
    useChannelApi,
    businessUnit,
    specSearch,
  ]);

  const linesQueryKey = useMemo(
    () =>
      [
        useChannelApi ? 'channel-ops-sell-out' : 'sellout-commercial-lines',
        smartPreset,
        distributorPick?.id ?? null,
        customerPick?.id ?? null,
        search,
        periodFrom,
        businessUnit ?? null,
        specSearch,
        useChannelApi ? channelPage : null,
        useChannelApi ? channelPageSize : null,
      ] as const,
    [
      useChannelApi,
      smartPreset,
      distributorPick?.id,
      customerPick?.id,
      search,
      periodFrom,
      businessUnit,
      specSearch,
      channelPage,
      channelPageSize,
    ],
  );

  const linesQ = useQuery({
    queryKey: linesQueryKey,
    queryFn: async ({ signal }) => {
      if (useChannelApi) {
        const params = new URLSearchParams({
          page: String(channelPage + 1),
          page_size: String(channelPageSize),
        });
        if (distributorPick != null) params.set('distributor_id', String(distributorPick.id));
        if (customerPick != null) params.set('customer_id', String(customerPick.id));
        if (periodFrom) params.set('date_from', periodFrom);
        if (businessUnit) params.set('business_unit', businessUnit);
        if (specSearch.trim()) params.set('spec_search', specSearch.trim());
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

  const zeroQ = useQuery({
    queryKey: ['sellout-zero-products'],
    queryFn: ({ signal }) =>
      apiGet<{ items: ZeroProduct[] }>('/api/v1/sellout/zero-sellout-products?lookback_days=365&limit=80', {
        signal,
      }),
    enabled: smartPreset === 'zero_sellout_products',
  });

  const channelCols = useMemo<ColDef<ChannelSelloutLine>[]>(() => {
    const cols: ColDef<ChannelSelloutLine>[] = [
      { field: 'date', headerName: 'Date', width: 110 },
      { field: 'sku', headerName: 'SKU', width: 120 },
      { field: 'customer_name', headerName: 'Customer', flex: 1, minWidth: 140 },
      { field: 'distributor_name', headerName: 'Distributor', width: 140 },
      { field: 'product_spec_cpu', headerName: 'CPU', width: 100 },
      { field: 'product_spec_gpu', headerName: 'GPU', width: 100 },
      { field: 'product_spec_ram', headerName: 'RAM', width: 90 },
      { field: 'product_spec_storage', headerName: 'Storage', width: 100 },
      { field: 'product_spec_generation', headerName: 'Gen', width: 90 },
      { field: 'product_spec_chassis', headerName: 'Chassis', width: 100 },
      {
        field: 'units',
        headerName: 'Units',
        width: 100,
        type: 'numericColumn',
        valueFormatter: (p) => Number(p.value ?? 0).toLocaleString(),
      },
      {
        field: 'revenue',
        headerName: 'Revenue',
        width: 110,
        type: 'numericColumn',
        valueFormatter: (p) => Number(p.value ?? 0).toLocaleString(),
      },
    ];
    if (depthAtLeast(depth, 'operational')) {
      cols.push(
        {
          field: 'prior_period_units',
          headerName: 'Prior period qty',
          width: 130,
          type: 'numericColumn',
          valueFormatter: (p) =>
            p.value == null ? '—' : Number(p.value).toLocaleString(),
        },
        {
          colId: 'change_pct',
          headerName: 'Change %',
          width: 110,
          type: 'numericColumn',
          valueGetter: (p: ValueGetterParams<ChannelSelloutLine>) => {
            const row = p.data;
            if (!row || row.prior_period_units == null || row.prior_period_units <= 0) return null;
            return ((row.units - row.prior_period_units) / row.prior_period_units) * 100;
          },
          valueFormatter: (p) => (p.value == null ? '—' : `${Number(p.value).toFixed(1)}%`),
        },
      );
    }
    return cols;
  }, [depth]);

  const legacyCols = useMemo<ColDef<SelloutLine>[]>(
    () => [
      { field: 'period_start', headerName: 'Period', width: 110 },
      { field: 'product_sku', headerName: 'SKU', width: 120 },
      {
        colId: 'customer',
        headerName: 'Customer',
        flex: 1,
        minWidth: 160,
        valueGetter: (p) =>
          p.data ? `${p.data.customer_name ?? ''} (${p.data.customer_code ?? ''})` : '',
      },
      { field: 'distributor_code', headerName: 'Distributor', width: 120 },
      {
        field: 'units',
        headerName: 'Units',
        width: 100,
        type: 'numericColumn',
        valueFormatter: (p) => Number(p.value ?? 0).toLocaleString(),
      },
      {
        field: 'revenue',
        headerName: 'Revenue',
        width: 110,
        type: 'numericColumn',
        valueFormatter: (p) => Number(p.value ?? 0).toLocaleString(),
      },
    ],
    [],
  );

  const channelGridOptions = useMemo<GridOptions<ChannelSelloutLine>>(
    () => ({
      pagination: false,
      suppressPaginationPanel: true,
      getRowId: (p) => `${p.data.date}|${p.data.sku}|${p.data.customer_name}|${p.rowIndex}`,
      rowHeight,
      headerHeight,
      defaultColDef: { resizable: true, sortable: true },
    }),
    [rowHeight, headerHeight],
  );

  const legacyGridOptions = useMemo<GridOptions<SelloutLine>>(
    () => ({
      pagination: false,
      suppressPaginationPanel: true,
      getRowId: (p) => String(p.data.id),
      rowHeight,
      headerHeight,
      defaultColDef: { resizable: true, sortable: true },
    }),
    [rowHeight, headerHeight],
  );

  const summary = summaryQ.data;
  const lines = linesQ.data;
  const channelItems = lines?.channel ? (lines.items as ChannelSelloutLine[]) : [];
  const legacyItems = lines && !lines.channel ? (lines.items as SelloutLine[]) : [];

  return (
    <>
      <Alert severity="info" sx={{ mb: 2 }}>
        Commercial view over <strong>fact_sales_sellout</strong> (populated when DSI import jobs are applied). Use{' '}
        <strong>Admin → Imports</strong> for distributor sales &amp; inventory loads. Product specs come from{' '}
        <code>dim_product.specs_json</code>.
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
          disabled={smartPreset === 'zero_sellout_products' || distributorId != null}
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

      {useChannelApi && smartPreset !== 'zero_sellout_products' ? (
        <TextField
          size="small"
          label="Spec search (contains)"
          value={specSearch}
          onChange={(e) => setSpecSearch(e.target.value)}
          placeholder="e.g. i7, 16GB, OLED"
          sx={{ minWidth: 240, mb: 2 }}
          helperText="Matches anywhere in product specs_json — not per-key filters yet"
        />
      ) : null}

      {smartPreset === 'zero_sellout_products' ? (
        <ModuleDataSection
          isLoading={zeroQ.isLoading}
          isError={zeroQ.isError}
          error={(zeroQ.error as Error) ?? null}
          onRetry={() => void zeroQ.refetch()}
          isEmpty={(zeroQ.data?.items ?? []).length === 0}
          empty={{
            title: 'No zero-sell-out products',
            description: 'No zero-sell-out products in lookback window.',
          }}
        >
          <Typography variant="subtitle2" gutterBottom>
            Active products with no sell-out in the last 365 days
          </Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>SKU</TableCell>
                <TableCell>Name</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(zeroQ.data?.items ?? []).map((p) => (
                <TableRow key={p.product_id}>
                  <TableCell>{p.sku}</TableCell>
                  <TableCell>{p.name}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ModuleDataSection>
      ) : (
        <>
          <ModuleGridToolbar onRefresh={() => void linesQ.refetch()} busy={linesQ.isFetching} />
          <ModuleDataSection
            isLoading={linesQ.isLoading}
            isError={linesQ.isError}
            error={(linesQ.error as Error) ?? null}
            onRetry={() => void linesQ.refetch()}
            isEmpty={(lines?.items ?? []).length === 0}
            empty={{
              title: 'No sell-out rows',
              description: 'No sell-out rows match the current filters.',
            }}
          >
            {lines?.channel ? (
              <>
                <EnterpriseDataGrid
                  rowData={channelItems}
                  columnDefs={channelCols}
                  height={paginatedGridHeight(
                    Math.min(channelPageSize, Math.max(channelItems.length, 1)),
                    { rowHeight, headerHeight },
                  )}
                  gridOptions={channelGridOptions}
                />
                <TablePagination
                  component="div"
                  count={lines.total}
                  page={channelPage}
                  onPageChange={(_e, nextPage) => setChannelPage(nextPage)}
                  rowsPerPage={channelPageSize}
                  onRowsPerPageChange={(e) => {
                    setChannelPageSize(Number(e.target.value));
                    setChannelPage(0);
                  }}
                  rowsPerPageOptions={[...CHANNEL_PAGE_SIZE_OPTIONS]}
                  labelDisplayedRows={({ from, to, count }) =>
                    `${from}–${to} of ${count !== -1 ? count.toLocaleString() : `more than ${to}`}`
                  }
                />
              </>
            ) : (
              <EnterpriseDataGrid
                rowData={legacyItems}
                columnDefs={legacyCols}
                height={paginatedGridHeight(Math.max(legacyItems.length, 1), {
                  rowHeight,
                  headerHeight,
                })}
                gridOptions={legacyGridOptions}
              />
            )}
          </ModuleDataSection>
        </>
      )}
    </>
  );
}
