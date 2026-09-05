'use client';

import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import NextLink from 'next/link';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { FundingChrome } from '@/features/promotions-funding/FundingChrome';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { apiGet, apiPatch, apiPost } from '@/lib/api';

type CustomerTermRow = {
  id: number;
  customer_id: number;
  customer_code: string;
  customer_name: string;
  customer_margin_pct: number;
  customer_rebate_pct: number;
};

type CustomerPick = {
  id: number;
  customer_code: string;
  customer_name: string;
};

function pctLabel(v: number): string {
  return `${(Number(v) * 100).toFixed(2)}%`;
}

export default function CustomerCommercialTermsPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState('');
  const [dlg, setDlg] = useState<'add' | 'edit' | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [custPick, setCustPick] = useState<CustomerPick | null>(null);
  const [margin, setMargin] = useState('0.12');
  const [rebate, setRebate] = useState('0.03');

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['commercial-planner', 'customer-terms', 'steward', filter],
    queryFn: ({ signal }) => {
      const q = filter.trim() ? `?q=${encodeURIComponent(filter.trim())}` : '';
      return apiGet<CustomerTermRow[]>(`/api/v1/commercial-planner/customer-terms${q}`, { signal });
    },
  });

  const save = useMutation({
    mutationFn: async () => {
      const m = Number(margin);
      const r = Number(rebate);
      if (dlg === 'edit' && editId != null) {
        return apiPatch<CustomerTermRow>(`/api/v1/commercial-planner/customer-terms/${editId}`, {
          customer_margin_pct: m,
          customer_rebate_pct: r,
        });
      }
      if (!custPick) throw new Error('Select a customer');
      return apiPost<CustomerTermRow>('/api/v1/commercial-planner/customer-terms', {
        customer_id: custPick.id,
        customer_margin_pct: m,
        customer_rebate_pct: r,
      });
    },
    onSuccess: async () => {
      setDlg(null);
      setEditId(null);
      setCustPick(null);
      await qc.invalidateQueries({ queryKey: ['commercial-planner', 'customer-terms'] });
      await refetch();
    },
  });

  const openAdd = () => {
    setDlg('add');
    setEditId(null);
    setCustPick(null);
    setMargin('0.12');
    setRebate('0.03');
  };

  const openEdit = (row: CustomerTermRow) => {
    setDlg('edit');
    setEditId(row.id);
    setCustPick({
      id: row.customer_id,
      customer_code: row.customer_code,
      customer_name: row.customer_name,
    });
    setMargin(String(row.customer_margin_pct));
    setRebate(String(row.customer_rebate_pct));
  };

  const columnDefs = useMemo<ColDef<CustomerTermRow>[]>(
    () => [
      { field: 'customer_code', headerName: 'Customer code', flex: 1, minWidth: 120 },
      { field: 'customer_name', headerName: 'Customer name', flex: 1.5, minWidth: 180 },
      {
        field: 'customer_margin_pct',
        headerName: 'Dealer margin',
        width: 130,
        valueFormatter: (p) => (p.value == null ? '' : pctLabel(Number(p.value))),
      },
      {
        field: 'customer_rebate_pct',
        headerName: 'Rebate / support',
        width: 140,
        valueFormatter: (p) => (p.value == null ? '' : pctLabel(Number(p.value))),
      },
      {
        headerName: '',
        width: 100,
        sortable: false,
        filter: false,
        cellRenderer: (p: ICellRendererParams<CustomerTermRow>) =>
          p.data ? (
            <Button size="small" onClick={() => openEdit(p.data!)} data-testid={`customer-terms-row-edit-${p.data.id}`}>
              Edit
            </Button>
          ) : null,
      },
    ],
    [],
  );

  return (
    <FundingChrome>
      <Alert severity="info" sx={{ mt: 2, mb: 2 }} data-testid="customer-terms-steward-guide">
        Customer margin and rebate defaults plus per-SKU assumptions feed the waterfall in the planner
        (dealer price → support per unit). Edited here, applied on the next recompute. SKU assumptions
        live on Commercial planner — this leaf does not invent a second economics editor.
      </Alert>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
        <TextField
          size="small"
          label="Filter by code or name"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          sx={{ minWidth: 280 }}
          data-testid="customer-terms-filter"
        />
        <Box sx={{ flex: 1 }} />
        <Button
          component={NextLink}
          href="/commercial-planner"
          variant="outlined"
          data-testid="customer-terms-sku-assumptions"
        >
          Open SKU assumptions
        </Button>
        <Button variant="contained" onClick={openAdd} data-testid="customer-terms-steward-add">
          Add terms
        </Button>
      </Stack>
      {isError ? (
        <Alert severity="error">{String((error as Error)?.message ?? 'Failed to load customer terms')}</Alert>
      ) : null}
      <EnterpriseDataGrid
        rowData={data ?? []}
        columnDefs={columnDefs}
        height={560}
        gridOptions={{
          getRowId: (p) => String(p.data.id),
          loading: isLoading,
        }}
      />

      <Dialog open={dlg != null} onClose={() => !save.isPending && setDlg(null)} fullWidth maxWidth="sm">
        <DialogTitle>{dlg === 'edit' ? 'Edit commercial terms' : 'Create commercial terms'}</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ pt: 1 }}>
            {dlg === 'add' ? (
              <EntitySearchAutocomplete<CustomerPick>
                label="Customer"
                value={custPick}
                onChange={setCustPick}
                getOptionLabel={(o) => `${o.customer_code} — ${o.customer_name}`}
                fetchOptions={async (q, signal) => {
                  const res = await apiGet<{
                    items: { id: number; customer_code: string; customer_name: string }[];
                  }>(`/api/v1/customers?page=1&page_size=25&q=${encodeURIComponent(q)}`, { signal });
                  return (res.items ?? []).map((r) => ({
                    id: r.id,
                    customer_code: r.customer_code,
                    customer_name: r.customer_name,
                  }));
                }}
              />
            ) : (
              <Typography variant="body2" color="text.secondary">
                Customer: {custPick?.customer_code} — {custPick?.customer_name}
              </Typography>
            )}
            <TextField
              label="Dealer margin (decimal, e.g. 0.12 = 12%)"
              value={margin}
              onChange={(e) => setMargin(e.target.value)}
              size="small"
              fullWidth
            />
            <TextField
              label="Rebate / support (decimal)"
              value={rebate}
              onChange={(e) => setRebate(e.target.value)}
              size="small"
              fullWidth
            />
            {save.isError ? (
              <Alert severity="error">
                {String((save.error as Error)?.message ?? 'Save failed. Check margin + rebate stay below 0.92.')}
              </Alert>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDlg(null)} disabled={save.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={
              save.isPending ||
              !Number.isFinite(Number(margin)) ||
              !Number.isFinite(Number(rebate)) ||
              (dlg === 'add' && !custPick)
            }
            onClick={() => save.mutate()}
            data-testid="customer-terms-steward-save"
          >
            {save.isPending ? 'Saving…' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>
    </FundingChrome>
  );
}
