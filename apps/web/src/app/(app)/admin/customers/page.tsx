'use client';

import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { CellValueChangedEvent, ColDef, GridOptions } from 'ag-grid-community';
import { useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { apiDelete, apiGet, apiPatch, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type CustomerRow = {
  id: number;
  code: string;
  name: string;
  region_id: number | null;
  channel_id: number | null;
  region_code: string | null;
  channel_code: string | null;
};

type CodeRow = { id: number; code: string; name: string };

function parseCustomerCsv(text: string): {
  code: string;
  name: string;
  region_code?: string;
  channel_code?: string;
}[] {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length === 0) return [];
  const first = lines[0].toLowerCase();
  const hasHeader = first.includes('code') && first.includes('name');
  const dataLines = hasHeader ? lines.slice(1) : lines;
  const rows: { code: string; name: string; region_code?: string; channel_code?: string }[] = [];
  for (const line of dataLines) {
    const parts = line.split(',').map((p) => p.trim().replace(/^"|"$/g, ''));
    if (parts.length < 2) continue;
    const [code, name, region_code, channel_code] = parts;
    if (!code || !name) continue;
    const r: { code: string; name: string; region_code?: string; channel_code?: string } = { code, name };
    if (region_code) r.region_code = region_code;
    if (channel_code) r.channel_code = channel_code;
    rows.push(r);
  }
  return rows;
}

export default function AdminCustomersPage() {
  const qc = useQueryClient();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [paste, setPaste] = useState('');

  const {
    data: customers,
    isLoading: customersLoading,
    isError: customersIsError,
    error: customersErr,
    refetch: refetchCustomers,
  } = useQuery({
    queryKey: ['admin-customers'],
    queryFn: ({ signal }) => apiGet<CustomerRow[]>('/api/v1/customers', { signal }),
  });
  const { data: channels } = useQuery({
    queryKey: ['catalog-channels'],
    queryFn: ({ signal }) => apiGet<CodeRow[]>('/api/v1/catalog/channels', { signal }),
  });
  const { data: regions } = useQuery({
    queryKey: ['catalog-regions'],
    queryFn: ({ signal }) => apiGet<CodeRow[]>('/api/v1/catalog/regions', { signal }),
  });

  const channelCodes = useMemo(() => ['', ...(channels ?? []).map((c) => c.code)], [channels]);
  const regionCodes = useMemo(() => ['', ...(regions ?? []).map((r) => r.code)], [regions]);

  const bulk = useMutation({
    mutationFn: (rows: ReturnType<typeof parseCustomerCsv>) => apiPost('/api/v1/customers/bulk', { rows }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-customers'] });
      setUploadOpen(false);
      setPaste('');
    },
  });

  const delCustomer = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/customers/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-customers'] }),
  });

  const onCellValueChanged = useCallback(
    async (e: CellValueChangedEvent<CustomerRow>) => {
      const id = e.data?.id;
      if (id == null || e.oldValue === e.newValue) return;
      const field = e.colDef.field;
      try {
        if (field === 'name') {
          await apiPatch(`/api/v1/customers/${id}`, { name: String(e.newValue ?? '') });
        } else if (field === 'channel_code') {
          const code = String(e.newValue ?? '');
          const ch = (channels ?? []).find((c) => c.code === code);
          await apiPatch(`/api/v1/customers/${id}`, { channel_id: ch ? ch.id : null });
        } else if (field === 'region_code') {
          const code = String(e.newValue ?? '');
          const reg = (regions ?? []).find((r) => r.code === code);
          await apiPatch(`/api/v1/customers/${id}`, { region_id: reg ? reg.id : null });
        }
        await qc.invalidateQueries({ queryKey: ['admin-customers'] });
      } catch (err) {
        console.error(err);
        await qc.invalidateQueries({ queryKey: ['admin-customers'] });
      }
    },
    [channels, qc, regions]
  );

  const colDefs: ColDef<CustomerRow>[] = useMemo(
    () => [
      { field: 'code', headerName: 'Code', pinned: 'left', minWidth: 120, editable: false },
      { field: 'name', headerName: 'Name', flex: 1, minWidth: 180, editable: true },
      {
        field: 'region_code',
        headerName: 'Region',
        minWidth: 120,
        editable: true,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: regionCodes },
      },
      {
        field: 'channel_code',
        headerName: 'Channel',
        minWidth: 120,
        editable: true,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: channelCodes },
      },
      gridDeleteColumn<CustomerRow>((id) => void delCustomer.mutate(id), { busy: delCustomer.isPending }),
    ],
    [channelCodes, regionCodes, delCustomer, delCustomer.isPending]
  );

  const gridOptions: GridOptions<CustomerRow> = useMemo(
    () => ({ singleClickEdit: true, onCellValueChanged }),
    [onCellValueChanged]
  );

  const rows = customers ?? [];

  return (
    <>
      <PageHeader crumbs={[{ label: 'Admin' }, { label: 'Customers' }]} title="Customers & channels" />
      <Alert severity="info" sx={{ mb: 2 }}>
        Assign each customer to a <strong>region</strong> and <strong>channel</strong> (how they show up in planning views).
        Edit cells directly, or paste CSV with optional header: <code>code,name,region_code,channel_code</code>.
      </Alert>
      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <Button variant="contained" onClick={() => setUploadOpen(true)}>
          Upload CSV (paste)
        </Button>
        <ModuleGridToolbar
          onRefresh={() => qc.invalidateQueries({ queryKey: ['admin-customers'] })}
          sx={{ mb: 0 }}
          busy={delCustomer.isPending}
        />
      </Stack>
      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          intro={<>Master list is stored in <strong>dim_customer</strong>. Channel codes must match catalog channels.</>}
          isLoading={customersLoading}
          isError={customersIsError}
          error={toQueryError(customersErr)}
          onRetry={() => void refetchCustomers()}
          isEmpty={rows.length === 0}
          empty={{
            title: 'No customers yet',
            description: 'Upload a CSV paste or use Data imports when a customer source is registered.',
            primary: { label: 'Getting started', href: '/getting-started' },
            secondary: { label: 'Data & imports', href: '/admin/imports' },
          }}
        >
          <EnterpriseDataGrid rowData={rows} columnDefs={colDefs} gridOptions={gridOptions} height={520} />
        </ModuleDataSection>
      </Paper>

      <Dialog open={uploadOpen} onClose={() => !bulk.isPending && setUploadOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Paste customer rows</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            Example: <code>CUST-2001,New Retail Partner,NA-W,RET</code>
          </Typography>
          <TextField
            multiline
            minRows={10}
            fullWidth
            value={paste}
            onChange={(ev) => setPaste(ev.target.value)}
            placeholder="code,name,region_code,channel_code"
          />
          {bulk.isError ? (
            <Alert severity="error" sx={{ mt: 2 }}>
              {(bulk.error as Error).message}
            </Alert>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUploadOpen(false)} disabled={bulk.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={bulk.isPending || !paste.trim()}
            onClick={() => bulk.mutate(parseCustomerCsv(paste))}
          >
            Import
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
