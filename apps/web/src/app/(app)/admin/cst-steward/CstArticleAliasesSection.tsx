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
  Stack,
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
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import {
  MasterColumnPickerDialog,
  type MasterColumnPickerGroup,
} from '@/components/masterGrid/MasterColumnPickerDialog';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { OPS_LIST_GRID_PAGINATION } from '@/features/shell/opsListGridPagination';
import { apiGet, apiPatch, apiPost, apiPostFormData } from '@/lib/api';

export type AliasRow = {
  id: number;
  customer_id?: number;
  customer_code: string | null;
  customer_name: string | null;
  article_no_normalized: string;
  product_id?: number;
  product_sku: string | null;
  product_name: string | null;
  sales_model_name: string | null;
  status: string;
  sku_twin_flag?: boolean;
  valid_from?: string | null;
  valid_to?: string | null;
  evidence_json?: Record<string, unknown> | null;
};

type AliasImportSummary = {
  rows_read: number;
  rows_deduped: number;
  proposed: number;
  updated_proposed: number;
  skipped_existing_confirmed: number;
  collisions: number;
  customer_unresolved: number;
  model_ambiguous: number;
  sku_twin_proposed?: number;
  model_miss: number;
  blank_skipped: number;
  proposed_alias_ids: number[];
  confirm?: { confirmed: number; skipped: number } | null;
};

type ProductPick = {
  id: number;
  sku: string;
  name: string;
  sales_model_name: string | null;
};

type CustomerPick = { id: number; customer_code: string; customer_name: string };

export const CST_ALIAS_GRID_STORAGE_KEY = 'cip.cst-steward.articleAliases.gridColumns.v1';

/** Hidden until Additional columns — SKU, product id, From/To, product name, customer code. */
export const CST_ALIAS_DEFAULT_HIDDEN_FIELDS = [
  'customer_code',
  'product_id',
  'product_sku',
  'product_name',
  'valid_from',
  'valid_to',
] as const;

export const CST_ALIAS_COLUMN_PICKER_GROUPS: MasterColumnPickerGroup[] = [
  {
    label: 'Retailer',
    fields: ['article_no_normalized', 'customer_name', 'customer_code'],
  },
  {
    label: 'Product Master',
    fields: ['sales_model_name', 'product_sku', 'product_name', 'product_id'],
  },
  {
    label: 'Validity',
    fields: ['status', 'valid_from', 'valid_to'],
  },
];

export const CST_ALIAS_COLUMN_LABELS: Record<string, string> = {
  article_no_normalized: 'Article',
  customer_name: 'Customer',
  customer_code: 'Customer code',
  sales_model_name: 'Sales model',
  product_sku: 'SKU',
  product_name: 'Product name',
  product_id: 'Product id',
  status: 'Status',
  valid_from: 'From',
  valid_to: 'To',
};

const PICKER_FIELDS = new Set(CST_ALIAS_COLUMN_PICKER_GROUPS.flatMap((g) => g.fields));

async function fetchProducts(q: string, signal: AbortSignal): Promise<ProductPick[]> {
  const qs = new URLSearchParams({ page: '1', page_size: '20' });
  if (q.trim()) qs.set('q', q.trim());
  const res = await apiGet<{ items: ProductPick[] }>(`/api/v1/products?${qs}`, { signal });
  return res.items ?? [];
}

async function fetchCustomers(q: string, signal: AbortSignal): Promise<CustomerPick[]> {
  const qs = new URLSearchParams({ page: '1', page_size: '20' });
  if (q.trim()) qs.set('q', q.trim());
  const res = await apiGet<{ items: CustomerPick[] }>(`/api/v1/customers?${qs}`, { signal });
  return res.items ?? [];
}

export function productSearchLabel(o: ProductPick): string {
  const model = (o.sales_model_name || '').trim();
  const sku = (o.sku || '').trim();
  const name = (o.name || '').trim();
  if (model) {
    const rest = [sku, name && name !== model ? name : ''].filter(Boolean).join(' — ');
    return rest ? `${model} · ${rest}` : model;
  }
  return [sku, name].filter(Boolean).join(' — ') || `Product ${o.id}`;
}

function productFromAlias(row: AliasRow): ProductPick | null {
  if (!row.product_id) return null;
  return {
    id: row.product_id,
    sku: row.product_sku || '',
    name: row.product_name || '',
    sales_model_name: row.sales_model_name,
  };
}

function aliasListUrl(status: string, customerId: number | null, q: string): string {
  const qs = new URLSearchParams();
  qs.set('status', status);
  if (customerId != null) qs.set('customer_id', String(customerId));
  if (q.trim()) qs.set('q', q.trim());
  return `/api/v1/cst-steward/article-aliases?${qs.toString()}`;
}

function defaultVisibility(): Record<string, boolean> {
  const hidden = new Set<string>(CST_ALIAS_DEFAULT_HIDDEN_FIELDS);
  const visibility: Record<string, boolean> = {};
  for (const field of PICKER_FIELDS) {
    visibility[field] = !hidden.has(field);
  }
  return visibility;
}

export function CstArticleAliasesSection() {
  const qc = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [aliasStatus, setAliasStatus] = useState('proposed,confirmed');
  const [customerFilter, setCustomerFilter] = useState<CustomerPick | null>(null);
  const [searchInput, setSearchInput] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [aliasImportMsg, setAliasImportMsg] = useState<string | null>(null);
  const [editAlias, setEditAlias] = useState<AliasRow | null>(null);
  const [editProduct, setEditProduct] = useState<ProductPick | null>(null);

  const [gridApi, setGridApi] = useState<GridApi<AliasRow> | null>(null);
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [columnSearch, setColumnSearch] = useState('');
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>(defaultVisibility);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(searchInput), 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  const {
    data: aliases,
    isLoading: loadingAliases,
    isError: errAliases,
    error: aliasesError,
    refetch: refetchAliases,
  } = useQuery({
    queryKey: ['cst-steward', 'aliases', aliasStatus, customerFilter?.id ?? null, debouncedQ],
    queryFn: ({ signal }) =>
      apiGet<AliasRow[]>(aliasListUrl(aliasStatus, customerFilter?.id ?? null, debouncedQ), { signal }),
  });

  const persistGridState = useCallback((api: GridApi<AliasRow>) => {
    try {
      localStorage.setItem(CST_ALIAS_GRID_STORAGE_KEY, JSON.stringify(api.getColumnState()));
    } catch {
      // no-op
    }
  }, []);

  const syncColumnVisibility = useCallback((api: GridApi<AliasRow>) => {
    if (!api?.getColumns) return;
    try {
      const visibility: Record<string, boolean> = {};
      for (const col of api.getColumns() ?? []) {
        const field = col?.getColDef?.()?.field as string | undefined;
        if (!field || !PICKER_FIELDS.has(field)) continue;
        visibility[field] = Boolean(col.isVisible?.());
      }
      if (Object.keys(visibility).length) setColumnVisibility(visibility);
    } catch {
      // no-op
    }
  }, []);

  const onGridReady = useCallback(
    (e: GridReadyEvent<AliasRow>) => {
      setGridApi(e.api);
      try {
        const raw = localStorage.getItem(CST_ALIAS_GRID_STORAGE_KEY);
        if (raw) {
          e.api.applyColumnState({ state: JSON.parse(raw), applyOrder: true });
        } else {
          e.api.applyColumnState({
            state: CST_ALIAS_DEFAULT_HIDDEN_FIELDS.map((colId) => ({ colId, hide: true })),
            applyOrder: true,
          });
        }
      } catch {
        // no-op
      }
      syncColumnVisibility(e.api);
    },
    [syncColumnVisibility],
  );

  const onColumnStateEvent = useCallback(
    (
      e:
        | ColumnMovedEvent<AliasRow>
        | ColumnVisibleEvent<AliasRow>
        | ColumnPinnedEvent<AliasRow>
        | ColumnResizedEvent<AliasRow>,
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

  const importAliases = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      return apiPostFormData<AliasImportSummary>(
        '/api/v1/cst-steward/article-aliases/import?confirm_unique=true',
        fd,
      );
    },
    onSuccess: async (summary) => {
      const confirmed = summary.confirm?.confirmed ?? 0;
      setAliasImportMsg(
        `Read ${summary.rows_deduped} · proposed ${summary.proposed + summary.updated_proposed} · SKU twins ${summary.sku_twin_proposed ?? 0} · confirmed ${confirmed} · collisions ${summary.collisions} · model miss ${summary.model_miss} · ambiguous ${summary.model_ambiguous}`,
      );
      await refetchAliases();
    },
  });

  const deriveEras = useMutation({
    mutationFn: () =>
      apiPost<Record<string, unknown>>('/api/v1/cst-steward/article-aliases/derive-eras-from-shipping', {}),
    onSuccess: async (summary) => {
      setAliasImportMsg(
        `Derive eras: groups ${String(summary.groups)} · proposed ${String(summary.eras_proposed)} · steward_manual ${String(summary.steward_manual)} · equal_pod ${String(summary.equal_pod_blocked)}`,
      );
      await refetchAliases();
    },
  });

  const confirmDerived = useMutation({
    mutationFn: () =>
      apiPost<Record<string, unknown>>('/api/v1/cst-steward/article-aliases/confirm-shipping-derived', {}),
    onSuccess: async (summary) => {
      setAliasImportMsg(
        `Confirmed shipping eras: ${String(summary.confirmed)} (failed ${String(summary.failed)} / candidates ${String(summary.candidates)})`,
      );
      await refetchAliases();
    },
  });

  const saveAliasEdit = useMutation({
    mutationFn: async () => {
      if (!editAlias || !editProduct) throw new Error('Pick a product');
      return apiPatch<AliasRow>(`/api/v1/cst-steward/article-aliases/${editAlias.id}`, {
        product_id: editProduct.id,
        status: 'proposed',
      });
    },
    onSuccess: async () => {
      setEditAlias(null);
      setEditProduct(null);
      await qc.invalidateQueries({ queryKey: ['cst-steward', 'aliases'] });
      await refetchAliases();
    },
  });

  const openEdit = useCallback((row: AliasRow) => {
    setEditAlias(row);
    setEditProduct(productFromAlias(row));
  }, []);

  const aliasCols = useMemo<ColDef<AliasRow>[]>(
    () => [
      {
        field: 'article_no_normalized',
        headerName: CST_ALIAS_COLUMN_LABELS.article_no_normalized,
        width: 150,
      },
      {
        field: 'customer_name',
        headerName: CST_ALIAS_COLUMN_LABELS.customer_name,
        flex: 1,
        minWidth: 140,
      },
      {
        field: 'customer_code',
        headerName: CST_ALIAS_COLUMN_LABELS.customer_code,
        width: 130,
        hide: true,
      },
      {
        field: 'sales_model_name',
        headerName: CST_ALIAS_COLUMN_LABELS.sales_model_name,
        flex: 1,
        minWidth: 160,
        valueFormatter: (p) => (p.value ? String(p.value) : '—'),
      },
      {
        field: 'product_sku',
        headerName: CST_ALIAS_COLUMN_LABELS.product_sku,
        width: 120,
        hide: true,
      },
      {
        field: 'product_name',
        headerName: CST_ALIAS_COLUMN_LABELS.product_name,
        flex: 1,
        minWidth: 140,
        hide: true,
      },
      {
        field: 'product_id',
        headerName: CST_ALIAS_COLUMN_LABELS.product_id,
        width: 100,
        hide: true,
      },
      {
        field: 'valid_from',
        headerName: CST_ALIAS_COLUMN_LABELS.valid_from,
        width: 110,
        hide: true,
        valueFormatter: (p) => p.value || '−∞',
      },
      {
        field: 'valid_to',
        headerName: CST_ALIAS_COLUMN_LABELS.valid_to,
        width: 110,
        hide: true,
        valueFormatter: (p) => p.value || '+∞',
      },
      {
        field: 'status',
        headerName: CST_ALIAS_COLUMN_LABELS.status,
        width: 150,
        cellRenderer: (p: ICellRendererParams<AliasRow>) =>
          p.data ? (
            <Stack direction="row" spacing={0.5} alignItems="center">
              <span>{p.value}</span>
              {p.data.sku_twin_flag ? (
                <Chip
                  size="small"
                  label="FLAG"
                  color="warning"
                  data-testid={`cst-alias-sku-twin-flag-${p.data.id}`}
                />
              ) : null}
            </Stack>
          ) : null,
      },
      {
        colId: 'actions',
        headerName: '',
        width: 260,
        sortable: false,
        filter: false,
        pinned: 'right',
        cellRenderer: (p: ICellRendererParams<AliasRow>) =>
          p.data ? (
            <Stack direction="row" spacing={0.5}>
              <Button
                size="small"
                onClick={() => openEdit(p.data!)}
                data-testid={`cst-alias-edit-${p.data.id}`}
              >
                Edit
              </Button>
              <Button
                size="small"
                variant="contained"
                onClick={() => confirmAlias.mutate(p.data!.id)}
                data-testid={`cst-alias-confirm-${p.data.id}`}
              >
                Confirm
              </Button>
              <Button
                size="small"
                onClick={() => rejectAlias.mutate(p.data!.id)}
                data-testid={`cst-alias-reject-${p.data.id}`}
              >
                Reject
              </Button>
            </Stack>
          ) : null,
      },
    ],
    [confirmAlias, openEdit, rejectAlias],
  );

  const gridOptions = useMemo(
    () => ({
      getRowId: (p: { data?: AliasRow }) => String(p.data!.id),
      loading: loadingAliases,
      ...OPS_LIST_GRID_PAGINATION,
      onGridReady,
      onColumnMoved: onColumnStateEvent,
      onColumnVisible: onColumnStateEvent,
      onColumnPinned: onColumnStateEvent,
      onColumnResized: onColumnStateEvent,
    }),
    [loadingAliases, onGridReady, onColumnStateEvent],
  );

  const busy =
    importAliases.isPending ||
    deriveEras.isPending ||
    confirmDerived.isPending ||
    confirmAlias.isPending ||
    rejectAlias.isPending;

  const toolbar = (
    <Stack spacing={1.5} sx={{ mb: 1 }}>
      <ModuleGridToolbar
        onRefresh={() => void refetchAliases()}
        refreshDisabled={loadingAliases}
        busy={busy}
        leading={
          <>
            <TextField
              select
              SelectProps={{ native: true }}
              size="small"
              label="Status"
              value={aliasStatus}
              onChange={(e) => setAliasStatus(e.target.value)}
              sx={{ minWidth: 220 }}
              data-testid="cst-alias-status-filter"
            >
              <option value="proposed">proposed</option>
              <option value="confirmed">confirmed</option>
              <option value="proposed,confirmed">proposed + confirmed</option>
              <option value="all">all</option>
              <option value="rejected">rejected</option>
            </TextField>
            <Box sx={{ minWidth: 260 }} data-testid="cst-alias-customer-filter">
              <EntitySearchAutocomplete<CustomerPick>
                label="Customer"
                value={customerFilter}
                onChange={setCustomerFilter}
                fetchOptions={fetchCustomers}
                getOptionLabel={(o) => `${o.customer_code} — ${o.customer_name}`}
              />
            </Box>
            <TextField
              size="small"
              label="Search article or sales model"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              sx={{ minWidth: 260 }}
              data-testid="cst-alias-search"
            />
            <Button
              variant="outlined"
              size="small"
              disabled={!gridApi}
              onClick={() => {
                setColumnSearch('');
                setColumnsOpen(true);
                if (gridApi) syncColumnVisibility(gridApi);
              }}
              data-testid="cst-aliases-columns-open"
            >
              Additional columns
            </Button>
            <Button
              variant="outlined"
              size="small"
              onClick={() => {
                try {
                  localStorage.removeItem(CST_ALIAS_GRID_STORAGE_KEY);
                  window.location.reload();
                } catch {
                  // no-op
                }
              }}
              data-testid="cst-aliases-columns-reset"
            >
              Reset column layout
            </Button>
            <Button
              component="label"
              variant="contained"
              size="small"
              disabled={importAliases.isPending}
              data-testid="cst-alias-upload"
            >
              {importAliases.isPending ? 'Importing…' : 'Upload SCM map'}
              <input
                ref={fileInputRef}
                type="file"
                hidden
                accept=".xlsx,.xlsm"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  e.target.value = '';
                  if (f) importAliases.mutate(f);
                }}
              />
            </Button>
            <Button
              variant="outlined"
              size="small"
              disabled={deriveEras.isPending}
              onClick={() => deriveEras.mutate()}
              data-testid="cst-alias-derive-eras"
            >
              {deriveEras.isPending ? 'Deriving…' : 'Derive eras from shipping'}
            </Button>
            <Button
              variant="outlined"
              size="small"
              disabled={confirmDerived.isPending}
              onClick={() => confirmDerived.mutate()}
              data-testid="cst-alias-confirm-derived"
            >
              {confirmDerived.isPending ? 'Confirming…' : 'Confirm shipping eras'}
            </Button>
          </>
        }
        sx={{ mb: 0 }}
      />
      <Typography variant="caption" color="text.secondary">
        Eras: [from, to). Shipping POD dates the clock; steward adjusts gaps. From/To stay in Additional
        columns.
      </Typography>
    </Stack>
  );

  return (
    <>
      {aliasImportMsg ? (
        <Alert severity="info" sx={{ mb: 1 }} data-testid="cst-alias-import-summary">
          {aliasImportMsg}
        </Alert>
      ) : null}
      {importAliases.isError ? (
        <Alert severity="error" sx={{ mb: 1 }}>
          {String((importAliases.error as Error)?.message)}
        </Alert>
      ) : null}
      <ModuleDataSection
        intro={
          <>
            <strong>Article</strong> is the retailer key (ASIN on Amazon). <strong>Sales model</strong> comes
            from Product Master via the linked product — it is not stored on the alias. Duplicate
            Product Master SKUs for one sales model are proposed (prefilled), never skipped.
            Confirm is still required. Tied shipping shows FLAG. FLAG ≠ BLOCK: unconfirmed aliases
            never auto-resolve CST rows.
          </>
        }
        introWhen="always"
        toolbar={toolbar}
        isLoading={loadingAliases}
        isError={errAliases}
        error={aliasesError as Error | null}
        onRetry={() => void refetchAliases()}
        isEmpty={!loadingAliases && !errAliases && (aliases?.length ?? 0) === 0}
        empty={{
          title: 'No article aliases',
          description: 'Upload an SCM Customer | Article code | Sales Model name workbook, or widen the status filter.',
        }}
        loadingLabel="Loading article aliases…"
      >
        <EnterpriseDataGrid
          rowData={aliases ?? []}
          columnDefs={aliasCols}
          height={560}
          gridOptions={gridOptions}
        />
      </ModuleDataSection>

      <MasterColumnPickerDialog
        open={columnsOpen}
        onClose={() => setColumnsOpen(false)}
        title="Article alias columns"
        groups={CST_ALIAS_COLUMN_PICKER_GROUPS}
        columnLabelByField={CST_ALIAS_COLUMN_LABELS}
        visibility={columnVisibility}
        onToggle={toggleColumnVisibility}
        gridReady={Boolean(gridApi)}
        search={columnSearch}
        onSearchChange={setColumnSearch}
      />

      <Dialog
        open={editAlias != null}
        onClose={() => !saveAliasEdit.isPending && setEditAlias(null)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>
          Edit alias — {editAlias?.customer_name} / {editAlias?.article_no_normalized}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ pt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Search Product Master by sales model or SKU. Do not type internal product ids.
            </Typography>
            <Box data-testid="cst-alias-edit-product-search">
              <EntitySearchAutocomplete<ProductPick>
                label="Product (sales model / SKU)"
                value={editProduct}
                onChange={setEditProduct}
                fetchOptions={fetchProducts}
                getOptionLabel={productSearchLabel}
                disabled={saveAliasEdit.isPending}
                helperText="Retargeting sets status back to proposed until you Confirm."
              />
            </Box>
            {saveAliasEdit.isError ? (
              <Alert severity="error">{String((saveAliasEdit.error as Error)?.message)}</Alert>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditAlias(null)} disabled={saveAliasEdit.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={() => saveAliasEdit.mutate()}
            disabled={saveAliasEdit.isPending || !editProduct}
            data-testid="cst-alias-edit-save"
          >
            {saveAliasEdit.isPending ? 'Saving…' : 'Save as proposed'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
