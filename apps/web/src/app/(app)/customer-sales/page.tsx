'use client';

import {
  Alert,
  Autocomplete,
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
  TextField,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { KpiCard } from '@/components/KpiCard';
import { PageHeader } from '@/components/PageHeader';
import { apiGet } from '@/lib/api';

type SmartPresetId = '' | 'fastest_movers' | 'zero_sellout_products';

type CustomerSalesSummary = {
  total_rows: number;
  total_units: number;
  total_value: number;
  latest_period: string | null;
  data_unavailable?: boolean;
};

type CustomerSalesLine = Record<string, unknown> & { id: number };
type LinesResponse = { total: number; skip: number; limit: number; items: CustomerSalesLine[] };
type DistHit = { id: number; distributor_code: string; distributor_name: string };
type CustHit = { id: number; customer_code: string; customer_name: string };
type FilterOptions = {
  distributors: DistHit[];
  customers: CustHit[];
  report_years?: number[];
  report_weeks?: number[];
  channel_types?: string[];
};

export default function CustomerSalesPage() {
  const [search, setSearch] = useState('');
  const [customerPick, setCustomerPick] = useState<CustHit | null>(null);
  const [productSearch, setProductSearch] = useState('');
  const [reportYear, setReportYear] = useState<string>('');
  const [reportWeek, setReportWeek] = useState<string>('');
  const [channelType, setChannelType] = useState<string>('');
  const [smartPreset, setSmartPreset] = useState<SmartPresetId>('');

  const { data: summary } = useQuery({
    queryKey: ['customer-sales-commercial-summary'],
    queryFn: ({ signal }) =>
      apiGet<CustomerSalesSummary>('/api/v1/customer-sales/commercial-summary', { signal }),
  });

  const { data: filterOptions } = useQuery({
    queryKey: ['customer-sales-filter-options'],
    queryFn: ({ signal }) =>
      apiGet<FilterOptions>('/api/v1/customer-sales/filter-options', { signal }),
  });

  const custOptions = filterOptions?.customers ?? [];
  const yearOptions = filterOptions?.report_years ?? [];
  const weekOptions = filterOptions?.report_weeks ?? [];
  const channelOptions = filterOptions?.channel_types ?? [];

  const linesQueryKey = useMemo(
    () =>
      [
        'customer-sales-commercial-lines',
        smartPreset,
        customerPick?.id ?? null,
        search,
        productSearch,
        reportYear,
        reportWeek,
        channelType,
      ] as const,
    [smartPreset, customerPick?.id, search, productSearch, reportYear, reportWeek, channelType],
  );

  const { data: lines, isLoading: linesLoading } = useQuery({
    queryKey: linesQueryKey,
    queryFn: ({ signal }) => {
      const params = new URLSearchParams();
      params.set('limit', '50');
      if (customerPick != null) params.set('customer_id', String(customerPick.id));
      if (search.trim()) params.set('search', search.trim());
      if (productSearch.trim()) params.set('product_search', productSearch.trim());
      if (reportYear) params.set('report_year', reportYear);
      if (reportWeek) params.set('report_week', reportWeek);
      if (channelType) params.set('channel_type', channelType);
      if (smartPreset && smartPreset !== 'zero_sellout_products') {
        params.set('smart_view', smartPreset);
      }
      return apiGet<LinesResponse>(`/api/v1/customer-sales/commercial-lines?${params.toString()}`, { signal });
    },
    enabled: smartPreset !== 'zero_sellout_products',
  });

  const { data: zeroProducts, isLoading: zeroLoading } = useQuery({
    queryKey: ['customer-sales-zero-products'],
    queryFn: ({ signal }) =>
      apiGet<{ items: { product_id: number; sku: string; name: string }[] }>(
        '/api/v1/customer-sales/zero-sellout-products?lookback_days=365&limit=80',
        { signal },
      ),
    enabled: smartPreset === 'zero_sellout_products',
  });

  const dataUnavailable = summary?.data_unavailable === true;

  return (
    <>
      <PageHeader crumbs={[{ label: 'Commercial' }, { label: 'Customer sales' }]} title="Customer sales" />

      {dataUnavailable ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          The <strong>customer_sales</strong> table needs to be migrated before data is available. Once the migration is
          complete, this dashboard will populate automatically.
        </Alert>
      ) : (
        <Alert severity="info" sx={{ mb: 2 }}>
          Commercial view over <strong>customer_sales</strong> data. Use <strong>Admin → Imports</strong> for data
          loads.
        </Alert>
      )}

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <Box sx={{ flex: '1 1 200px' }}>
          <KpiCard
            label="Total units sold"
            value={summary != null ? summary.total_units.toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—'}
          />
        </Box>
        <Box sx={{ flex: '1 1 200px' }}>
          <KpiCard
            label="Total sell-out value"
            value={summary != null ? summary.total_value.toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—'}
          />
        </Box>
        <Box sx={{ flex: '1 1 200px' }}>
          <KpiCard label="Latest period" value={summary?.latest_period ?? '—'} />
        </Box>
        <Box sx={{ flex: '1 1 200px' }}>
          <KpiCard label="Retailers reporting" value={summary?.total_rows ?? '—'} />
        </Box>
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
          label="Search customer / store"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ minWidth: 240, flex: 1 }}
          disabled={smartPreset === 'zero_sellout_products'}
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
        <TextField
          size="small"
          label="Product search"
          value={productSearch}
          onChange={(e) => setProductSearch(e.target.value)}
          sx={{ minWidth: 180, flex: 1 }}
          disabled={smartPreset === 'zero_sellout_products'}
        />
        <FormControl size="small" sx={{ minWidth: 130 }}>
          <InputLabel id="cs-year">Report year</InputLabel>
          <Select
            labelId="cs-year"
            label="Report year"
            value={reportYear}
            onChange={(e) => setReportYear(String(e.target.value))}
            disabled={smartPreset === 'zero_sellout_products'}
          >
            <MenuItem value="">(any)</MenuItem>
            {yearOptions.map((y) => (
              <MenuItem key={y} value={String(y)}>
                {y}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 130 }}>
          <InputLabel id="cs-week">Report week</InputLabel>
          <Select
            labelId="cs-week"
            label="Report week"
            value={reportWeek}
            onChange={(e) => setReportWeek(String(e.target.value))}
            disabled={smartPreset === 'zero_sellout_products'}
          >
            <MenuItem value="">(any)</MenuItem>
            {weekOptions.map((w) => (
              <MenuItem key={w} value={String(w)}>
                W{w}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel id="cs-channel">Channel type</InputLabel>
          <Select
            labelId="cs-channel"
            label="Channel type"
            value={channelType}
            onChange={(e) => setChannelType(String(e.target.value))}
            disabled={smartPreset === 'zero_sellout_products'}
          >
            <MenuItem value="">(any)</MenuItem>
            {channelOptions.map((c) => (
              <MenuItem key={c} value={c}>
                {c}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
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
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Customer</TableCell>
                      <TableCell>Product</TableCell>
                      <TableCell>Store</TableCell>
                      <TableCell>Week / Year</TableCell>
                      <TableCell align="right">Qty sold</TableCell>
                      <TableCell align="right">Qty returned</TableCell>
                      <TableCell align="right">Selling price</TableCell>
                      <TableCell align="right">Cost price</TableCell>
                      <TableCell>Currency</TableCell>
                      <TableCell>Channel</TableCell>
                      <TableCell>Resolution status</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(lines?.items ?? []).map((r) => (
                      <TableRow key={r.id}>
                        <TableCell>{String(r.customer_name ?? r.customer_code ?? '—')}</TableCell>
                        <TableCell>{String(r.product_name ?? r.product_sku ?? '—')}</TableCell>
                        <TableCell>{String(r.store_name ?? r.store_code ?? '—')}</TableCell>
                        <TableCell>
                          W{String(r.report_week ?? '—')} / {String(r.report_year ?? '—')}
                        </TableCell>
                        <TableCell align="right">
                          {r.qty_sold != null ? Number(r.qty_sold).toLocaleString() : '—'}
                        </TableCell>
                        <TableCell align="right">
                          {r.qty_returned != null ? Number(r.qty_returned).toLocaleString() : '—'}
                        </TableCell>
                        <TableCell align="right">
                          {r.selling_price != null ? Number(r.selling_price).toLocaleString() : '—'}
                        </TableCell>
                        <TableCell align="right">
                          {r.cost_price != null ? Number(r.cost_price).toLocaleString() : '—'}
                        </TableCell>
                        <TableCell>{String(r.currency_code ?? '—')}</TableCell>
                        <TableCell>{String(r.channel_type ?? '—')}</TableCell>
                        <TableCell>{String(r.resolution_status ?? '—')}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            )}
          </Box>
        </Paper>
      )}
    </>
  );
}
