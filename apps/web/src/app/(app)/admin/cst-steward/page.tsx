'use client';

import {
  Alert,
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
import type { ColDef, GridApi, ICellRendererParams, SelectionChangedEvent } from 'ag-grid-community';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import type { BulkTableSelectionMode } from '@/components/bulkTable/BulkSelectionToolbar';
import { PageHeader } from '@/components/PageHeader';
import type { MasterColumnPickerGroup } from '@/components/masterGrid/MasterColumnPickerDialog';
import { MasterDataGridShell } from '@/components/masterGrid/MasterDataGridShell';
import { apiGet, apiPatch, apiPost } from '@/lib/api';

type KeyAccountRow = {
  id: number | null;
  customer_id: number;
  customer_code: string;
  customer_name: string;
  is_key_account: boolean;
  reports_expected: boolean;
  expected_cadence: string;
  overdue_threshold_days: number;
  notes: string | null;
  feed_profile_json: Record<string, unknown> | null;
};

type KeyAccountGridRow = Omit<KeyAccountRow, 'id'> & { id: number };

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
  customer_code: string | null;
  customer_name: string | null;
  article_no_normalized: string;
  product_sku: string | null;
  product_name: string | null;
  status: string;
};

const TAB_KEYS = ['key-accounts', 'slots', 'aliases'] as const;
type TabKey = (typeof TAB_KEYS)[number];

const GRID_STATE_KEY = 'cip.admin.cst-steward.key-accounts.grid.v2';
const SLOTS_GRID_STATE_KEY = 'cip.admin.cst-steward.slots.grid.v1';
const ALIAS_GRID_STATE_KEY = 'cip.admin.cst-steward.aliases.grid.v1';
const DEFAULT_PAGE_SIZE = 100;
const PAGE_SIZE_OPTIONS = [50, 100, 200, 500];

type ListEnvelope<T> = { items: T[]; total: number };

const KEY_ACCOUNT_COLUMN_GROUPS: MasterColumnPickerGroup[] = [
  {
    label: 'Identity',
    fields: ['customer_code', 'customer_name'],
  },
  {
    label: 'Feed config',
    fields: ['is_key_account', 'reports_expected', 'expected_cadence'],
  },
];

const KEY_ACCOUNT_COLUMN_LABELS: Record<string, string> = {
  customer_code: 'Code',
  customer_name: 'Name',
  is_key_account: 'Key account',
  reports_expected: 'Reports expected',
  expected_cadence: 'Cadence',
};

const SLOT_COLUMN_GROUPS: MasterColumnPickerGroup[] = [
  {
    label: 'Slot',
    fields: ['status', 'week_start_date', 'customer_code', 'customer_name'],
  },
];

const SLOT_COLUMN_LABELS: Record<string, string> = {
  status: 'Status',
  week_start_date: 'Week start',
  customer_code: 'Code',
  customer_name: 'Customer',
};

const ALIAS_COLUMN_GROUPS: MasterColumnPickerGroup[] = [
  {
    label: 'Alias',
    fields: ['article_no_normalized', 'customer_name', 'status'],
  },
  {
    label: 'Product',
    fields: ['product_sku', 'product_name'],
  },
];

const ALIAS_COLUMN_LABELS: Record<string, string> = {
  article_no_normalized: 'Article',
  customer_name: 'Customer',
  product_sku: 'SKU',
  product_name: 'Product',
  status: 'Status',
};

function tabIndexFromParam(raw: string | null): number {
  if (!raw) return 0;
  const idx = TAB_KEYS.indexOf(raw as TabKey);
  return idx >= 0 ? idx : 0;
}

export default function CstStewardPage() {
  const qc = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const tab = tabIndexFromParam(searchParams.get('tab'));
  const urlQ = searchParams.get('q') ?? '';
  const keyOnly = searchParams.get('key_only') === '1';
  const page = Math.max(1, Number(searchParams.get('page') || '1') || 1);
  const pageSizeRaw = Number(searchParams.get('page_size') || String(DEFAULT_PAGE_SIZE)) || DEFAULT_PAGE_SIZE;
  const pageSize = PAGE_SIZE_OPTIONS.includes(pageSizeRaw) ? pageSizeRaw : DEFAULT_PAGE_SIZE;

  const [filterInput, setFilterInput] = useState(urlQ);
  const [debouncedQ, setDebouncedQ] = useState(urlQ);
  const [dlg, setDlg] = useState<KeyAccountRow | null>(null);
  const [keyFlag, setKeyFlag] = useState(false);
  const [reportsExpected, setReportsExpected] = useState(false);
  const [cadence, setCadence] = useState('weekly');
  const [threshold, setThreshold] = useState('10');
  const [notes, setNotes] = useState('');
  const [feedRaw, setFeedRaw] = useState('');

  const [aliasGridApi, setAliasGridApi] = useState<GridApi<AliasRow> | null>(null);
  const [aliasBulkSelectionMode, setAliasBulkSelectionMode] = useState<BulkTableSelectionMode>('normal');
  const [selectedAliasIds, setSelectedAliasIds] = useState<number[]>([]);
  const [bulkMessage, setBulkMessage] = useState<string | null>(null);

  const searchKey = searchParams.toString();

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

  const handleGridUrlChange = useCallback(
    (patch: Record<string, string | null>, resetPage?: boolean) => {
      const changes = { ...patch };
      if (resetPage) changes.page = '1';
      setParamState(changes);
    },
    [setParamState],
  );

  const gridUrl = useMemo(
    () => ({
      page,
      pageSize,
      q: debouncedQ,
      sortBy: 'id',
      sortDir: 'asc' as const,
    }),
    [page, pageSize, debouncedQ],
  );

  useEffect(() => {
    setFilterInput(urlQ);
    setDebouncedQ(urlQ);
  }, [urlQ]);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(filterInput), 300);
    return () => clearTimeout(t);
  }, [filterInput]);

  useEffect(() => {
    const next = debouncedQ.trim();
    if (next === urlQ) return;
    setParamState({ q: next || null, page: '1' });
  }, [debouncedQ, urlQ, setParamState]);

  const {
    data: accountsPage,
    isLoading: loadingAccounts,
    isFetching: fetchingAccounts,
    isError: errAccounts,
    error: accountsError,
    refetch: refetchAccounts,
  } = useQuery({
    queryKey: ['cst-steward', 'key-accounts', debouncedQ, keyOnly, page, pageSize],
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams();
      if (debouncedQ.trim()) sp.set('q', debouncedQ.trim());
      if (keyOnly) sp.set('key_only', 'true');
      sp.set('limit', String(pageSize));
      sp.set('offset', String((page - 1) * pageSize));
      return apiGet<ListEnvelope<KeyAccountRow>>(`/api/v1/cst-steward/key-accounts?${sp.toString()}`, {
        signal,
      });
    },
    enabled: tab === 0,
  });
  const accounts = accountsPage?.items;
  const accountsTotal = accountsPage?.total ?? 0;

  const accountRows = useMemo<KeyAccountGridRow[]>(
    () =>
      (accounts ?? []).map((row) => ({
        ...row,
        id: row.id ?? row.customer_id,
      })),
    [accounts],
  );

  const {
    data: worklist,
    isLoading: loadingSlots,
    isFetching: fetchingSlots,
    isError: errSlots,
    error: slotsError,
    refetch: refetchSlots,
  } = useQuery({
    queryKey: ['cst-steward', 'slots', page, pageSize],
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams();
      sp.set('limit', String(pageSize));
      sp.set('offset', String((page - 1) * pageSize));
      return apiGet<{
        counts: Record<string, number>;
        items: SlotItem[];
        total: number;
      }>(`/api/v1/cst-steward/report-slots/worklist?${sp.toString()}`, { signal });
    },
    enabled: tab === 1,
  });
  const slotsTotal = worklist?.total ?? 0;

  const {
    data: aliasesPage,
    isLoading: loadingAliases,
    isFetching: fetchingAliases,
    isError: errAliases,
    error: aliasesError,
    refetch: refetchAliases,
  } = useQuery({
    queryKey: ['cst-steward', 'aliases', page, pageSize],
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams();
      sp.set('status', 'proposed');
      sp.set('limit', String(pageSize));
      sp.set('offset', String((page - 1) * pageSize));
      return apiGet<ListEnvelope<AliasRow>>(`/api/v1/cst-steward/article-aliases?${sp.toString()}`, {
        signal,
      });
    },
    enabled: tab === 2,
  });
  const aliases = aliasesPage?.items;
  const aliasesTotal = aliasesPage?.total ?? 0;

  const save = useMutation({
    mutationFn: async () => {
      if (!dlg) throw new Error('No customer selected');
      return apiPatch<KeyAccountRow>(`/api/v1/cst-steward/key-accounts/${dlg.customer_id}`, {
        is_key_account: keyFlag,
        reports_expected: reportsExpected,
        expected_cadence: cadence,
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
    mutationFn: (id: number) =>
      apiPost(`/api/v1/cst-steward/article-aliases/${id}/reject`, { reason: 'steward_reject' }),
    onSuccess: async () => {
      await refetchAliases();
    },
  });

  type AliasBatchResponse = {
    results: { alias_id: number; ok: boolean; status?: string; error?: string }[];
    ok_count: number;
    error_count: number;
  };

  const batchConfirmAliases = useMutation({
    mutationFn: (aliasIds: number[]) =>
      apiPost<AliasBatchResponse>('/api/v1/cst-steward/article-aliases/batch-confirm', {
        alias_ids: aliasIds,
      }),
    onSuccess: async (data) => {
      setBulkMessage(`Confirmed ${data.ok_count} · failed ${data.error_count}`);
      setSelectedAliasIds([]);
      aliasGridApi?.deselectAll();
      await refetchAliases();
    },
  });

  const batchRejectAliases = useMutation({
    mutationFn: (aliasIds: number[]) =>
      apiPost<AliasBatchResponse>('/api/v1/cst-steward/article-aliases/batch-reject', {
        alias_ids: aliasIds,
        reason: 'steward_reject',
      }),
    onSuccess: async (data) => {
      setBulkMessage(`Rejected ${data.ok_count} · failed ${data.error_count}`);
      setSelectedAliasIds([]);
      aliasGridApi?.deselectAll();
      await refetchAliases();
    },
  });

  const openEdit = (row: KeyAccountRow) => {
    setDlg(row);
    setKeyFlag(Boolean(row.is_key_account));
    setReportsExpected(Boolean(row.reports_expected));
    setCadence(row.expected_cadence || 'weekly');
    setThreshold(String(row.overdue_threshold_days ?? 10));
    setNotes(row.notes ?? '');
    setFeedRaw(row.feed_profile_json ? JSON.stringify(row.feed_profile_json, null, 2) : '');
  };

  const accountCols = useMemo<ColDef<KeyAccountGridRow>[]>(
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
        headerName: '',
        colId: 'actions',
        width: 100,
        sortable: false,
        filter: false,
        cellRenderer: (p: ICellRendererParams<KeyAccountGridRow>) =>
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
      { field: 'article_no_normalized', headerName: 'Article', width: 140 },
      { field: 'customer_name', headerName: 'Customer', flex: 1, minWidth: 140 },
      { field: 'product_sku', headerName: 'SKU', width: 120 },
      { field: 'product_name', headerName: 'Product', flex: 1, minWidth: 140 },
      { field: 'status', headerName: 'Status', width: 100 },
      {
        headerName: '',
        colId: 'actions',
        width: 180,
        sortable: false,
        filter: false,
        cellRenderer: (p: ICellRendererParams<AliasRow>) =>
          p.data ? (
            <Stack direction="row" spacing={0.5}>
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

  const onAliasSelectionChanged = useCallback((e: SelectionChangedEvent<AliasRow>) => {
    setSelectedAliasIds(e.api.getSelectedRows().map((r) => r.id));
  }, []);

  const filterActive = Boolean(debouncedQ.trim()) || keyOnly;
  const accountsEmptyDescription = filterActive
    ? 'No rows match the current search/key-account filter. Clear the search or turn off “Key accounts only”.'
    : 'Nothing to edit yet. Open a row’s Edit dialog once customers appear here (flag key-account / cadence from Master Data → Customers, or after CST feed imports).';

  const slotsEmptyDescription =
    'Worklist is empty because there are no due, late, or missing slots right now. Click “Advance slots now” to mint the current period’s expectations for key accounts that report — received slots drop off this list by design.';

  const aliasesEmptyDescription =
    'No proposed article aliases awaiting Confirm/Reject. Aliases appear here after CST imports propose mappings; they never auto-resolve (FLAG ≠ BLOCK).';

  return (
    <>
      <PageHeader crumbs={[{ label: 'Master Data' }, { label: 'CST steward' }]} title="CST steward" />
      <Alert severity="info" sx={{ mb: 2 }} data-testid="cst-steward-guide">
        What you can do here: <strong>Edit</strong> key-account / cadence / feed profile on the first tab;{' '}
        <strong>Advance slots now</strong> on Report slots (worklist shows due/late/missing only);{' '}
        <strong>Confirm / Reject</strong> proposed article aliases on the third tab (row actions or bulk selection).
        This is not a full customer editor or CST analytics dashboard — use Master Data → Customers for create/edit
        identity. Aliases never auto-resolve (FLAG ≠ BLOCK).
      </Alert>
      <Tabs
        value={tab}
        onChange={(_, v: number) =>
          setParamState({ tab: TAB_KEYS[v] ?? 'key-accounts', page: '1' })
        }
        sx={{ mb: 1.5 }}
        data-testid="cst-steward-tabs"
      >
        <Tab label="Key accounts & feed profile" />
        <Tab
          label={`Report slots${worklist ? ` (${worklist.counts?.due ?? 0}/${worklist.counts?.late ?? 0}/${worklist.counts?.missing ?? 0})` : ''}`}
        />
        <Tab label="Article aliases" />
      </Tabs>

      {tab === 0 ? (
        <MasterDataGridShell<KeyAccountGridRow>
          entityKey="cst-steward"
          rows={accountRows}
          columnDefs={accountCols}
          total={accountsTotal}
          isLoading={loadingAccounts}
          isError={errAccounts}
          error={(accountsError as Error) ?? null}
          onRetry={() => void refetchAccounts()}
          empty={{
            title: 'No key-account / feed-profile rows',
            description: accountsEmptyDescription,
          }}
          url={gridUrl}
          onUrlChange={handleGridUrlChange}
          defaultPageSize={DEFAULT_PAGE_SIZE}
          defaultSortBy="customer_code"
          defaultSortDir="asc"
          pageSizeOptions={PAGE_SIZE_OPTIONS}
          enableEmptyUrlSeed={false}
          gridStateStorageKey={GRID_STATE_KEY}
          columnPickerTitle="CST key-account columns"
          columnPickerGroups={KEY_ACCOUNT_COLUMN_GROUPS}
          columnLabelByField={KEY_ACCOUNT_COLUMN_LABELS}
          gridOptions={{ getRowId: (p) => String(p.data.customer_id) }}
          bulkSelectionEnabled={false}
          onRefresh={() => void refetchAccounts()}
          refreshBusy={fetchingAccounts}
          filterSlot={
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <TextField
                size="small"
                label="Filter"
                value={filterInput}
                onChange={(e) => setFilterInput(e.target.value)}
                sx={{ minWidth: 260 }}
                data-testid="cst-key-filter"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={keyOnly}
                    onChange={(e) =>
                      setParamState({ key_only: e.target.checked ? '1' : null, page: '1' })
                    }
                    data-testid="cst-key-only"
                  />
                }
                label="Key accounts only"
              />
            </Stack>
          }
        />
      ) : null}

      {tab === 1 ? (
        <>
          {advance.isError ? (
            <Alert severity="error" sx={{ mb: 1.5 }}>
              {String((advance.error as Error)?.message)}
            </Alert>
          ) : null}
          <MasterDataGridShell<SlotItem>
            entityKey="cst-slots"
            rows={worklist?.items ?? []}
            columnDefs={slotCols}
            total={slotsTotal}
            isLoading={loadingSlots}
            isError={errSlots}
            error={(slotsError as Error) ?? null}
            onRetry={() => void refetchSlots()}
            intro="Due / late / missing only — received slots drop off."
            empty={{
              title: 'No open report slots',
              description: slotsEmptyDescription,
            }}
            url={gridUrl}
            onUrlChange={handleGridUrlChange}
            defaultPageSize={DEFAULT_PAGE_SIZE}
            defaultSortBy="week_start_date"
            defaultSortDir="desc"
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            enableEmptyUrlSeed={false}
            gridStateStorageKey={SLOTS_GRID_STATE_KEY}
            columnPickerTitle="CST report-slot columns"
            columnPickerGroups={SLOT_COLUMN_GROUPS}
            columnLabelByField={SLOT_COLUMN_LABELS}
            gridOptions={{ getRowId: (p) => String(p.data.id) }}
            bulkSelectionEnabled={false}
            onRefresh={() => void refetchSlots()}
            refreshBusy={fetchingSlots}
            toolbarStart={
              <Button
                variant="outlined"
                onClick={() => advance.mutate()}
                disabled={advance.isPending}
                data-testid="cst-slots-advance"
              >
                {advance.isPending ? 'Advancing…' : 'Advance slots now'}
              </Button>
            }
          />
        </>
      ) : null}

      {tab === 2 ? (
        <>
          {bulkMessage ? (
            <Alert severity="info" sx={{ mb: 1.5 }} onClose={() => setBulkMessage(null)} data-testid="cst-aliases-bulk-result">
              {bulkMessage}
            </Alert>
          ) : null}
          <MasterDataGridShell<AliasRow>
            entityKey="cst-aliases"
            rows={aliases ?? []}
            columnDefs={aliasCols}
            total={aliasesTotal}
            isLoading={loadingAliases}
            isError={errAliases}
            error={(aliasesError as Error) ?? null}
            onRetry={() => void refetchAliases()}
            empty={{
              title: 'No proposed aliases',
              description: aliasesEmptyDescription,
            }}
            url={gridUrl}
            onUrlChange={handleGridUrlChange}
            defaultPageSize={DEFAULT_PAGE_SIZE}
            defaultSortBy="article_no_normalized"
            defaultSortDir="asc"
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            enableEmptyUrlSeed={false}
            gridStateStorageKey={ALIAS_GRID_STATE_KEY}
            columnPickerTitle="CST article-alias columns"
            columnPickerGroups={ALIAS_COLUMN_GROUPS}
            columnLabelByField={ALIAS_COLUMN_LABELS}
            gridHeight={560}
            gridOptions={{
              getRowId: (p) => String(p.data.id),
              onSelectionChanged: onAliasSelectionChanged,
            }}
            bulkSelectionEnabled
            bulkSelectionMode={aliasBulkSelectionMode}
            onBulkSelectionModeChange={setAliasBulkSelectionMode}
            bulkBusy={batchConfirmAliases.isPending || batchRejectAliases.isPending}
            onGridApiChange={setAliasGridApi}
            onRefresh={() => void refetchAliases()}
            refreshBusy={fetchingAliases}
            toolbarStart={
              <>
                <Button
                  variant="contained"
                  disabled={
                    selectedAliasIds.length === 0 ||
                    batchConfirmAliases.isPending ||
                    batchRejectAliases.isPending
                  }
                  onClick={() => batchConfirmAliases.mutate(selectedAliasIds)}
                  data-testid="cst-aliases-bulk-confirm"
                >
                  Confirm selected ({selectedAliasIds.length})
                </Button>
                <Button
                  variant="outlined"
                  disabled={
                    selectedAliasIds.length === 0 ||
                    batchConfirmAliases.isPending ||
                    batchRejectAliases.isPending
                  }
                  onClick={() => batchRejectAliases.mutate(selectedAliasIds)}
                  data-testid="cst-aliases-bulk-reject"
                >
                  Reject selected ({selectedAliasIds.length})
                </Button>
              </>
            }
          />
        </>
      ) : null}

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
