'use client';

import {
  Alert,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import type { ColDef } from 'ag-grid-community';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useMemo, useState } from 'react';

import { PageHeader } from '@/components/PageHeader';
import { MasterDataGridShell } from '@/components/masterGrid/MasterDataGridShell';
import type { MasterColumnPickerGroup } from '@/components/masterGrid/MasterColumnPickerDialog';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { apiGet, apiPost } from '@/lib/api';

import { CporPortfolioIntelligencePanel } from './CporPortfolioIntelligencePanel';

type CporCaseRow = {
  id: number;
  case_code: string;
  customer_code: string | null;
  customer_name: string | null;
  promotion_type: string;
  window_start: string | null;
  window_end: string | null;
  status: string;
  workflow_status: string;
  export_version: number;
  origin?: string | null;
  ttl_support_zar: number | null;
  ttl_support_usd: number | null;
  payment_evidence_count?: number;
  paid_amount_sum?: number | null;
  owed_amount?: number | null;
  outstanding_amount?: number | null;
  recon_status?: string | null;
  recon_flags?: string[];
  last_payment_date?: string | null;
  latest_payment_status?: string | null;
  credit_note_ids?: string[];
};

type CasesPage = { items: CporCaseRow[]; total: number; page: number; page_size: number };
type CustomerPick = { id: number; customer_code: string; customer_name: string };
type PromoTypes = { promotion_types: string[] };

const GRID_STATE_KEY = 'cip.cpor.cases.grid.v2';
const DEFAULT_PAGE_SIZE = 50;
const DEFAULT_SORT_BY = 'id';
const DEFAULT_SORT_DIR = 'desc' as const;

const COLUMN_GROUPS: MasterColumnPickerGroup[] = [
  {
    label: 'Core',
    fields: ['case_code', 'customer', 'promotion_type', 'window', 'status', 'workflow_status', 'origin'],
  },
  {
    label: 'Support',
    fields: ['ttl_support_zar', 'ttl_support_usd', 'export_version'],
  },
  {
    label: 'Payment recon',
    fields: [
      'owed_amount',
      'paid_amount_sum',
      'outstanding_amount',
      'recon_status',
      'latest_payment_status',
      'last_payment_date',
      'payment_evidence_count',
    ],
  },
];

const DEFAULT_HIDDEN = ['export_version', 'workflow_status'] as const;

export default function CporCasesListPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const qc = useQueryClient();

  const page = Math.max(1, Number(searchParams.get('page') || '1') || 1);
  const pageSize = Math.max(1, Number(searchParams.get('page_size') || String(DEFAULT_PAGE_SIZE)) || DEFAULT_PAGE_SIZE);
  const q = searchParams.get('q') || '';
  const status = searchParams.get('status') || '';
  const sortBy = searchParams.get('sort_by') || DEFAULT_SORT_BY;
  const sortDir = (searchParams.get('sort_dir') === 'asc' ? 'asc' : 'desc') as 'asc' | 'desc';

  const setParamState = useCallback(
    (patch: Record<string, string | null>, resetPage?: boolean) => {
      const next = new URLSearchParams(searchParams.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v == null || v === '') next.delete(k);
        else next.set(k, v);
      }
      if (resetPage) next.set('page', '1');
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname);
    },
    [pathname, router, searchParams],
  );

  const [dlg, setDlg] = useState(false);
  const [cust, setCust] = useState<CustomerPick | null>(null);
  const [promoType, setPromoType] = useState('Sell out PP');
  const [windowStart, setWindowStart] = useState('');
  const [windowEnd, setWindowEnd] = useState('');
  const [roe, setRoe] = useState('');
  const [caseCode, setCaseCode] = useState('');
  const [customerPickerHint, setCustomerPickerHint] = useState<string | null>(null);

  const { data: types } = useQuery({
    queryKey: ['cpor', 'promotion-types'],
    queryFn: ({ signal }) => apiGet<PromoTypes>('/api/v1/cpor/meta/promotion-types', { signal }),
  });

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['cpor', 'cases', page, pageSize, q, status, sortBy, sortDir],
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams();
      sp.set('page', String(page));
      sp.set('page_size', String(pageSize));
      if (q.trim()) sp.set('q', q.trim());
      if (status) sp.set('status', status);
      return apiGet<CasesPage>(`/api/v1/cpor/cases?${sp.toString()}`, { signal });
    },
  });

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

  const [bulkSelectionMode, setBulkSelectionMode] = useState<'normal' | 'selecting'>('normal');

  const columnDefs = useMemo<ColDef<CporCaseRow>[]>(
    () => [
      { field: 'case_code', headerName: 'Case', width: 130 },
      {
        colId: 'customer',
        headerName: 'Customer',
        flex: 1,
        minWidth: 160,
        valueGetter: (p) =>
          p.data ? `${p.data.customer_code ?? ''} — ${p.data.customer_name ?? ''}` : '',
      },
      { field: 'promotion_type', headerName: 'Type', width: 140 },
      {
        colId: 'window',
        headerName: 'Window',
        width: 180,
        valueGetter: (p) =>
          p.data ? `${p.data.window_start ?? ''} → ${p.data.window_end ?? ''}` : '',
      },
      {
        field: 'status',
        headerName: 'Status',
        width: 110,
        cellRenderer: (p: { value?: string }) =>
          p.value ? <Chip size="small" label={p.value} /> : null,
      },
      { field: 'workflow_status', headerName: 'Workflow', width: 130 },
      {
        field: 'origin',
        headerName: 'Origin',
        width: 120,
        cellRenderer: (p: { value?: string }) =>
          p.value ? <Chip size="small" variant="outlined" label={p.value} /> : null,
      },
      { field: 'export_version', headerName: 'Ver', width: 70 },
      {
        field: 'ttl_support_zar',
        headerName: 'Ttl ZAR',
        width: 110,
        valueFormatter: (p) => (p.value == null ? '' : Number(p.value).toFixed(2)),
      },
      {
        field: 'ttl_support_usd',
        headerName: 'Ttl USD',
        width: 110,
        valueFormatter: (p) => (p.value == null ? '' : Number(p.value).toFixed(2)),
      },
      {
        field: 'owed_amount',
        headerName: 'Owed',
        width: 110,
        valueFormatter: (p) => (p.value == null ? '' : Number(p.value).toFixed(2)),
      },
      {
        field: 'paid_amount_sum',
        headerName: 'Paid',
        width: 110,
        valueFormatter: (p) => (p.value == null ? '' : Number(p.value).toFixed(2)),
      },
      {
        field: 'outstanding_amount',
        headerName: 'Outstanding',
        width: 120,
        valueFormatter: (p) => (p.value == null ? '' : Number(p.value).toFixed(2)),
      },
      {
        field: 'recon_status',
        headerName: 'Recon',
        width: 130,
        cellRenderer: (p: { value?: string }) =>
          p.value ? <Chip size="small" variant="outlined" label={p.value} /> : null,
      },
      {
        field: 'latest_payment_status',
        headerName: 'Payment',
        width: 120,
        cellRenderer: (p: { value?: string }) =>
          p.value ? <Chip size="small" color="info" label={p.value} /> : null,
      },
      { field: 'last_payment_date', headerName: 'Last paid', width: 120 },
      { field: 'payment_evidence_count', headerName: 'CN rows', width: 90 },
    ],
    [],
  );

  const columnLabelByField = useMemo(() => {
    const m: Record<string, string> = {};
    for (const c of columnDefs) {
      const key = String(c.colId || c.field || '');
      if (key && c.headerName) m[key] = String(c.headerName);
    }
    return m;
  }, [columnDefs]);

  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Commercial Planning' }, { label: 'CPOR Cases' }]}
        title="CPOR Cases"
      />
      <Alert severity="info" sx={{ mb: 2 }}>
        Reseller-channel promotion funding cases. Recon: <strong>owed</strong> = approved
        ttl_support; <strong>paid</strong> = payment/CN evidence in paid/processed/closed.
        File case status stays evidence-only.
      </Alert>
      <CporPortfolioIntelligencePanel />
      <Stack direction="row" spacing={1} sx={{ mb: 1.5 }} alignItems="center" flexWrap="wrap">
        <TextField
          select
          size="small"
          label="Status"
          value={status}
          onChange={(e) => setParamState({ status: e.target.value || null }, true)}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="">All</MenuItem>
          {['draft', 'proposed', 'approved', 'rejected', 'active', 'ended', 'settled', 'cancelled'].map(
            (s) => (
              <MenuItem key={s} value={s}>
                {s}
              </MenuItem>
            ),
          )}
        </TextField>
        <Button
          component={Link}
          variant="outlined"
          href="/commercial-planner/cpor-cases/historical-import"
          data-testid="cpor-historical-import"
        >
          Import historical
        </Button>
        <Button
          component={Link}
          variant="outlined"
          href="/commercial-planner/cpor-cases/payment-evidence-import"
          data-testid="cpor-payment-evidence-import"
        >
          Import payment / CN
        </Button>
        <Button variant="contained" onClick={() => setDlg(true)} data-testid="cpor-new-case">
          New case
        </Button>
      </Stack>

      <MasterDataGridShell
        entityKey="cpor-cases"
        rows={data?.items ?? []}
        columnDefs={columnDefs}
        total={data?.total ?? 0}
        isLoading={isLoading}
        isError={isError}
        error={error as Error | null}
        onRetry={() => void refetch()}
        empty={{
          title: 'No CPOR cases yet',
          description: 'Create a case, import a historical tracking workbook, or import payment / CN evidence.',
          primary: { label: 'New case', href: '/commercial-planner/cpor-cases?create=1' },
          secondary: {
            label: 'Import payment / CN',
            href: '/commercial-planner/cpor-cases/payment-evidence-import',
          },
        }}
        url={{ page, pageSize, q, sortBy, sortDir }}
        onUrlChange={setParamState}
        defaultPageSize={DEFAULT_PAGE_SIZE}
        defaultSortBy={DEFAULT_SORT_BY}
        defaultSortDir={DEFAULT_SORT_DIR}
        gridStateStorageKey={GRID_STATE_KEY}
        defaultInitiallyHiddenFields={DEFAULT_HIDDEN}
        columnPickerTitle="Manage CPOR case columns"
        columnPickerGroups={COLUMN_GROUPS}
        columnLabelByField={columnLabelByField}
        bulkSelectionEnabled={false}
        bulkSelectionMode={bulkSelectionMode}
        onBulkSelectionModeChange={setBulkSelectionMode}
        onPreviewBulkDelete={() => undefined}
        onRefresh={() => void refetch()}
        gridOptions={{
          getRowId: (p) => String(p.data.id),
          onRowClicked: (e) => {
            if (e.data?.id) router.push(`/commercial-planner/cpor-cases/${e.data.id}`);
          },
        }}
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
              fetchOptions={async (query, signal) => {
                const needle = query.trim();
                if (needle) {
                  setCustomerPickerHint(null);
                  const res = await apiGet<{ items: CustomerPick[]; total: number }>(
                    `/api/v1/customers?page=1&page_size=25&q=${encodeURIComponent(needle)}`,
                    { signal },
                  );
                  return res.items ?? [];
                }
                const keyRes = await apiGet<{ items: CustomerPick[]; total: number }>(
                  `/api/v1/customers?page=1&page_size=25&is_key_account=true`,
                  { signal },
                );
                if ((keyRes.total ?? 0) > 0 && (keyRes.items?.length ?? 0) > 0) {
                  setCustomerPickerHint(null);
                  return keyRes.items ?? [];
                }
                setCustomerPickerHint('No key accounts flagged — showing all customers');
                const allRes = await apiGet<{ items: CustomerPick[]; total: number }>(
                  `/api/v1/customers?page=1&page_size=25`,
                  { signal },
                );
                return allRes.items ?? [];
              }}
            />
            {customerPickerHint ? (
              <Alert severity="info" data-testid="cpor-customer-picker-hint">
                {customerPickerHint}
              </Alert>
            ) : null}
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
              type="date"
              label="Window start"
              InputLabelProps={{ shrink: true }}
              value={windowStart}
              onChange={(e) => setWindowStart(e.target.value)}
              fullWidth
            />
            <TextField
              size="small"
              type="date"
              label="Window end"
              InputLabelProps={{ shrink: true }}
              value={windowEnd}
              onChange={(e) => setWindowEnd(e.target.value)}
              fullWidth
            />
            <TextField
              size="small"
              label="ROE snapshot (optional)"
              value={roe}
              onChange={(e) => setRoe(e.target.value)}
              fullWidth
            />
            <TextField
              size="small"
              label="External case code (optional)"
              value={caseCode}
              onChange={(e) => setCaseCode(e.target.value)}
              fullWidth
            />
            {create.isError ? (
              <Alert severity="error">{String((create.error as Error).message)}</Alert>
            ) : null}
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
