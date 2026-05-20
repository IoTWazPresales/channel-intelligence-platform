'use client';

import ViewColumnIcon from '@mui/icons-material/ViewColumn';
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
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
import { useEffect, useMemo, useState } from 'react';

import { PageHeader } from '@/components/PageHeader';
import { apiGet } from '@/lib/api';

import { InboundShipmentsColumnsDialog, type OptionalColumnMeta } from './InboundShipmentsColumnsDialog';
import { ShippingCommercialSummary } from './ShippingCommercialSummary';

const LS_GRID = 'cip.commercial.inbound-shipments.grid.optional.v1';

const DATE_FIELD_OPTIONS: { value: string; label: string }[] = [
  { value: 'eta_date', label: 'ETA date' },
  { value: 'promise_date', label: 'Promise date' },
  { value: 'pod_date', label: 'POD date' },
  { value: 'ship_confirm_date', label: 'Ship confirm date' },
  { value: 'schedule_ship_date', label: 'Schedule ship date' },
  { value: 'exwork_date', label: 'Ex-work date' },
  { value: 'erd_date', label: 'ERD date' },
  { value: 'est_pod_date', label: 'Est. POD date' },
  { value: 'created_at', label: 'Created at (day, UTC)' },
  { value: 'updated_at', label: 'Updated at (day, UTC)' },
];

type SmartPresetId = 'arriving_week' | 'overdue' | 'landed_week' | 'outstanding';

type CountBucket = { key: string; count: number };

type ShippingSummary = {
  total_lines: number;
  by_line_state: CountBucket[];
  by_status: CountBucket[];
  by_distributor: CountBucket[];
};

type ShippingLine = Record<string, unknown> & { id: number };

type LinesResponse = { total: number; skip: number; limit: number; items: ShippingLine[] };

type DistHit = { id: number; distributor_code: string; distributor_name: string };
type CustHit = { id: number; customer_code: string; customer_name: string };

function localDateYMD(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function startOfISOWeek(d: Date): Date {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const dow = x.getDay();
  const diff = dow === 0 ? -6 : 1 - dow;
  x.setDate(x.getDate() + diff);
  return x;
}

function addDaysCal(d: Date, n: number): Date {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  x.setDate(x.getDate() + n);
  return x;
}

function fmtShortDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function fmtOptionalCell(value: unknown): string {
  if (value == null || value === '') return '—';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return '—';
    }
  }
  return String(value);
}

function fmtCellForKey(key: string, value: unknown): string {
  if (value == null || value === '') return '—';
  if (key.includes('date') || key.endsWith('_at')) {
    const s = typeof value === 'string' ? value : String(value);
    if (s && /^\d{4}-\d{2}-\d{2}/.test(s)) return fmtShortDate(s);
  }
  return fmtOptionalCell(value);
}

export default function InboundShipmentsPage() {
  const [lineState, setLineState] = useState<string>('');
  const [cargoStatus, setCargoStatus] = useState<string>('');
  const [distributorPick, setDistributorPick] = useState<DistHit | null>(null);
  const [customerPick, setCustomerPick] = useState<CustHit | null>(null);
  const [search, setSearch] = useState('');
  const [dateField, setDateField] = useState('eta_date');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [productFamily, setProductFamily] = useState('');
  const [productModel, setProductModel] = useState('');
  const [currencyCode, setCurrencyCode] = useState('');
  const [operatingUnit, setOperatingUnit] = useState('');
  const [podDateFilter, setPodDateFilter] = useState<'' | 'true' | 'false'>('');
  const [smartPreset, setSmartPreset] = useState<SmartPresetId | null>(null);

  const [colDialogOpen, setColDialogOpen] = useState(false);
  const [optionalFields, setOptionalFields] = useState<string[]>([]);
  const [persistReady, setPersistReady] = useState(false);

  const { data: colMeta, isLoading: colMetaLoading } = useQuery({
    queryKey: ['shipping-inbound-optional-columns'],
    queryFn: ({ signal }) =>
      apiGet<{ items: OptionalColumnMeta[] }>('/api/v1/shipping/inbound-optional-columns', { signal }),
  });

  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_GRID);
      if (raw) {
        const p = JSON.parse(raw) as { optionalFields?: string[] };
        if (Array.isArray(p.optionalFields)) {
          setOptionalFields(p.optionalFields);
        }
      }
    } catch {
      /* ignore */
    }
    setPersistReady(true);
  }, []);

  useEffect(() => {
    if (!colMeta?.items?.length) return;
    const allowed = new Set(colMeta.items.map((c) => c.field));
    setOptionalFields((prev) => prev.filter((f) => allowed.has(f)));
  }, [colMeta]);

  useEffect(() => {
    if (!persistReady) return;
    try {
      localStorage.setItem(LS_GRID, JSON.stringify({ optionalFields }));
    } catch {
      /* ignore */
    }
  }, [optionalFields, persistReady]);

  const optionalSet = useMemo(() => new Set(optionalFields), [optionalFields]);
  const allowedOptional = colMeta?.items ?? [];
  const allowedSet = useMemo(() => new Set(allowedOptional.map((c) => c.field)), [allowedOptional]);
  const columnLabels = useMemo(() => new Map(allowedOptional.map((c) => [c.field, c.label])), [allowedOptional]);
  const displayOptionalFields = useMemo(
    () => optionalFields.filter((f) => optionalSet.has(f) && allowedSet.has(f)),
    [optionalFields, optionalSet, allowedSet]
  );

  const clearSmartPreset = () => {
    setSmartPreset(null);
    setLineState('');
    setCargoStatus('');
    setDateField('eta_date');
    setDateFrom('');
    setDateTo('');
    setPodDateFilter('');
  };

  const applySmartPreset = (id: SmartPresetId) => {
    if (smartPreset === id) {
      clearSmartPreset();
      return;
    }
    const today = new Date();
    const w0 = startOfISOWeek(today);
    const w6 = addDaysCal(w0, 6);
    const yest = addDaysCal(today, -1);
    setSmartPreset(id);
    switch (id) {
      case 'arriving_week':
        setDateField('eta_date');
        setDateFrom(localDateYMD(w0));
        setDateTo(localDateYMD(w6));
        setCargoStatus('scheduled');
        setLineState('');
        setPodDateFilter('');
        break;
      case 'overdue':
        setDateField('promise_date');
        setDateFrom('');
        setDateTo(localDateYMD(yest));
        setCargoStatus('scheduled');
        setLineState('');
        setPodDateFilter('true');
        break;
      case 'landed_week':
        setDateField('pod_date');
        setDateFrom(localDateYMD(w0));
        setDateTo(localDateYMD(w6));
        setCargoStatus('received');
        setLineState('');
        setPodDateFilter('false');
        break;
      case 'outstanding':
        setLineState('open_order');
        setDateField('eta_date');
        setDateFrom('');
        setDateTo('');
        setCargoStatus('');
        setPodDateFilter('');
        break;
      default:
        break;
    }
  };

  const { data: summary } = useQuery({
    queryKey: ['shipping-summary'],
    queryFn: ({ signal }) => apiGet<ShippingSummary>('/api/v1/shipping/summary', { signal }),
  });

  const { data: filterOptions } = useQuery({
    queryKey: ['shipping-filter-options'],
    queryFn: ({ signal }) =>
      apiGet<{ distributors: DistHit[]; customers: CustHit[] }>('/api/v1/shipping/filter-options', { signal }),
  });

  const distOptions = filterOptions?.distributors ?? [];
  const custOptions = filterOptions?.customers ?? [];

  const includeRawRow = displayOptionalFields.includes('raw_source_row');

  const queryKey = useMemo(
    () =>
      [
        'shipping-lines',
        lineState,
        cargoStatus,
        distributorPick?.id ?? null,
        customerPick?.id ?? null,
        search,
        dateField,
        dateFrom,
        dateTo,
        productFamily,
        productModel,
        currencyCode,
        operatingUnit,
        podDateFilter,
        includeRawRow,
      ] as const,
    [
      lineState,
      cargoStatus,
      distributorPick?.id,
      customerPick?.id,
      search,
      dateField,
      dateFrom,
      dateTo,
      productFamily,
      productModel,
      currencyCode,
      operatingUnit,
      podDateFilter,
      includeRawRow,
    ]
  );

  const { data: lines, isLoading: linesLoading } = useQuery({
    queryKey,
    queryFn: ({ signal }) => {
      const params = new URLSearchParams();
      params.set('limit', '50');
      if (lineState) params.set('line_state', lineState);
      if (cargoStatus) params.set('status', cargoStatus);
      if (distributorPick != null) params.set('distributor_id', String(distributorPick.id));
      if (customerPick != null) params.set('customer_id', String(customerPick.id));
      if (search.trim()) params.set('search', search.trim());
      if (dateField) params.set('date_field', dateField);
      if (dateFrom.trim()) params.set('date_from', dateFrom.trim());
      if (dateTo.trim()) params.set('date_to', dateTo.trim());
      if (productFamily.trim()) params.set('product_family', productFamily.trim());
      if (productModel.trim()) params.set('product_model', productModel.trim());
      if (currencyCode.trim()) params.set('currency_code', currencyCode.trim());
      if (operatingUnit.trim()) params.set('operating_unit', operatingUnit.trim());
      if (podDateFilter === 'true') params.set('pod_date_is_null', 'true');
      if (podDateFilter === 'false') params.set('pod_date_is_null', 'false');
      if (includeRawRow) params.set('include_raw_row', 'true');
      return apiGet<LinesResponse>(`/api/v1/shipping/lines?${params.toString()}`, { signal });
    },
  });

  return (
    <>
      <PageHeader crumbs={[{ label: 'Inbound shipments' }]} title="Inbound shipments" />
      <Alert severity="info" sx={{ mb: 2 }}>
        Truth layer from <strong>fact_inbound_shipment</strong> (populated when an inbound import job is applied).
        Steward raw imports under <strong>Admin → Shipment evidence</strong>.
      </Alert>
      <ShippingCommercialSummary />

      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.5 }}>
        Smart views
      </Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }} alignItems="center">
        <Chip
          label="Arriving this week"
          size="small"
          variant={smartPreset === 'arriving_week' ? 'filled' : 'outlined'}
          color={smartPreset === 'arriving_week' ? 'primary' : 'default'}
          onClick={() => applySmartPreset('arriving_week')}
        />
        <Chip
          label="Overdue (promise passed, not landed)"
          size="small"
          variant={smartPreset === 'overdue' ? 'filled' : 'outlined'}
          color={smartPreset === 'overdue' ? 'primary' : 'default'}
          onClick={() => applySmartPreset('overdue')}
        />
        <Chip
          label="Landed this week"
          size="small"
          variant={smartPreset === 'landed_week' ? 'filled' : 'outlined'}
          color={smartPreset === 'landed_week' ? 'primary' : 'default'}
          onClick={() => applySmartPreset('landed_week')}
        />
        <Chip
          label="Outstanding orders"
          size="small"
          variant={smartPreset === 'outstanding' ? 'filled' : 'outlined'}
          color={smartPreset === 'outstanding' ? 'primary' : 'default'}
          onClick={() => applySmartPreset('outstanding')}
        />
        {smartPreset ? (
          <Button size="small" onClick={clearSmartPreset}>
            Clear view
          </Button>
        ) : null}
      </Stack>

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap alignItems="flex-start">
        <TextField
          size="small"
          label="Search"
          placeholder="Distributor, product, SKU, sales model, order #, channel partner…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setSmartPreset(null);
          }}
          sx={{ minWidth: 260, flex: 1 }}
        />
        <Autocomplete
          sx={{ minWidth: 280, flex: 1 }}
          size="small"
          loading={!filterOptions}
          options={distOptions}
          value={distributorPick}
          onChange={(_e, v) => {
            setDistributorPick(v);
            setSmartPreset(null);
          }}
          getOptionLabel={(o) => `${o.distributor_name} (${o.distributor_code})`}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={(params) => (
            <TextField {...params} label="Distributor (canonical)" placeholder="All distributors · type to filter" />
          )}
        />
        <Autocomplete
          sx={{ minWidth: 260, flex: 1 }}
          size="small"
          loading={!filterOptions}
          options={custOptions}
          value={customerPick}
          onChange={(_e, v) => {
            setCustomerPick(v);
            setSmartPreset(null);
          }}
          getOptionLabel={(o) => `${o.customer_name} (${o.customer_code})`}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={(params) => (
            <TextField {...params} label="Channel partner (customer)" placeholder="All customers · type to filter" />
          )}
        />
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel id="flt-line-state">Line state</InputLabel>
          <Select
            labelId="flt-line-state"
            label="Line state"
            value={lineState}
            onChange={(e) => {
              setLineState(String(e.target.value));
              setSmartPreset(null);
            }}
          >
            <MenuItem value="">(any)</MenuItem>
            {(summary?.by_line_state ?? []).map((b) => (
              <MenuItem key={b.key} value={b.key}>
                {b.key}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel id="flt-cargo">Cargo status</InputLabel>
          <Select
            labelId="flt-cargo"
            label="Cargo status"
            value={cargoStatus}
            onChange={(e) => {
              setCargoStatus(String(e.target.value));
              setSmartPreset(null);
            }}
          >
            <MenuItem value="">(any)</MenuItem>
            {(summary?.by_status ?? []).map((b) => (
              <MenuItem key={b.key} value={b.key}>
                {b.key}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 180 }}>
          <InputLabel id="flt-date-field">Date field</InputLabel>
          <Select
            labelId="flt-date-field"
            label="Date field"
            value={dateField}
            onChange={(e) => {
              setDateField(String(e.target.value));
              setSmartPreset(null);
            }}
          >
            {DATE_FIELD_OPTIONS.map((o) => (
              <MenuItem key={o.value} value={o.value}>
                {o.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <TextField
          size="small"
          label="Date from"
          type="date"
          InputLabelProps={{ shrink: true }}
          value={dateFrom}
          onChange={(e) => {
            setDateFrom(e.target.value);
            setSmartPreset(null);
          }}
          sx={{ width: 160 }}
        />
        <TextField
          size="small"
          label="Date to"
          type="date"
          InputLabelProps={{ shrink: true }}
          value={dateTo}
          onChange={(e) => {
            setDateTo(e.target.value);
            setSmartPreset(null);
          }}
          sx={{ width: 160 }}
        />
        <TextField
          size="small"
          label="Product family"
          placeholder="Category / line / series"
          value={productFamily}
          onChange={(e) => {
            setProductFamily(e.target.value);
            setSmartPreset(null);
          }}
          sx={{ minWidth: 160 }}
        />
        <TextField
          size="small"
          label="Product model"
          placeholder="Model, marketing name, SKU…"
          value={productModel}
          onChange={(e) => {
            setProductModel(e.target.value);
            setSmartPreset(null);
          }}
          sx={{ minWidth: 160 }}
        />
        <TextField
          size="small"
          label="Currency"
          placeholder="e.g. USD"
          value={currencyCode}
          onChange={(e) => {
            setCurrencyCode(e.target.value);
            setSmartPreset(null);
          }}
          sx={{ width: 100 }}
        />
        <TextField
          size="small"
          label="Operating unit"
          value={operatingUnit}
          onChange={(e) => {
            setOperatingUnit(e.target.value);
            setSmartPreset(null);
          }}
          sx={{ minWidth: 140 }}
        />
        <Button
          size="small"
          variant="outlined"
          startIcon={<ViewColumnIcon />}
          onClick={() => setColDialogOpen(true)}
          sx={{ flexShrink: 0, alignSelf: 'center' }}
        >
          Additional columns
        </Button>
      </Stack>

      <Box sx={{ overflowX: 'auto' }}>
        {linesLoading ? (
          <Typography color="text.secondary">Loading rows…</Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Distributor</TableCell>
                <TableCell>Channel partner</TableCell>
                <TableCell>Product (sales model)</TableCell>
                <TableCell>Line state</TableCell>
                <TableCell>Cargo status</TableCell>
                <TableCell>ETA</TableCell>
                <TableCell>Promise</TableCell>
                <TableCell>POD</TableCell>
                {displayOptionalFields.map((f) => (
                  <TableCell key={f}>{columnLabels.get(f) ?? f}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {(lines?.items ?? []).map((row) => (
                <TableRow key={row.id}>
                  <TableCell>
                    <Typography variant="body2">
                      {(row.distributor_display ?? row.distributor_name ?? '—') as string}
                    </Typography>
                    {row.distributor_code && row.distributor_name ? (
                      <Typography variant="caption" color="text.secondary" display="block">
                        {String(row.distributor_code)}
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {(row.channel_partner_label ?? '—') as string}
                    </Typography>
                    {row.channel_partner_caption ? (
                      <Typography variant="caption" color="text.secondary" display="block">
                        {String(row.channel_partner_caption)}
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {(row.sales_model_name ?? row.product_name ?? row.item_code ?? '—') as string}
                    </Typography>
                    {row.product_sku ? (
                      <Typography variant="caption" color="text.secondary" display="block">
                        SKU {String(row.product_sku)}
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell>{String(row.line_state ?? '—')}</TableCell>
                  <TableCell>{String(row.status ?? '—')}</TableCell>
                  <TableCell>{fmtShortDate(row.eta_date as string | undefined)}</TableCell>
                  <TableCell>{fmtShortDate(row.promise_date as string | undefined)}</TableCell>
                  <TableCell>{fmtShortDate(row.pod_date as string | undefined)}</TableCell>
                  {displayOptionalFields.map((f) => (
                    <TableCell key={f} sx={{ maxWidth: 260, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {fmtCellForKey(f, row[f])}
                    </TableCell>
                  ))}
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

      <InboundShipmentsColumnsDialog
        open={colDialogOpen}
        onClose={() => setColDialogOpen(false)}
        optionalFields={optionalFields}
        onOptionalFieldsChange={setOptionalFields}
        columnOptions={allowedOptional}
        columnsLoading={colMetaLoading}
      />
    </>
  );
}
