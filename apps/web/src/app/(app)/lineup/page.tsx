'use client';

import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Link,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { CellValueChangedEvent, ColDef, GridOptions, RowClickedEvent } from 'ag-grid-community';
import NextLink from 'next/link';
import type { ChangeEvent } from 'react';
import { useCallback, useMemo, useRef, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { apiDelete, apiGet, apiPatch, apiPost } from '@/lib/api';
import { parseLineupImportCsv } from '@/lib/lineupImportCsv';
import { toQueryError } from '@/lib/queryError';

type Row = {
  id: number;
  customer_code: string | null;
  customer_name?: string | null;
  channel_code: string | null;
  period_start: string;
  period_label: string | null;
  sku: string | null;
  product_name?: string | null;
  predecessor_sku: string | null;
  successor_sku: string | null;
  current_range_summary: string | null;
  planned_range_summary: string | null;
  planned_launch_date: string | null;
  planned_eol_date: string | null;
  current_volume_units: number | null;
  planned_volume_units: number;
  overlap_cannibalization_flag: boolean;
  whitespace_gap_flag: boolean;
  approval_status: string;
  link_buy_plan_id: number | null;
  link_pricing_id: number | null;
  link_promotion_id: number | null;
  link_budget_request_id: number | null;
  link_roadmap_id: number | null;
  notes?: string | null;
};

const APPROVAL_STATUSES = ['draft', 'pending_approval', 'submitted', 'approved', 'rejected'] as const;

type LineupBulkResponse = {
  inserted: number;
  updated: number;
  skipped: number;
  errors: number;
  results: Array<{ row_index: number; status: string; id?: number; errors: string[] }>;
};

type LineupEventRow = {
  id: number;
  event_type: string;
  old_approval_status: string | null;
  new_approval_status: string | null;
  notes: string | null;
  actor: string | null;
  created_at: string | null;
};

export default function LineupPage() {
  const qc = useQueryClient();
  const [patchMsg, setPatchMsg] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState('');
  const [replaceMatching, setReplaceMatching] = useState(false);
  const [importParseMsg, setImportParseMsg] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['lineup-items'],
    queryFn: ({ signal }) => apiGet<Row[]>('/api/v1/lineup/items', { signal }),
  });

  const delRow = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/lineup/items/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lineup-items'] }),
  });
  const clearAll = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/lineup/items/clear-all', { confirm: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lineup-items'] }),
  });

  const bulkImport = useMutation({
    mutationFn: (body: { rows: unknown[]; replace_matching: boolean }) =>
      apiPost<LineupBulkResponse>('/api/v1/lineup/items/bulk', body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['lineup-items'] });
      void qc.invalidateQueries({ queryKey: ['lineup-events'] });
    },
  });

  const { data: eventRows } = useQuery({
    queryKey: ['lineup-events', selectedId],
    queryFn: ({ signal }) => apiGet<LineupEventRow[]>(`/api/v1/lineup/items/${selectedId}/events`, { signal }),
    enabled: selectedId != null,
  });

  const onCellValueChanged = useCallback(
    async (e: CellValueChangedEvent<Row>) => {
      const id = e.data?.id;
      if (id == null || e.oldValue === e.newValue) return;
      const field = e.colDef.field;
      setPatchMsg(null);
      try {
        if (field === 'approval_status') {
          await apiPatch(`/api/v1/lineup/items/${id}`, {
            approval_status: String(e.newValue ?? ''),
            notes: e.data?.notes ?? null,
          });
        } else if (field === 'notes') {
          await apiPatch(`/api/v1/lineup/items/${id}`, { notes: String(e.newValue ?? '') || null });
        } else {
          return;
        }
        await qc.invalidateQueries({ queryKey: ['lineup-items'] });
      } catch (err) {
        console.error(err);
        setPatchMsg(err instanceof Error ? err.message : String(err));
        await qc.invalidateQueries({ queryKey: ['lineup-items'] });
      }
    },
    [qc]
  );

  const colDefs: ColDef<Row>[] = useMemo(() => {
    const busyDel = delRow.isPending || clearAll.isPending;
    return [
      { field: 'customer_code', headerName: 'Customer', pinned: 'left', minWidth: 120, editable: false },
      {
        field: 'customer_name',
        headerName: 'Customer name',
        minWidth: 160,
        editable: false,
        valueGetter: (p) => p.data?.customer_name ?? '',
      },
      { field: 'channel_code', headerName: 'Channel', minWidth: 100, editable: false },
      { field: 'period_label', headerName: 'Period label', minWidth: 110, editable: false },
      { field: 'period_start', headerName: 'Period start', minWidth: 120, editable: false },
      { field: 'sku', headerName: 'SKU', minWidth: 120, editable: false },
      {
        field: 'product_name',
        headerName: 'Product',
        minWidth: 160,
        editable: false,
        valueGetter: (p) => p.data?.product_name ?? '',
      },
      { field: 'predecessor_sku', headerName: 'Predecessor', minWidth: 120, editable: false },
      { field: 'successor_sku', headerName: 'Successor', minWidth: 120, editable: false },
      { field: 'current_range_summary', headerName: 'Current range', flex: 1, minWidth: 180, editable: false },
      { field: 'planned_range_summary', headerName: 'Planned range', flex: 1, minWidth: 180, editable: false },
      { field: 'planned_launch_date', headerName: 'Launch', minWidth: 120, editable: false },
      { field: 'planned_eol_date', headerName: 'EOL', minWidth: 120, editable: false },
      { field: 'current_volume_units', headerName: 'Vol (current)', minWidth: 130, editable: false },
      { field: 'planned_volume_units', headerName: 'Vol (plan)', minWidth: 120, editable: false },
      { field: 'overlap_cannibalization_flag', headerName: 'Overlap', minWidth: 110, editable: false },
      { field: 'whitespace_gap_flag', headerName: 'Whitespace', minWidth: 120, editable: false },
      {
        field: 'approval_status',
        headerName: 'Approval',
        minWidth: 160,
        editable: true,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: [...APPROVAL_STATUSES] },
      },
      {
        field: 'notes',
        headerName: 'Notes',
        flex: 1,
        minWidth: 200,
        editable: true,
      },
      { field: 'link_buy_plan_id', headerName: 'Buy plan id', minWidth: 120, editable: false },
      { field: 'link_pricing_id', headerName: 'Pricing id', minWidth: 110, editable: false },
      { field: 'link_promotion_id', headerName: 'Promo id', minWidth: 100, editable: false },
      { field: 'link_budget_request_id', headerName: 'Budget req id', minWidth: 130, editable: false },
      { field: 'link_roadmap_id', headerName: 'Roadmap id', minWidth: 110, editable: false },
      gridDeleteColumn<Row>((id) => void delRow.mutate(id), { busy: busyDel }),
    ];
  }, [delRow, delRow.isPending, clearAll.isPending]);

  const onRowClicked = useCallback((e: RowClickedEvent<Row>) => {
    const id = e.data?.id;
    setSelectedId(id != null ? id : null);
  }, []);

  const gridOptions: GridOptions<Row> = useMemo(
    () => ({
      singleClickEdit: true,
      onCellValueChanged,
      onRowClicked,
      getRowStyle: (p) =>
        p.data?.id != null && p.data.id === selectedId
          ? { backgroundColor: 'rgba(25, 118, 210, 0.12)' }
          : undefined,
    }),
    [onCellValueChanged, onRowClicked, selectedId]
  );

  const runImport = useCallback(() => {
    setImportParseMsg(null);
    const parsed = parseLineupImportCsv(importText);
    if (parsed.headerErrors.length) {
      setImportParseMsg(parsed.headerErrors.join('\n'));
      return;
    }
    if (parsed.rows.length === 0) {
      setImportParseMsg('No data rows to import after parsing.');
      return;
    }
    const warn =
      parsed.parseWarnings.length > 0
        ? `${parsed.parseWarnings.length} parse warning(s); first: ${parsed.parseWarnings[0]!.message}`
        : null;
    if (warn) setImportParseMsg(warn);
    void bulkImport.mutateAsync({ rows: parsed.rows, replace_matching: replaceMatching }).then(
      () => {
        setImportOpen(false);
        setImportText('');
      },
      (err) => {
        setImportParseMsg(err instanceof Error ? err.message : String(err));
      }
    );
  }, [bulkImport, importText, replaceMatching]);

  const onCsvFile = useCallback((ev: ChangeEvent<HTMLInputElement>) => {
    const f = ev.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => setImportText(String(reader.result ?? ''));
    reader.readAsText(f, 'UTF-8');
    ev.target.value = '';
  }, []);

  const rows = data ?? [];

  return (
    <>
      <PageHeader crumbs={[{ label: 'Planning' }, { label: 'Line-up planning' }]} title="Line-up planning" />
      <Alert severity="info" sx={{ mb: 2 }}>
        <Typography variant="body2" component="div">
          <strong>Line-up</strong> is customer / channel / period assortment planning with optional links to buy plans,
          pricing, <Link component={NextLink} href="/promotions">promotions</Link> (see CPOR export tab), budgets, and{' '}
          <Link component={NextLink} href="/roadmap">
            roadmap
          </Link>
          . Use <strong>Bulk CSV import</strong> to upsert rows (optional replace). Click a row to inspect{' '}
          <strong>approval history</strong>. Edit <strong>Approval</strong> or <strong>Notes</strong> inline; other
          columns stay read-only until deeper edit flows land.
        </Typography>
      </Alert>
      {patchMsg ? (
        <Alert severity="warning" sx={{ mb: 2 }} onClose={() => setPatchMsg(null)}>
          {patchMsg}
        </Alert>
      ) : null}
      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          intro={
            <Stack spacing={1}>
              <span>
                Rows map to <code>fact_lineup_plan_item</code>. Use <strong>Delete</strong> or{' '}
                <strong>Clear all rows</strong> for demo cleanup. For promo-linked rows, follow export workflow on{' '}
                <Link component={NextLink} href="/promotions">
                  Promotions → CPOR export & approval
                </Link>
                .
              </span>
            </Stack>
          }
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={rows.length === 0}
          empty={{
            title: 'No line-up plan rows',
            description:
              'Line-up rows appear when fact_lineup_plan_item is populated via imports or internal planning writes.',
            primary: { label: 'Data imports', href: '/admin/imports' },
            secondary: { label: 'Buy plans', href: '/buy-plans' },
          }}
          toolbar={
            <ModuleGridToolbar
              onRefresh={() => qc.invalidateQueries({ queryKey: ['lineup-items'] })}
              onUpload={() => {
                setImportParseMsg(null);
                setImportOpen(true);
              }}
              uploadLabel="Bulk CSV import"
              onClearAll={() => {
                if (!window.confirm('Delete every line-up plan row? This cannot be undone.')) return;
                void clearAll.mutate();
              }}
              importsHref="/admin/imports"
              busy={delRow.isPending || clearAll.isPending || bulkImport.isPending}
            />
          }
        >
          <EnterpriseDataGrid rowData={rows} columnDefs={colDefs} gridOptions={gridOptions} />
        </ModuleDataSection>
      </Paper>

      {bulkImport.isSuccess && bulkImport.data ? (
        <Paper sx={{ p: 2, mt: 2 }}>
          <Typography variant="subtitle1" gutterBottom>
            Last import result
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
            <Typography variant="body2">Inserted: {bulkImport.data.inserted}</Typography>
            <Typography variant="body2">Updated: {bulkImport.data.updated}</Typography>
            <Typography variant="body2">Skipped: {bulkImport.data.skipped}</Typography>
            <Typography variant="body2">Row errors: {bulkImport.data.errors}</Typography>
          </Stack>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Batch row #</TableCell>
                <TableCell>Outcome</TableCell>
                <TableCell>Item id</TableCell>
                <TableCell>Detail</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {bulkImport.data.results.map((r) => (
                <TableRow key={`${r.row_index}-${r.status}`}>
                  <TableCell>{r.row_index + 1}</TableCell>
                  <TableCell>{r.status}</TableCell>
                  <TableCell>{r.id ?? '—'}</TableCell>
                  <TableCell>{r.errors?.length ? r.errors.join('; ') : '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <Paper sx={{ p: 2, mt: 2 }}>
        <Typography variant="subtitle1" gutterBottom>
          Approval history
        </Typography>
        {selectedId == null ? (
          <Typography variant="body2" color="text.secondary">
            Select a grid row to load audit events for that line-up item.
          </Typography>
        ) : !eventRows?.length ? (
          <Typography variant="body2" color="text.secondary">
            No approval-change events for item #{selectedId} yet (events are recorded when approval status changes).
          </Typography>
        ) : (
          <Stack spacing={1}>
            <Typography variant="body2" color="text.secondary">
              Latest first for item #{selectedId}.
            </Typography>
            {eventRows.map((ev) => (
              <Box key={ev.id} sx={{ borderLeft: 2, borderColor: 'divider', pl: 1 }}>
                <Typography variant="body2">
                  <strong>{ev.new_approval_status}</strong>
                  {ev.old_approval_status != null ? ` ← ${ev.old_approval_status}` : ''}
                </Typography>
                <Typography variant="caption" color="text.secondary" component="div">
                  {ev.created_at ?? '—'} · {ev.actor ?? 'unknown actor'} · {ev.event_type}
                </Typography>
                {ev.notes ? (
                  <Typography variant="body2" sx={{ mt: 0.5 }}>
                    Notes snapshot: {ev.notes}
                  </Typography>
                ) : null}
              </Box>
            ))}
          </Stack>
        )}
      </Paper>

      <Dialog open={importOpen} onClose={() => !bulkImport.isPending && setImportOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Bulk CSV import</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            First row must be headers (customer_code / Customer, period_start / period, sku / SKU, …). Export XLSX to
            CSV if needed. Without &quot;Replace matching&quot;, existing natural keys are skipped with a reason.
          </Typography>
          <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
            <Button variant="outlined" size="small" onClick={() => fileRef.current?.click()}>
              Choose CSV file
            </Button>
            <input ref={fileRef} type="file" accept=".csv,text/csv" hidden onChange={onCsvFile} />
          </Stack>
          <FormControlLabel
            control={
              <Checkbox
                checked={replaceMatching}
                onChange={(_, c) => setReplaceMatching(c)}
                disabled={bulkImport.isPending}
              />
            }
            label="Replace matching rows (upsert updates in place)"
          />
          <TextField
            multiline
            minRows={10}
            fullWidth
            sx={{ mt: 1 }}
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder="customer_code,period_start,sku&#10;ACME,2025-01-01,MY-SKU"
            disabled={bulkImport.isPending}
          />
          {importParseMsg ? (
            <Alert severity="warning" sx={{ mt: 2 }}>
              {importParseMsg}
            </Alert>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setImportOpen(false)} disabled={bulkImport.isPending}>
            Close
          </Button>
          <Button variant="contained" disabled={bulkImport.isPending || !importText.trim()} onClick={() => runImport()}>
            {bulkImport.isPending ? 'Importing…' : 'Run import'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
