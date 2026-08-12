'use client';

import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Stack,
  Switch,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { PageHeader } from '@/components/PageHeader';
import { apiGet, apiPatch, apiPost, apiPostFormData } from '@/lib/api';

type KeyAccountRow = {
  id: number | null;
  customer_id: number;
  customer_code: string;
  customer_name: string;
  is_key_account: boolean;
  reports_expected: boolean;
  expected_cadence: string;
  report_structure_type: string | null;
  overdue_threshold_days: number;
  notes: string | null;
  feed_profile_json: Record<string, unknown> | null;
};

type SlotItem = {
  id: number;
  customer_id: number;
  customer_code: string | null;
  customer_name: string | null;
  week_start_date: string | null;
  status: string;
};

type AliasRow = {
  id: number;
  customer_id?: number;
  customer_code: string | null;
  customer_name: string | null;
  article_no_normalized: string;
  product_id?: number;
  product_sku: string | null;
  product_name: string | null;
  status: string;
  valid_from?: string | null;
  valid_to?: string | null;
  evidence_json?: Record<string, unknown> | null;
};

type AliasImportSummary = {
  rows_read: number;
  rows_deduped: number;
  proposed: number;
  updated_proposed: number;
  skipped_existing_confirmed: number;
  collisions: number;
  customer_unresolved: number;
  model_ambiguous: number;
  model_miss: number;
  blank_skipped: number;
  proposed_alias_ids: number[];
  confirm?: { confirmed: number; skipped: number } | null;
};

export default function CstStewardPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState(0);
  const [filter, setFilter] = useState('');
  const [dlg, setDlg] = useState<KeyAccountRow | null>(null);
  const [keyFlag, setKeyFlag] = useState(false);
  const [reportsExpected, setReportsExpected] = useState(false);
  const [cadence, setCadence] = useState('weekly');
  const [structureType, setStructureType] = useState('');
  const [threshold, setThreshold] = useState('10');
  const [notes, setNotes] = useState('');
  const [feedRaw, setFeedRaw] = useState('');

  const [aliasStatus, setAliasStatus] = useState('proposed,confirmed');
  const [aliasImportMsg, setAliasImportMsg] = useState<string | null>(null);
  const [editAlias, setEditAlias] = useState<AliasRow | null>(null);
  const [editProductId, setEditProductId] = useState('');

  const { data: accounts, isLoading: loadingAccounts, isError: errAccounts, error: accountsError, refetch: refetchAccounts } =
    useQuery({
      queryKey: ['cst-steward', 'key-accounts', filter],
      queryFn: ({ signal }) => {
        const q = filter.trim() ? `?q=${encodeURIComponent(filter.trim())}` : '';
        return apiGet<KeyAccountRow[]>(`/api/v1/cst-steward/key-accounts${q}`, { signal });
      },
      enabled: tab === 0,
    });

  const { data: worklist, isLoading: loadingSlots, refetch: refetchSlots } = useQuery({
    queryKey: ['cst-steward', 'slots'],
    queryFn: ({ signal }) =>
      apiGet<{
        counts: Record<string, number>;
        items: SlotItem[];
      }>('/api/v1/cst-steward/report-slots/worklist', { signal }),
    enabled: tab === 1,
  });

  const { data: aliases, isLoading: loadingAliases, refetch: refetchAliases } = useQuery({
    queryKey: ['cst-steward', 'aliases', aliasStatus],
    queryFn: ({ signal }) =>
      apiGet<AliasRow[]>(
        `/api/v1/cst-steward/article-aliases?status=${encodeURIComponent(aliasStatus)}`,
        { signal },
      ),
    enabled: tab === 2,
  });

  const save = useMutation({
    mutationFn: async () => {
      if (!dlg) throw new Error('No customer selected');
      return apiPatch<KeyAccountRow>(`/api/v1/cst-steward/key-accounts/${dlg.customer_id}`, {
        is_key_account: keyFlag,
        reports_expected: reportsExpected,
        expected_cadence: cadence,
        report_structure_type: structureType.trim() || null,
        overdue_threshold_days: Number(threshold),
        notes: notes.trim() || null,
        feed_profile_raw: feedRaw.trim() || '',
      });
    },
    onSuccess: async () => {
      setDlg(null);
      await qc.invalidateQueries({ queryKey: ['cst-steward', 'key-accounts'] });
      await refetchAccounts();
    },
  });

  const advance = useMutation({
    mutationFn: () => apiPost('/api/v1/cst-steward/report-slots/advance', {}),
    onSuccess: async () => {
      await refetchSlots();
    },
  });

  const confirmAlias = useMutation({
    mutationFn: (id: number) => apiPost(`/api/v1/cst-steward/article-aliases/${id}/confirm`, {}),
    onSuccess: async () => {
      await refetchAliases();
    },
  });

  const rejectAlias = useMutation({
    mutationFn: (id: number) => apiPost(`/api/v1/cst-steward/article-aliases/${id}/reject`, { reason: 'steward_reject' }),
    onSuccess: async () => {
      await refetchAliases();
    },
  });

  const importAliases = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      return apiPostFormData<AliasImportSummary>(
        '/api/v1/cst-steward/article-aliases/import?confirm_unique=true',
        fd,
      );
    },
    onSuccess: async (summary) => {
      const confirmed = summary.confirm?.confirmed ?? 0;
      setAliasImportMsg(
        `Read ${summary.rows_deduped} · proposed ${summary.proposed + summary.updated_proposed} · confirmed ${confirmed} · collisions ${summary.collisions} · model miss ${summary.model_miss} · ambiguous ${summary.model_ambiguous}`,
      );
      await refetchAliases();
    },
  });

  const deriveEras = useMutation({
    mutationFn: () => apiPost<Record<string, unknown>>('/api/v1/cst-steward/article-aliases/derive-eras-from-shipping', {}),
    onSuccess: async (summary) => {
      setAliasImportMsg(
        `Derive eras: groups ${String(summary.groups)} · proposed ${String(summary.eras_proposed)} · steward_manual ${String(summary.steward_manual)} · equal_pod ${String(summary.equal_pod_blocked)}`,
      );
      await refetchAliases();
    },
  });

  const confirmDerived = useMutation({
    mutationFn: () => apiPost<Record<string, unknown>>('/api/v1/cst-steward/article-aliases/confirm-shipping-derived', {}),
    onSuccess: async (summary) => {
      setAliasImportMsg(
        `Confirmed shipping eras: ${String(summary.confirmed)} (failed ${String(summary.failed)} / candidates ${String(summary.candidates)})`,
      );
      await refetchAliases();
    },
  });

  const saveAliasEdit = useMutation({
    mutationFn: async () => {
      if (!editAlias) throw new Error('No alias');
      const pid = Number(editProductId);
      if (!Number.isFinite(pid) || pid < 1) throw new Error('Enter a valid product_id');
      return apiPatch<AliasRow>(`/api/v1/cst-steward/article-aliases/${editAlias.id}`, {
        product_id: pid,
        status: 'proposed',
      });
    },
    onSuccess: async () => {
      setEditAlias(null);
      await refetchAliases();
    },
  });

  const openEdit = (row: KeyAccountRow) => {
    setDlg(row);
    setKeyFlag(Boolean(row.is_key_account));
    setReportsExpected(Boolean(row.reports_expected));
    setCadence(row.expected_cadence || 'weekly');
    setStructureType(row.report_structure_type || '');
    setThreshold(String(row.overdue_threshold_days ?? 10));
    setNotes(row.notes ?? '');
    setFeedRaw(row.feed_profile_json ? JSON.stringify(row.feed_profile_json, null, 2) : '');
  };

  const accountCols = useMemo<ColDef<KeyAccountRow>[]>(
    () => [
      { field: 'customer_code', headerName: 'Code', width: 140 },
      { field: 'customer_name', headerName: 'Name', flex: 1, minWidth: 180 },
      {
        field: 'is_key_account',
        headerName: 'Key account',
        width: 110,
        valueFormatter: (p) => (p.value ? 'Yes' : 'No'),
      },
      {
        field: 'reports_expected',
        headerName: 'Reports expected',
        width: 130,
        valueFormatter: (p) => (p.value ? 'Yes' : 'No'),
      },
      { field: 'expected_cadence', headerName: 'Cadence', width: 110 },
      {
        field: 'report_structure_type',
        headerName: 'Structure',
        width: 120,
        valueFormatter: (p) => (p.value ? String(p.value) : '—'),
      },
      {
        headerName: '',
        width: 100,
        sortable: false,
        filter: false,
        cellRenderer: (p: ICellRendererParams<KeyAccountRow>) =>
          p.data ? (
            <Button size="small" onClick={() => openEdit(p.data!)} data-testid={`cst-key-edit-${p.data.customer_id}`}>
              Edit
            </Button>
          ) : null,
      },
    ],
    [],
  );

  const slotCols = useMemo<ColDef<SlotItem>[]>(
    () => [
      { field: 'status', headerName: 'Status', width: 100 },
      { field: 'week_start_date', headerName: 'Week start', width: 120 },
      { field: 'customer_code', headerName: 'Code', width: 140 },
      { field: 'customer_name', headerName: 'Customer', flex: 1, minWidth: 160 },
    ],
    [],
  );

  const aliasCols = useMemo<ColDef<AliasRow>[]>(
    () => [
      { field: 'article_no_normalized', headerName: 'Article', width: 130 },
      { field: 'customer_name', headerName: 'Customer', flex: 1, minWidth: 120 },
      { field: 'product_id', headerName: 'Product id', width: 90 },
      { field: 'product_sku', headerName: 'SKU', width: 110 },
      { field: 'product_name', headerName: 'Product', flex: 1, minWidth: 120 },
      { field: 'valid_from', headerName: 'From', width: 110, valueFormatter: (p) => p.value || '−∞' },
      { field: 'valid_to', headerName: 'To', width: 110, valueFormatter: (p) => p.value || '+∞' },
      { field: 'status', headerName: 'Status', width: 100 },
      {
        headerName: '',
        width: 260,
        sortable: false,
        filter: false,
        cellRenderer: (p: ICellRendererParams<AliasRow>) =>
          p.data ? (
            <Stack direction="row" spacing={0.5}>
              <Button
                size="small"
                onClick={() => {
                  setEditAlias(p.data!);
                  setEditProductId(String(p.data!.product_id ?? ''));
                }}
                data-testid={`cst-alias-edit-${p.data.id}`}
              >
                Edit
              </Button>
              <Button
                size="small"
                variant="contained"
                onClick={() => confirmAlias.mutate(p.data!.id)}
                data-testid={`cst-alias-confirm-${p.data.id}`}
              >
                Confirm
              </Button>
              <Button size="small" onClick={() => rejectAlias.mutate(p.data!.id)} data-testid={`cst-alias-reject-${p.data.id}`}>
                Reject
              </Button>
            </Stack>
          ) : null,
      },
    ],
    [confirmAlias, rejectAlias],
  );

  return (
    <>
      <PageHeader crumbs={[{ label: 'Master Data' }, { label: 'CST steward' }]} title="CST steward" />
      <Alert severity="info" sx={{ mb: 2 }} data-testid="cst-steward-guide">
        Key-account flag, report cadence / feed profile, expected-report worklist, and article-alias confirm. FLAG ≠
        BLOCK — unconfirmed aliases never auto-resolve. Slot advance is steward/dev triggered here; beat job is
        registered but not run against cip from this page without intent.
      </Alert>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 1.5 }} data-testid="cst-steward-tabs">
        <Tab label="Key accounts & feed profile" />
        <Tab label={`Report slots${worklist ? ` (${worklist.counts?.due ?? 0}/${worklist.counts?.late ?? 0}/${worklist.counts?.missing ?? 0})` : ''}`} />
        <Tab label="Article aliases" />
      </Tabs>

      {tab === 0 ? (
        <>
          <Stack direction="row" spacing={1} sx={{ mb: 1.5 }} alignItems="center">
            <TextField
              size="small"
              label="Filter"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              sx={{ minWidth: 260 }}
              data-testid="cst-key-filter"
            />
          </Stack>
          {errAccounts ? <Alert severity="error">{String((accountsError as Error)?.message)}</Alert> : null}
          <EnterpriseDataGrid
            rowData={accounts ?? []}
            columnDefs={accountCols}
            height={520}
            gridOptions={{ getRowId: (p) => String(p.data!.customer_id), loading: loadingAccounts }}
          />
        </>
      ) : null}

      {tab === 1 ? (
        <>
          <Stack direction="row" spacing={1} sx={{ mb: 1.5 }} alignItems="center">
            <Typography variant="body2" color="text.secondary">
              Due / late / missing only — received slots drop off.
            </Typography>
            <Box sx={{ flex: 1 }} />
            <Button
              variant="outlined"
              onClick={() => advance.mutate()}
              disabled={advance.isPending}
              data-testid="cst-slots-advance"
            >
              {advance.isPending ? 'Advancing…' : 'Advance slots now'}
            </Button>
          </Stack>
          {advance.isError ? <Alert severity="error">{String((advance.error as Error)?.message)}</Alert> : null}
          <EnterpriseDataGrid
            rowData={worklist?.items ?? []}
            columnDefs={slotCols}
            height={520}
            gridOptions={{ getRowId: (p) => String(p.data!.id), loading: loadingSlots }}
          />
        </>
      ) : null}

      {tab === 2 ? (
        <>
          <Stack direction="row" spacing={1} sx={{ mb: 1.5 }} alignItems="center">
            <TextField
              select
              SelectProps={{ native: true }}
              size="small"
              label="Status"
              value={aliasStatus}
              onChange={(e) => setAliasStatus(e.target.value)}
              sx={{ minWidth: 220 }}
              data-testid="cst-alias-status-filter"
            >
              <option value="proposed">proposed</option>
              <option value="confirmed">confirmed</option>
              <option value="proposed,confirmed">proposed + confirmed</option>
              <option value="all">all</option>
              <option value="rejected">rejected</option>
            </TextField>
            <Button component="label" variant="contained" disabled={importAliases.isPending} data-testid="cst-alias-upload">
              {importAliases.isPending ? 'Importing…' : 'Upload SCM map'}
              <input
                type="file"
                hidden
                accept=".xlsx,.xlsm"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  e.target.value = '';
                  if (f) importAliases.mutate(f);
                }}
              />
            </Button>
            <Button
              variant="outlined"
              disabled={deriveEras.isPending}
              onClick={() => deriveEras.mutate()}
              data-testid="cst-alias-derive-eras"
            >
              {deriveEras.isPending ? 'Deriving…' : 'Derive eras from shipping'}
            </Button>
            <Button
              variant="outlined"
              disabled={confirmDerived.isPending}
              onClick={() => confirmDerived.mutate()}
              data-testid="cst-alias-confirm-derived"
            >
              {confirmDerived.isPending ? 'Confirming…' : 'Confirm shipping eras'}
            </Button>
            <Typography variant="body2" color="text.secondary">
              Eras: [from, to). Shipping POD dates the clock; steward adjusts gaps.
            </Typography>
          </Stack>
          {aliasImportMsg ? (
            <Alert severity="info" sx={{ mb: 1 }} data-testid="cst-alias-import-summary">
              {aliasImportMsg}
            </Alert>
          ) : null}
          {importAliases.isError ? (
            <Alert severity="error" sx={{ mb: 1 }}>
              {String((importAliases.error as Error)?.message)}
            </Alert>
          ) : null}
          <EnterpriseDataGrid
            rowData={aliases ?? []}
            columnDefs={aliasCols}
            height={560}
            gridOptions={{ getRowId: (p) => String(p.data!.id), loading: loadingAliases }}
          />
        </>
      ) : null}

      <Dialog open={editAlias != null} onClose={() => !saveAliasEdit.isPending && setEditAlias(null)} fullWidth maxWidth="xs">
        <DialogTitle>
          Edit alias — {editAlias?.customer_name} / {editAlias?.article_no_normalized}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ pt: 1 }}>
            <TextField
              size="small"
              label="product_id"
              value={editProductId}
              onChange={(e) => setEditProductId(e.target.value)}
              fullWidth
              data-testid="cst-alias-edit-product-id"
            />
            {saveAliasEdit.isError ? <Alert severity="error">{String((saveAliasEdit.error as Error)?.message)}</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditAlias(null)} disabled={saveAliasEdit.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={() => saveAliasEdit.mutate()}
            disabled={saveAliasEdit.isPending}
            data-testid="cst-alias-edit-save"
          >
            {saveAliasEdit.isPending ? 'Saving…' : 'Save as proposed'}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={dlg != null} onClose={() => !save.isPending && setDlg(null)} fullWidth maxWidth="sm">
        <DialogTitle>
          Edit CST config — {dlg?.customer_code} — {dlg?.customer_name}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ pt: 1 }}>
            <FormControlLabel
              control={<Switch checked={keyFlag} onChange={(e) => setKeyFlag(e.target.checked)} />}
              label="Key account"
            />
            <FormControlLabel
              control={<Switch checked={reportsExpected} onChange={(e) => setReportsExpected(e.target.checked)} />}
              label="Reports expected"
            />
            <TextField
              select
              SelectProps={{ native: true }}
              size="small"
              label="Cadence"
              value={cadence}
              onChange={(e) => setCadence(e.target.value)}
              fullWidth
            >
              <option value="weekly">weekly</option>
              <option value="monthly">monthly</option>
              <option value="adhoc">adhoc</option>
            </TextField>
            <TextField
              select
              SelectProps={{ native: true }}
              size="small"
              label="Report structure type"
              value={structureType}
              onChange={(e) => setStructureType(e.target.value)}
              fullWidth
              helperText="Parser family for this customer's files. Empty = unset."
              data-testid="cst-structure-type"
            >
              <option value="">(unset)</option>
              <option value="flat">flat</option>
              <option value="pivoted">pivoted</option>
              <option value="multi_sheet">multi_sheet</option>
              <option value="mtd_delta">mtd_delta</option>
              <option value="wide_extract">wide_extract</option>
            </TextField>
            <TextField
              size="small"
              label="Overdue threshold (days)"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              fullWidth
            />
            <TextField
              size="small"
              label="Notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              fullWidth
              multiline
              minRows={2}
            />
            <TextField
              size="small"
              label="Feed profile JSON"
              value={feedRaw}
              onChange={(e) => setFeedRaw(e.target.value)}
              fullWidth
              multiline
              minRows={6}
              helperText="Declarative per-customer variance (vat_basis, sheet roles, column map). Empty clears."
              data-testid="cst-feed-profile-editor"
            />
            {save.isError ? <Alert severity="error">{String((save.error as Error)?.message)}</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDlg(null)} disabled={save.isPending}>
            Cancel
          </Button>
          <Button variant="contained" onClick={() => save.mutate()} disabled={save.isPending} data-testid="cst-key-save">
            {save.isPending ? 'Saving…' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
