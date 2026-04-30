'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  FormControlLabel,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  CellValueChangedEvent,
  ColDef,
  ColumnMovedEvent,
  ColumnPinnedEvent,
  ColumnResizedEvent,
  ColumnVisibleEvent,
  GridOptions,
  GridReadyEvent,
} from 'ag-grid-community';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Suspense } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { ProductSkuEconomicsPanel } from '@/features/admin/ProductSkuEconomicsPanel';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { apiDelete, apiGet, apiPatch, apiPost, HttpConflictError } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type ProductRow = {
  id: number;
  sku: string;
  part_number: string | null;
  name: string;
  sales_model_name: string | null;
  model_name: string | null;
  series_name: string | null;
  product_line: string | null;
  business_unit: string | null;
  category: string | null;
  form_factor: string | null;
  country_code: string | null;
  ean: string | null;
  upc: string | null;
  lifecycle_status: string | null;
  launch_date: string | null;
  retired_date: string | null;
  is_active: boolean;
  channel_id: number | null;
  channel_code: string | null;
  missing_required_fields: string[];
  last_import_date: string | null;
};

type CodeRow = { id: number; code: string; name: string };
type ProductListResponse = {
  items: ProductRow[];
  page: number;
  page_size: number;
  total: number;
  sort_by: string;
  sort_dir: 'asc' | 'desc';
};

const PRODUCT_GRID_STATE_KEY = 'cip.admin.products.gridState.v1';
const PRODUCT_SAVED_VIEWS_KEY = 'cip.admin.products.savedViews.v1';
const DEFAULT_PAGE_SIZE = 50;
const DEFAULT_SORT_BY = 'sku';
const DEFAULT_SORT_DIR: 'asc' | 'desc' = 'asc';
const DEFAULT_VIEW_NAME = 'Control view';
const ALL_PRODUCT_COLUMN_FIELDS = [
  'sku',
  'name',
  'category',
  'part_number',
  'sales_model_name',
  'model_name',
  'series_name',
  'product_line',
  'business_unit',
  'form_factor',
  'country_code',
  'ean',
  'upc',
  'lifecycle_status',
  'launch_date',
  'retired_date',
  'is_active',
  'channel_code',
  'missing_required_fields',
  'last_import_date',
] as const;
type ProductColumnField = (typeof ALL_PRODUCT_COLUMN_FIELDS)[number];
const PRODUCT_COLUMN_GROUPS: { label: string; fields: ProductColumnField[] }[] = [
  { label: 'Core identity', fields: ['sku', 'name', 'category', 'channel_code', 'is_active'] },
  { label: 'Commercial naming', fields: ['part_number', 'sales_model_name', 'model_name', 'series_name'] },
  { label: 'Portfolio attributes', fields: ['product_line', 'business_unit', 'form_factor', 'country_code'] },
  { label: 'Lifecycle & compliance', fields: ['lifecycle_status', 'launch_date', 'retired_date'] },
  { label: 'Codes & diagnostics', fields: ['ean', 'upc', 'missing_required_fields', 'last_import_date'] },
];
type SavedView = {
  name: string;
  query: string;
};

function parseBool(v: string | null): boolean | null {
  if (v == null || v === '') return null;
  if (v === 'true') return true;
  if (v === 'false') return false;
  return null;
}

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

function AdminProductsPageContent() {
  const qc = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [paste, setPaste] = useState('');
  const [selectedRow, setSelectedRow] = useState<ProductRow | null>(null);
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [viewName, setViewName] = useState('');
  const [gridApi, setGridApi] = useState<any | null>(null);
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [columnSearch, setColumnSearch] = useState('');
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>({});

  const page = Number(searchParams.get('page') || '1') || 1;
  const pageSize = Number(searchParams.get('page_size') || `${DEFAULT_PAGE_SIZE}`) || DEFAULT_PAGE_SIZE;
  const q = searchParams.get('q') ?? '';
  const isActiveFilter = parseBool(searchParams.get('is_active'));
  const categoryFilter = searchParams.get('category') ?? '';
  const lifecycleFilter = searchParams.get('lifecycle_status') ?? '';
  const channelCodeFilter = searchParams.get('channel_code') ?? '';
  const launchDateFrom = searchParams.get('launch_date_from') ?? '';
  const launchDateTo = searchParams.get('launch_date_to') ?? '';
  const retiredDateFrom = searchParams.get('retired_date_from') ?? '';
  const retiredDateTo = searchParams.get('retired_date_to') ?? '';
  const sortBy = searchParams.get('sort_by') ?? DEFAULT_SORT_BY;
  const sortDir = (searchParams.get('sort_dir') as 'asc' | 'desc' | null) ?? DEFAULT_SORT_DIR;

  const setParamState = useCallback(
    (changes: Record<string, string | null>, resetPage = false) => {
      const sp = new URLSearchParams(searchParams.toString());
      for (const [k, v] of Object.entries(changes)) {
        if (v == null || v === '') sp.delete(k);
        else sp.set(k, v);
      }
      if (resetPage) sp.set('page', '1');
      router.replace(`${pathname}?${sp.toString()}`);
    },
    [pathname, router, searchParams]
  );

  useEffect(() => {
    if (!searchParams.toString()) {
      const sp = new URLSearchParams();
      sp.set('page', '1');
      sp.set('page_size', String(DEFAULT_PAGE_SIZE));
      sp.set('sort_by', DEFAULT_SORT_BY);
      sp.set('sort_dir', DEFAULT_SORT_DIR);
      router.replace(`${pathname}?${sp.toString()}`);
    }
  }, [pathname, router, searchParams]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(PRODUCT_SAVED_VIEWS_KEY);
      if (!raw) {
        const defaultView: SavedView = {
          name: DEFAULT_VIEW_NAME,
          query: `page=1&page_size=${DEFAULT_PAGE_SIZE}&sort_by=${DEFAULT_SORT_BY}&sort_dir=${DEFAULT_SORT_DIR}`,
        };
        localStorage.setItem(PRODUCT_SAVED_VIEWS_KEY, JSON.stringify([defaultView]));
        setSavedViews([defaultView]);
        return;
      }
      const parsed = JSON.parse(raw) as SavedView[];
      setSavedViews(Array.isArray(parsed) ? parsed : []);
    } catch {
      setSavedViews([]);
    }
  }, []);

  const {
    data: products,
    isLoading: productsLoading,
    isError: productsIsError,
    error: productsErr,
    refetch: refetchProducts,
  } = useQuery({
    queryKey: [
      'admin-products',
      page,
      pageSize,
      q,
      isActiveFilter,
      categoryFilter,
      lifecycleFilter,
      channelCodeFilter,
      launchDateFrom,
      launchDateTo,
      retiredDateFrom,
      retiredDateTo,
      sortBy,
      sortDir,
    ],
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams();
      sp.set('page', String(page));
      sp.set('page_size', String(pageSize));
      sp.set('sort_by', sortBy);
      sp.set('sort_dir', sortDir);
      if (q.trim()) sp.set('q', q.trim());
      if (isActiveFilter != null) sp.set('is_active', String(isActiveFilter));
      if (categoryFilter) sp.set('category', categoryFilter);
      if (lifecycleFilter) sp.set('lifecycle_status', lifecycleFilter);
      if (channelCodeFilter) sp.set('channel_code', channelCodeFilter);
      if (launchDateFrom) sp.set('launch_date_from', launchDateFrom);
      if (launchDateTo) sp.set('launch_date_to', launchDateTo);
      if (retiredDateFrom) sp.set('retired_date_from', retiredDateFrom);
      if (retiredDateTo) sp.set('retired_date_to', retiredDateTo);
      return apiGet<ProductListResponse>(`/api/v1/products?${sp.toString()}`, { signal });
    },
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
  const onDeleteProduct = useCallback(
    (id: number) => {
      delProduct.mutate(id);
    },
    [delProduct.mutate]
  );

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
        } else if (field === 'lifecycle_status') {
          await apiPatch(`/api/v1/products/${id}`, { lifecycle_status: String(e.newValue ?? '') || null });
        } else if (field === 'launch_date') {
          await apiPatch(`/api/v1/products/${id}`, { launch_date: String(e.newValue ?? '') || null });
        } else if (field === 'retired_date') {
          await apiPatch(`/api/v1/products/${id}`, { retired_date: String(e.newValue ?? '') || null });
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
      { field: 'part_number', headerName: 'Part number', minWidth: 140, editable: false, hide: true },
      { field: 'sales_model_name', headerName: 'Sales model', minWidth: 170, editable: false, hide: true },
      { field: 'model_name', headerName: 'Model family', minWidth: 170, editable: false, hide: true },
      { field: 'series_name', headerName: 'Series', minWidth: 150, editable: false, hide: true },
      { field: 'product_line', headerName: 'Product line', minWidth: 160, editable: false, hide: true },
      { field: 'business_unit', headerName: 'Business unit', minWidth: 150, editable: false, hide: true },
      { field: 'form_factor', headerName: 'Form factor', minWidth: 120, editable: true },
      { field: 'country_code', headerName: 'Country', minWidth: 120, editable: false, hide: true },
      { field: 'ean', headerName: 'EAN', minWidth: 140, editable: false, hide: true },
      { field: 'upc', headerName: 'UPC', minWidth: 140, editable: false, hide: true },
      { field: 'lifecycle_status', headerName: 'Lifecycle', minWidth: 120, editable: true },
      { field: 'launch_date', headerName: 'Launch date', minWidth: 130, editable: true },
      { field: 'retired_date', headerName: 'Retired date', minWidth: 130, editable: true },
      { field: 'is_active', headerName: 'Active', width: 100, editable: true, cellDataType: 'boolean' },
      {
        field: 'channel_code',
        headerName: 'Primary channel',
        minWidth: 140,
        editable: true,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: channelCodes },
      },
      {
        field: 'missing_required_fields',
        headerName: 'Missing required',
        minWidth: 180,
        editable: false,
        cellDataType: false,
        valueGetter: (p) => {
          const miss = p.data?.missing_required_fields ?? [];
          return Array.isArray(miss) ? miss.join(', ') : '';
        },
        cellRenderer: (p: { data: ProductRow }) => {
          const miss = p.data?.missing_required_fields ?? [];
          if (!miss.length) return <Chip size="small" color="success" label="Complete" />;
          return <Chip size="small" color="warning" label={`${miss.length} missing`} />;
        },
      },
      { field: 'last_import_date', headerName: 'Last import', minWidth: 130, editable: false },
      {
        headerName: 'Details',
        colId: '__detail',
        width: 90,
        maxWidth: 100,
        pinned: 'right',
        sortable: false,
        filter: false,
        resizable: false,
        cellRenderer: (p: { data: ProductRow }) => (
          <Button size="small" variant="text" onClick={() => setSelectedRow(p.data)}>
            Open
          </Button>
        ),
      },
      gridDeleteColumn<ProductRow>((id) => onDeleteProduct(id), {
        busy: delProduct.isPending,
        confirmMessage:
          'Delete this product from the global catalogue? Derived metrics and aliases are removed automatically. If sales, inventory, pricing, lineup, or other core facts still reference this SKU, the delete will be blocked.',
      }),
    ],
    [channelCodes, onDeleteProduct, delProduct.isPending]
  );

  const columnLabelByField = useMemo(() => {
    const out: Record<string, string> = {};
    for (const col of colDefs) {
      if (!col.field) continue;
      out[col.field] = col.headerName ?? col.field;
    }
    return out;
  }, [colDefs]);

  const persistGridState = useCallback((api: any) => {
    try {
      const state = api.getColumnState();
      localStorage.setItem(PRODUCT_GRID_STATE_KEY, JSON.stringify(state));
    } catch {
      // no-op
    }
  }, []);
  const syncColumnVisibility = useCallback(
    (api: any) => {
      if (!api?.getColumns) return;
      try {
        const visibility: Record<string, boolean> = {};
        for (const col of api.getColumns() ?? []) {
          const field = col?.getColDef?.()?.field;
          if (!field || !ALL_PRODUCT_COLUMN_FIELDS.includes(field as ProductColumnField)) continue;
          visibility[field] = Boolean(col.isVisible?.());
        }
        if (Object.keys(visibility).length) setColumnVisibility(visibility);
      } catch {
        // no-op
      }
    },
    [setColumnVisibility]
  );
  const onGridReady = useCallback(
    (e: GridReadyEvent<ProductRow>) => {
      setGridApi(e.api);
      try {
        const raw = localStorage.getItem(PRODUCT_GRID_STATE_KEY);
        if (raw) {
          e.api.applyColumnState({ state: JSON.parse(raw), applyOrder: true });
        }
      } catch {
        // no-op
      }
      syncColumnVisibility(e.api);
    },
    [syncColumnVisibility]
  );
  const onColumnStateEvent = useCallback(
    (
      e:
        | ColumnMovedEvent<ProductRow>
        | ColumnVisibleEvent<ProductRow>
        | ColumnPinnedEvent<ProductRow>
        | ColumnResizedEvent<ProductRow>
    ) => {
      persistGridState(e.api);
      syncColumnVisibility(e.api);
    },
    [persistGridState, syncColumnVisibility]
  );

  const gridOptions: GridOptions<ProductRow> = useMemo(
    () => ({
      singleClickEdit: true,
      onCellValueChanged,
      sideBar: 'columns',
      onGridReady,
      onColumnMoved: onColumnStateEvent,
      onColumnVisible: onColumnStateEvent,
      onColumnPinned: onColumnStateEvent,
      onColumnResized: onColumnStateEvent,
    }),
    [onCellValueChanged, onGridReady, onColumnStateEvent]
  );
  const groupedColumnOptions = useMemo(() => {
    const query = columnSearch.trim().toLowerCase();
    return PRODUCT_COLUMN_GROUPS.map((group) => {
      const options = group.fields
        .map((field) => ({ field, label: columnLabelByField[field] ?? field }))
        .filter((opt) => !query || opt.label.toLowerCase().includes(query) || opt.field.toLowerCase().includes(query));
      return { ...group, options };
    }).filter((group) => group.options.length > 0);
  }, [columnLabelByField, columnSearch]);
  const toggleColumnVisibility = useCallback(
    (field: ProductColumnField, visible: boolean) => {
      if (!gridApi?.setColumnsVisible) return;
      gridApi.setColumnsVisible([field], visible);
      persistGridState(gridApi);
      setColumnVisibility((prev) => ({ ...prev, [field]: visible }));
    },
    [gridApi, persistGridState]
  );

  const rows = products?.items ?? [];
  const total = products?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const categories = useMemo(() => {
    const s = new Set<string>();
    for (const r of rows) if (r.category) s.add(r.category);
    return [...s].sort();
  }, [rows]);
  const lifecycleStatuses = useMemo(() => {
    const s = new Set<string>();
    for (const r of rows) if (r.lifecycle_status) s.add(r.lifecycle_status);
    return [...s].sort();
  }, [rows]);

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
        <Button
          variant="outlined"
          disabled={!gridApi}
          onClick={() => gridApi?.exportDataAsCsv({ fileName: `products_control_view_page${page}.csv` })}
        >
          Export current filtered/sorted view
        </Button>
        <Button
          variant="outlined"
          onClick={() => {
            try {
              localStorage.removeItem(PRODUCT_GRID_STATE_KEY);
              window.location.reload();
            } catch {
              // no-op
            }
          }}
        >
          Reset column layout
        </Button>
        <Button
          variant="outlined"
          onClick={() => {
            setColumnSearch('');
            setColumnsOpen(true);
            if (gridApi) syncColumnVisibility(gridApi);
          }}
        >
          Columns
        </Button>
        <ModuleGridToolbar
          onRefresh={() => qc.invalidateQueries({ queryKey: ['admin-products'] })}
          sx={{ mb: 0 }}
          busy={delProduct.isPending}
        />
      </Stack>
      <Paper sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} useFlexGap alignItems={{ md: 'center' }}>
          <TextField
            size="small"
            label="Search"
            value={q}
            onChange={(e) => setParamState({ q: e.target.value }, true)}
            placeholder="SKU, name, category, model"
          />
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Active</InputLabel>
            <Select
              label="Active"
              value={isActiveFilter == null ? '' : String(isActiveFilter)}
              onChange={(e) => setParamState({ is_active: String(e.target.value || '') }, true)}
            >
              <MenuItem value="">All</MenuItem>
              <MenuItem value="true">Active only</MenuItem>
              <MenuItem value="false">Inactive only</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel>Category</InputLabel>
            <Select
              label="Category"
              value={categoryFilter}
              onChange={(e) => setParamState({ category: String(e.target.value || '') }, true)}
            >
              <MenuItem value="">All</MenuItem>
              {categories.map((c) => (
                <MenuItem key={c} value={c}>
                  {c}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 170 }}>
            <InputLabel>Lifecycle</InputLabel>
            <Select
              label="Lifecycle"
              value={lifecycleFilter}
              onChange={(e) => setParamState({ lifecycle_status: String(e.target.value || '') }, true)}
            >
              <MenuItem value="">All</MenuItem>
              {lifecycleStatuses.map((c) => (
                <MenuItem key={c} value={c}>
                  {c}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel>Primary channel</InputLabel>
            <Select
              label="Primary channel"
              value={channelCodeFilter}
              onChange={(e) => setParamState({ channel_code: String(e.target.value || '') }, true)}
            >
              <MenuItem value="">All</MenuItem>
              {(channels ?? []).map((c) => (
                <MenuItem key={c.code} value={c.code}>
                  {c.code}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            size="small"
            label="Launch from"
            type="date"
            value={launchDateFrom}
            onChange={(e) => setParamState({ launch_date_from: e.target.value }, true)}
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            size="small"
            label="Launch to"
            type="date"
            value={launchDateTo}
            onChange={(e) => setParamState({ launch_date_to: e.target.value }, true)}
            InputLabelProps={{ shrink: true }}
          />
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Sort by</InputLabel>
            <Select
              label="Sort by"
              value={sortBy}
              onChange={(e) => setParamState({ sort_by: String(e.target.value || DEFAULT_SORT_BY) })}
            >
              <MenuItem value="sku">SKU</MenuItem>
              <MenuItem value="name">Name</MenuItem>
              <MenuItem value="category">Category</MenuItem>
              <MenuItem value="lifecycle_status">Lifecycle</MenuItem>
              <MenuItem value="launch_date">Launch date</MenuItem>
              <MenuItem value="retired_date">Retired date</MenuItem>
              <MenuItem value="is_active">Active</MenuItem>
              <MenuItem value="updated_at">Updated</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 110 }}>
            <InputLabel>Dir</InputLabel>
            <Select
              label="Dir"
              value={sortDir}
              onChange={(e) => setParamState({ sort_dir: String(e.target.value || DEFAULT_SORT_DIR) })}
            >
              <MenuItem value="asc">Asc</MenuItem>
              <MenuItem value="desc">Desc</MenuItem>
            </Select>
          </FormControl>
          <Button variant="text" onClick={() => setParamState({ q: '', is_active: '', category: '', lifecycle_status: '', channel_code: '', launch_date_from: '', launch_date_to: '', retired_date_from: '', retired_date_to: '', sort_by: DEFAULT_SORT_BY, sort_dir: DEFAULT_SORT_DIR }, true)}>
            Clear filters
          </Button>
        </Stack>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 2 }} alignItems={{ md: 'center' }}>
          <TextField
            size="small"
            label="Save current view"
            value={viewName}
            onChange={(e) => setViewName(e.target.value)}
            sx={{ minWidth: 220 }}
          />
          <Button
            variant="outlined"
            onClick={() => {
              const n = viewName.trim();
              if (!n) return;
              const view: SavedView = { name: n, query: searchParams.toString() };
              const next = [view, ...savedViews.filter((x) => x.name !== n)];
              setSavedViews(next);
              localStorage.setItem(PRODUCT_SAVED_VIEWS_KEY, JSON.stringify(next));
              setViewName('');
            }}
          >
            Save private view
          </Button>
          <FormControl size="small" sx={{ minWidth: 220 }}>
            <InputLabel>Apply saved view</InputLabel>
            <Select
              label="Apply saved view"
              value=""
              onChange={(e) => {
                const picked = savedViews.find((v) => v.name === e.target.value);
                if (!picked) return;
                router.replace(`${pathname}?${picked.query}`);
              }}
            >
              {savedViews.map((v) => (
                <MenuItem key={v.name} value={v.name}>
                  {v.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Typography variant="caption" color="text.secondary">
            Private views are local to this browser.
          </Typography>
        </Stack>
      </Paper>
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
          <Stack direction="row" spacing={1} sx={{ mt: 2 }} alignItems="center">
            <Button disabled={page <= 1} onClick={() => setParamState({ page: String(page - 1) })}>
              Prev
            </Button>
            <Typography variant="body2">
              Page {page} / {totalPages} ({total} rows)
            </Typography>
            <Button disabled={page >= totalPages} onClick={() => setParamState({ page: String(page + 1) })}>
              Next
            </Button>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Page size</InputLabel>
              <Select
                label="Page size"
                value={String(pageSize)}
                onChange={(e) => setParamState({ page_size: String(e.target.value || DEFAULT_PAGE_SIZE) }, true)}
              >
                <MenuItem value="25">25</MenuItem>
                <MenuItem value="50">50</MenuItem>
                <MenuItem value="100">100</MenuItem>
                <MenuItem value="200">200</MenuItem>
              </Select>
            </FormControl>
          </Stack>
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
      <Dialog open={columnsOpen} onClose={() => setColumnsOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Manage product columns</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 0.5 }}>
            <TextField
              size="small"
              label="Search columns"
              placeholder="Find by label or field key"
              value={columnSearch}
              onChange={(e) => setColumnSearch(e.target.value)}
            />
            {!gridApi ? (
              <Alert severity="info">Grid is still initializing. Column toggles become available in a moment.</Alert>
            ) : null}
            {groupedColumnOptions.map((group) => (
              <Paper key={group.label} variant="outlined" sx={{ p: 1.25 }}>
                <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                  {group.label}
                </Typography>
                <Stack>
                  {group.options.map((opt) => (
                    <FormControlLabel
                      key={opt.field}
                      control={
                        <Checkbox
                          checked={columnVisibility[opt.field] ?? false}
                          onChange={(e) => toggleColumnVisibility(opt.field, e.target.checked)}
                          disabled={!gridApi}
                        />
                      }
                      label={opt.label}
                    />
                  ))}
                </Stack>
              </Paper>
            ))}
            {!groupedColumnOptions.length ? (
              <Typography variant="body2" color="text.secondary">
                No columns match the current search.
              </Typography>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setColumnsOpen(false)}>Done</Button>
        </DialogActions>
      </Dialog>
      <Drawer
        anchor="right"
        open={Boolean(selectedRow)}
        onClose={() => setSelectedRow(null)}
        sx={{
          '& .MuiDrawer-paper': {
            top: { xs: 56, sm: 64 },
            height: { xs: 'calc(100% - 56px)', sm: 'calc(100% - 64px)' },
          },
        }}
      >
        <Box sx={{ width: 460, p: 2 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            Product details
          </Typography>
          {!selectedRow ? null : (
            <Stack spacing={1.5}>
              <Typography variant="body2">
                <strong>SKU:</strong> {selectedRow.sku}
              </Typography>
              <Typography variant="body2">
                <strong>Name:</strong> {selectedRow.name}
              </Typography>
              <Typography variant="body2">
                <strong>Category:</strong> {selectedRow.category ?? '—'}
              </Typography>
              <Typography variant="body2">
                <strong>Form factor:</strong> {selectedRow.form_factor ?? '—'}
              </Typography>
              <Typography variant="body2">
                <strong>Lifecycle:</strong> {selectedRow.lifecycle_status ?? '—'}
              </Typography>
              <Typography variant="body2">
                <strong>Launch:</strong> {selectedRow.launch_date ?? '—'}
              </Typography>
              <Typography variant="body2">
                <strong>Retired:</strong> {selectedRow.retired_date ?? '—'}
              </Typography>
              <Typography variant="body2">
                <strong>Primary channel:</strong> {selectedRow.channel_code ?? '—'}
              </Typography>
              <Typography variant="body2">
                <strong>Last import:</strong> {selectedRow.last_import_date ?? '—'}
              </Typography>
              <Typography variant="body2">
                <strong>Missing required:</strong>{' '}
                {selectedRow.missing_required_fields.length ? selectedRow.missing_required_fields.join(', ') : 'None'}
              </Typography>
              <Divider sx={{ my: 1 }} />
              <ProductSkuEconomicsPanel productId={selectedRow.id} productSku={selectedRow.sku} />
              <Stack direction="row" spacing={1}>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={async () => {
                    await apiPatch(`/api/v1/products/${selectedRow.id}`, { is_active: !selectedRow.is_active });
                    await qc.invalidateQueries({ queryKey: ['admin-products'] });
                    setSelectedRow({ ...selectedRow, is_active: !selectedRow.is_active });
                  }}
                >
                  Set {selectedRow.is_active ? 'Inactive' : 'Active'}
                </Button>
              </Stack>
            </Stack>
          )}
        </Box>
      </Drawer>
    </>
  );
}

export default function AdminProductsPage() {
  return (
    <Suspense fallback={<Typography color="text.secondary">Loading products workspace…</Typography>}>
      <AdminProductsPageContent />
    </Suspense>
  );
}
