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
import type { ColDef, GridApi, GridOptions, ICellRendererParams } from 'ag-grid-community';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import type { MasterColumnPickerGroup } from '@/components/masterGrid/MasterColumnPickerDialog';
import { MasterDataGridShell } from '@/components/masterGrid/MasterDataGridShell';
import { apiGet, apiPost, safeDisplayError } from '@/lib/api';
import { pageFromSkipLimit, parseSkipLimitParams, skipFromPage } from '@/lib/skipLimitSearchParams';

const DEFAULT_LIMIT = 100;
const PAGE_SIZE_OPTIONS = [25, 50, 100, 200, 500] as const;
const LS_SHELL_GRID = 'cip.admin.product-master-gaps.shell.grid.v1';

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

type GapGridRow = GapRow & { id: string };

type WorklistResponse = {
  rows: GapRow[];
  total: number;
  skip: number;
  limit: number;
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

const PMG_COLUMN_GROUPS: MasterColumnPickerGroup[] = [
  {
    label: 'Token',
    fields: ['token', 'sources', 'status', 'resolution_statuses'],
  },
  {
    label: 'Impact',
    fields: ['occurrence_count', 'quantity_impact', 'sample_identifiers', 'affected_job_ids'],
  },
];

const PMG_COLUMN_LABELS: Record<string, string> = {
  token: 'Product token',
  sources: 'Source(s)',
  status: 'Status',
  resolution_statuses: 'Resolution detail',
  occurrence_count: 'Occurrences',
  quantity_impact: 'Qty impact',
  sample_identifiers: 'Sample IDs',
  affected_job_ids: 'Jobs',
};

export function ProductMasterGapWorklistView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const searchKey = searchParams.toString();

  const { skip, limit } = useMemo(
    () => parseSkipLimitParams(searchParams, { defaultLimit: DEFAULT_LIMIT, pageSizeOptions: PAGE_SIZE_OPTIONS }),
    [searchParams],
  );

  const setParamState = useCallback(
    (changes: Record<string, string | null>) => {
      const sp = new URLSearchParams(searchKey);
      for (const [k, v] of Object.entries(changes)) {
        if (v == null || v === '') sp.delete(k);
        else sp.set(k, v);
      }
      const next = sp.toString();
      router.replace(next ? `${pathname}?${next}` : pathname);
    },
    [pathname, router, searchKey],
  );

  const source = (searchParams.get('source') || 'all') as 'all' | 'shipment' | 'dsi' | 'cpor_claim';
  const status = (searchParams.get('status') || 'all') as 'all' | 'unresolved' | 'ignored';

  const [selectedCount, setSelectedCount] = useState(0);
  const [gridApi, setGridApi] = useState<GridApi<GapGridRow> | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [writeAlias, setWriteAlias] = useState(true);
  const [banner, setBanner] = useState<{ severity: 'info' | 'success' | 'warning' | 'error'; text: string } | null>(
    null,
  );
  const queryClient = useQueryClient();

  const q = useQuery({
    queryKey: ['product-master-gaps', source, status, skip, limit],
    queryFn: () => {
      const params = new URLSearchParams();
      if (source !== 'all') params.set('source', source);
      if (status !== 'all') params.set('status', status);
      params.set('skip', String(skip));
      params.set('limit', String(limit));
      return apiGet<WorklistResponse>(`/api/v1/product-master-gaps/worklist?${params.toString()}`);
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

  useEffect(() => {
    gridApi?.deselectAll();
    setSelectedCount(0);
  }, [skip, limit, source, status, gridApi]);

  const gridRows = useMemo<GapGridRow[]>(
    () => (q.data?.rows ?? []).map((row) => ({ ...row, id: row.token })),
    [q.data?.rows],
  );

  const columnDefs = useMemo<ColDef<GapGridRow>[]>(
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
        cellRenderer: (p: ICellRendererParams<GapGridRow>) => {
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
        cellRenderer: (p: ICellRendererParams<GapGridRow>) => {
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

  const gridOptions = useMemo<GridOptions<GapGridRow>>(
    () => ({
      getRowId: (p) => p.data?.id ?? p.data?.token ?? '',
      rowSelection: {
        mode: 'multiRow',
        checkboxes: true,
        headerCheckbox: true,
        enableClickSelection: false,
      },
      onSelectionChanged: (e) => {
        setSelectedCount(e.api.getSelectedRows().length);
      },
    }),
    [],
  );

  const total = q.data?.total ?? 0;
  const shellPage = pageFromSkipLimit(skip, limit);

  const onShellUrlChange = useCallback(
    (patch: Record<string, string | null>, resetPage?: boolean) => {
      const next: Record<string, string | null> = {};
      if (patch.page_size != null) {
        next.limit = patch.page_size;
        next.skip = null;
      } else if (patch.page != null) {
        const p = Math.max(1, Number(patch.page) || 1);
        const nextSkip = skipFromPage(p, limit);
        next.skip = nextSkip <= 0 ? null : String(nextSkip);
      }
      if (resetPage) next.skip = null;
      setParamState(next);
    },
    [limit, setParamState],
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
        Catalogue gaps across shipment evidence, DSI staging, and CPOR claims. Select tokens on the
        current page → Preview → Confirm resolve. Selection does not carry across pages. This
        surface never creates Product Master rows; DSI facts are not rewritten (FLAG only).
      </Alert>
      {banner ? (
        <Alert severity={banner.severity} onClose={() => setBanner(null)} data-testid="pmg-banner">
          {banner.text}
        </Alert>
      ) : null}

      {q.data ? (
        <Typography variant="body2" color="text.secondary" data-testid="pmg-summary">
          {total} token{total === 1 ? '' : 's'}
          {job310Count > 0 ? ` · ${job310Count} on this page touching job 310` : ''}
        </Typography>
      ) : null}

      <MasterDataGridShell<GapGridRow>
        entityKey="product-master-gaps"
        rows={gridRows}
        columnDefs={columnDefs}
        total={total}
        isLoading={q.isLoading}
        isError={q.isError}
        error={(q.error as Error) ?? null}
        onRetry={() => void q.refetch()}
        empty={{
          title: 'No unresolved product tokens',
          description: 'All imported product identifiers resolved to Product Master for the current filters.',
        }}
        url={{
          page: shellPage,
          pageSize: limit,
          q: '',
          sortBy: 'token',
          sortDir: 'asc',
        }}
        onUrlChange={onShellUrlChange}
        defaultPageSize={DEFAULT_LIMIT}
        defaultSortBy="token"
        defaultSortDir="asc"
        pageSizeOptions={[...PAGE_SIZE_OPTIONS]}
        enableEmptyUrlSeed={false}
        gridStateStorageKey={LS_SHELL_GRID}
        columnPickerTitle="Product master gap columns"
        columnPickerGroups={PMG_COLUMN_GROUPS}
        columnLabelByField={PMG_COLUMN_LABELS}
        gridHeight={560}
        gridOptions={gridOptions}
        bulkSelectionEnabled={false}
        onGridApiChange={setGridApi}
        onRefresh={() => void q.refetch()}
        refreshBusy={q.isFetching}
        toolbarStart={
          <>
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
          </>
        }
        filterSlot={
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} flexWrap="wrap" useFlexGap>
            <FormControl size="small" sx={{ minWidth: 140 }}>
              <InputLabel id="pmg-source">Source</InputLabel>
              <Select
                labelId="pmg-source"
                label="Source"
                value={source}
                onChange={(e) =>
                  setParamState({ source: e.target.value === 'all' ? null : e.target.value, skip: null })
                }
              >
                <MenuItem value="all">All</MenuItem>
                <MenuItem value="shipment">Shipment</MenuItem>
                <MenuItem value="dsi">DSI</MenuItem>
                <MenuItem value="cpor_claim">CPOR claim</MenuItem>
              </Select>
            </FormControl>
            <FormControl size="small" sx={{ minWidth: 140 }}>
              <InputLabel id="pmg-status">Status</InputLabel>
              <Select
                labelId="pmg-status"
                label="Status"
                value={status}
                onChange={(e) =>
                  setParamState({ status: e.target.value === 'all' ? null : e.target.value, skip: null })
                }
              >
                <MenuItem value="all">All</MenuItem>
                <MenuItem value="unresolved">Unresolved</MenuItem>
                <MenuItem value="ignored">Ignored</MenuItem>
              </Select>
            </FormControl>
          </Stack>
        }
      />

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
                  CPOR {item.counts?.cpor_claim ?? 0} · jobs{' '}
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
