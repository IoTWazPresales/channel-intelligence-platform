'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import type { ColDef, GridApi } from 'ag-grid-community';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import {
  MasterColumnPickerDialog,
  type MasterColumnPickerGroup,
} from '@/components/masterGrid/MasterColumnPickerDialog';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { apiGet, apiPost } from '@/lib/api';
import { useDebouncedUrlQuery } from '@/lib/useDebouncedUrlQuery';

type CporCaseRow = {
  id: number;
  case_code: string;
  case_name?: string | null;
  customer_code: string | null;
  customer_name: string | null;
  promotion_type: string;
  window_start: string | null;
  window_end: string | null;
  status: string;
  workflow_status: string;
  export_version: number;
  ttl_support_zar: number | null;
  ttl_support_usd: number | null;
  line_count: number;
  missing_roe: boolean;
};

type CustomerPick = { id: number; customer_code: string; customer_name: string };

type PromoTypes = { promotion_types: string[] };

type ListEnvelope = { items: CporCaseRow[]; total: number };

const STATUS_OPTIONS = [
  'draft',
  'proposed',
  'approved',
  'rejected',
  'active',
  'ended',
  'settled',
  'cancelled',
] as const;

const DEFAULT_PAGE_SIZE = 50;
const PAGE_SIZE_OPTIONS = [25, 50, 100, 200] as const;
const CPOR_GRID_STATE_KEY = 'cip.cpor-cases.gridState.v1';

const CPOR_COLUMN_GROUPS: MasterColumnPickerGroup[] = [
  { label: 'Identity', fields: ['case_code', 'case_name', 'customer'] },
  { label: 'Promotion', fields: ['promotion_type', 'window', 'status', 'workflow_status'] },
  { label: 'Totals', fields: ['export_version', 'line_count', 'ttl_support_zar', 'ttl_support_usd', 'missing_roe'] },
];

const CPOR_COLUMN_LABELS: Record<string, string> = {
  case_code: 'Case',
  case_name: 'Name',
  customer: 'Customer',
  promotion_type: 'Type',
  window: 'Window',
  status: 'Status',
  workflow_status: 'Workflow',
  export_version: 'Ver',
  line_count: 'Lines',
  ttl_support_zar: 'Ttl ZAR',
  ttl_support_usd: 'Ttl USD',
  missing_roe: 'Missing ROE',
};

export default function CporCasesListPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const qc = useQueryClient();

  const status = searchParams.get('status') ?? '';
  const q = searchParams.get('q') ?? '';
  const customerIdRaw = searchParams.get('customer_id') ?? '';
  const customerId = customerIdRaw ? Number(customerIdRaw) : null;
  const page = Math.max(1, Number(searchParams.get('page') || '1') || 1);
  const pageSizeRaw = Number(searchParams.get('page_size') || String(DEFAULT_PAGE_SIZE)) || DEFAULT_PAGE_SIZE;
  const pageSize = (PAGE_SIZE_OPTIONS as readonly number[]).includes(pageSizeRaw)
    ? pageSizeRaw
    : DEFAULT_PAGE_SIZE;

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

  const [searchInput, setSearchInput] = useDebouncedUrlQuery(
    q,
    useCallback((next) => setParamState({ q: next || null, page: '1' }), [setParamState]),
  );

  const [dlg, setDlg] = useState(false);
  const [cust, setCust] = useState<CustomerPick | null>(null);
  const [filterCustomer, setFilterCustomer] = useState<CustomerPick | null>(null);
  const [promoType, setPromoType] = useState('Sell out PP');
  const [windowStart, setWindowStart] = useState('');
  const [windowEnd, setWindowEnd] = useState('');
  const [roe, setRoe] = useState('');
  const [caseCode, setCaseCode] = useState('');
  const [customerPickerHint, setCustomerPickerHint] = useState<string | null>(null);
  const [gridApi, setGridApi] = useState<GridApi<CporCaseRow> | null>(null);
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [columnSearch, setColumnSearch] = useState('');
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>({});

  const { data: types } = useQuery({
    queryKey: ['cpor', 'promotion-types'],
    queryFn: ({ signal }) => apiGet<PromoTypes>('/api/v1/cpor/meta/promotion-types', { signal }),
  });

  const {
    data: casesPage,
    isLoading,
    isFetching,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['cpor', 'cases', status, q, customerId, page, pageSize],
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams();
      if (status) sp.set('status', status);
      if (q.trim()) sp.set('q', q.trim());
      if (customerId != null && Number.isFinite(customerId)) sp.set('customer_id', String(customerId));
      sp.set('limit', String(pageSize));
      sp.set('offset', String((page - 1) * pageSize));
      return apiGet<ListEnvelope>(`/api/v1/cpor/cases?${sp.toString()}`, { signal });
    },
  });

  const cases = casesPage?.items ?? [];
  const total = casesPage?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const create = useMutation({
    mutationFn: () =>
      apiPost<CporCaseRow>('/api/v1/cpor/cases', {
        customer_id: cust!.id,
        promotion_type: promoType,
        window_start: windowStart,
        window_end: windowEnd,
        case_code: caseCode.trim() || null,
        roe_snapshot: roe.trim() ? Number(roe) : null,
      }),
    onSuccess: async (row) => {
      setDlg(false);
      await qc.invalidateQueries({ queryKey: ['cpor', 'cases'] });
      router.push(`/commercial-planner/cpor-cases/${row.id}`);
    },
  });

  const toggleColumnVisibility = useCallback(
    (columnId: string, visible: boolean) => {
      setColumnVisibility((prev) => ({ ...prev, [columnId]: visible }));
      if (!gridApi?.setColumnsVisible) return;
      gridApi.setColumnsVisible([columnId], visible);
      try {
        localStorage.setItem(CPOR_GRID_STATE_KEY, JSON.stringify(gridApi.getColumnState()));
      } catch {
        /* ignore */
      }
    },
    [gridApi],
  );

  const columnDefs = useMemo<ColDef<CporCaseRow>[]>(
    () => [
      { colId: 'case_code', field: 'case_code', headerName: 'Case', width: 130 },
      { colId: 'case_name', field: 'case_name', headerName: 'Name', width: 160, hide: true },
      {
        colId: 'customer',
        headerName: 'Customer',
        flex: 1,
        minWidth: 160,
        valueGetter: (p) =>
          p.data ? `${p.data.customer_code ?? ''} — ${p.data.customer_name ?? ''}` : '',
      },
      { colId: 'promotion_type', field: 'promotion_type', headerName: 'Type', width: 140 },
      {
        colId: 'window',
        headerName: 'Window',
        width: 180,
        valueGetter: (p) =>
          p.data ? `${p.data.window_start ?? ''} → ${p.data.window_end ?? ''}` : '',
      },
      {
        colId: 'status',
        field: 'status',
        headerName: 'Status',
        width: 110,
        cellRenderer: (p: { value?: string }) =>
          p.value ? <Chip size="small" label={p.value} /> : null,
      },
      { colId: 'workflow_status', field: 'workflow_status', headerName: 'Workflow', width: 130 },
      { colId: 'export_version', field: 'export_version', headerName: 'Ver', width: 70 },
      { colId: 'line_count', field: 'line_count', headerName: 'Lines', width: 80 },
      {
        colId: 'ttl_support_zar',
        field: 'ttl_support_zar',
        headerName: 'Ttl ZAR',
        width: 110,
        valueFormatter: (p) => (p.value == null ? '' : Number(p.value).toFixed(2)),
      },
      {
        colId: 'ttl_support_usd',
        field: 'ttl_support_usd',
        headerName: 'Ttl USD',
        width: 110,
        valueFormatter: (p) => (p.value == null ? '' : Number(p.value).toFixed(2)),
      },
      {
        colId: 'missing_roe',
        field: 'missing_roe',
        headerName: 'Missing ROE',
        width: 120,
        hide: true,
        valueFormatter: (p) => (p.value ? 'yes' : ''),
      },
    ],
    [],
  );

  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Commercial Planning' }, { label: 'CPOR Cases' }]}
        title="CPOR Cases"
      />
      <Alert severity="info" sx={{ mb: 2 }}>
        Reseller-channel promotion funding cases. Money is computed server-side (U2). Flags never block saves.
      </Alert>
      <Stack direction="row" spacing={1} sx={{ mb: 1.5 }} alignItems="center" flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          label="Search"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Case code / name / customer"
          sx={{ minWidth: 220 }}
          data-testid="cpor-search"
        />
        <TextField
          select
          size="small"
          label="Status"
          value={status}
          onChange={(e) => setParamState({ status: e.target.value || null, page: '1' })}
          sx={{ minWidth: 160 }}
          data-testid="cpor-status-filter"
        >
          <MenuItem value="">All</MenuItem>
          {STATUS_OPTIONS.map((s) => (
            <MenuItem key={s} value={s}>
              {s}
            </MenuItem>
          ))}
        </TextField>
        <Box sx={{ minWidth: 260, flex: '1 1 220px' }} data-testid="cpor-customer-filter">
          <EntitySearchAutocomplete<CustomerPick>
            label="Customer"
            value={filterCustomer}
            onChange={(v) => {
              setFilterCustomer(v);
              setParamState({
                customer_id: v ? String(v.id) : null,
                page: '1',
              });
            }}
            getOptionLabel={(o) => `${o.customer_code} — ${o.customer_name}`}
            fetchOptions={async (needle, signal) => {
              const res = await apiGet<{ items: CustomerPick[]; total: number }>(
                `/api/v1/customers?page=1&page_size=25&q=${encodeURIComponent(needle)}`,
                { signal },
              );
              return res.items;
            }}
          />
        </Box>
        <Box sx={{ flex: 1 }} />
        <Button variant="outlined" size="small" onClick={() => setColumnsOpen(true)} data-testid="cpor-columns">
          Columns
        </Button>
        <ModuleGridToolbar onRefresh={() => void refetch()} busy={isFetching} sx={{ mb: 0 }} />
        <Button variant="contained" onClick={() => setDlg(true)} data-testid="cpor-new-case">
          New case
        </Button>
      </Stack>
      <ModuleDataSection
        isLoading={isLoading}
        isError={isError}
        error={(error as Error) ?? null}
        onRetry={() => void refetch()}
        isEmpty={total === 0}
        empty={{
          title: 'No CPOR cases',
          description: status || q || customerId
            ? 'No cases match the current filters.'
            : 'Create a case to get started.',
        }}
      >
        <EnterpriseDataGrid
          rowData={cases}
          columnDefs={columnDefs}
          height={560}
          gridOptions={{
            getRowId: (p) => String(p.data.id),
            loading: isFetching,
            onGridReady: (e) => {
              setGridApi(e.api);
              try {
                const raw = localStorage.getItem(CPOR_GRID_STATE_KEY);
                if (raw) {
                  const state = JSON.parse(raw);
                  if (Array.isArray(state)) e.api.applyColumnState({ state, applyOrder: true });
                }
              } catch {
                /* ignore */
              }
              const vis: Record<string, boolean> = {};
              for (const col of e.api.getColumns() ?? []) {
                vis[col.getColId()] = col.isVisible();
              }
              setColumnVisibility(vis);
            },
            onRowClicked: (e) => {
              if (e.data?.id) router.push(`/commercial-planner/cpor-cases/${e.data.id}`);
            },
          }}
        />
        <Stack direction="row" spacing={1} sx={{ mt: 2 }} alignItems="center" data-testid="cpor-cases-pager">
          <Button
            disabled={page <= 1 || isFetching}
            onClick={() => setParamState({ page: String(page - 1) })}
            data-testid="cpor-cases-prev"
          >
            Prev
          </Button>
          <Typography variant="body2">
            Page {page} / {totalPages} ({total} cases)
          </Typography>
          <Button
            disabled={page >= totalPages || isFetching}
            onClick={() => setParamState({ page: String(page + 1) })}
            data-testid="cpor-cases-next"
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
              data-testid="cpor-cases-page-size"
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

      <MasterColumnPickerDialog
        open={columnsOpen}
        onClose={() => setColumnsOpen(false)}
        title="CPOR case columns"
        groups={CPOR_COLUMN_GROUPS}
        columnLabelByField={CPOR_COLUMN_LABELS}
        visibility={columnVisibility}
        onToggle={toggleColumnVisibility}
        gridReady={Boolean(gridApi)}
        search={columnSearch}
        onSearchChange={setColumnSearch}
      />

      <Dialog open={dlg} onClose={() => !create.isPending && setDlg(false)} fullWidth maxWidth="sm">
        <DialogTitle>New CPOR case</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ pt: 1 }}>
            <EntitySearchAutocomplete<CustomerPick>
              label="Customer"
              value={cust}
              onChange={setCust}
              getOptionLabel={(o) => `${o.customer_code} — ${o.customer_name}`}
              helperText={customerPickerHint ?? undefined}
              fetchOptions={async (needle, signal) => {
                setCustomerPickerHint(null);
                if (needle.trim()) {
                  const res = await apiGet<{ items: CustomerPick[]; total: number }>(
                    `/api/v1/customers?page=1&page_size=25&q=${encodeURIComponent(needle)}`,
                    { signal },
                  );
                  return res.items;
                }
                const keyRes = await apiGet<{ items: CustomerPick[]; total: number }>(
                  `/api/v1/customers?page=1&page_size=25&is_key_account=true`,
                  { signal },
                );
                if (keyRes.items.length) return keyRes.items;
                setCustomerPickerHint('No key accounts — showing recent customers.');
                const allRes = await apiGet<{ items: CustomerPick[]; total: number }>(
                  `/api/v1/customers?page=1&page_size=25`,
                  { signal },
                );
                return allRes.items;
              }}
            />
            <TextField
              select
              size="small"
              label="Promotion type"
              value={promoType}
              onChange={(e) => setPromoType(e.target.value)}
              fullWidth
            >
              {(types?.promotion_types ?? ['Sell out PP']).map((t) => (
                <MenuItem key={t} value={t}>
                  {t}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              size="small"
              label="Window start"
              type="date"
              value={windowStart}
              onChange={(e) => setWindowStart(e.target.value)}
              InputLabelProps={{ shrink: true }}
              fullWidth
            />
            <TextField
              size="small"
              label="Window end"
              type="date"
              value={windowEnd}
              onChange={(e) => setWindowEnd(e.target.value)}
              InputLabelProps={{ shrink: true }}
              fullWidth
            />
            <TextField
              size="small"
              label="Case code (optional)"
              value={caseCode}
              onChange={(e) => setCaseCode(e.target.value)}
              fullWidth
            />
            <TextField
              size="small"
              label="ROE snapshot (optional)"
              value={roe}
              onChange={(e) => setRoe(e.target.value)}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDlg(false)} disabled={create.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!cust || !windowStart || !windowEnd || create.isPending}
            onClick={() => create.mutate()}
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
