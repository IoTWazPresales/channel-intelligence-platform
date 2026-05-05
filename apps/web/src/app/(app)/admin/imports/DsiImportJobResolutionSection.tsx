'use client';

import type { GridOptions, RowClickedEvent } from 'ag-grid-community';
import type { ColDef } from 'ag-grid-community';
import NextLink from 'next/link';
import Link from '@mui/material/Link';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo, useRef, useState } from 'react';
import { AgGridReact } from 'ag-grid-react';

import { BulkSelectionToolbar, type BulkTableSelectionMode } from '@/components/bulkTable/BulkSelectionToolbar';
import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { apiPost, safeDisplayError } from '@/lib/api';

import {
  DsiCandidateStewardPanel,
  type DsiCandidateRow,
} from '../mappings/DsiCandidateStewardPanel';

type BulkAction = 'ignore' | 'map_customer' | 'map_distributor' | 'resolve_product';

function dsiSourceCustomerNameCell(ctx: Record<string, unknown> | null | undefined): string {
  if (!ctx) return '';
  const s = ctx.source_customer_name_raw_samples;
  if (!Array.isArray(s)) return '';
  return s
    .filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
    .map((x) => x.trim())
    .join('; ');
}

function dsiProductMatchSummaryCell(ctx: Record<string, unknown> | null | undefined): string {
  if (!ctx) return '';
  const sum = ctx.product_match_summary;
  if (typeof sum === 'string' && sum.trim()) return sum.trim();
  return '';
}

type BulkPreviewResponse = {
  import_job_id: number;
  action: BulkAction;
  results: Array<Record<string, unknown>>;
  totals: Record<string, unknown>;
};

type BulkApplyResponse = {
  import_job_id: number;
  action: BulkAction;
  applied: number;
  failed: number;
  results: Array<Record<string, unknown>>;
  totals: Record<string, unknown>;
};

export function DsiImportJobResolutionSection({
  importJobId,
  candidates,
  onInvalidate,
}: {
  importJobId: number;
  candidates: DsiCandidateRow[];
  onInvalidate: () => void;
}) {
  const qc = useQueryClient();
  const gridRef = useRef<AgGridReact<DsiCandidateRow> | null>(null);
  const [detailCandidate, setDetailCandidate] = useState<DsiCandidateRow | null>(null);

  const [bulkMode, setBulkMode] = useState<BulkTableSelectionMode>('normal');
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  const [bulkAction, setBulkAction] = useState<BulkAction>('ignore');
  const [bulkNotes, setBulkNotes] = useState('');
  const [bulkCustomerId, setBulkCustomerId] = useState('');
  const [bulkDistributorId, setBulkDistributorId] = useState('');
  const [bulkProductId, setBulkProductId] = useState('');
  const [bulkRawToken, setBulkRawToken] = useState('');
  const [bulkConfirmIneligible, setBulkConfirmIneligible] = useState(false);
  const [bulkAuditNote, setBulkAuditNote] = useState('');

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewData, setPreviewData] = useState<BulkPreviewResponse | null>(null);
  const [previewApplyToken, setPreviewApplyToken] = useState<string | null>(null);

  const buildBulkBody = useCallback(() => {
    const ids = [...selectedIds];
    const base: Record<string, unknown> = {
      action: bulkAction,
      candidate_ids: ids,
    };
    if (bulkAction === 'ignore') {
      base.notes = bulkNotes.trim() || null;
    }
    if (bulkAction === 'map_customer') {
      base.customer_id = Number(bulkCustomerId);
      base.raw_token = bulkRawToken.trim() || null;
    }
    if (bulkAction === 'map_distributor') {
      base.distributor_id = Number(bulkDistributorId);
      base.raw_token = bulkRawToken.trim() || null;
    }
    if (bulkAction === 'resolve_product') {
      base.product_id = Number(bulkProductId);
      base.raw_token = bulkRawToken.trim() || null;
      base.confirm_ineligible_product = bulkConfirmIneligible;
      base.audit_note = bulkAuditNote.trim() || null;
    }
    return base;
  }, [
    selectedIds,
    bulkAction,
    bulkNotes,
    bulkCustomerId,
    bulkDistributorId,
    bulkProductId,
    bulkRawToken,
    bulkConfirmIneligible,
    bulkAuditNote,
  ]);

  const previewToken = useMemo(() => JSON.stringify(buildBulkBody()), [buildBulkBody]);

  const bulkFormReady = useMemo(() => {
    if (bulkAction === 'ignore') return true;
    if (bulkAction === 'map_customer') {
      return bulkCustomerId.trim() !== '' && Number.isFinite(Number(bulkCustomerId));
    }
    if (bulkAction === 'map_distributor') {
      return bulkDistributorId.trim() !== '' && Number.isFinite(Number(bulkDistributorId));
    }
    if (bulkAction === 'resolve_product') {
      const pid = bulkProductId.trim();
      if (!pid || !Number.isFinite(Number(pid))) return false;
      if (bulkConfirmIneligible && bulkAuditNote.trim().length < 8) return false;
      return true;
    }
    return false;
  }, [
    bulkAction,
    bulkCustomerId,
    bulkDistributorId,
    bulkProductId,
    bulkConfirmIneligible,
    bulkAuditNote,
  ]);

  const bulkPreview = useMutation({
    mutationFn: async () => {
      const body = buildBulkBody();
      return apiPost<BulkPreviewResponse>(
        `/api/v1/mappings/import-jobs/${importJobId}/dsi-steward-bulk-preview`,
        body
      );
    },
    onSuccess: (data) => {
      setPreviewData(data);
      setPreviewApplyToken(previewToken);
      setPreviewOpen(true);
    },
  });

  const bulkApply = useMutation({
    mutationFn: async () => {
      const body = buildBulkBody();
      return apiPost<BulkApplyResponse>(
        `/api/v1/mappings/import-jobs/${importJobId}/dsi-steward-bulk-apply`,
        body
      );
    },
    onSuccess: () => {
      setPreviewOpen(false);
      setPreviewData(null);
      setPreviewApplyToken(null);
      setBulkMode('normal');
      gridRef.current?.api?.deselectAll();
      setSelectedIds([]);
      qc.invalidateQueries({ queryKey: ['distributor-si-candidates', importJobId] });
      qc.invalidateQueries({ queryKey: ['import-job-rows', importJobId] });
      qc.invalidateQueries({ queryKey: ['import-jobs'] });
      onInvalidate();
    },
  });

  const dsiRevalidateFromServer = useMutation({
    mutationFn: async () =>
      apiPost<{ ok: boolean }>(
        `/api/v1/mappings/import-jobs/${importJobId}/revalidate-distributor-sales-inventory`,
        {}
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['distributor-si-candidates', importJobId] });
      void qc.invalidateQueries({ queryKey: ['import-job-rows', importJobId] });
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
      onInvalidate();
    },
  });

  const colDefs = useMemo<ColDef<DsiCandidateRow>[]>(
    () => [
      { field: 'entity_type', headerName: 'Entity type', minWidth: 160 },
      {
        headerName: 'Raw samples',
        minWidth: 160,
        valueGetter: (p) => {
          const s = p.data?.sample_raw_values;
          if (s == null || !Array.isArray(s)) return '';
          return s.filter(Boolean).join('; ');
        },
      },
      { field: 'normalized_key', headerName: 'Normalized', minWidth: 140 },
      { field: 'dealer_group_token', headerName: 'Customer account', minWidth: 120 },
      {
        headerName: 'Source customer',
        minWidth: 140,
        valueGetter: (p) => dsiSourceCustomerNameCell(p.data?.context ?? null),
      },
      {
        headerName: 'Product match',
        minWidth: 160,
        valueGetter: (p) => dsiProductMatchSummaryCell(p.data?.context ?? null),
      },
      { field: 'status', headerName: 'Status', width: 110 },
      { field: 'row_count', headerName: 'Rows', width: 80 },
      { field: 'total_units', headerName: 'Units', width: 90 },
      { field: 'total_reported_value', headerName: 'Value', width: 90 },
    ],
    []
  );

  const onRowClicked = useCallback((e: RowClickedEvent<DsiCandidateRow>) => {
    if (e.data) setDetailCandidate(e.data);
  }, []);

  const gridOptions = useMemo<GridOptions<DsiCandidateRow>>(
    () => ({
      rowSelection: {
        mode: 'multiRow',
        checkboxes: true,
        headerCheckbox: true,
        enableClickSelection: false,
      },
      onSelectionChanged: (e) => {
        const rows = e.api.getSelectedRows() as DsiCandidateRow[];
        setSelectedIds(rows.map((r) => r.id));
      },
      onRowClicked,
    }),
    [onRowClicked]
  );

  const applyReady = previewApplyToken !== null && previewApplyToken === previewToken && previewData !== null;

  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid="dsi-import-job-resolution">
      <Stack spacing={2}>
        <Typography variant="subtitle2">Resolve blockers for this import</Typography>
        <Alert severity="info">
          <Typography variant="body2" component="div">
            <strong>Validate → Resolve → Revalidate → Apply</strong>: steward actions call the same APIs as the global{' '}
            <Link component={NextLink} href={`/admin/mappings?import_job_id=${importJobId}`}>
              Mapping queue
            </Link>
            . Click a row for single-row actions; use bulk mode for many candidates. Preview before apply.
          </Typography>
        </Alert>

        <EnterpriseDataGrid
          ref={gridRef}
          rowData={candidates}
          columnDefs={colDefs}
          height={360}
          gridOptions={gridOptions}
        />

        <BulkSelectionToolbar
          mode={bulkMode}
          selectedCount={selectedIds.length}
          visibleRowCount={candidates.length}
          onEnterSelectionMode={() => setBulkMode('selecting')}
          onExitSelectionMode={() => {
            setBulkMode('normal');
            gridRef.current?.api?.deselectAll();
            setSelectedIds([]);
          }}
          onSelectAllVisible={() => {
            gridRef.current?.api?.selectAll();
          }}
          onDeselectAll={() => {
            gridRef.current?.api?.deselectAll();
            setSelectedIds([]);
          }}
          busy={bulkPreview.isPending || bulkApply.isPending}
          previewDangerLabel="Preview bulk steward"
          previewDangerDisabled={
            selectedIds.length === 0 || bulkPreview.isPending || !bulkFormReady
          }
          onPreviewDangerAction={() => void bulkPreview.mutateAsync()}
        />

        {bulkMode === 'selecting' ? (
          <Stack spacing={2} data-testid="dsi-bulk-action-form">
            <Typography variant="caption" color="text.secondary">
              Bulk raw-token override is optional; leave blank so each row keeps its own candidate samples (same as
              single-row steward).
            </Typography>
            <FormControl size="small" fullWidth>
              <InputLabel id="dsi-bulk-action">Bulk action</InputLabel>
              <Select
                labelId="dsi-bulk-action"
                label="Bulk action"
                value={bulkAction}
                onChange={(e) => setBulkAction(e.target.value as BulkAction)}
              >
                <MenuItem value="ignore">Ignore candidate</MenuItem>
                <MenuItem value="map_customer">Map to existing customer</MenuItem>
                <MenuItem value="map_distributor">Map to existing distributor</MenuItem>
                <MenuItem value="resolve_product">Resolve product (ProductAlias)</MenuItem>
              </Select>
            </FormControl>
            {bulkAction === 'ignore' ? (
              <TextField
                label="Notes (optional)"
                value={bulkNotes}
                onChange={(e) => setBulkNotes(e.target.value)}
                fullWidth
                size="small"
              />
            ) : null}
            {bulkAction === 'map_customer' ? (
              <TextField
                label="Customer id"
                value={bulkCustomerId}
                onChange={(e) => setBulkCustomerId(e.target.value)}
                type="number"
                required
                fullWidth
                size="small"
              />
            ) : null}
            {bulkAction === 'map_distributor' ? (
              <TextField
                label="Distributor id"
                value={bulkDistributorId}
                onChange={(e) => setBulkDistributorId(e.target.value)}
                type="number"
                required
                fullWidth
                size="small"
              />
            ) : null}
            {bulkAction === 'resolve_product' ? (
              <Stack spacing={1}>
                <TextField
                  label="Product id"
                  value={bulkProductId}
                  onChange={(e) => setBulkProductId(e.target.value)}
                  type="number"
                  required
                  fullWidth
                  size="small"
                />
                <label>
                  <input
                    type="checkbox"
                    checked={bulkConfirmIneligible}
                    onChange={(e) => setBulkConfirmIneligible(e.target.checked)}
                  />{' '}
                  Confirm inactive/ineligible product (requires audit note)
                </label>
                <TextField
                  label="Audit note (when confirming inactive)"
                  value={bulkAuditNote}
                  onChange={(e) => setBulkAuditNote(e.target.value)}
                  fullWidth
                  size="small"
                  multiline
                  minRows={2}
                />
              </Stack>
            ) : null}
            {(bulkAction === 'map_customer' || bulkAction === 'map_distributor' || bulkAction === 'resolve_product') ? (
              <TextField
                label="Raw token override for all selected (optional)"
                value={bulkRawToken}
                onChange={(e) => setBulkRawToken(e.target.value)}
                fullWidth
                size="small"
              />
            ) : null}
            <Typography variant="caption" color="text.secondary">
              Use <strong>Preview bulk steward</strong> in the toolbar above, then <strong>Apply bulk steward</strong>{' '}
              here or in the preview dialog after reviewing rows.
            </Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Button
                variant="contained"
                disabled={!applyReady || bulkApply.isPending || !bulkFormReady}
                onClick={() => void bulkApply.mutateAsync()}
                data-testid="dsi-bulk-apply"
              >
                Apply bulk steward
              </Button>
            </Stack>
          </Stack>
        ) : null}

        {bulkPreview.isError ? (
          <Alert severity="error">{safeDisplayError(bulkPreview.error)}</Alert>
        ) : null}
        {bulkApply.isError ? <Alert severity="error">{safeDisplayError(bulkApply.error)}</Alert> : null}

        <Typography variant="caption" color="text.secondary">
          Single-row steward (selected grid row)
        </Typography>
        <DsiCandidateStewardPanel
          importJobId={importJobId}
          candidate={detailCandidate}
          onDone={() => {
            void qc.invalidateQueries({ queryKey: ['distributor-si-candidates', importJobId] });
            onInvalidate();
          }}
        />

        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
          <Button
            variant="outlined"
            disabled={dsiRevalidateFromServer.isPending}
            onClick={() => void dsiRevalidateFromServer.mutateAsync()}
            data-testid="dsi-import-revalidate-server"
          >
            {dsiRevalidateFromServer.isPending ? 'Re-running server validation…' : 'Re-run validation from server'}
          </Button>
          <Typography variant="caption" color="text.secondary">
            Run after bulk or single-row steward saves so staging refreshes.
          </Typography>
        </Stack>
        {dsiRevalidateFromServer.isError ? (
          <Alert severity="error">{safeDisplayError(dsiRevalidateFromServer.error)}</Alert>
        ) : null}

      </Stack>

      <Dialog open={previewOpen} onClose={() => setPreviewOpen(false)} fullWidth maxWidth="lg">
        <DialogTitle>Bulk steward preview</DialogTitle>
        <DialogContent>
          {previewData ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="body2">
                Action <strong>{previewData.action}</strong> · ok count{' '}
                <strong>{String(previewData.totals?.ok_count ?? '—')}</strong> · staging rows (ok){' '}
                <strong>{String(previewData.totals?.staging_rows_affected ?? '—')}</strong>
              </Typography>
              <Table size="small" data-testid="dsi-bulk-preview-table">
                <TableHead>
                  <TableRow>
                    <TableCell>ID</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>Ok</TableCell>
                    <TableCell>Detail</TableCell>
                    <TableCell align="right">Rows</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {previewData.results.map((r) => (
                    <TableRow key={String(r.candidate_id)}>
                      <TableCell>{String(r.candidate_id)}</TableCell>
                      <TableCell>{String(r.entity_type ?? '')}</TableCell>
                      <TableCell>{String(r.ok)}</TableCell>
                      <TableCell>{String(r.detail ?? r.skip_reason ?? '')}</TableCell>
                      <TableCell align="right">{String(r.row_count ?? '')}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreviewOpen(false)}>Close</Button>
          <Button
            variant="contained"
            disabled={!applyReady || bulkApply.isPending || !bulkFormReady}
            onClick={() => void bulkApply.mutateAsync()}
          >
            Apply
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}
