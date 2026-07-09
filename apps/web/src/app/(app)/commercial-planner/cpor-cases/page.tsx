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
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import type { ColDef } from 'ag-grid-community';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { PageHeader } from '@/components/PageHeader';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { apiGet, apiPost } from '@/lib/api';

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
  ttl_support_zar: number | null;
  ttl_support_usd: number | null;
  missing_roe: boolean;
};

type CustomerPick = { id: number; customer_code: string; customer_name: string };

type PromoTypes = { promotion_types: string[] };

export default function CporCasesListPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [status, setStatus] = useState('');
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
    queryKey: ['cpor', 'cases', status],
    queryFn: ({ signal }) => {
      const q = status ? `?status=${encodeURIComponent(status)}` : '';
      return apiGet<CporCaseRow[]>(`/api/v1/cpor/cases${q}`, { signal });
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

  const columnDefs = useMemo<ColDef<CporCaseRow>[]>(
    () => [
      { field: 'case_code', headerName: 'Case', width: 130 },
      {
        headerName: 'Customer',
        flex: 1,
        minWidth: 160,
        valueGetter: (p) =>
          p.data ? `${p.data.customer_code ?? ''} — ${p.data.customer_name ?? ''}` : '',
      },
      { field: 'promotion_type', headerName: 'Type', width: 140 },
      {
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
      <Stack direction="row" spacing={1} sx={{ mb: 1.5 }} alignItems="center">
        <TextField
          select
          size="small"
          label="Status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
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
        <Box sx={{ flex: 1 }} />
        <Button variant="contained" onClick={() => setDlg(true)} data-testid="cpor-new-case">
          New case
        </Button>
      </Stack>
      {isError ? <Alert severity="error">{String((error as Error)?.message)}</Alert> : null}
      <EnterpriseDataGrid
        rowData={data ?? []}
        columnDefs={columnDefs}
        height={560}
        gridOptions={{
          getRowId: (p) => String(p.data.id),
          loading: isLoading,
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
              fetchOptions={async (q, signal) => {
                const needle = q.trim();
                // Typing searches all customers. Empty query defaults to key accounts
                // with graceful fallback when none are flagged.
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
            {create.isError ? <Alert severity="error">{String((create.error as Error)?.message)}</Alert> : null}
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
