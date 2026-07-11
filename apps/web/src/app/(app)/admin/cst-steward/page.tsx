'use client';

import {
  Alert,
  Box,
  Button,
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
  Switch,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import type {
  ColDef,
  ColumnMovedEvent,
  ColumnPinnedEvent,
  ColumnResizedEvent,
  ColumnVisibleEvent,
  GridApi,
  GridReadyEvent,
  ICellRendererParams,
} from 'ag-grid-community';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import {
  MasterColumnPickerDialog,
  type MasterColumnPickerGroup,
} from '@/components/masterGrid/MasterColumnPickerDialog';
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

  const [gridApi, setGridApi] = useState<GridApi<KeyAccountRow> | null>(null);
  const [aliasGridApi, setAliasGridApi] = useState<GridApi<AliasRow> | null>(null);
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [aliasColumnsOpen, setAliasColumnsOpen] = useState(false);
  const [columnSearch, setColumnSearch] = useState('');
  const [aliasColumnSearch, setAliasColumnSearch] = useState('');
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>({});
  const [aliasColumnVisibility, setAliasColumnVisibility] = useState<Record<string, boolean>>({});

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
  const accountsTotalPages = Math.max(1, Math.ceil(accountsTotal / pageSize));

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
  const slotsTotalPages = Math.max(1, Math.ceil(slotsTotal / pageSize));

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
  const aliasesTotalPages = Math.max(1, Math.ceil(aliasesTotal / pageSize));

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
    mutationFn: (id: number) => apiPost(`/api/v1/cst-steward/article-aliases/${id}/reject`, { reason: 'steward_reject' }),
    onSuccess: async () => {
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

  const persistGridState = useCallback((api: GridApi<KeyAccountRow>) => {
    try {
      localStorage.setItem(GRID_STATE_KEY, JSON.stringify(api.getColumnState()));
    } catch {
      // no-op
    }
  }, []);

  const syncColumnVisibility = useCallback((api: GridApi<KeyAccountRow>) => {
    if (!api?.getColumns) return;
    try {
      const known = new Set(KEY_ACCOUNT_COLUMN_GROUPS.flatMap((g) => g.fields));
      const visibility: Record<string, boolean> = {};
      for (const col of api.getColumns() ?? []) {
        const field = col?.getColDef?.()?.field as string | undefined;
        if (!field || !known.has(field)) continue;
        visibility[field] = Boolean(col.isVisible?.());
      }
      if (Object.keys(visibility).length) setColumnVisibility(visibility);
    } catch {
      // no-op
    }
  }, []);

  const onAccountsGridReady = useCallback(
    (e: GridReadyEvent<KeyAccountRow>) => {
      setGridApi(e.api);
      try {
        const raw = localStorage.getItem(GRID_STATE_KEY);
        if (raw) {
          e.api.applyColumnState({ state: JSON.parse(raw), applyOrder: true });
        }
      } catch {
        // no-op
      }
      syncColumnVisibility(e.api);
    },
    [syncColumnVisibility],
  );

  const persistAliasGridState = useCallback((api: GridApi<AliasRow>) => {
    try {
      localStorage.setItem(ALIAS_GRID_STATE_KEY, JSON.stringify(api.getColumnState()));
    } catch {
      // no-op
    }
  }, []);

  const syncAliasColumnVisibility = useCallback((api: GridApi<AliasRow>) => {
    if (!api?.getColumns) return;
    try {
      const known = new Set(ALIAS_COLUMN_GROUPS.flatMap((g) => g.fields));
      const visibility: Record<string, boolean> = {};
      for (const col of api.getColumns() ?? []) {
        const field = col?.getColDef?.()?.field as string | undefined;
        if (!field || !known.has(field)) continue;
        visibility[field] = Boolean(col.isVisible?.());
      }
      if (Object.keys(visibility).length) setAliasColumnVisibility(visibility);
    } catch {
      // no-op
    }
  }, []);

  const onAliasesGridReady = useCallback(
    (e: GridReadyEvent<AliasRow>) => {
      setAliasGridApi(e.api);
      try {
        const raw = localStorage.getItem(ALIAS_GRID_STATE_KEY);
        if (raw) {
          e.api.applyColumnState({ state: JSON.parse(raw), applyOrder: true });
        }
      } catch {
        // no-op
      }
      syncAliasColumnVisibility(e.api);
    },
    [syncAliasColumnVisibility],
  );

  const onAliasColumnStateEvent = useCallback(
    (
      e:
        | ColumnMovedEvent<AliasRow>
        | ColumnVisibleEvent<AliasRow>
        | ColumnPinnedEvent<AliasRow>
        | ColumnResizedEvent<AliasRow>,
    ) => {
      persistAliasGridState(e.api);
      syncAliasColumnVisibility(e.api);
    },
    [persistAliasGridState, syncAliasColumnVisibility],
  );

  const toggleAliasColumnVisibility = useCallback(
    (columnId: string, visible: boolean) => {
      if (!aliasGridApi?.setColumnsVisible) return;
      aliasGridApi.setColumnsVisible([columnId], visible);
      persistAliasGridState(aliasGridApi);
      setAliasColumnVisibility((prev) => ({ ...prev, [columnId]: visible }));
    },
    [aliasGridApi, persistAliasGridState],
  );

  const onColumnStateEvent = useCallback(
    (
      e:
        | ColumnMovedEvent<KeyAccountRow>
        | ColumnVisibleEvent<KeyAccountRow>
        | ColumnPinnedEvent<KeyAccountRow>
        | ColumnResizedEvent<KeyAccountRow>,
    ) => {
      persistGridState(e.api);
      syncColumnVisibility(e.api);
    },
    [persistGridState, syncColumnVisibility],
  );

  const toggleColumnVisibility = useCallback(
    (columnId: string, visible: boolean) => {
      if (!gridApi?.setColumnsVisible) return;
      gridApi.setColumnsVisible([columnId], visible);
      persistGridState(gridApi);
      setColumnVisibility((prev) => ({ ...prev, [columnId]: visible }));
    },
    [gridApi, persistGridState],
  );

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
        headerName: '',
        colId: 'actions',
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

  const filterActive = Boolean(debouncedQ.trim()) || keyOnly;
  const accountsEmptyDescription = filterActive
    ? 'No key-account rows match the current filter. Clear the search or turn off “Key accounts only”.'
    : 'No CST key-account / feed-profile rows yet. Flag customers from Master Data or import CST feeds.';

  return (
    <>
      <PageHeader crumbs={[{ label: 'Master Data' }, { label: 'CST steward' }]} title="CST steward" />
      <Alert severity="info" sx={{ mb: 2 }} data-testid="cst-steward-guide">
        Key-account flag, report cadence / feed profile, expected-report worklist, and article-alias confirm. FLAG ≠
        BLOCK — unconfirmed aliases never auto-resolve. Slot advance is steward/dev triggered here; beat job is
        registered but not run against cip from this page without intent.
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
        <>
          <Stack direction="row" spacing={1} sx={{ mb: 1.5 }} alignItems="center" flexWrap="wrap" useFlexGap>
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
            <Button
              variant="outlined"
              disabled={!gridApi}
              onClick={() => {
                setColumnSearch('');
                setColumnsOpen(true);
                if (gridApi) syncColumnVisibility(gridApi);
              }}
              data-testid="cst-steward-columns-open"
            >
              Columns
            </Button>
            <Button
              variant="outlined"
              onClick={() => {
                try {
                  localStorage.removeItem(GRID_STATE_KEY);
                  window.location.reload();
                } catch {
                  // no-op
                }
              }}
              data-testid="cst-steward-columns-reset"
            >
              Reset column layout
            </Button>
            <ModuleGridToolbar
              onRefresh={() => void refetchAccounts()}
              busy={fetchingAccounts}
              sx={{ mb: 0 }}
            />
          </Stack>
          <ModuleDataSection
            isLoading={loadingAccounts}
            isError={errAccounts}
            error={(accountsError as Error) ?? null}
            onRetry={() => void refetchAccounts()}
            isEmpty={accountsTotal === 0}
            empty={{
              title: 'No key accounts',
              description: accountsEmptyDescription,
            }}
          >
            <EnterpriseDataGrid
              rowData={accounts ?? []}
              columnDefs={accountCols}
              height={520}
              gridOptions={{
                getRowId: (p) => String(p.data.customer_id),
                onGridReady: onAccountsGridReady,
                onColumnMoved: onColumnStateEvent,
                onColumnVisible: onColumnStateEvent,
                onColumnPinned: onColumnStateEvent,
                onColumnResized: onColumnStateEvent,
              }}
            />
            <Stack direction="row" spacing={1} sx={{ mt: 2 }} alignItems="center" data-testid="cst-accounts-pager">
              <Button
                disabled={page <= 1 || fetchingAccounts}
                onClick={() => setParamState({ page: String(page - 1) })}
              >
                Prev
              </Button>
              <Typography variant="body2">
                Page {page} / {accountsTotalPages} ({accountsTotal} rows)
              </Typography>
              <Button
                disabled={page >= accountsTotalPages || fetchingAccounts}
                onClick={() => setParamState({ page: String(page + 1) })}
              >
                Next
              </Button>
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Page size</InputLabel>
                <Select
                  label="Page size"
                  value={String(pageSize)}
                  onChange={(e) =>
                    setParamState({ page_size: String(e.target.value || DEFAULT_PAGE_SIZE), page: '1' })
                  }
                  data-testid="cst-accounts-page-size"
                >
                  {PAGE_SIZE_OPTIONS.map((n) => (
                    <MenuItem key={n} value={String(n)}>
                      {n}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Stack>
          </ModuleDataSection>
        </>
      ) : null}

      {tab === 1 ? (
        <>
          <Stack direction="row" spacing={1} sx={{ mb: 1.5 }} alignItems="center" flexWrap="wrap" useFlexGap>
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
            <ModuleGridToolbar
              onRefresh={() => void refetchSlots()}
              busy={fetchingSlots}
              sx={{ mb: 0 }}
            />
          </Stack>
          {advance.isError ? <Alert severity="error">{String((advance.error as Error)?.message)}</Alert> : null}
          <ModuleDataSection
            isLoading={loadingSlots}
            isError={errSlots}
            error={(slotsError as Error) ?? null}
            onRetry={() => void refetchSlots()}
            isEmpty={slotsTotal === 0}
            empty={{
              title: 'No open report slots',
              description: 'Due / late / missing slots appear here. Advance slots to mint the current week’s expectations.',
            }}
          >
            <EnterpriseDataGrid
              rowData={worklist?.items ?? []}
              columnDefs={slotCols}
              height={520}
              gridOptions={{ getRowId: (p) => String(p.data.id) }}
            />
            <Stack direction="row" spacing={1} sx={{ mt: 2 }} alignItems="center" data-testid="cst-slots-pager">
              <Button
                disabled={page <= 1 || fetchingSlots}
                onClick={() => setParamState({ page: String(page - 1) })}
              >
                Prev
              </Button>
              <Typography variant="body2">
                Page {page} / {slotsTotalPages} ({slotsTotal} rows)
              </Typography>
              <Button
                disabled={page >= slotsTotalPages || fetchingSlots}
                onClick={() => setParamState({ page: String(page + 1) })}
              >
                Next
              </Button>
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Page size</InputLabel>
                <Select
                  label="Page size"
                  value={String(pageSize)}
                  onChange={(e) =>
                    setParamState({ page_size: String(e.target.value || DEFAULT_PAGE_SIZE), page: '1' })
                  }
                  data-testid="cst-slots-page-size"
                >
                  {PAGE_SIZE_OPTIONS.map((n) => (
                    <MenuItem key={n} value={String(n)}>
                      {n}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Stack>
          </ModuleDataSection>
        </>
      ) : null}

      {tab === 2 ? (
        <>
          <Stack direction="row" spacing={1} sx={{ mb: 1.5 }} alignItems="center" flexWrap="wrap" useFlexGap>
            <Box sx={{ flex: 1 }} />
            <Button
              variant="outlined"
              disabled={!aliasGridApi}
              onClick={() => {
                setAliasColumnSearch('');
                setAliasColumnsOpen(true);
                if (aliasGridApi) syncAliasColumnVisibility(aliasGridApi);
              }}
              data-testid="cst-aliases-columns-open"
            >
              Columns
            </Button>
            <Button
              variant="outlined"
              onClick={() => {
                try {
                  localStorage.removeItem(ALIAS_GRID_STATE_KEY);
                  window.location.reload();
                } catch {
                  // no-op
                }
              }}
              data-testid="cst-aliases-columns-reset"
            >
              Reset column layout
            </Button>
            <ModuleGridToolbar
              onRefresh={() => void refetchAliases()}
              busy={fetchingAliases}
              sx={{ mb: 0 }}
            />
          </Stack>
          <ModuleDataSection
            isLoading={loadingAliases}
            isError={errAliases}
            error={(aliasesError as Error) ?? null}
            onRetry={() => void refetchAliases()}
            isEmpty={aliasesTotal === 0}
            empty={{
              title: 'No proposed aliases',
              description: 'Proposed customer article aliases awaiting confirm/reject will show here.',
            }}
          >
            <EnterpriseDataGrid
              rowData={aliases ?? []}
              columnDefs={aliasCols}
              height={560}
              gridOptions={{
                getRowId: (p) => String(p.data.id),
                onGridReady: onAliasesGridReady,
                onColumnMoved: onAliasColumnStateEvent,
                onColumnVisible: onAliasColumnStateEvent,
                onColumnPinned: onAliasColumnStateEvent,
                onColumnResized: onAliasColumnStateEvent,
              }}
            />
            <Stack direction="row" spacing={1} sx={{ mt: 2 }} alignItems="center" data-testid="cst-aliases-pager">
              <Button
                disabled={page <= 1 || fetchingAliases}
                onClick={() => setParamState({ page: String(page - 1) })}
              >
                Prev
              </Button>
              <Typography variant="body2">
                Page {page} / {aliasesTotalPages} ({aliasesTotal} rows)
              </Typography>
              <Button
                disabled={page >= aliasesTotalPages || fetchingAliases}
                onClick={() => setParamState({ page: String(page + 1) })}
              >
                Next
              </Button>
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Page size</InputLabel>
                <Select
                  label="Page size"
                  value={String(pageSize)}
                  onChange={(e) =>
                    setParamState({ page_size: String(e.target.value || DEFAULT_PAGE_SIZE), page: '1' })
                  }
                  data-testid="cst-aliases-page-size"
                >
                  {PAGE_SIZE_OPTIONS.map((n) => (
                    <MenuItem key={n} value={String(n)}>
                      {n}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Stack>
          </ModuleDataSection>
        </>
      ) : null}

      <MasterColumnPickerDialog
        open={columnsOpen}
        onClose={() => setColumnsOpen(false)}
        title="CST key-account columns"
        groups={KEY_ACCOUNT_COLUMN_GROUPS}
        columnLabelByField={KEY_ACCOUNT_COLUMN_LABELS}
        visibility={columnVisibility}
        onToggle={toggleColumnVisibility}
        gridReady={Boolean(gridApi)}
        search={columnSearch}
        onSearchChange={setColumnSearch}
      />

      <MasterColumnPickerDialog
        open={aliasColumnsOpen}
        onClose={() => setAliasColumnsOpen(false)}
        title="CST article-alias columns"
        groups={ALIAS_COLUMN_GROUPS}
        columnLabelByField={ALIAS_COLUMN_LABELS}
        visibility={aliasColumnVisibility}
        onToggle={toggleAliasColumnVisibility}
        gridReady={Boolean(aliasGridApi)}
        search={aliasColumnSearch}
        onSearchChange={setAliasColumnSearch}
      />

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
