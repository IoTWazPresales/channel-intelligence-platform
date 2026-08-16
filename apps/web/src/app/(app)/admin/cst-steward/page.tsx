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
import { navPageChrome } from '@/features/shell/navPageChrome';
import { OPS_LIST_GRID_PAGINATION } from '@/features/shell/opsListGridPagination';
import { apiGet, apiPatch, apiPost } from '@/lib/api';

import { CstArticleAliasesSection } from './CstArticleAliasesSection';

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

  return (
    <>
      <PageHeader {...navPageChrome('/admin/cst-steward')} />
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
            gridOptions={{
              getRowId: (p) => String(p.data!.customer_id),
              loading: loadingAccounts,
              ...OPS_LIST_GRID_PAGINATION,
            }}
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
            gridOptions={{
              getRowId: (p) => String(p.data!.id),
              loading: loadingSlots,
              ...OPS_LIST_GRID_PAGINATION,
            }}
          />
        </>
      ) : null}

      {tab === 2 ? <CstArticleAliasesSection /> : null}

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
