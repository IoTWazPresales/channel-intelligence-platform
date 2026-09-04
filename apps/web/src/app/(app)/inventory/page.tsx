'use client';

import { Button, Dialog, DialogActions, DialogContent, DialogTitle, Paper, Stack, TextField } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { useMemo, useState } from 'react';

import { BulkPasteDialog } from '@/components/BulkPasteDialog';
import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { navPageChrome } from '@/features/shell/navPageChrome';
import { apiDelete, apiGet, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type Row = {
  id: number;
  product_sku: string | null;
  customer_code: string | null;
  on_hand_units: number;
  on_order_units: number;
  as_of_date: string;
};

type InvPasteRow = {
  sku: string;
  customer_code: string;
  as_of_date: string;
  on_hand_units: number;
  on_order_units: number;
};

function parseInventoryPaste(text: string): InvPasteRow[] {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (!lines.length) return [];
  const first = lines[0].toLowerCase();
  const hasHeader = first.includes('sku') && first.includes('customer');
  const dataLines = hasHeader ? lines.slice(1) : lines;
  const rows: InvPasteRow[] = [];
  for (const line of dataLines) {
    const parts = line.split(/[,\t]/).map((p) => p.trim().replace(/^"|"$/g, ''));
    if (parts.length < 4) continue;
    const [sku, customer_code, as_of_date, onHandS, onOrderS] = parts;
    if (!sku || !customer_code || !as_of_date) continue;
    const on_hand_units = Number(onHandS);
    const on_order_units = onOrderS !== undefined && onOrderS !== '' ? Number(onOrderS) : 0;
    if (!Number.isFinite(on_hand_units) || !Number.isFinite(on_order_units)) continue;
    rows.push({ sku, customer_code, as_of_date, on_hand_units, on_order_units });
  }
  return rows;
}

export default function InventoryPage() {
  const qc = useQueryClient();
  const [pasteOpen, setPasteOpen] = useState(false);
  const [paste, setPaste] = useState('');
  const [addOpen, setAddOpen] = useState(false);
  const [sku, setSku] = useState('');
  const [cust, setCust] = useState('');
  const [asOf, setAsOf] = useState(() => new Date().toISOString().slice(0, 10));
  const [onHand, setOnHand] = useState('');
  const [onOrder, setOnOrder] = useState('0');

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['inventory-customer'],
    queryFn: ({ signal }) => apiGet<Row[]>('/api/v1/inventory/customer', { signal }),
  });

  const bulk = useMutation({
    mutationFn: (rows: InvPasteRow[]) => apiPost<{ created: number }>('/api/v1/inventory/customer/bulk', { rows }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inventory-customer'] });
      setPasteOpen(false);
      setPaste('');
    },
  });

  const addOne = useMutation({
    mutationFn: () =>
      apiPost<{ id: number }>('/api/v1/inventory/customer', {
        sku: sku.trim(),
        customer_code: cust.trim(),
        as_of_date: asOf.trim(),
        on_hand_units: Number(onHand),
        on_order_units: onOrder.trim() === '' ? 0 : Number(onOrder),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inventory-customer'] });
      setAddOpen(false);
      setSku('');
      setCust('');
      setAsOf(new Date().toISOString().slice(0, 10));
      setOnHand('');
      setOnOrder('0');
    },
  });

  const delRow = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/inventory/customer/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventory-customer'] }),
  });
  const clearAll = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/inventory/customer/clear-all', { confirm: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventory-customer'] }),
  });

  const colDefs: ColDef<Row>[] = useMemo(() => {
    const busyDel = delRow.isPending || clearAll.isPending;
    return [
      { field: 'product_sku', headerName: 'SKU', pinned: 'left', minWidth: 140 },
      { field: 'customer_code', headerName: 'Customer', minWidth: 120 },
      { field: 'on_hand_units', headerName: 'On hand', type: 'numericColumn' },
      { field: 'on_order_units', headerName: 'On order', type: 'numericColumn' },
      { field: 'as_of_date', headerName: 'As of', minWidth: 120 },
      gridDeleteColumn<Row>((id) => void delRow.mutate(id), { busy: busyDel }),
    ];
  }, [delRow, delRow.isPending, clearAll.isPending]);

  const rows = data ?? [];
  const busy = bulk.isPending || addOne.isPending || delRow.isPending || clearAll.isPending;

  return (
    <>
      <PageHeader {...navPageChrome('/stock', { search: '?lens=cover' })} />
      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          intro="Rows are stored in fact_inventory_customer. Unknown SKUs and customer codes create placeholder dimension rows."
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={rows.length === 0}
          empty={{
            title: 'No customer inventory rows',
            description: 'Use Add row or Paste upload, or use Import Center for file-based loads.',
            primary: { label: 'Import Center', href: '/admin/imports' },
            secondary: { label: 'Attention', href: '/brief' },
          }}
          toolbar={
            <ModuleGridToolbar
              onRefresh={() => qc.invalidateQueries({ queryKey: ['inventory-customer'] })}
              onClearAll={() => {
                if (!window.confirm('Delete every customer inventory row? This cannot be undone.')) return;
                void clearAll.mutate();
              }}
              onAdd={() => setAddOpen(true)}
              onUpload={() => setPasteOpen(true)}
              importsHref="/admin/imports"
              busy={busy}
            />
          }
        >
          <EnterpriseDataGrid rowData={rows} columnDefs={colDefs} />
        </ModuleDataSection>
      </Paper>

      <BulkPasteDialog
        open={pasteOpen}
        title="Paste customer inventory"
        hint={
          <>
            Columns: <code>sku, customer_code, as_of_date, on_hand_units</code> and optional{' '}
            <code>on_order_units</code> (defaults to 0). Example: <code>SKU-001,CUST-1001,2026-04-12,180,60</code>
          </>
        }
        placeholder="sku,customer_code,as_of_date,on_hand_units,on_order_units"
        value={paste}
        onChange={setPaste}
        onClose={() => !bulk.isPending && setPasteOpen(false)}
        onSubmit={() => bulk.mutate(parseInventoryPaste(paste))}
        busy={bulk.isPending}
        error={bulk.error as Error | null}
      />

      <Dialog open={addOpen} onClose={() => !addOne.isPending && setAddOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Add inventory row</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="SKU" required value={sku} onChange={(e) => setSku(e.target.value)} fullWidth />
            <TextField label="Customer code" required value={cust} onChange={(e) => setCust(e.target.value)} fullWidth />
            <TextField label="As of date" required type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} fullWidth InputLabelProps={{ shrink: true }} />
            <TextField label="On hand units" required type="number" value={onHand} onChange={(e) => setOnHand(e.target.value)} fullWidth />
            <TextField label="On order units" type="number" value={onOrder} onChange={(e) => setOnOrder(e.target.value)} fullWidth />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)} disabled={addOne.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={addOne.isPending || !sku.trim() || !cust.trim() || !Number.isFinite(Number(onHand))}
            onClick={() => addOne.mutate()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
