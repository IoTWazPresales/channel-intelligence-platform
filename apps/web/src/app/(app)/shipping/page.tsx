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
  Paper,
  Select,
  Stack,
  TablePagination,
  TextField,
  Typography,
} from '@mui/material';
import type { ColDef, GridOptions, ValueFormatterParams } from 'ag-grid-community';
import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { apiGet } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

import { buildShippingLinesUrl, type ShippingFilterParams } from './buildShippingLinesUrl';
import { InboundShipmentsColumnsDialog, type OptionalColumnMeta } from './InboundShipmentsColumnsDialog';
import { ShippingCommercialSummary } from './ShippingCommercialSummary';
import { fmtCellForKey, fmtShortDate } from './shippingGridFormatters';
import type { SmartPresetId } from './shippingSmartPresets';

const LS_GRID = 'cip.commercial.inbound-shipments.grid.optional.v1';
const PAGE_SIZE_OPTIONS = [25, 50, 100, 250, 500] as const;

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

type CountBucket = { key: string; count: number };

type ShippingSummary = {
  total_lines: number;
  by_line_state: CountBucket[];
  by_status: CountBucket[];
  by_distributor: CountBucket[];
};

export type ShippingLine = {
  id: number;
  distributor_display?: string | null;
  distributor_name?: string | null;
  distributor_code?: string | null;
  channel_partner_label?: string | null;
  channel_partner_caption?: string | null;
  sales_model_name?: string | null;
  product_name?: string | null;
  item_code?: string | null;
  product_sku?: string | null;
  line_state?: string | null;
  status?: string | null;
  eta_date?: string | null;
  promise_date?: string | null;
  pod_date?: string | null;
  quantity?: number | null;
  amount?: number | null;
  currency_code?: string | null;
  [key: string]: unknown;
};

type LinesResponse = { total: number; skip: number; limit: number; items: ShippingLine[] };

type DistHit = { id: number; distributor_code: string; distributor_name: string };
type CustHit = { id: number; customer_code: string; customer_name: string };

type DeliveryLensId = 'delivered' | 'in_transit';

function cargoStatusLabel(key: string): string {
  if (key === 'received') return 'Delivered';
  if (key === 'scheduled') return 'In transit';
  return key;
}

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

function dateColFormatter(p: ValueFormatterParams<ShippingLine>): string {
  return fmtShortDate(p.value as string | undefined);
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
  const [deliveryLens, setDeliveryLens] = useState<DeliveryLensId | null>(null);
  const [skip, setSkip] = useState(0);
  const [limit, setLimit] = useState<number>(50);

  const [colDialogOpen, setColDialogOpen] = useState(false);
  const [optionalFields, setOptionalFields] = useState<string[]>([]);
  const [persistReady, setPersistReady] = useState(false);

  const gridSectionRef = useRef<HTMLDivElement | null>(null);

  const resetPagination = useCallback(() => setSkip(0), []);

  const { data: colMeta, isLoading: colMetaLoading } = useQuery({
    queryKey: ['shipping-inbound-optional-columns'],
    queryFn: ({ signal }) =>
      apiGet<{ items: OptionalColumnMeta[] }>('/api/v1/shipping/inbound-optional-columns', { signal }),
  });

  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_GRID);
      if (raw) {
        const p = JSON.parse(raw) as { optionalFields?: string[]; pageSize?: number };
        if (Array.isArray(p.optionalFields)) {
          setOptionalFields(p.optionalFields);
        }
        if (typeof p.pageSize === 'number' && PAGE_SIZE_OPTIONS.includes(p.pageSize as (typeof PAGE_SIZE_OPTIONS)[number])) {
          setLimit(p.pageSize);
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
      localStorage.setItem(LS_GRID, JSON.stringify({ optionalFields, pageSize: limit }));
    } catch {
      /* ignore */
    }
  }, [optionalFields, limit, persistReady]);

  const optionalSet = useMemo(() => new Set(optionalFields), [optionalFields]);
  const allowedOptional = colMeta?.items ?? [];
  const allowedSet = useMemo(() => new Set(allowedOptional.map((c) => c.field)), [allowedOptional]);
  const columnLabels = useMemo(() => new Map(allowedOptional.map((c) => [c.field, c.label])), [allowedOptional]);
  const displayOptionalFields = useMemo(
    () => optionalFields.filter((f) => optionalSet.has(f) && allowedSet.has(f)),
    [optionalFields, optionalSet, allowedSet]
  );

  const clearSmartPreset = useCallback(() => {
    setSmartPreset(null);
    setDeliveryLens(null);
    setLineState('');
    setCargoStatus('');
    setDateField('eta_date');
    setDateFrom('');
    setDateTo('');
    setPodDateFilter('');
    resetPagination();
  }, [resetPagination]);

  const applyDeliveryLens = useCallback(
    (id: DeliveryLensId) => {
      setSmartPreset(null);
      setDeliveryLens(id);
      resetPagination();
      setDateField('eta_date');
      setDateFrom('');
      setDateTo('');
      setLineState('');
      if (id === 'delivered') {
        setCargoStatus('received');
        setPodDateFilter('false');
      } else {
        setCargoStatus('scheduled');
        setPodDateFilter('true');
      }
      gridSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },
    [resetPagination]
  );

  const toggleDeliveryLens = (id: DeliveryLensId) => {
    if (deliveryLens === id) {
      clearSmartPreset();
      return;
    }
    applyDeliveryLens(id);
  };

  const applySmartPreset = useCallback(
    (id: SmartPresetId) => {
      const today = new Date();
      const w0 = startOfISOWeek(today);
      const w6 = addDaysCal(w0, 6);
      const yest = addDaysCal(today, -1);
      setSmartPreset(id);
      setDeliveryLens(null);
      resetPagination();
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
      gridSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },
    [resetPagination]
  );

  const filterScheduledPipeline = useCallback(() => {
    clearSmartPreset();
    setDeliveryLens(null);
    setCargoStatus('scheduled');
    setLineState('');
    setPodDateFilter('');
    resetPagination();
    gridSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [clearSmartPreset, resetPagination]);

  const toggleSmartPreset = (id: SmartPresetId) => {
    if (smartPreset === id) {
      clearSmartPreset();
      return;
    }
    applySmartPreset(id);
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

  const filterParams = useMemo<ShippingFilterParams>(
    () => ({
      lineState,
      cargoStatus,
      distributorId: distributorPick?.id ?? null,
      customerId: customerPick?.id ?? null,
      search,
      dateField,
      dateFrom,
      dateTo,
      productFamily,
      productModel,
      currencyCode,
      operatingUnit,
      podDateFilter,
    }),
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
    ]
  );

  const listUrl = useMemo(
    () => buildShippingLinesUrl({ ...filterParams, skip, limit, includeRawRow }),
    [filterParams, skip, limit, includeRawRow]
  );

  const { data: lines, isLoading: linesLoading, isError: linesIsError, error: linesError, refetch } = useQuery({
    queryKey: ['shipping-lines', listUrl],
    queryFn: ({ signal }) => apiGet<LinesResponse>(listUrl, { signal }),
  });

  const baseColDefs: ColDef<ShippingLine>[] = useMemo(
    () => [
      { field: 'id', headerName: 'ID', width: 88, pinned: 'left' },
      {
        headerName: 'Distributor',
        minWidth: 160,
        valueGetter: (p) => {
          const label = (p.data?.distributor_display ?? p.data?.distributor_name ?? '—') as string;
          const code = p.data?.distributor_code;
          if (code && p.data?.distributor_name) return `${label}\n${code}`;
          return label;
        },
      },
      {
        headerName: 'Channel partner',
        minWidth: 160,
        valueGetter: (p) => (p.data?.channel_partner_label ?? '—') as string,
      },
      {
        headerName: 'Product (sales model)',
        minWidth: 180,
        valueGetter: (p) =>
          (p.data?.sales_model_name ?? p.data?.product_name ?? p.data?.item_code ?? '—') as string,
      },
      { field: 'line_state', headerName: 'Line state', minWidth: 120 },
      { field: 'status', headerName: 'Cargo status', minWidth: 120 },
      { field: 'eta_date', headerName: 'ETA', minWidth: 118, valueFormatter: dateColFormatter },
      { field: 'promise_date', headerName: 'Promise', minWidth: 118, valueFormatter: dateColFormatter },
      { field: 'pod_date', headerName: 'POD', minWidth: 118, valueFormatter: dateColFormatter },
      { field: 'quantity', headerName: 'Qty', width: 90 },
      { field: 'amount', headerName: 'Amount', width: 100 },
      { field: 'currency_code', headerName: 'CCY', width: 72 },
    ],
    []
  );

  const optionalColDefs: ColDef<ShippingLine>[] = useMemo(
    () =>
      displayOptionalFields.map((f) => ({
        field: f,
        headerName: columnLabels.get(f) ?? f,
        minWidth: f === 'raw_source_row' ? 220 : 130,
        valueFormatter: (p: ValueFormatterParams<ShippingLine>) => fmtCellForKey(f, p.value),
        wrapText: f === 'raw_source_row',
        autoHeight: f === 'raw_source_row',
      })),
    [displayOptionalFields, columnLabels]
  );

  const colDefs = useMemo(() => [...baseColDefs, ...optionalColDefs], [baseColDefs, optionalColDefs]);

  const gridOptions = useMemo(
    () => ({
      getRowId: (p: { data: ShippingLine }) => String(p.data.id),
      defaultColDef: { sortable: true, filter: true, resizable: true },
    }),
    []
  );

  const total = lines?.total ?? 0;
  const page = limit > 0 ? Math.floor(skip / limit) : 0;
  const pageCount = Math.max(0, Math.ceil(total / limit) - 1);

  return (
    <>
      <PageHeader crumbs={[{ label: 'Inbound shipments' }]} title="Inbound shipments" />
      <Alert severity="info" sx={{ mb: 2 }}>
        Truth layer from <strong>fact_inbound_shipment</strong> (populated when an inbound import job is applied).
        Steward raw imports under <strong>Admin → Shipment evidence</strong>.
      </Alert>
      <ShippingCommercialSummary
        filterParams={filterParams}
        onApplySmartPreset={applySmartPreset}
        onFilterScheduledPipeline={filterScheduledPipeline}
      />

      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.5 }}>
        Smart views
      </Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }} alignItems="center">
        <Chip
          label="Arriving this week"
          size="small"
          variant={smartPreset === 'arriving_week' ? 'filled' : 'outlined'}
          color={smartPreset === 'arriving_week' ? 'primary' : 'default'}
          onClick={() => toggleSmartPreset('arriving_week')}
        />
        <Chip
          label="Overdue (promise passed, not landed)"
          size="small"
          variant={smartPreset === 'overdue' ? 'filled' : 'outlined'}
          color={smartPreset === 'overdue' ? 'primary' : 'default'}
          onClick={() => toggleSmartPreset('overdue')}
        />
        <Chip
          label="Delivered this week"
          size="small"
          variant={smartPreset === 'landed_week' ? 'filled' : 'outlined'}
          color={smartPreset === 'landed_week' ? 'primary' : 'default'}
          onClick={() => toggleSmartPreset('landed_week')}
        />
        <Chip
          label="Delivered (all)"
          size="small"
          variant={deliveryLens === 'delivered' ? 'filled' : 'outlined'}
          color={deliveryLens === 'delivered' ? 'success' : 'default'}
          onClick={() => toggleDeliveryLens('delivered')}
        />
        <Chip
          label="In transit"
          size="small"
          variant={deliveryLens === 'in_transit' ? 'filled' : 'outlined'}
          color={deliveryLens === 'in_transit' ? 'info' : 'default'}
          onClick={() => toggleDeliveryLens('in_transit')}
        />
        <Chip
          label="Outstanding orders"
          size="small"
          variant={smartPreset === 'outstanding' ? 'filled' : 'outlined'}
          color={smartPreset === 'outstanding' ? 'primary' : 'default'}
          onClick={() => toggleSmartPreset('outstanding')}
        />
        {smartPreset || deliveryLens ? (
          <Button size="small" onClick={clearSmartPreset}>
            Clear view
          </Button>
        ) : null}
      </Stack>

      <Paper ref={gridSectionRef} sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap alignItems="flex-start">
          <TextField
            size="small"
            label="Search"
            placeholder="Distributor, product, SKU, sales model, order #, channel partner…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setSmartPreset(null);
              setDeliveryLens(null);
              resetPagination();
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
              setDeliveryLens(null);
              resetPagination();
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
              setDeliveryLens(null);
              resetPagination();
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
                setDeliveryLens(null);
                resetPagination();
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
                setDeliveryLens(null);
                resetPagination();
              }}
            >
              <MenuItem value="">(any)</MenuItem>
              {(summary?.by_status ?? []).map((b) => (
                <MenuItem key={b.key} value={b.key}>
                  {cargoStatusLabel(b.key)}
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
                setDeliveryLens(null);
                resetPagination();
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
              setDeliveryLens(null);
              resetPagination();
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
              setDeliveryLens(null);
              resetPagination();
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
              setDeliveryLens(null);
              resetPagination();
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
              setDeliveryLens(null);
              resetPagination();
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
              setDeliveryLens(null);
              resetPagination();
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
              setDeliveryLens(null);
              resetPagination();
            }}
            sx={{ minWidth: 140 }}
          />
        </Stack>

        <TablePagination
          component="div"
          count={total}
          page={total === 0 ? 0 : Math.min(page, pageCount)}
          onPageChange={(_, nextPage) => {
            setSkip(nextPage * limit);
          }}
          rowsPerPage={limit}
          onRowsPerPageChange={(e) => {
            const next = Number(e.target.value);
            setLimit(next);
            setSkip(0);
          }}
          rowsPerPageOptions={[...PAGE_SIZE_OPTIONS]}
          labelDisplayedRows={({ from, to, count }) => `${from}–${to} of ${count !== -1 ? count : `more than ${to}`}`}
          sx={{ borderBottom: 1, borderColor: 'divider', mb: 1 }}
        />

        <ModuleDataSection
          intro="Sort and filter in the grid. Pagination applies to the server query — change filters to narrow the full result set."
          introWhen="always"
          isLoading={linesLoading}
          isError={linesIsError}
          error={toQueryError(linesError)}
          onRetry={() => void refetch()}
          isEmpty={!linesLoading && (lines?.items?.length ?? 0) === 0}
          empty={{
            title: 'No shipment lines match',
            description: 'Adjust filters or run an inbound import apply to populate fact_inbound_shipment.',
            primary: { label: 'Data imports', href: '/admin/imports?template=inbound_shipments' },
            secondary: { label: 'Shipment evidence', href: '/admin/shipment-evidence' },
          }}
          toolbar={
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center" sx={{ mb: 2 }}>
              <Button
                size="small"
                variant="outlined"
                startIcon={<ViewColumnIcon />}
                onClick={() => setColDialogOpen(true)}
                data-testid="shipping-additional-columns"
              >
                Additional columns
              </Button>
              <ModuleGridToolbar onRefresh={() => void refetch()} importsHref="/admin/imports?template=inbound_shipments" />
            </Stack>
          }
        >
          <EnterpriseDataGrid
            rowData={lines?.items ?? []}
            columnDefs={colDefs as ColDef[]}
            gridOptions={gridOptions as GridOptions}
            height={520}
          />
        </ModuleDataSection>
      </Paper>

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
