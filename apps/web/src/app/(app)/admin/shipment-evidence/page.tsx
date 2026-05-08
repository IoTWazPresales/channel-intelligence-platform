'use client';

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
  TextField,
  Typography,
} from '@mui/material';
import type { ColDef, RowClickedEvent } from 'ag-grid-community';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { apiGet } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type ShipmentEvidenceRow = {
  id: number;
  import_job_id: number;
  source_sheet: string | null;
  source_row_number: number;
  report_type: string;
  line_state: string;
  bill_to_raw: string | null;
  ship_to_raw: string | null;
  order_no: string | null;
  delivery_no: string | null;
  item_code: string | null;
  sales_model_name: string | null;
  quantity: number | null;
  amount: number | null;
  currency_code: string | null;
  ship_confirm_date: string | null;
  product_id: number | null;
  product_sku: string | null;
  product_resolution_status: string;
  distributor_id: number | null;
  distributor_code: string | null;
  distributor_resolution_status: string;
};

type ListResponse = { total: number; skip: number; limit: number; items: ShipmentEvidenceRow[] };

type DetailResponse = ShipmentEvidenceRow & {
  raw_source_row: Record<string, unknown>;
  import_job_file_name: string | null;
  import_job_status: string | null;
  product_resolution_token: string | null;
  product_resolution_detail: string | null;
  distributor_resolution_token: string | null;
};

function buildListUrl(params: {
  skip: number;
  limit: number;
  importJobId: string;
  lineState: string;
  reportType: string;
  productStatus: string;
  distStatus: string;
  search: string;
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
  return `/api/v1/shipment-evidence?${q.toString()}`;
}

export default function ShipmentEvidenceAdminPage() {
  const [skip, setSkip] = useState(0);
  const limit = 100;
  const [importJobId, setImportJobId] = useState('');
  const [lineState, setLineState] = useState('');
  const [reportType, setReportType] = useState('');
  const [productStatus, setProductStatus] = useState('');
  const [distStatus, setDistStatus] = useState('');
  const [search, setSearch] = useState('');
  const [detailId, setDetailId] = useState<number | null>(null);

  const listUrl = useMemo(
    () => buildListUrl({ skip, limit, importJobId, lineState, reportType, productStatus, distStatus, search }),
    [skip, importJobId, lineState, reportType, productStatus, distStatus, search]
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

  const colDefs: ColDef<ShipmentEvidenceRow>[] = useMemo(
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

  const onRowClicked = useCallback((e: RowClickedEvent<ShipmentEvidenceRow>) => {
    if (e.data?.id != null) setDetailId(e.data.id);
  }, []);

  const gridOptions = useMemo(() => ({ onRowClicked }), [onRowClicked]);

  const total = data?.total ?? 0;
  const canPrev = skip > 0;
  const canNext = skip + limit < total;

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
          <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
            <Button size="small" disabled={!canPrev} onClick={() => setSkip((s) => Math.max(0, s - limit))}>
              Previous
            </Button>
            <Button size="small" disabled={!canNext} onClick={() => setSkip((s) => s + limit)}>
              Next
            </Button>
            <Typography variant="body2" sx={{ alignSelf: 'center', ml: 1 }}>
              Showing {data?.items?.length ?? 0} of {total} (skip {skip})
            </Typography>
          </Stack>
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
            <ModuleGridToolbar
              importsHref="/admin/imports?template=inbound_shipments"
              onRefresh={() => void refetch()}
            />
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
