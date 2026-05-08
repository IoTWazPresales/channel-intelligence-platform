'use client';

import ViewColumnIcon from '@mui/icons-material/ViewColumn';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  MenuItem,
  Paper,
  Stack,
  TablePagination,
  TextField,
  Typography,
} from '@mui/material';
import type { ColDef, RowClickedEvent, ValueGetterParams } from 'ag-grid-community';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { apiGet } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

import {
  SHIPMENT_EVIDENCE_OPTIONAL_FIELDS,
  ShipmentEvidenceColumnsDialog,
} from './ShipmentEvidenceColumnsDialog';

const LS_GRID = 'cip.admin.shipment-evidence.grid.v1';
const PAGE_SIZE_OPTIONS = [25, 50, 100, 250, 500, 1000] as const;

export type ShipmentEvidenceGridRow = {
  id: number;
  import_job_id: number;
  source_sheet: string | null;
  source_row_number: number;
  report_type: string;
  line_state: string;
  operating_unit?: string | null;
  bill_to_raw: string | null;
  ship_to_raw?: string | null;
  order_no?: string | null;
  order_line?: string | null;
  delivery_no: string | null;
  invoice_line?: string | null;
  item_code: string | null;
  sales_model_name: string | null;
  customer_item?: string | null;
  ean_code?: string | null;
  upc_code?: string | null;
  mpor_item_no?: string | null;
  quantity: number | null;
  unit_price?: number | null;
  amount: number | null;
  currency_code: string | null;
  ship_confirm_date: string | null;
  schedule_ship_date?: string | null;
  promise_date?: string | null;
  exwork_date?: string | null;
  erd_date?: string | null;
  product_id?: number | null;
  product_sku: string | null;
  product_resolution_status: string;
  product_resolution_token?: string | null;
  product_resolution_detail?: string | null;
  distributor_id?: number | null;
  distributor_code: string | null;
  distributor_resolution_status: string;
  distributor_resolution_token?: string | null;
  created_at?: string | null;
  raw_source_row?: Record<string, unknown>;
};

type ListResponse = { total: number; skip: number; limit: number; items: ShipmentEvidenceGridRow[] };

type DetailResponse = ShipmentEvidenceGridRow & {
  raw_source_row: Record<string, unknown>;
  import_job_file_name: string | null;
  import_job_status: string | null;
};

type RawKeysResponse = { import_job_id: number; keys: string[] };

function formatRawCell(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

function buildListUrl(params: {
  skip: number;
  limit: number;
  importJobId: string;
  lineState: string;
  reportType: string;
  productStatus: string;
  distStatus: string;
  search: string;
  includeRawRow: boolean;
}): string {
  const q = new URLSearchParams();
  q.set('skip', String(params.skip));
  q.set('limit', String(params.limit));
  if (params.importJobId.trim()) q.set('import_job_id', params.importJobId.trim());
  if (params.lineState) q.set('line_state', params.lineState);
  if (params.reportType) q.set('report_type', params.reportType);
  if (params.productStatus) q.set('product_resolution_status', params.productStatus);
  if (params.distStatus) q.set('distributor_resolution_status', params.distStatus);
  if (params.search.trim()) q.set('search', params.search.trim());
  if (params.includeRawRow) q.set('include_raw_row', 'true');
  return `/api/v1/shipment-evidence?${q.toString()}`;
}

export default function ShipmentEvidenceAdminPage() {
  const [skip, setSkip] = useState(0);
  const [limit, setLimit] = useState(100);
  const [importJobId, setImportJobId] = useState('');
  const [lineState, setLineState] = useState('');
  const [reportType, setReportType] = useState('');
  const [productStatus, setProductStatus] = useState('');
  const [distStatus, setDistStatus] = useState('');
  const [search, setSearch] = useState('');
  const [detailId, setDetailId] = useState<number | null>(null);
  const [colDialogOpen, setColDialogOpen] = useState(false);
  const [optionalFields, setOptionalFields] = useState<string[]>([]);
  const [rawKeys, setRawKeys] = useState<string[]>([]);
  const [persistReady, setPersistReady] = useState(false);

  const parsedJobId = useMemo(() => {
    const t = importJobId.trim();
    if (!t) return null;
    const n = Number(t);
    return Number.isFinite(n) && n > 0 ? n : null;
  }, [importJobId]);

  const includeRawRow = rawKeys.length > 0;

  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_GRID);
      if (raw) {
        const p = JSON.parse(raw) as {
          version?: number;
          optionalFields?: string[];
          rawKeys?: string[];
          pageSize?: number;
        };
        const allowed = new Set(SHIPMENT_EVIDENCE_OPTIONAL_FIELDS.map((c) => c.field));
        if (Array.isArray(p.optionalFields)) {
          setOptionalFields(p.optionalFields.filter((f) => allowed.has(f)));
        }
        if (Array.isArray(p.rawKeys)) setRawKeys(p.rawKeys);
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
    if (!persistReady) return;
    try {
      localStorage.setItem(
        LS_GRID,
        JSON.stringify({ version: 1, optionalFields, rawKeys, pageSize: limit })
      );
    } catch {
      /* ignore */
    }
  }, [optionalFields, rawKeys, limit, persistReady]);

  const listUrl = useMemo(
    () =>
      buildListUrl({
        skip,
        limit,
        importJobId,
        lineState,
        reportType,
        productStatus,
        distStatus,
        search,
        includeRawRow,
      }),
    [skip, limit, importJobId, lineState, reportType, productStatus, distStatus, search, includeRawRow]
  );

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['shipment-evidence', listUrl],
    queryFn: ({ signal }) => apiGet<ListResponse>(listUrl, { signal }),
  });

  const { data: detail } = useQuery({
    queryKey: ['shipment-evidence-detail', detailId],
    queryFn: ({ signal }) => apiGet<DetailResponse>(`/api/v1/shipment-evidence/${detailId}`, { signal }),
    enabled: detailId != null,
  });

  const rawKeysUrl =
    parsedJobId != null ? `/api/v1/shipment-evidence/raw-column-keys?import_job_id=${parsedJobId}` : '';

  const { data: rawKeysData, isFetching: rawKeysFetching } = useQuery({
    queryKey: ['shipment-evidence-raw-keys', parsedJobId],
    queryFn: ({ signal }) => apiGet<RawKeysResponse>(rawKeysUrl, { signal }),
    enabled: parsedJobId != null,
  });

  const catalogKeys = rawKeysData?.keys ?? [];

  useEffect(() => {
    if (parsedJobId == null || rawKeysData == null) return;
    const allowed = new Set(rawKeysData.keys);
    setRawKeys((prev) => prev.filter((k) => allowed.has(k)));
  }, [parsedJobId, rawKeysData]);

  const baseColDefs: ColDef<ShipmentEvidenceGridRow>[] = useMemo(
    () => [
      { field: 'id', headerName: 'ID', width: 90, pinned: 'left' },
      { field: 'import_job_id', headerName: 'Job', width: 90 },
      { field: 'source_sheet', headerName: 'Sheet', minWidth: 100 },
      { field: 'source_row_number', headerName: 'Row', width: 80 },
      { field: 'line_state', headerName: 'Line state', minWidth: 120 },
      { field: 'report_type', headerName: 'Report', minWidth: 180 },
      { field: 'bill_to_raw', headerName: 'Bill to', minWidth: 140 },
      { field: 'item_code', headerName: 'Item', minWidth: 130 },
      { field: 'sales_model_name', headerName: 'Sales model', minWidth: 160 },
      { field: 'product_resolution_status', headerName: 'Product status', minWidth: 140 },
      { field: 'product_sku', headerName: 'PM SKU', minWidth: 120 },
      { field: 'distributor_resolution_status', headerName: 'Dist. status', minWidth: 120 },
      { field: 'distributor_code', headerName: 'Distributor', minWidth: 120 },
      { field: 'quantity', headerName: 'Qty', width: 90 },
      { field: 'amount', headerName: 'Amount', width: 100 },
      { field: 'currency_code', headerName: 'CCY', width: 70 },
      { field: 'ship_confirm_date', headerName: 'Ship confirm', minWidth: 120 },
    ],
    []
  );

  const optionalColDefs = useMemo(() => {
    return optionalFields.map((f) => {
      const meta = SHIPMENT_EVIDENCE_OPTIONAL_FIELDS.find((x) => x.field === f);
      const wide = f.includes('detail') || f.includes('token');
      return {
        field: f as keyof ShipmentEvidenceGridRow & string,
        headerName: meta?.label ?? f,
        minWidth: wide ? 220 : 130,
      } satisfies ColDef<ShipmentEvidenceGridRow>;
    });
  }, [optionalFields]);

  const rawColDefs = useMemo(() => {
    return rawKeys.map((k) => ({
      colId: `raw:${k}`,
      headerName: k,
      valueGetter: (p: ValueGetterParams<ShipmentEvidenceGridRow>) => formatRawCell(p.data?.raw_source_row?.[k]),
      minWidth: 140,
      sortable: true,
      filter: true,
    })) satisfies ColDef<ShipmentEvidenceGridRow>[];
  }, [rawKeys]);

  const colDefs = useMemo(
    () => [...baseColDefs, ...optionalColDefs, ...rawColDefs],
    [baseColDefs, optionalColDefs, rawColDefs]
  );

  const onRowClicked = useCallback((e: RowClickedEvent<ShipmentEvidenceGridRow>) => {
    if (e.data?.id != null) setDetailId(e.data.id);
  }, []);

  const gridOptions = useMemo(
    () => ({
      onRowClicked,
      getRowId: (p: { data: ShipmentEvidenceGridRow }) => String(p.data.id),
    }),
    [onRowClicked]
  );

  const total = data?.total ?? 0;
  const page = limit > 0 ? Math.floor(skip / limit) : 0;
  const pageCount = Math.max(0, Math.ceil(total / limit) - 1);

  return (
    <Box sx={{ p: 2 }}>
      <PageHeader
        crumbs={[
          { label: 'Data imports', href: '/admin/imports' },
          { label: 'Shipment evidence' },
        ]}
        title="Shipment & order evidence"
      />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: 900 }}>
        Canonical lines from shipment / open-order imports (report auto-detect). Upload via Data imports using
        template &quot;Shipment / order evidence&quot;.
      </Typography>

      <Stack spacing={2} sx={{ mt: 2 }}>
        <Alert severity="info">
          Use{' '}
          <Link href="/admin/imports?template=inbound_shipments">Data imports → Shipment / order evidence</Link> to
          load CSV or XLSX. This grid is read-only; re-run the import job to refresh rows.
        </Alert>

        <Paper sx={{ p: 2 }}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} flexWrap="wrap">
            <TextField
              size="small"
              label="Search"
              value={search}
              onChange={(e) => {
                setSkip(0);
                setSearch(e.target.value);
              }}
              sx={{ minWidth: 220 }}
            />
            <TextField
              size="small"
              label="Import job ID"
              value={importJobId}
              onChange={(e) => {
                setSkip(0);
                setImportJobId(e.target.value);
              }}
              sx={{ width: 140 }}
            />
            <TextField
              select
              size="small"
              label="Line state"
              value={lineState}
              onChange={(e) => {
                setSkip(0);
                setLineState(e.target.value);
              }}
              sx={{ width: 160 }}
            >
              <MenuItem value="">(any)</MenuItem>
              <MenuItem value="shipped">shipped</MenuItem>
              <MenuItem value="open_order">open_order</MenuItem>
            </TextField>
            <TextField
              select
              size="small"
              label="Report type"
              value={reportType}
              onChange={(e) => {
                setSkip(0);
                setReportType(e.target.value);
              }}
              sx={{ width: 220 }}
            >
              <MenuItem value="">(any)</MenuItem>
              <MenuItem value="xxomrpt0025_shipment">xxomrpt0025_shipment</MenuItem>
              <MenuItem value="xxomrpt0027_order">xxomrpt0027_order</MenuItem>
              <MenuItem value="acza_workbook_shipped">acza_workbook_shipped</MenuItem>
              <MenuItem value="acza_workbook_unship">acza_workbook_unship</MenuItem>
            </TextField>
            <TextField
              select
              size="small"
              label="Product resolution"
              value={productStatus}
              onChange={(e) => {
                setSkip(0);
                setProductStatus(e.target.value);
              }}
              sx={{ width: 200 }}
            >
              <MenuItem value="">(any)</MenuItem>
              <MenuItem value="resolved_unique">resolved_unique</MenuItem>
              <MenuItem value="ambiguous">ambiguous</MenuItem>
              <MenuItem value="inactive_only">inactive_only</MenuItem>
              <MenuItem value="no_match">no_match</MenuItem>
              <MenuItem value="no_identifier">no_identifier</MenuItem>
            </TextField>
            <TextField
              select
              size="small"
              label="Distributor resolution"
              value={distStatus}
              onChange={(e) => {
                setSkip(0);
                setDistStatus(e.target.value);
              }}
              sx={{ width: 200 }}
            >
              <MenuItem value="">(any)</MenuItem>
              <MenuItem value="resolved">resolved</MenuItem>
              <MenuItem value="unresolved">unresolved</MenuItem>
              <MenuItem value="skipped_empty">skipped_empty</MenuItem>
            </TextField>
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
          />
        </Paper>

        <ModuleDataSection
          title="Evidence lines"
          description="Click a row to open raw source JSON and resolution tokens."
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={!isLoading && (data?.items?.length ?? 0) === 0}
          emptyState={{
            title: 'No evidence rows yet',
            description: 'Run a Shipment / order evidence import job first.',
          }}
          toolbar={
            <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
              <Button
                size="small"
                variant="outlined"
                startIcon={<ViewColumnIcon />}
                onClick={() => setColDialogOpen(true)}
                data-testid="shipment-evidence-columns"
              >
                Additional columns
              </Button>
              <ModuleGridToolbar
                importsHref="/admin/imports?template=inbound_shipments"
                onRefresh={() => void refetch()}
              />
            </Stack>
          }
        >
          <EnterpriseDataGrid
            rowData={data?.items ?? []}
            columnDefs={colDefs}
            gridOptions={gridOptions}
            height={520}
          />
        </ModuleDataSection>
      </Stack>

      <ShipmentEvidenceColumnsDialog
        open={colDialogOpen}
        onClose={() => setColDialogOpen(false)}
        optionalFields={optionalFields}
        onOptionalFieldsChange={setOptionalFields}
        rawKeys={rawKeys}
        onRawKeysChange={setRawKeys}
        catalogKeys={catalogKeys}
        catalogLoading={parsedJobId != null && rawKeysFetching}
        importJobIdFilter={importJobId}
      />

      <Dialog open={detailId != null} onClose={() => setDetailId(null)} maxWidth="md" fullWidth>
        <DialogTitle>Evidence line {detailId}</DialogTitle>
        <DialogContent>
          {detail ? (
            <Stack spacing={1}>
              <Typography variant="body2">
                Job {detail.import_job_id} — {detail.import_job_file_name ?? '—'} ({detail.import_job_status ?? '—'})
              </Typography>
              <Typography variant="body2">
                Product: {detail.product_resolution_status}
                {detail.product_resolution_token ? ` · token: ${detail.product_resolution_token}` : ''}
              </Typography>
              {detail.product_resolution_detail ? (
                <Typography variant="caption" color="text.secondary">
                  {detail.product_resolution_detail}
                </Typography>
              ) : null}
              <Typography variant="body2">
                Distributor: {detail.distributor_resolution_status}
                {detail.distributor_resolution_token ? ` · token: ${detail.distributor_resolution_token}` : ''}
              </Typography>
              <Typography variant="subtitle2" sx={{ mt: 1 }}>
                Raw source row
              </Typography>
              <Paper variant="outlined" sx={{ p: 1, maxHeight: 360, overflow: 'auto' }}>
                <pre style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(detail.raw_source_row, null, 2)}
                </pre>
              </Paper>
              <Button variant="outlined" onClick={() => setDetailId(null)}>
                Close
              </Button>
            </Stack>
          ) : (
            <Typography variant="body2">Loading…</Typography>
          )}
        </DialogContent>
      </Dialog>
    </Box>
  );
}
