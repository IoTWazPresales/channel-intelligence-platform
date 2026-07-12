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
  TableRow,
  TextField,
  Typography,
  Paper,
} from '@mui/material';
import type { ColDef, GridApi, GridOptions, ValueGetterParams } from 'ag-grid-community';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';

import { MasterDataGridShell } from '@/components/masterGrid/MasterDataGridShell';
import type { MasterColumnPickerGroup } from '@/components/masterGrid/MasterColumnPickerDialog';
import { ModuleDataSection } from '@/components/ModuleDataSection';
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
  id: string;
  date: string;
  distributor_name: string | null;
  customer_name: string | null;
  product_name: string | null;
  sku: string | null;
  business_unit?: string | null;
  product_line?: string | null;
  series_name?: string | null;
  sales_model_name?: string | null;
  category?: string | null;
  lifecycle_status?: string | null;
  units: number;
  unit_price: number | null;
  revenue: number;
  prior_period_units: number | null;
  specs_flat?: Record<string, string>;
  product_spec_cpu?: string | null;
  product_spec_gpu?: string | null;
  product_spec_ram?: string | null;
  product_spec_storage?: string | null;
  product_spec_generation?: string | null;
  product_spec_chassis?: string | null;
  product_spec_processor?: string | null;
  product_spec_display?: string | null;
  product_spec_os?: string | null;
  product_spec_colour?: string | null;
  product_spec_warranty?: string | null;
};

type LinesResponse = { total: number; skip: number; limit: number; items: SelloutLine[] };
type ChannelLinesResponse = {
  total: number;
  page: number;
  page_size: number;
  items: Omit<ChannelSelloutLine, 'id'>[];
  specs_field_keys?: string[];
};

type DistHit = { id: number; distributor_code: string; distributor_name: string };
type CustHit = { id: number; customer_code: string; customer_name: string };
type ZeroProduct = { product_id: number; sku: string; name: string };

const CHANNEL_PAGE_SIZE_OPTIONS = [25, 50, 100];
const CHANNEL_DEFAULT_PAGE_SIZE = 50;
/** v2: catalogue specs default-hidden; reset old layouts that forced specs visible. */
const SELLOUT_GRID_STATE_KEY = 'cip.channel-ops.sell-out.shell.grid.v2';

const COMMON_SPEC_FIELDS = [
  'product_spec_cpu',
  'product_spec_gpu',
  'product_spec_ram',
  'product_spec_storage',
  'product_spec_generation',
  'product_spec_chassis',
  'product_spec_processor',
  'product_spec_display',
  'product_spec_os',
  'product_spec_colour',
  'product_spec_warranty',
] as const;

const CATALOGUE_STATIC_FIELDS = [
  'product_name',
  'business_unit',
  'product_line',
  'series_name',
  'sales_model_name',
  'category',
  'lifecycle_status',
  'unit_price',
] as const;

const CHANNEL_COLUMN_GROUPS_BASE: MasterColumnPickerGroup[] = [
  {
    label: 'Core',
    fields: ['date', 'sku', 'customer_name', 'distributor_name', 'units', 'revenue'],
  },
  {
    label: 'Product catalogue',
    fields: [...CATALOGUE_STATIC_FIELDS],
  },
  {
    label: 'Common specs (named)',
    fields: [...COMMON_SPEC_FIELDS],
  },
  {
    label: 'Commercial',
    fields: ['prior_period_units', 'change_pct'],
  },
];

const CHANNEL_DEFAULT_HIDDEN_FIELDS = [
  ...CATALOGUE_STATIC_FIELDS,
  ...COMMON_SPEC_FIELDS,
] as const;

function specColIdFromRawKey(rawKey: string): string {
  const safe = rawKey.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 96);
  return `spec:${safe || 'key'}`;
}

const LEGACY_COLUMN_GROUPS: MasterColumnPickerGroup[] = [
  {
    id: 'core',
    label: 'Core',
    fields: ['period_start', 'product_sku', 'distributor_code', 'units', 'revenue'],
  },
];

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
  const [channelPage, setChannelPage] = useState(1);
  const [channelPageSize, setChannelPageSize] = useState(CHANNEL_DEFAULT_PAGE_SIZE);
  const [accumulatedSpecKeys, setAccumulatedSpecKeys] = useState<string[]>([]);
  const prevAccumulatedSpecKeysRef = useRef<string[]>([]);
  const [gridApi, setGridApi] = useState<GridApi<ChannelSelloutLine> | null>(null);
  const useChannelApi = depthAtLeast(depth, 'operational');

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
    setChannelPage(1);
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
          page: String(channelPage),
          page_size: String(channelPageSize),
        });
        if (distributorPick != null) params.set('distributor_id', String(distributorPick.id));
        if (customerPick != null) params.set('customer_id', String(customerPick.id));
        if (periodFrom) params.set('date_from', periodFrom);
        if (businessUnit) params.set('business_unit', businessUnit);
        if (specSearch.trim()) params.set('spec_search', specSearch.trim());
        const res = await apiGet<ChannelLinesResponse>(`/api/v1/channel-ops/sell-out?${params}`, { signal });
        let items = res.items.map((r, i) => ({
          ...r,
          id: `${r.date}|${r.sku}|${r.customer_name}|${i}`,
        }));
        if (smartPreset === 'slowest_movers') {
          items = [...items].sort((a, b) => a.units - b.units);
        } else if (smartPreset === 'fastest_movers') {
          items = [...items].sort((a, b) => b.units - a.units);
        }
        return {
          total: res.total,
          skip: 0,
          limit: res.page_size,
          items,
          channel: true as const,
          specs_field_keys: res.specs_field_keys ?? [],
        };
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

  const channelColumnGroups = useMemo<MasterColumnPickerGroup[]>(() => {
    if (!depthAtLeast(depth, 'operational')) {
      return CHANNEL_COLUMN_GROUPS_BASE.map((g) =>
        g.label === 'Commercial'
          ? { ...g, fields: g.fields.filter((f) => f !== 'change_pct' && f !== 'prior_period_units') }
          : g,
      ).filter((g) => g.fields.length > 0);
    }
    return CHANNEL_COLUMN_GROUPS_BASE;
  }, [depth]);

  const specsFieldKeysSig = useMemo(() => {
    const fromApi =
      linesQ.data && 'specs_field_keys' in linesQ.data && linesQ.data.channel
        ? (linesQ.data.specs_field_keys ?? [])
        : [];
    const fromRows =
      linesQ.data?.channel
        ? (linesQ.data.items as ChannelSelloutLine[]).flatMap((r) => Object.keys(r.specs_flat ?? {}))
        : [];
    const keys = new Set([...fromApi, ...fromRows]);
    return JSON.stringify([...keys].filter(Boolean).sort((a, b) => a.localeCompare(b)));
  }, [linesQ.data]);

  useEffect(() => {
    if (!specsFieldKeysSig) return;
    let incoming: string[] = [];
    try {
      incoming = JSON.parse(specsFieldKeysSig) as string[];
    } catch {
      return;
    }
    if (!incoming.length) return;
    setAccumulatedSpecKeys((prev) => {
      const s = new Set(prev);
      for (const k of incoming) {
        if (k) s.add(k);
      }
      const next = [...s].sort((a, b) => a.localeCompare(b));
      if (next.length === prev.length && next.every((k, i) => k === prev[i])) return prev;
      return next;
    });
  }, [specsFieldKeysSig]);

  useEffect(() => {
    if (!gridApi || !accumulatedSpecKeys.length) return;
    const prev = new Set(prevAccumulatedSpecKeysRef.current);
    const added = accumulatedSpecKeys.filter((k) => !prev.has(k));
    prevAccumulatedSpecKeysRef.current = accumulatedSpecKeys;
    if (!added.length) return;
    const ids = added.map((k) => specColIdFromRawKey(k));
    try {
      gridApi.setColumnsVisible(ids, false);
    } catch {
      // no-op
    }
  }, [accumulatedSpecKeys, gridApi]);

  const columnPickerExtraGroups = useMemo<MasterColumnPickerGroup[] | undefined>(() => {
    if (!accumulatedSpecKeys.length) return undefined;
    return [
      {
        label: 'Catalogue specs (flattened; grows as you page)',
        fields: accumulatedSpecKeys.map(specColIdFromRawKey),
      },
    ];
  }, [accumulatedSpecKeys]);

  const columnLabelByField = useMemo(() => {
    const out: Record<string, string> = {
      product_name: 'Product name',
      business_unit: 'Business unit',
      product_line: 'Product line',
      series_name: 'Series',
      sales_model_name: 'Sales model',
      category: 'Category',
      lifecycle_status: 'Lifecycle',
      unit_price: 'Unit price',
      product_spec_cpu: 'CPU',
      product_spec_gpu: 'GPU',
      product_spec_ram: 'RAM',
      product_spec_storage: 'Storage',
      product_spec_generation: 'Generation',
      product_spec_chassis: 'Chassis',
      product_spec_processor: 'Processor',
      product_spec_display: 'Display',
      product_spec_os: 'OS',
      product_spec_colour: 'Colour',
      product_spec_warranty: 'Warranty',
    };
    for (const rawKey of accumulatedSpecKeys) {
      out[specColIdFromRawKey(rawKey)] = `Spec: ${rawKey}`;
    }
    return out;
  }, [accumulatedSpecKeys]);

  const channelCols = useMemo<ColDef<ChannelSelloutLine>[]>(() => {
    const cols: ColDef<ChannelSelloutLine>[] = [
      { field: 'date', headerName: 'Date', width: 110 },
      { field: 'sku', headerName: 'SKU', width: 120 },
      { field: 'product_name', headerName: 'Product', flex: 1, minWidth: 140, hide: true },
      { field: 'customer_name', headerName: 'Customer', flex: 1, minWidth: 140 },
      { field: 'distributor_name', headerName: 'Distributor', width: 140 },
      { field: 'business_unit', headerName: 'Business unit', width: 120, hide: true },
      { field: 'product_line', headerName: 'Product line', width: 120, hide: true },
      { field: 'series_name', headerName: 'Series', width: 120, hide: true },
      { field: 'sales_model_name', headerName: 'Sales model', width: 140, hide: true },
      { field: 'category', headerName: 'Category', width: 120, hide: true },
      { field: 'lifecycle_status', headerName: 'Lifecycle', width: 110, hide: true },
      ...COMMON_SPEC_FIELDS.map(
        (field) =>
          ({
            field,
            headerName: columnLabelByField[field] ?? field,
            width: 110,
            hide: true,
          }) satisfies ColDef<ChannelSelloutLine>,
      ),
      {
        field: 'units',
        headerName: 'Units',
        width: 100,
        type: 'numericColumn',
        valueFormatter: (p) => Number(p.value ?? 0).toLocaleString(),
      },
      {
        field: 'unit_price',
        headerName: 'Unit price',
        width: 110,
        type: 'numericColumn',
        hide: true,
        valueFormatter: (p) => (p.value == null ? '—' : Number(p.value).toLocaleString()),
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
          field: 'change_pct',
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
    for (const rawKey of accumulatedSpecKeys) {
      const colId = specColIdFromRawKey(rawKey);
      cols.push({
        colId,
        field: colId,
        headerName: `Spec: ${rawKey}`,
        width: 130,
        hide: true,
        valueGetter: (p) => p.data?.specs_flat?.[rawKey] ?? '',
      });
    }
    return cols;
  }, [depth, accumulatedSpecKeys, columnLabelByField]);

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
      getRowId: (p) => String(p.data.id),
      defaultColDef: { resizable: true, sortable: true },
    }),
    [],
  );

  const legacyGridOptions = useMemo<GridOptions<SelloutLine>>(
    () => ({
      pagination: false,
      suppressPaginationPanel: true,
      getRowId: (p) => String(p.data.id),
      defaultColDef: { resizable: true, sortable: true },
    }),
    [],
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
      ) : lines?.channel ? (
        <MasterDataGridShell
          entityKey="channel-ops-sell-out"
          rows={channelItems}
          columnDefs={channelCols}
          total={lines.total}
          isLoading={linesQ.isLoading}
          isError={linesQ.isError}
          error={(linesQ.error as Error) ?? null}
          onRetry={() => void linesQ.refetch()}
          empty={{
            title: 'No sell-out rows',
            description: 'No sell-out rows match the current filters.',
          }}
          url={{
            page: channelPage,
            pageSize: channelPageSize,
            q: '',
            sortBy: 'date',
            sortDir: 'desc',
          }}
          onUrlChange={(patch, resetPage) => {
            if (patch.page_size != null) {
              setChannelPageSize(Number(patch.page_size) || CHANNEL_DEFAULT_PAGE_SIZE);
              setChannelPage(1);
              return;
            }
            if (resetPage) setChannelPage(1);
            if (patch.page != null) setChannelPage(Math.max(1, Number(patch.page) || 1));
          }}
          defaultPageSize={CHANNEL_DEFAULT_PAGE_SIZE}
          defaultSortBy="date"
          defaultSortDir="desc"
          pageSizeOptions={[...CHANNEL_PAGE_SIZE_OPTIONS]}
          enableEmptyUrlSeed={false}
          gridStateStorageKey={SELLOUT_GRID_STATE_KEY}
          defaultInitiallyHiddenFields={[...CHANNEL_DEFAULT_HIDDEN_FIELDS]}
          columnPickerTitle="Sell-out columns"
          columnPickerGroups={channelColumnGroups}
          columnPickerExtraGroups={columnPickerExtraGroups}
          columnLabelByField={columnLabelByField}
          gridOptions={channelGridOptions}
          bulkSelectionEnabled={false}
          onGridApiChange={setGridApi}
          onRefresh={() => void linesQ.refetch()}
          refreshBusy={linesQ.isFetching}
        />
      ) : (
        <MasterDataGridShell
          entityKey="channel-ops-sell-out-legacy"
          rows={legacyItems}
          columnDefs={legacyCols}
          total={lines?.total ?? legacyItems.length}
          isLoading={linesQ.isLoading}
          isError={linesQ.isError}
          error={(linesQ.error as Error) ?? null}
          onRetry={() => void linesQ.refetch()}
          empty={{
            title: 'No sell-out rows',
            description: 'No sell-out rows match the current filters.',
          }}
          url={{ page: 1, pageSize: 50, q: search, sortBy: 'period_start', sortDir: 'desc' }}
          onUrlChange={() => undefined}
          defaultPageSize={50}
          defaultSortBy="period_start"
          defaultSortDir="desc"
          enableEmptyUrlSeed={false}
          gridStateStorageKey={`${SELLOUT_GRID_STATE_KEY}.legacy`}
          columnPickerTitle="Sell-out columns (raw)"
          columnPickerGroups={LEGACY_COLUMN_GROUPS}
          gridOptions={legacyGridOptions}
          bulkSelectionEnabled={false}
          onRefresh={() => void linesQ.refetch()}
          refreshBusy={linesQ.isFetching}
        />
      )}
    </>
  );
}
