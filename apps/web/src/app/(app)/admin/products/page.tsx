'use client';

import {
  Alert,
  Box,
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
import { apiDelete, apiGet, apiPatch, apiPost, HttpConflictError } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type ProductRow = {
  id: number;
  sku: string;
  name: string;
  category: string | null;
  form_factor: string | null;
  is_active: boolean;
  channel_id: number | null;
  channel_code: string | null;
};

type CodeRow = { id: number; code: string; name: string };

function parseProductCsv(text: string): {
  sku: string;
  name: string;
  category?: string;
  channel_code?: string;
}[] {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length === 0) return [];
  const first = lines[0].toLowerCase();
  const hasHeader = first.includes('sku') && first.includes('name');
  const dataLines = hasHeader ? lines.slice(1) : lines;
  const rows: { sku: string; name: string; category?: string; channel_code?: string }[] = [];
  for (const line of dataLines) {
    const parts = line.split(',').map((p) => p.trim().replace(/^"|"$/g, ''));
    if (parts.length < 2) continue;
    const [sku, name, category, channel_code] = parts;
    if (!sku || !name) continue;
    const r: { sku: string; name: string; category?: string; channel_code?: string } = { sku, name };
    if (category) r.category = category;
    if (channel_code) r.channel_code = channel_code;
    rows.push(r);
  }
  return rows;
}

export default function AdminProductsPage() {
  const qc = useQueryClient();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [paste, setPaste] = useState('');

  const {
    data: products,
    isLoading: productsLoading,
    isError: productsIsError,
    error: productsErr,
    refetch: refetchProducts,
  } = useQuery({
    queryKey: ['admin-products'],
    queryFn: ({ signal }) => apiGet<ProductRow[]>('/api/v1/products', { signal }),
  });
  const { data: channels } = useQuery({
    queryKey: ['catalog-channels'],
    queryFn: ({ signal }) => apiGet<CodeRow[]>('/api/v1/catalog/channels', { signal }),
  });

  const channelCodes = useMemo(() => ['', ...(channels ?? []).map((c) => c.code)], [channels]);

  const bulk = useMutation({
    mutationFn: (rows: ReturnType<typeof parseProductCsv>) => apiPost('/api/v1/products/bulk', { rows }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-products'] });
      setUploadOpen(false);
      setPaste('');
    },
  });

  const delProduct = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/products/id/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-products'] }),
  });

  const onCellValueChanged = useCallback(
    async (e: CellValueChangedEvent<ProductRow>) => {
      const id = e.data?.id;
      if (id == null || e.oldValue === e.newValue) return;
      const field = e.colDef.field;
      try {
        if (field === 'name') {
          await apiPatch(`/api/v1/products/${id}`, { name: String(e.newValue ?? '') });
        } else if (field === 'category') {
          await apiPatch(`/api/v1/products/${id}`, { category: String(e.newValue ?? '') || null });
        } else if (field === 'form_factor') {
          await apiPatch(`/api/v1/products/${id}`, { form_factor: String(e.newValue ?? '') || null });
        } else if (field === 'is_active') {
          await apiPatch(`/api/v1/products/${id}`, { is_active: Boolean(e.newValue) });
        } else if (field === 'channel_code') {
          const code = String(e.newValue ?? '');
          const ch = (channels ?? []).find((c) => c.code === code);
          await apiPatch(`/api/v1/products/${id}`, { channel_id: ch ? ch.id : null });
        }
        await qc.invalidateQueries({ queryKey: ['admin-products'] });
      } catch (err) {
        console.error(err);
        await qc.invalidateQueries({ queryKey: ['admin-products'] });
      }
    },
    [channels, qc]
  );

  const colDefs: ColDef<ProductRow>[] = useMemo(
    () => [
      { field: 'sku', headerName: 'SKU', pinned: 'left', minWidth: 140, editable: false },
      { field: 'name', headerName: 'Name', flex: 1, minWidth: 180, editable: true },
      { field: 'category', headerName: 'Category', minWidth: 120, editable: true },
      { field: 'form_factor', headerName: 'Form factor', minWidth: 120, editable: true },
      { field: 'is_active', headerName: 'Active', width: 100, editable: true, cellDataType: 'boolean' },
      {
        field: 'channel_code',
        headerName: 'Primary channel',
        minWidth: 140,
        editable: true,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: channelCodes },
      },
      gridDeleteColumn<ProductRow>((id) => void delProduct.mutate(id), {
        busy: delProduct.isPending,
        confirmMessage:
          'Delete this product from the global catalogue? Derived metrics and aliases are removed automatically. If sales, inventory, pricing, lineup, or other core facts still reference this SKU, the delete will be blocked.',
      }),
    ],
    [channelCodes, delProduct, delProduct.isPending]
  );

  const gridOptions: GridOptions<ProductRow> = useMemo(
    () => ({ singleClickEdit: true, onCellValueChanged }),
    [onCellValueChanged]
  );

  const rows = products ?? [];

  return (
    <>
      <PageHeader crumbs={[{ label: 'Admin' }, { label: 'Products' }]} title="Products & channel placement" />
      <Alert severity="info" sx={{ mb: 2 }}>
        <strong>Primary channel</strong> on a product is a planning default (SKU-level shelf); sell-out rows can still
        carry their own channel. Edit grid cells or paste CSV: <code>sku,name,category,channel_code</code>.
      </Alert>
      {delProduct.isError ? (
        <Alert severity="warning" sx={{ mb: 2 }} onClose={() => delProduct.reset()}>
          {HttpConflictError.is(delProduct.error) ? (
            <Stack spacing={1}>
              <Typography variant="body2">{delProduct.error.message}</Typography>
              {delProduct.error.references.length > 0 ? (
                <>
                  <Typography variant="subtitle2" component="div">
                    Still referenced in:
                  </Typography>
                  <Box component="ul" sx={{ m: 0, pl: 2 }}>
                    {delProduct.error.references.map((r) => (
                      <Typography key={`${r.label}-${r.count}`} component="li" variant="body2">
                        {r.label} ({r.count})
                      </Typography>
                    ))}
                  </Box>
                </>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  This response did not include a per-area breakdown. Restart or rebuild the API from the current repo
                  (for example <code>pnpm dev:api</code> or <code>pnpm docker:rebuild:api</code>) so delete conflicts return
                  reference counts.
                </Typography>
              )}
              <Typography variant="body2" color="text.secondary">
                Clear or reassign the listed dependent rows on the relevant screens (or use Clear all where available),
                or set <strong>Active</strong> to false instead of deleting.
              </Typography>
            </Stack>
          ) : (
            <Typography variant="body2">{(delProduct.error as Error).message}</Typography>
          )}
        </Alert>
      ) : null}
      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <Button variant="contained" onClick={() => setUploadOpen(true)}>
          Upload CSV (paste)
        </Button>
        <ModuleGridToolbar
          onRefresh={() => qc.invalidateQueries({ queryKey: ['admin-products'] })}
          sx={{ mb: 0 }}
          busy={delProduct.isPending}
        />
      </Stack>
      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          intro={<>Rows are stored in <strong>dim_product</strong> with optional <strong>channel_id</strong>.</>}
          isLoading={productsLoading}
          isError={productsIsError}
          error={toQueryError(productsErr)}
          onRetry={() => void refetchProducts()}
          isEmpty={rows.length === 0}
          empty={{
            title: 'No products yet',
            description: 'Upload a CSV paste or use Data imports when a product source is registered.',
            primary: { label: 'Getting started', href: '/getting-started' },
            secondary: { label: 'Data & imports', href: '/admin/imports' },
          }}
        >
          <EnterpriseDataGrid rowData={rows} columnDefs={colDefs} gridOptions={gridOptions} height={520} />
        </ModuleDataSection>
      </Paper>

      <Dialog open={uploadOpen} onClose={() => !bulk.isPending && setUploadOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Paste product rows</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            Example: <code>SKU-NEW-01,Widget Pro,Audio,RET</code>
          </Typography>
          <TextField
            multiline
            minRows={10}
            fullWidth
            value={paste}
            onChange={(ev) => setPaste(ev.target.value)}
            placeholder="sku,name,category,channel_code"
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
            onClick={() => bulk.mutate(parseProductCsv(paste))}
          >
            Import
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
