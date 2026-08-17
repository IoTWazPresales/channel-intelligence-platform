'use client';

import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import type { ColDef, GridApi, ICellRendererParams } from 'ag-grid-community';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { OPS_LIST_GRID_PAGINATION } from '@/features/shell/opsListGridPagination';
import { apiGet, apiPost, safeDisplayError } from '@/lib/api';

type GapRow = {
  token: string;
  sources: string[];
  status: 'unresolved' | 'ignored';
  resolution_statuses: string[];
  occurrence_count: number;
  quantity_impact: number;
  sample_identifiers: string;
  first_seen: string | null;
  last_seen: string | null;
  affected_job_ids: number[];
  deep_link: { href: string; label: string };
};

type WorklistResponse = {
  rows: GapRow[];
  total: number;
  truncated: boolean;
  data_unavailable: boolean;
};

type PreviewItem = {
  token: string;
  matched?: boolean;
  product_id?: number;
  match_tier?: string;
  reason?: string;
  counts?: {
    shipment: number;
    dsi_staging: number;
    cpor_claim: number;
    cst_staging?: number;
    dsi_facts: number;
  };
  flags?: string[];
  flag_detail?: string | null;
  affected_job_ids?: number[];
};

type PreviewResponse = {
  items: PreviewItem[];
  matched_count: number;
  unmatched_count: number;
};

type ApplyResponse = {
  ok: boolean;
  applied: boolean;
  summary?: { tokens: number; repointed: number; skipped: number };
};

export function ProductMasterGapWorklistView() {
  const [source, setSource] = useState<'all' | 'shipment' | 'dsi' | 'cpor_claim' | 'cst'>('all');
  const [status, setStatus] = useState<'all' | 'unresolved' | 'ignored'>('all');
  const [selectedCount, setSelectedCount] = useState(0);
  const [gridApi, setGridApi] = useState<GridApi<GapRow> | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [writeAlias, setWriteAlias] = useState(true);
  const [banner, setBanner] = useState<{ severity: 'info' | 'success' | 'warning' | 'error'; text: string } | null>(
    null,
  );
  const queryClient = useQueryClient();

  const q = useQuery({
    queryKey: ['product-master-gaps', source, status],
    queryFn: () => {
      const params = new URLSearchParams();
      if (source !== 'all') params.set('source', source);
      if (status !== 'all') params.set('status', status);
      const qs = params.toString();
      return apiGet<WorklistResponse>(`/api/v1/product-master-gaps/worklist${qs ? `?${qs}` : ''}`);
    },
  });

  const scanMut = useMutation({
    mutationFn: () => apiPost<{ matched_count: number; scanned_tokens: number }>('/api/v1/product-master-gaps/scan'),
    onSuccess: (data) => {
      setBanner({
        severity: 'info',
        text: `Scan complete: ${data.matched_count} of ${data.scanned_tokens} open token(s) now match Product Master.`,
      });
    },
    onError: (err) => setBanner({ severity: 'error', text: safeDisplayError(err) }),
  });

  const previewMut = useMutation({
    mutationFn: (tokens: string[]) =>
      apiPost<PreviewResponse>('/api/v1/product-master-gaps/preview', { tokens }),
    onSuccess: (data) => {
      setPreview(data);
      setPreviewOpen(true);
      setBanner(null);
    },
    onError: (err) => setBanner({ severity: 'error', text: safeDisplayError(err) }),
  });

  const applyMut = useMutation({
    mutationFn: (tokens: string[]) =>
      apiPost<ApplyResponse>('/api/v1/product-master-gaps/apply', {
        tokens,
        confirm: true,
        write_alias: writeAlias,
      }),
    onSuccess: (data) => {
      const s = data.summary;
      setBanner({
        severity: 'success',
        text: s
          ? `Resolved ${s.repointed} token(s); skipped ${s.skipped}.`
          : 'Catalogue gap resolve applied.',
      });
      setPreviewOpen(false);
      setPreview(null);
      gridApi?.deselectAll();
      setSelectedCount(0);
      void queryClient.invalidateQueries({ queryKey: ['product-master-gaps'] });
    },
    onError: (err) => setBanner({ severity: 'error', text: safeDisplayError(err) }),
  });

  const columnDefs = useMemo<ColDef<GapRow>[]>(
    () => [
      { field: 'token', headerName: 'Product token', flex: 1, minWidth: 180 },
      {
        field: 'sources',
        headerName: 'Source(s)',
        width: 150,
        valueFormatter: (p) => (p.value as string[] | undefined)?.join(', ') ?? '',
      },
      {
        field: 'status',
        headerName: 'Status',
        width: 110,
        cellRenderer: (p: ICellRendererParams<GapRow>) => {
          const v = p.data?.status;
          if (!v) return null;
          return (
            <Chip
              size="small"
              label={v}
              color={v === 'ignored' ? 'default' : 'warning'}
              variant={v === 'ignored' ? 'outlined' : 'filled'}
            />
          );
        },
      },
      {
        field: 'resolution_statuses',
        headerName: 'Resolution detail',
        width: 160,
        valueFormatter: (p) => (p.value as string[] | undefined)?.join(', ') ?? '',
      },
      {
        field: 'occurrence_count',
        headerName: 'Occurrences',
        width: 120,
        type: 'numericColumn',
      },
      {
        field: 'quantity_impact',
        headerName: 'Qty impact',
        width: 110,
        type: 'numericColumn',
        valueFormatter: (p) => new Intl.NumberFormat().format(Math.round(Number(p.value ?? 0))),
      },
      { field: 'sample_identifiers', headerName: 'Sample IDs', flex: 1, minWidth: 160 },
      {
        field: 'affected_job_ids',
        headerName: 'Jobs',
        width: 100,
        valueFormatter: (p) => (p.value as number[] | undefined)?.join(', ') ?? '',
      },
      {
        colId: 'action',
        headerName: 'Steward',
        width: 130,
        cellRenderer: (p: ICellRendererParams<GapRow>) => {
          const link = p.data?.deep_link;
          if (!link) return null;
          return (
            <Button size="small" component={Link} href={link.href} variant="text">
              {link.label}
            </Button>
          );
        },
      },
    ],
    [],
  );

  const gridOptions = useMemo(
    () => ({
      getRowId: (p: { data: GapRow }) => p.data.token,
      rowSelection: {
        mode: 'multiRow' as const,
        checkboxes: true,
        headerCheckbox: true,
        enableClickSelection: false,
      },
      onGridReady: (e: { api: GridApi<GapRow> }) => setGridApi(e.api),
      onSelectionChanged: (e: { api: GridApi<GapRow> }) => {
        setSelectedCount(e.api.getSelectedRows().length);
      },
      ...OPS_LIST_GRID_PAGINATION,
    }),
    [],
  );

  const job310Count = useMemo(
    () => (q.data?.rows ?? []).filter((r) => r.affected_job_ids.includes(310)).length,
    [q.data?.rows],
  );

  const selectedTokens = () =>
    (gridApi?.getSelectedRows() ?? [])
      .map((r) => r.token)
      .filter(Boolean);

  const matchedPreview = (preview?.items ?? []).filter((i) => i.matched);
  const unmatchedPreview = (preview?.items ?? []).filter((i) => !i.matched);
  const hasDsiFactsFlag = (preview?.items ?? []).some((i) =>
    (i.flags ?? []).includes('dsi_facts_repoint_deferred'),
  );

  return (
    <Stack spacing={2}>
      <Alert severity="info">
        Catalogue gaps across shipment evidence, DSI staging, CST sell-through, and CPOR claims. Select
        tokens → Preview → Confirm resolve. This surface never creates Product Master rows; DSI facts are
        not rewritten (FLAG only).
      </Alert>
      {banner ? (
        <Alert severity={banner.severity} onClose={() => setBanner(null)} data-testid="pmg-banner">
          {banner.text}
        </Alert>
      ) : null}

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} flexWrap="wrap" useFlexGap alignItems="center">
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel id="pmg-source">Source</InputLabel>
          <Select
            labelId="pmg-source"
            label="Source"
            value={source}
            onChange={(e) => setSource(e.target.value as typeof source)}
          >
            <MenuItem value="all">All</MenuItem>
            <MenuItem value="shipment">Shipment</MenuItem>
            <MenuItem value="dsi">DSI</MenuItem>
            <MenuItem value="cpor_claim">CPOR claim</MenuItem>
            <MenuItem value="cst">CST</MenuItem>
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel id="pmg-status">Status</InputLabel>
          <Select
            labelId="pmg-status"
            label="Status"
            value={status}
            onChange={(e) => setStatus(e.target.value as typeof status)}
          >
            <MenuItem value="all">All</MenuItem>
            <MenuItem value="unresolved">Unresolved</MenuItem>
            <MenuItem value="ignored">Ignored</MenuItem>
          </Select>
        </FormControl>
        <Button
          size="small"
          variant="outlined"
          onClick={() => scanMut.mutate()}
          disabled={scanMut.isPending}
          data-testid="pmg-scan"
        >
          Scan for matches
        </Button>
        <Button
          size="small"
          variant="contained"
          onClick={() => {
            const tokens = selectedTokens();
            if (!tokens.length) {
              setBanner({ severity: 'warning', text: 'Select at least one token.' });
              return;
            }
            previewMut.mutate(tokens);
          }}
          disabled={selectedCount === 0 || previewMut.isPending}
          data-testid="pmg-preview-resolve"
        >
          Preview resolve ({selectedCount})
        </Button>
      </Stack>

      {q.data ? (
        <Typography variant="body2" color="text.secondary" data-testid="pmg-summary">
          {q.data.total} token{q.data.total === 1 ? '' : 's'}
          {job310Count > 0 ? ` · ${job310Count} touching job 310` : ''}
          {q.data.truncated ? ' (truncated)' : ''}
        </Typography>
      ) : null}

      <ModuleDataSection
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        onRetry={() => void q.refetch()}
        isEmpty={Boolean(q.data && q.data.rows.length === 0)}
        empty={{
          title: 'No unresolved product tokens',
          description: 'All imported product identifiers resolved to Product Master for the current filters.',
        }}
      >
        <Box data-testid="pmg-grid">
          <EnterpriseDataGrid
            rowData={q.data?.rows ?? []}
            columnDefs={columnDefs}
            height={560}
            gridOptions={gridOptions}
          />
        </Box>
      </ModuleDataSection>

      <Dialog open={previewOpen} onClose={() => setPreviewOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Confirm catalogue gap resolve</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Typography variant="body2">
              Matched {preview?.matched_count ?? 0} · unmatched {preview?.unmatched_count ?? 0}. Apply
              updates shipment evidence / DSI staging candidates / CPOR claim lines only — never creates
              products.
            </Typography>
            {hasDsiFactsFlag ? (
              <Alert severity="warning">
                DSI fact rows are not rewritten (source_key includes product_id). Staging candidates are
                resolved; leftovers stay FLAG, not BLOCK.
              </Alert>
            ) : null}
            <FormControlLabel
              control={
                <Checkbox checked={writeAlias} onChange={(e) => setWriteAlias(e.target.checked)} />
              }
              label="Write steward-approved ProductAlias for matched tokens"
            />
            {matchedPreview.map((item) => (
              <Box key={item.token} sx={{ borderBottom: 1, borderColor: 'divider', pb: 1 }}>
                <Typography variant="subtitle2">
                  {item.token} → product #{item.product_id} ({item.match_tier})
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  shipment {item.counts?.shipment ?? 0} · DSI staging {item.counts?.dsi_staging ?? 0} ·
                  CPOR {item.counts?.cpor_claim ?? 0} · CST {item.counts?.cst_staging ?? 0} · jobs{' '}
                  {(item.affected_job_ids ?? []).join(', ') || '—'}
                </Typography>
              </Box>
            ))}
            {unmatchedPreview.length > 0 ? (
              <Alert severity="info">
                Unmatched (skipped on apply): {unmatchedPreview.map((i) => i.token).join(', ')}
              </Alert>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreviewOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            color="primary"
            disabled={!matchedPreview.length || applyMut.isPending}
            onClick={() => applyMut.mutate(matchedPreview.map((i) => i.token))}
            data-testid="pmg-confirm-resolve"
          >
            Confirm resolve
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
