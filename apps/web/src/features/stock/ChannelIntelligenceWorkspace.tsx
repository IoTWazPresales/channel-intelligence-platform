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
import { useSearchParams } from 'next/navigation';
import { useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { FactColumnPicker, FactColumnsButton } from '@/features/workbench-ui/FactColumnPicker';
import { factGridLayout, useFactGridChrome } from '@/features/workbench-ui/gridFind';
import { ScopeBar } from '@/features/workbench-ui/controls';
import { useFactColumns } from '@/features/workbench-ui/useFactColumns';
import { apiGet } from '@/lib/api';

type CustomerPick = { id: number; customer_code: string; customer_name: string };
type ProductPick = { id: number; sku: string; name: string; sales_model_name?: string | null };

type IntelRow = {
  customer_id: number;
  product_id: number;
  customer_code?: string | null;
  customer_name?: string | null;
  product_sku?: string | null;
  product_name?: string | null;
  sales_model_name?: string | null;
  site_label: string | null;
  last_period?: string | null;
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
  as_of?: string;
  grain_policy: string;
  message?: string;
  thresholds?: Record<string, unknown>;
};

/** Name only (D7): the customer code is not welded into the name cell. */
function customerLabel(row: Pick<IntelRow, 'customer_id' | 'customer_name'>): string {
  return row.customer_name || `Customer ${row.customer_id}`;
}

function productLabel(row: Pick<IntelRow, 'product_id' | 'product_sku' | 'product_name' | 'sales_model_name'>): string {
  const name = row.sales_model_name || row.product_name;
  if (name) {
    return row.product_sku ? `${name} (${row.product_sku})` : name;
  }
  return `Product ${row.product_id}`;
}

export function ChannelIntelligenceWorkspace() {
  const [customer, setCustomer] = useState<CustomerPick | null>(null);
  // Links from the Sell-through tab carry ?customer_id=; cleared once a customer is picked here.
  const search = useSearchParams();
  const [linkedCustomerId, setLinkedCustomerId] = useState<string | null>(() => search.get('customer_id'));
  const [product, setProduct] = useState<ProductPick | null>(null);
  const [site, setSite] = useState('');
  const [selected, setSelected] = useState<IntelRow | null>(null);
  const factColumns = useFactColumns<IntelRow>('channel-intelligence');
  const gridChrome = useFactGridChrome('channel-intelligence', { layout: factGridLayout(factColumns) });

  const params = new URLSearchParams();
  if (customer) params.set('customer_id', String(customer.id));
  else if (linkedCustomerId) params.set('customer_id', linkedCustomerId);
  if (product) params.set('product_id', String(product.id));
  if (site.trim()) params.set('site_label', site.trim());
  params.set('page_size', '500');

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['channel-intelligence', customer?.id ?? linkedCustomerId ?? '', product?.id ?? '', site],
    queryFn: ({ signal }) =>
      apiGet<IntelResponse>(`/api/v1/channel-intelligence?${params.toString()}`, { signal }),
  });

  const fetchCustomers = useCallback(async (query: string, signal: AbortSignal) => {
    const q = query.trim();
    const res = await apiGet<{ items: CustomerPick[] }>(
      `/api/v1/customers?page=1&page_size=25${q ? `&q=${encodeURIComponent(q)}` : ''}`,
      { signal },
    );
    return res.items ?? [];
  }, []);

  const fetchProducts = useCallback(async (query: string, signal: AbortSignal) => {
    const q = query.trim();
    const res = await apiGet<{ items: ProductPick[] }>(
      `/api/v1/products?page=1&page_size=25${q ? `&q=${encodeURIComponent(q)}` : ''}`,
      { signal },
    );
    return res.items ?? [];
  }, []);

  const cols = useMemo<ColDef<IntelRow>[]>(
    () => [
      {
        headerName: 'Customer',
        flex: 1,
        minWidth: 180,
        valueGetter: (p) => (p.data ? customerLabel(p.data) : ''),
      },
      {
        headerName: 'Product',
        flex: 1.2,
        minWidth: 200,
        valueGetter: (p) => (p.data ? productLabel(p.data) : ''),
      },
      { field: 'site_label', headerName: 'Site', flex: 1, minWidth: 120 },
      { field: 'last_period', headerName: 'Last figures', width: 120 },
      {
        field: 'data_state',
        headerName: 'State',
        width: 150,
        valueFormatter: (p) =>
          p.value === 'insufficient_data' ? 'Too little history' : p.value === 'ok' ? 'OK' : String(p.value ?? ''),
      },
      {
        field: 'velocity_4wk',
        headerName: 'Per week (4 wks)',
        width: 100,
        valueFormatter: (p) => (p.value == null ? '—' : Number(p.value).toFixed(2)),
      },
      {
        field: 'velocity_13wk',
        headerName: 'Per week (13 wks)',
        width: 100,
        valueFormatter: (p) => (p.value == null ? '—' : Number(p.value).toFixed(2)),
      },
      {
        field: 'weeks_of_cover',
        headerName: 'Weeks of cover',
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
          if (p.data?.data_state === 'insufficient_data') flags.push('under 4 weeks');
          return flags.join(', ') || '—';
        },
      },
      ...factColumns.optionalColDefs,
    ],
    [factColumns.optionalColDefs],
  );

  return (
    <Box data-testid="channel-intelligence-workspace">
      <Alert severity="info" variant="outlined" sx={{ mt: 2, mb: 2 }}>
        One row per customer, product and store, measured up to the latest figures loaded. Sales per week
        are averaged over the last 4 and 13 weeks (monthly figures count as a weekly average). A row needs
        at least {String(data?.thresholds?.min_observed_weeks ?? 4)} weeks of history before cover and trend are worked out.
        For charts, missing reports and SKUs that need action, use the Sell-through tab.
      </Alert>
      <Box sx={{ mb: 2 }}>
      <ScopeBar
        chips={[]}
        filters={
          <>
          {gridChrome.filters}
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Box sx={{ minWidth: 220 }} data-testid="sellthrough-customer-filter">
          <EntitySearchAutocomplete<CustomerPick>
            label="Customer"
            value={customer}
            onChange={setCustomer}
            getOptionLabel={(o) =>
              o.customer_name ? `${o.customer_code} — ${o.customer_name}` : o.customer_code
            }
            fetchOptions={fetchCustomers}
          />
        </Box>
        <Box sx={{ minWidth: 220 }} data-testid="sellthrough-product-filter">
          <EntitySearchAutocomplete<ProductPick>
            label="Product"
            value={product}
            onChange={setProduct}
            getOptionLabel={(o) => {
              const name = o.sales_model_name || o.name;
              return name ? `${o.sku} — ${name}` : o.sku;
            }}
            fetchOptions={fetchProducts}
          />
        </Box>
        <TextField
          size="small"
          label="Site label"
          value={site}
          onChange={(e) => setSite(e.target.value)}
          sx={{ width: 180 }}
        />
        {!customer && linkedCustomerId ? (
          <Chip
            size="small"
            color="primary"
            label={`Customer: ${data?.items?.[0]?.customer_name ?? linkedCustomerId}`}
            onDelete={() => setLinkedCustomerId(null)}
          />
        ) : null}
        <Chip
          size="small"
          label={
            data && data.total > data.items.length
              ? `showing ${data.items.length} of ${data.total} — filter to narrow`
              : `rows: ${data?.total ?? '…'}`
          }
        />
        {data?.as_of ? <Chip size="small" variant="outlined" label={`measured to ${data.as_of}`} /> : null}
        {data?.data_unavailable ? <Chip size="small" color="warning" label="Figures not available" /> : null}
      </Stack>
          </>
        }
        savedViews={gridChrome.viewNames}
        savedView={gridChrome.active}
        onSavedView={gridChrome.selectView}
        trailing={
          <>
            {gridChrome.trailing}
            <Button size="small" variant="outlined" onClick={() => refetch()}>
              Refresh
            </Button>
            <FactColumnsButton
              gridId="channel-intelligence"
              onClick={factColumns.openPicker}
              count={factColumns.optionalFields.length}
            />
          </>
        }
      />
      </Box>
      <ModuleDataSection
        isLoading={isLoading}
        isError={isError}
        error={isError ? new Error(String((error as Error)?.message)) : null}
        onRetry={() => void refetch()}
        isEmpty={(data?.items ?? []).length === 0}
        empty={{
          title: data?.data_unavailable ? 'Sell-through figures are not available' : 'No sell-through rows',
          description: data?.data_unavailable
            ? 'Sell-through and stock have not been imported yet, so customer and product figures cannot be shown.'
            : 'Adjust the filters above, or import customer sell-through and stock via the Import Center.',
          primary: { label: 'Import Center', href: '/admin/imports' },
        }}
      >
        <EnterpriseDataGrid
          ref={gridChrome.gridRef}
          quickFilterText={gridChrome.query}
          rowData={data?.items ?? []}
          columnDefs={cols}
          height={520}
          gridOptions={{
            getRowId: (p) =>
              `${p.data.customer_id}-${p.data.product_id}-${p.data.site_label ?? ''}`,
            onRowClicked: (e) => setSelected(e.data ?? null),
          }}
        />
      </ModuleDataSection>
      <Drawer anchor="right" open={!!selected} onClose={() => setSelected(null)}>
        <Box sx={{ width: 360, p: 2 }}>
          <Typography variant="h6" sx={{ mb: 0.5 }}>
            {selected ? customerLabel(selected) : 'Factors'}
          </Typography>
          {selected ? (
            <>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                {productLabel(selected)}
                {selected.site_label ? ` · ${selected.site_label}` : ''}
              </Typography>
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
            </>
          ) : null}
        </Box>
      </Drawer>
      <FactColumnPicker {...factColumns.pickerProps} />
    </Box>
  );
}
