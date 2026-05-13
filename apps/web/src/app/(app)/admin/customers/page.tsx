'use client';

import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  FormControl,
  FormControlLabel,
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
import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { CustomerCommercialTermsPanel } from '@/features/admin/CustomerCommercialTermsPanel';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { apiDelete, apiGet, apiPatch, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type CustomerRow = {
  id: number;
  customer_code: string;
  customer_name: string;
  customer_status: string;
  partner_tier: string | null;
  account_owner_internal: string | null;
  notes_summary: string | null;
  region_id: number | null;
  channel_id: number | null;
  preferred_distributor_id: number | null;
  region_code: string | null;
  channel_code: string | null;
  preferred_distributor_code: string | null;
  preferred_distributor_name: string | null;
  location_count?: number;
  contact_count?: number;
  alias_count?: number;
  last_import_at?: string | null;
  alias_link_status?: string;
  created_at?: string | null;
  updated_at?: string | null;
};
type CustomerLocationRow = {
  id: number;
  customer_id: number;
  location_code: string;
  location_name: string;
  location_type: string;
  region_id: number | null;
  region_code: string | null;
  is_active: boolean;
  notes_summary: string | null;
};
type CustomerContactRow = {
  id: number;
  customer_id: number;
  contact_name: string;
  contact_role: string;
  email: string | null;
  phone: string | null;
  is_primary: boolean;
  is_active: boolean;
  notes_summary: string | null;
};

type CodeRow = { id: number; code: string; name: string };
type CreateCustomerBody = {
  customer_code: string;
  customer_name: string;
  customer_status: string;
  region_id: number | null;
  channel_id: number | null;
  partner_tier: string;
  account_owner_internal: string;
  preferred_distributor_id: number | null;
  notes_summary: string;
};
type CustomerListResponse = {
  items: CustomerRow[];
  page: number;
  page_size: number;
  total: number;
  sort_by: string;
  sort_dir: 'asc' | 'desc';
};

const CUSTOMER_GRID_STATE_KEY = 'cip.admin.customers.gridState.v1';
const DEFAULT_PAGE_SIZE = 50;
const DEFAULT_SORT_BY = 'customer_code';
const DEFAULT_SORT_DIR: 'asc' | 'desc' = 'asc';
const ALL_CUSTOMER_COLUMN_FIELDS = [
  'id',
  'customer_code',
  'customer_name',
  'customer_status',
  'region_id',
  'channel_id',
  'preferred_distributor_id',
  'region_code',
  'channel_code',
  'preferred_distributor_code',
  'partner_tier',
  'account_owner_internal',
  'notes_summary',
  'location_count',
  'contact_count',
  'alias_count',
  'last_import_at',
  'alias_link_status',
  'created_at',
  'updated_at',
] as const;
type CustomerColumnField = (typeof ALL_CUSTOMER_COLUMN_FIELDS)[number];

/** Defaults applied once via column state in onGridReady (avoids hide flapping when colDefs refresh). */
const DEFAULT_INITIALLY_HIDDEN_CUSTOMER_FIELDS: readonly CustomerColumnField[] = [
  'id',
  'region_id',
  'channel_id',
  'preferred_distributor_id',
  'partner_tier',
  'alias_count',
  'last_import_at',
  'alias_link_status',
  'account_owner_internal',
  'notes_summary',
  'location_count',
  'contact_count',
  'created_at',
  'updated_at',
];

const STATIC_CUSTOMER_COLUMN_GROUPS: { label: string; fields: CustomerColumnField[] }[] = [
  { label: 'dim_customer — identity', fields: ['id', 'customer_code', 'customer_name', 'customer_status'] },
  { label: 'dim_customer — foreign keys', fields: ['region_id', 'channel_id', 'preferred_distributor_id'] },
  { label: 'Resolved codes (joins)', fields: ['region_code', 'channel_code', 'preferred_distributor_code'] },
  { label: 'dim_customer — classification & notes', fields: ['partner_tier', 'account_owner_internal', 'notes_summary'] },
  { label: 'Related counts (not on dim row)', fields: ['location_count', 'contact_count'] },
  { label: 'Import & alias linkage', fields: ['alias_count', 'last_import_at', 'alias_link_status'] },
  { label: 'dim_customer — timestamps', fields: ['created_at', 'updated_at'] },
];
const STATUS_OPTIONS = ['', 'active', 'inactive', 'onboarding', 'blocked'];
const PARTNER_TIER_OPTIONS = ['', 'strategic', 'tier_1', 'tier_2', 'tier_3', 'core', 'long_tail'];
const LOCATION_TYPE_OPTIONS = ['hq', 'store', 'warehouse', 'branch', 'online', 'other'];
const CONTACT_ROLE_OPTIONS = ['general', 'procurement', 'sales', 'operations', 'finance', 'support', 'executive'];

function gridShortDateTime(p: { value: unknown }): string {
  const v = p.value as string | null | undefined;
  if (!v) return '—';
  try {
    return new Date(v).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
  } catch {
    return String(v);
  }
}

/** Map URL / UI `sort_by` to list API query param (API uses `code` / `name` for dim columns). */
function customerListSortByForApi(uiSortBy: string): string {
  if (uiSortBy === 'customer_code') return 'code';
  if (uiSortBy === 'customer_name') return 'name';
  return uiSortBy;
}

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

function AdminCustomersPageContent() {
  const qc = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [paste, setPaste] = useState('');
  const [selectedRow, setSelectedRow] = useState<CustomerRow | null>(null);
  const [createForm, setCreateForm] = useState<CreateCustomerBody>({
    customer_code: '',
    customer_name: '',
    customer_status: 'active',
    region_id: null,
    channel_id: null,
    partner_tier: '',
    account_owner_internal: '',
    preferred_distributor_id: null,
    notes_summary: '',
  });
  const [createError, setCreateError] = useState<string | null>(null);
  const [locationDraft, setLocationDraft] = useState({
    location_code: '',
    location_name: '',
    location_type: 'store',
    region_id: '',
    is_active: true,
    notes_summary: '',
  });
  const [contactDraft, setContactDraft] = useState({
    contact_name: '',
    contact_role: 'general',
    email: '',
    phone: '',
    is_primary: false,
    is_active: true,
    notes_summary: '',
  });
  const [editingLocationId, setEditingLocationId] = useState<number | null>(null);
  const [editingContactId, setEditingContactId] = useState<number | null>(null);
  const [gridApi, setGridApi] = useState<any | null>(null);
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [columnSearch, setColumnSearch] = useState('');
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>({});

  const page = Number(searchParams.get('page') || '1') || 1;
  const pageSize = Number(searchParams.get('page_size') || `${DEFAULT_PAGE_SIZE}`) || DEFAULT_PAGE_SIZE;
  const q = searchParams.get('q') ?? '';
  const customerStatusFilter = searchParams.get('customer_status') ?? '';
  const partnerTierFilter = searchParams.get('partner_tier') ?? '';
  const regionCodeFilter = searchParams.get('region_code') ?? '';
  const channelCodeFilter = searchParams.get('channel_code') ?? '';
  const preferredDistributorFilter = searchParams.get('preferred_distributor_code') ?? '';
  const minAliasCountFilter = searchParams.get('min_alias_count') ?? '';
  const aliasLinkFilter = searchParams.get('alias_link') ?? '';
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
    if (searchParams.get('create') === '1') {
      setCreateOpen(true);
      setCreateError(null);
    }
  }, [searchParams]);

  const {
    data: customers,
    isLoading: customersLoading,
    isError: customersIsError,
    error: customersErr,
    refetch: refetchCustomers,
  } = useQuery({
    queryKey: [
      'admin-customers',
      page,
      pageSize,
      q,
      customerStatusFilter,
      partnerTierFilter,
      regionCodeFilter,
      channelCodeFilter,
      preferredDistributorFilter,
      minAliasCountFilter,
      aliasLinkFilter,
      sortBy,
      sortDir,
    ],
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams();
      sp.set('page', String(page));
      sp.set('page_size', String(pageSize));
      sp.set('sort_by', customerListSortByForApi(sortBy));
      sp.set('sort_dir', sortDir);
      if (q.trim()) sp.set('q', q.trim());
      if (customerStatusFilter) sp.set('customer_status', customerStatusFilter);
      if (partnerTierFilter) sp.set('partner_tier', partnerTierFilter);
      if (regionCodeFilter) sp.set('region_code', regionCodeFilter);
      if (channelCodeFilter) sp.set('channel_code', channelCodeFilter);
      if (preferredDistributorFilter) sp.set('preferred_distributor_code', preferredDistributorFilter);
      const mac = minAliasCountFilter.trim();
      if (mac !== '' && Number.isFinite(Number(mac))) sp.set('min_alias_count', String(Number(mac)));
      const al = aliasLinkFilter.trim().toLowerCase();
      if (al === 'linked' || al === 'unlinked') sp.set('alias_link', al);
      return apiGet<CustomerListResponse>(`/api/v1/customers?${sp.toString()}`, { signal });
    },
  });
  const { data: channels } = useQuery({
    queryKey: ['catalog-channels'],
    queryFn: ({ signal }) => apiGet<CodeRow[]>('/api/v1/catalog/channels', { signal }),
  });
  const { data: regions } = useQuery({
    queryKey: ['catalog-regions'],
    queryFn: ({ signal }) => apiGet<CodeRow[]>('/api/v1/catalog/regions', { signal }),
  });
  const { data: distributors } = useQuery({
    queryKey: ['admin-distributors'],
    queryFn: async ({ signal }) => {
      const res = await apiGet<CodeRow[] | { items: CodeRow[] }>('/api/v1/distributors', { signal });
      // API may return a paginated envelope { items, page, total } or a bare array
      if (Array.isArray(res)) return res;
      const env = res as { items?: CodeRow[] };
      return Array.isArray(env.items) ? env.items : [];
    },
  });
  const {
    data: locations,
    isLoading: locationsLoading,
  } = useQuery({
    queryKey: ['customer-locations', selectedRow?.id],
    queryFn: ({ signal }) =>
      apiGet<CustomerLocationRow[]>(`/api/v1/customers/${selectedRow!.id}/locations`, { signal }),
    enabled: Boolean(selectedRow?.id),
  });
  const {
    data: contacts,
    isLoading: contactsLoading,
  } = useQuery({
    queryKey: ['customer-contacts', selectedRow?.id],
    queryFn: ({ signal }) =>
      apiGet<CustomerContactRow[]>(`/api/v1/customers/${selectedRow!.id}/contacts`, { signal }),
    enabled: Boolean(selectedRow?.id),
  });

  const channelCodes = useMemo(() => ['', ...(channels ?? []).map((c) => c.code)], [channels]);
  const regionCodes = useMemo(() => ['', ...(regions ?? []).map((r) => r.code)], [regions]);
  const distributorCodes = useMemo(
    () => ['', ...(distributors ?? []).map((d) => d.code)],
    [distributors]
  );

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
  const createCustomer = useMutation({
    mutationFn: (payload: CreateCustomerBody) =>
      apiPost('/api/v1/customers', {
        ...payload,
        customer_code: payload.customer_code.trim(),
        customer_name: payload.customer_name.trim(),
        customer_status: payload.customer_status,
        partner_tier: payload.partner_tier || null,
        account_owner_internal: payload.account_owner_internal.trim() || null,
        notes_summary: payload.notes_summary.trim() || null,
      }),
    onSuccess: async () => {
      setCreateError(null);
      setCreateOpen(false);
      setCreateForm({
        customer_code: '',
        customer_name: '',
        customer_status: 'active',
        region_id: null,
        channel_id: null,
        partner_tier: '',
        account_owner_internal: '',
        preferred_distributor_id: null,
        notes_summary: '',
      });
      if (searchParams.get('create') === '1') {
        setParamState({ create: null }, false);
      }
      await qc.invalidateQueries({ queryKey: ['admin-customers'] });
    },
    onError: (err) => {
      setCreateError((err as Error).message);
    },
  });
  const createLocation = useMutation({
    mutationFn: () =>
      apiPost(`/api/v1/customers/${selectedRow!.id}/locations`, {
        location_code: locationDraft.location_code.trim(),
        location_name: locationDraft.location_name.trim(),
        location_type: locationDraft.location_type,
        region_id: locationDraft.region_id ? Number(locationDraft.region_id) : null,
        is_active: locationDraft.is_active,
        notes_summary: locationDraft.notes_summary.trim() || null,
      }),
    onSuccess: async () => {
      setLocationDraft({
        location_code: '',
        location_name: '',
        location_type: 'store',
        region_id: '',
        is_active: true,
        notes_summary: '',
      });
      await qc.invalidateQueries({ queryKey: ['customer-locations', selectedRow?.id] });
      await qc.invalidateQueries({ queryKey: ['admin-customers'] });
    },
  });
  const patchLocation = useMutation({
    mutationFn: (payload: CustomerLocationRow) =>
      apiPatch(`/api/v1/customers/${payload.customer_id}/locations/${payload.id}`, {
        location_code: payload.location_code,
        location_name: payload.location_name,
        location_type: payload.location_type,
        region_id: payload.region_id,
        is_active: payload.is_active,
        notes_summary: payload.notes_summary,
      }),
    onSuccess: async () => {
      setEditingLocationId(null);
      await qc.invalidateQueries({ queryKey: ['customer-locations', selectedRow?.id] });
      await qc.invalidateQueries({ queryKey: ['admin-customers'] });
    },
  });
  const deleteLocation = useMutation({
    mutationFn: (locationId: number) => apiDelete(`/api/v1/customers/${selectedRow!.id}/locations/${locationId}`),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['customer-locations', selectedRow?.id] });
      await qc.invalidateQueries({ queryKey: ['admin-customers'] });
    },
  });
  const createContact = useMutation({
    mutationFn: () =>
      apiPost(`/api/v1/customers/${selectedRow!.id}/contacts`, {
        contact_name: contactDraft.contact_name.trim(),
        contact_role: contactDraft.contact_role,
        email: contactDraft.email.trim() || null,
        phone: contactDraft.phone.trim() || null,
        is_primary: contactDraft.is_primary,
        is_active: contactDraft.is_active,
        notes_summary: contactDraft.notes_summary.trim() || null,
      }),
    onSuccess: async () => {
      setContactDraft({
        contact_name: '',
        contact_role: 'general',
        email: '',
        phone: '',
        is_primary: false,
        is_active: true,
        notes_summary: '',
      });
      await qc.invalidateQueries({ queryKey: ['customer-contacts', selectedRow?.id] });
      await qc.invalidateQueries({ queryKey: ['admin-customers'] });
    },
  });
  const patchContact = useMutation({
    mutationFn: (payload: CustomerContactRow) =>
      apiPatch(`/api/v1/customers/${payload.customer_id}/contacts/${payload.id}`, {
        contact_name: payload.contact_name,
        contact_role: payload.contact_role,
        email: payload.email,
        phone: payload.phone,
        is_primary: payload.is_primary,
        is_active: payload.is_active,
        notes_summary: payload.notes_summary,
      }),
    onSuccess: async () => {
      setEditingContactId(null);
      await qc.invalidateQueries({ queryKey: ['customer-contacts', selectedRow?.id] });
      await qc.invalidateQueries({ queryKey: ['admin-customers'] });
    },
  });
  const deleteContact = useMutation({
    mutationFn: (contactId: number) => apiDelete(`/api/v1/customers/${selectedRow!.id}/contacts/${contactId}`),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['customer-contacts', selectedRow?.id] });
      await qc.invalidateQueries({ queryKey: ['admin-customers'] });
    },
  });

  const onCellValueChanged = useCallback(
    async (e: CellValueChangedEvent<CustomerRow>) => {
      const id = e.data?.id;
      if (id == null || e.oldValue === e.newValue) return;
      const field = e.colDef.field;
      try {
        if (field === 'customer_name') {
          await apiPatch(`/api/v1/customers/${id}`, { name: String(e.newValue ?? '') });
        } else if (field === 'customer_status') {
          await apiPatch(`/api/v1/customers/${id}`, { customer_status: String(e.newValue ?? '') });
        } else if (field === 'partner_tier') {
          await apiPatch(`/api/v1/customers/${id}`, { partner_tier: String(e.newValue ?? '') || null });
        } else if (field === 'account_owner_internal') {
          await apiPatch(`/api/v1/customers/${id}`, {
            account_owner_internal: String(e.newValue ?? '') || null,
          });
        } else if (field === 'notes_summary') {
          await apiPatch(`/api/v1/customers/${id}`, { notes_summary: String(e.newValue ?? '') || null });
        } else if (field === 'channel_code') {
          const code = String(e.newValue ?? '');
          const ch = (channels ?? []).find((c) => c.code === code);
          await apiPatch(`/api/v1/customers/${id}`, { channel_id: ch ? ch.id : null });
        } else if (field === 'region_code') {
          const code = String(e.newValue ?? '');
          const reg = (regions ?? []).find((r) => r.code === code);
          await apiPatch(`/api/v1/customers/${id}`, { region_id: reg ? reg.id : null });
        } else if (field === 'preferred_distributor_code') {
          const code = String(e.newValue ?? '');
          const dist = (distributors ?? []).find((d) => d.code === code);
          await apiPatch(`/api/v1/customers/${id}`, {
            preferred_distributor_id: dist ? dist.id : null,
          });
        }
        await qc.invalidateQueries({ queryKey: ['admin-customers'] });
      } catch (err) {
        console.error(err);
        await qc.invalidateQueries({ queryKey: ['admin-customers'] });
      }
    },
    [channels, distributors, qc, regions]
  );

  const colDefs: ColDef<CustomerRow>[] = useMemo(
    () => [
      { field: 'customer_code', headerName: 'Customer code', pinned: 'left', minWidth: 140, editable: false },
      {
        field: 'id',
        headerName: 'ID',
        minWidth: 80,
        maxWidth: 100,
        type: 'numericColumn',
        editable: false,
      },
      { field: 'customer_name', headerName: 'Customer name', flex: 1, minWidth: 190, editable: true },
      {
        field: 'customer_status',
        headerName: 'Status',
        minWidth: 130,
        editable: true,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: STATUS_OPTIONS.filter(Boolean) },
      },
      {
        field: 'partner_tier',
        headerName: 'Partner tier',
        minWidth: 130,
        editable: true,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: PARTNER_TIER_OPTIONS.filter(Boolean) },
      },
      {
        field: 'region_code',
        headerName: 'Primary region',
        minWidth: 120,
        editable: true,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: regionCodes },
      },
      {
        field: 'channel_code',
        headerName: 'Primary channel',
        minWidth: 120,
        editable: true,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: channelCodes },
      },
      {
        field: 'preferred_distributor_code',
        headerName: 'Preferred distributor',
        minWidth: 170,
        editable: true,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: distributorCodes },
      },
      {
        field: 'region_id',
        headerName: 'Region ID',
        minWidth: 100,
        type: 'numericColumn',
        editable: false,
      },
      {
        field: 'channel_id',
        headerName: 'Channel ID',
        minWidth: 100,
        type: 'numericColumn',
        editable: false,
      },
      {
        field: 'preferred_distributor_id',
        headerName: 'Preferred dist. ID',
        minWidth: 130,
        type: 'numericColumn',
        editable: false,
      },
      {
        field: 'location_count',
        headerName: 'Locations #',
        minWidth: 110,
        type: 'numericColumn',
        editable: false,
      },
      {
        field: 'contact_count',
        headerName: 'Contacts #',
        minWidth: 110,
        type: 'numericColumn',
        editable: false,
      },
      {
        field: 'alias_count',
        headerName: 'Alias #',
        minWidth: 90,
        type: 'numericColumn',
        editable: false,
      },
      {
        field: 'last_import_at',
        headerName: 'Last import (alias)',
        minWidth: 160,
        editable: false,
        valueFormatter: gridShortDateTime,
      },
      {
        field: 'alias_link_status',
        headerName: 'Alias link',
        minWidth: 120,
        editable: false,
        cellRenderer: ({ value }: { value?: string }) =>
          value === 'linked' ? (
            <Chip size="small" color="success" label="Linked" variant="outlined" />
          ) : (
            <Chip size="small" color="default" label="Unlinked" variant="outlined" />
          ),
      },
      { field: 'account_owner_internal', headerName: 'Account owner', minWidth: 170, editable: true },
      {
        field: 'notes_summary',
        headerName: 'Notes',
        minWidth: 180,
        editable: true,
      },
      {
        field: 'created_at',
        headerName: 'Created',
        minWidth: 160,
        editable: false,
        valueFormatter: gridShortDateTime,
      },
      {
        field: 'updated_at',
        headerName: 'Updated',
        minWidth: 160,
        editable: false,
        valueFormatter: gridShortDateTime,
      },
      {
        headerName: 'Details',
        colId: '__detail',
        width: 90,
        maxWidth: 100,
        pinned: 'right',
        sortable: false,
        filter: false,
        resizable: false,
        cellRenderer: (p: { data: CustomerRow }) => (
          <Button size="small" variant="text" onClick={() => setSelectedRow(p.data)}>
            Open
          </Button>
        ),
      },
      gridDeleteColumn<CustomerRow>((id) => void delCustomer.mutate(id), { busy: delCustomer.isPending }),
    ],
    [channelCodes, distributorCodes, regionCodes, delCustomer, delCustomer.isPending]
  );

  const columnLabelByField = useMemo(() => {
    const out: Record<string, string> = {};
    for (const col of colDefs) {
      if (!col.field) continue;
      out[col.field] = (col.headerName as string) ?? col.field;
    }
    return out;
  }, [colDefs]);

  const persistGridState = useCallback((api: any) => {
    try {
      const state = api.getColumnState();
      localStorage.setItem(CUSTOMER_GRID_STATE_KEY, JSON.stringify(state));
    } catch {
      // no-op
    }
  }, []);

  const syncColumnVisibility = useCallback((api: any) => {
    if (!api?.getColumns) return;
    try {
      const visibility: Record<string, boolean> = {};
      for (const col of api.getColumns() ?? []) {
        const def = col?.getColDef?.();
        const field = def?.field as string | undefined;
        if (!field) continue;
        if (ALL_CUSTOMER_COLUMN_FIELDS.includes(field as CustomerColumnField)) {
          visibility[field] = Boolean(col.isVisible?.());
        }
      }
      if (Object.keys(visibility).length) setColumnVisibility(visibility);
    } catch {
      // no-op
    }
  }, []);

  const onGridReady = useCallback(
    (e: GridReadyEvent<CustomerRow>) => {
      setGridApi(e.api);
      try {
        const raw = localStorage.getItem(CUSTOMER_GRID_STATE_KEY);
        if (raw) {
          e.api.applyColumnState({ state: JSON.parse(raw), applyOrder: true });
        } else {
          e.api.applyColumnState({
            state: DEFAULT_INITIALLY_HIDDEN_CUSTOMER_FIELDS.map((colId) => ({ colId, hide: true })),
            applyOrder: true,
          });
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
        | ColumnMovedEvent<CustomerRow>
        | ColumnVisibleEvent<CustomerRow>
        | ColumnPinnedEvent<CustomerRow>
        | ColumnResizedEvent<CustomerRow>
    ) => {
      persistGridState(e.api);
      syncColumnVisibility(e.api);
    },
    [persistGridState, syncColumnVisibility]
  );

  const groupedColumnPickerBlocks = useMemo((): { label: string; options: { id: string; label: string }[] }[] => {
    const query = columnSearch.trim().toLowerCase();
    return STATIC_CUSTOMER_COLUMN_GROUPS.map((group) => ({
      label: group.label,
      options: group.fields
        .map((field) => ({ id: field, label: columnLabelByField[field] ?? field }))
        .filter((opt) => !query || opt.label.toLowerCase().includes(query) || opt.id.toLowerCase().includes(query)),
    })).filter((group) => group.options.length > 0);
  }, [columnLabelByField, columnSearch]);

  const toggleColumnVisibility = useCallback(
    (columnId: string, visible: boolean) => {
      if (!gridApi?.setColumnsVisible) return;
      gridApi.setColumnsVisible([columnId], visible);
      persistGridState(gridApi);
      setColumnVisibility((prev) => ({ ...prev, [columnId]: visible }));
    },
    [gridApi, persistGridState]
  );

  const gridOptions: GridOptions<CustomerRow> = useMemo(
    () => ({
      singleClickEdit: true,
      onCellValueChanged,
      // Column visibility uses the toolbar picker (Product Master pattern); no Enterprise sidebar.
      onGridReady,
      onColumnMoved: onColumnStateEvent,
      onColumnVisible: onColumnStateEvent,
      onColumnPinned: onColumnStateEvent,
      onColumnResized: onColumnStateEvent,
    }),
    [onCellValueChanged, onGridReady, onColumnStateEvent]
  );

  const rows = customers?.items ?? [];
  const total = customers?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <>
      <PageHeader crumbs={[{ label: 'Admin' }, { label: 'Customers' }]} title="Customers & channels" />
      <Alert severity="info" sx={{ mb: 2 }}>
        Customer account master is governed here. For bulk updates use Data & imports; use this table for operational
        maintenance, filters, and classification edits.
      </Alert>
      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <Button
          variant="contained"
          onClick={() => {
            setCreateError(null);
            setCreateOpen(true);
          }}
        >
          Add customer
        </Button>
        <Button
          variant="outlined"
          onClick={() => router.push('/admin/imports?template=customer_master')}
        >
          Import customer master
        </Button>
        <Button variant="contained" onClick={() => setUploadOpen(true)}>
          Quick paste CSV (legacy)
        </Button>
        <Button
          variant="outlined"
          disabled={!gridApi}
          onClick={() => {
            setColumnSearch('');
            setColumnsOpen(true);
            if (gridApi) syncColumnVisibility(gridApi);
          }}
        >
          Columns
        </Button>
        <Button
          variant="outlined"
          onClick={() => {
            try {
              localStorage.removeItem(CUSTOMER_GRID_STATE_KEY);
              window.location.reload();
            } catch {
              // no-op
            }
          }}
        >
          Reset column layout
        </Button>
        <ModuleGridToolbar
          onRefresh={() => qc.invalidateQueries({ queryKey: ['admin-customers'] })}
          sx={{ mb: 0 }}
          busy={delCustomer.isPending}
        />
      </Stack>
      <Paper sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} useFlexGap alignItems={{ md: 'center' }}>
          <TextField
            size="small"
            label="Search"
            value={q}
            onChange={(e) => setParamState({ q: e.target.value }, true)}
            placeholder="Code, name, owner, notes"
          />
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Status</InputLabel>
            <Select
              label="Status"
              value={customerStatusFilter}
              onChange={(e) => setParamState({ customer_status: String(e.target.value || '') }, true)}
            >
              <MenuItem value="">All</MenuItem>
              {STATUS_OPTIONS.filter(Boolean).map((s) => (
                <MenuItem key={s} value={s}>
                  {s}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Partner tier</InputLabel>
            <Select
              label="Partner tier"
              value={partnerTierFilter}
              onChange={(e) => setParamState({ partner_tier: String(e.target.value || '') }, true)}
            >
              <MenuItem value="">All</MenuItem>
              {PARTNER_TIER_OPTIONS.filter(Boolean).map((s) => (
                <MenuItem key={s} value={s}>
                  {s}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel>Primary region</InputLabel>
            <Select
              label="Primary region"
              value={regionCodeFilter}
              onChange={(e) => setParamState({ region_code: String(e.target.value || '') }, true)}
            >
              <MenuItem value="">All</MenuItem>
              {(regions ?? []).map((r) => (
                <MenuItem key={r.code} value={r.code}>
                  {r.code}
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
          <FormControl size="small" sx={{ minWidth: 190 }}>
            <InputLabel>Preferred distributor</InputLabel>
            <Select
              label="Preferred distributor"
              value={preferredDistributorFilter}
              onChange={(e) =>
                setParamState({ preferred_distributor_code: String(e.target.value || '') }, true)
              }
            >
              <MenuItem value="">All</MenuItem>
              {(distributors ?? []).map((d) => (
                <MenuItem key={d.code} value={d.code}>
                  {d.code}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            size="small"
            label="Min alias #"
            type="number"
            inputProps={{ min: 0 }}
            value={minAliasCountFilter}
            onChange={(e) => {
              const v = e.target.value;
              setParamState({ min_alias_count: v.trim() === '' ? null : v }, true);
            }}
            sx={{ minWidth: 120 }}
          />
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel>Alias link</InputLabel>
            <Select
              label="Alias link"
              value={aliasLinkFilter}
              onChange={(e) => setParamState({ alias_link: String(e.target.value || '') }, true)}
            >
              <MenuItem value="">All</MenuItem>
              <MenuItem value="linked">Linked</MenuItem>
              <MenuItem value="unlinked">Unlinked</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel>Sort by</InputLabel>
            <Select
              label="Sort by"
              value={sortBy}
              onChange={(e) => setParamState({ sort_by: String(e.target.value || DEFAULT_SORT_BY) })}
            >
              <MenuItem value="customer_code">Customer code</MenuItem>
              <MenuItem value="customer_name">Customer name</MenuItem>
              <MenuItem value="id">ID</MenuItem>
              <MenuItem value="customer_status">Status</MenuItem>
              <MenuItem value="partner_tier">Partner tier</MenuItem>
              <MenuItem value="region_id">Region ID</MenuItem>
              <MenuItem value="channel_id">Channel ID</MenuItem>
              <MenuItem value="preferred_distributor_id">Preferred distributor ID</MenuItem>
              <MenuItem value="region_code">Region</MenuItem>
              <MenuItem value="channel_code">Channel</MenuItem>
              <MenuItem value="account_owner_internal">Owner</MenuItem>
              <MenuItem value="preferred_distributor_code">Preferred distributor</MenuItem>
              <MenuItem value="location_count">Locations #</MenuItem>
              <MenuItem value="contact_count">Contacts #</MenuItem>
              <MenuItem value="alias_count">Alias count</MenuItem>
              <MenuItem value="last_import_at">Last import (alias)</MenuItem>
              <MenuItem value="created_at">Created</MenuItem>
              <MenuItem value="updated_at">Updated</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 100 }}>
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
          <Button
            variant="text"
            onClick={() =>
              setParamState(
                {
                  q: '',
                  customer_status: '',
                  partner_tier: '',
                  region_code: '',
                  channel_code: '',
                  preferred_distributor_code: '',
                  min_alias_count: '',
                  alias_link: '',
                  sort_by: DEFAULT_SORT_BY,
                  sort_dir: DEFAULT_SORT_DIR,
                },
                true
              )
            }
          >
            Clear filters
          </Button>
        </Stack>
      </Paper>
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
            description:
              'Create your first customer manually for immediate operations, or import customer master when source governance is ready.',
            primary: { label: 'Add customer', href: '/admin/customers?create=1' },
            secondary: { label: 'Import customer master', href: '/admin/imports?template=customer_master' },
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

      <Dialog open={columnsOpen} onClose={() => setColumnsOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Manage customer columns</DialogTitle>
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
            {groupedColumnPickerBlocks.map((group) => (
              <Paper key={group.label} variant="outlined" sx={{ p: 1.25 }}>
                <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                  {group.label}
                </Typography>
                <Stack>
                  {group.options.map((opt) => (
                    <FormControlLabel
                      key={opt.id}
                      control={
                        <Checkbox
                          checked={columnVisibility[opt.id] ?? false}
                          onChange={(e) => toggleColumnVisibility(opt.id, e.target.checked)}
                          disabled={!gridApi}
                        />
                      }
                      label={opt.label}
                    />
                  ))}
                </Stack>
              </Paper>
            ))}
            {!groupedColumnPickerBlocks.length ? (
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
      <Dialog
        open={createOpen}
        onClose={() => {
          if (createCustomer.isPending) return;
          setCreateOpen(false);
          if (searchParams.get('create') === '1') setParamState({ create: null }, false);
        }}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Add customer</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 0.5 }}>
            <TextField
              label="Customer code (optional)"
              value={createForm.customer_code}
              onChange={(e) => setCreateForm((s) => ({ ...s, customer_code: e.target.value }))}
              placeholder="Leave blank to auto-generate TMP-CUST-..."
              helperText="Blank code generates a temporary internal code (TMP-CUST-...)."
            />
            <TextField
              label="Customer name"
              required
              value={createForm.customer_name}
              onChange={(e) => setCreateForm((s) => ({ ...s, customer_name: e.target.value }))}
            />
            <FormControl size="small">
              <InputLabel id="create-customer-status-label">Status</InputLabel>
              <Select
                labelId="create-customer-status-label"
                id="create-customer-status"
                label="Status"
                value={createForm.customer_status}
                onChange={(e) => setCreateForm((s) => ({ ...s, customer_status: String(e.target.value || 'active') }))}
              >
                {STATUS_OPTIONS.filter(Boolean).map((s) => (
                  <MenuItem key={s} value={s}>
                    {s}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl size="small">
              <InputLabel id="create-customer-region-label">Primary region</InputLabel>
              <Select
                labelId="create-customer-region-label"
                id="create-customer-region"
                label="Primary region"
                value={createForm.region_id == null ? '' : String(createForm.region_id)}
                onChange={(e) =>
                  setCreateForm((s) => ({
                    ...s,
                    region_id: e.target.value === '' ? null : Number(e.target.value),
                  }))
                }
              >
                <MenuItem value="">Select region</MenuItem>
                {(regions ?? []).map((r) => (
                  <MenuItem key={r.id} value={String(r.id)}>
                    {r.code} - {r.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl size="small">
              <InputLabel id="create-customer-channel-label">Primary channel</InputLabel>
              <Select
                labelId="create-customer-channel-label"
                id="create-customer-channel"
                label="Primary channel"
                value={createForm.channel_id == null ? '' : String(createForm.channel_id)}
                onChange={(e) =>
                  setCreateForm((s) => ({
                    ...s,
                    channel_id: e.target.value === '' ? null : Number(e.target.value),
                  }))
                }
              >
                <MenuItem value="">Select channel</MenuItem>
                {(channels ?? []).map((c) => (
                  <MenuItem key={c.id} value={String(c.id)}>
                    {c.code} - {c.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl size="small">
              <InputLabel id="create-customer-tier-label">Partner tier</InputLabel>
              <Select
                labelId="create-customer-tier-label"
                id="create-customer-tier"
                label="Partner tier"
                value={createForm.partner_tier}
                onChange={(e) => setCreateForm((s) => ({ ...s, partner_tier: String(e.target.value || '') }))}
              >
                <MenuItem value="">None</MenuItem>
                {PARTNER_TIER_OPTIONS.filter(Boolean).map((s) => (
                  <MenuItem key={s} value={s}>
                    {s}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label="Account owner (internal)"
              value={createForm.account_owner_internal}
              onChange={(e) => setCreateForm((s) => ({ ...s, account_owner_internal: e.target.value }))}
            />
            <FormControl size="small">
              <InputLabel id="create-customer-distributor-label">Preferred distributor (optional)</InputLabel>
              <Select
                labelId="create-customer-distributor-label"
                id="create-customer-distributor"
                label="Preferred distributor (optional)"
                value={createForm.preferred_distributor_id == null ? '' : String(createForm.preferred_distributor_id)}
                onChange={(e) =>
                  setCreateForm((s) => ({
                    ...s,
                    preferred_distributor_id: e.target.value === '' ? null : Number(e.target.value),
                  }))
                }
              >
                <MenuItem value="">None</MenuItem>
                {(distributors ?? []).map((d) => (
                  <MenuItem key={d.id} value={String(d.id)}>
                    {d.code} - {d.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label="Notes summary (optional)"
              multiline
              minRows={3}
              value={createForm.notes_summary}
              onChange={(e) => setCreateForm((s) => ({ ...s, notes_summary: e.target.value }))}
            />
            {createError ? <Alert severity="error">{createError}</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setCreateOpen(false);
              if (searchParams.get('create') === '1') setParamState({ create: null }, false);
            }}
            disabled={createCustomer.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={
              createCustomer.isPending ||
              !createForm.customer_name.trim() ||
              createForm.region_id == null ||
              createForm.channel_id == null
            }
            onClick={() => createCustomer.mutate(createForm)}
          >
            {createCustomer.isPending ? 'Creating…' : 'Create customer'}
          </Button>
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
        <Box sx={{ width: 430, p: 2 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            Customer details
          </Typography>
          {!selectedRow ? null : (
            <Stack spacing={1.5}>
              <Typography variant="subtitle2">Account summary</Typography>
              <Typography variant="body2">
                <strong>Customer code:</strong> {selectedRow.customer_code}
              </Typography>
              <Typography variant="body2">
                <strong>Customer name:</strong> {selectedRow.customer_name}
              </Typography>
              <Typography variant="body2">
                <strong>Status:</strong> {selectedRow.customer_status}
              </Typography>
              <Typography variant="body2">
                <strong>Partner tier:</strong> {selectedRow.partner_tier ?? '—'}
              </Typography>
              <Typography variant="body2">
                <strong>Primary region:</strong> {selectedRow.region_code ?? '—'}
              </Typography>
              <Typography variant="body2">
                <strong>Primary channel:</strong> {selectedRow.channel_code ?? '—'}
              </Typography>
              <Typography variant="body2">
                <strong>Account owner:</strong> {selectedRow.account_owner_internal ?? '—'}
              </Typography>
              <Typography variant="body2">
                <strong>Preferred distributor:</strong> {selectedRow.preferred_distributor_name ?? selectedRow.preferred_distributor_code ?? '—'}
              </Typography>
              <Typography variant="body2">
                <strong>Locations:</strong> {selectedRow.location_count ?? 0} | <strong>Contacts:</strong>{' '}
                {selectedRow.contact_count ?? 0}
              </Typography>
              <Typography variant="body2">
                <strong>Notes:</strong> {selectedRow.notes_summary ?? '—'}
              </Typography>
              <Divider sx={{ my: 1 }} />
              <CustomerCommercialTermsPanel customerId={selectedRow.id} customerCode={selectedRow.customer_code} />
              <Typography variant="subtitle2" sx={{ pt: 1 }}>
                Locations
              </Typography>
              {locationsLoading ? <Typography variant="body2">Loading locations…</Typography> : null}
              {(locations ?? []).map((loc) => (
                <Paper key={loc.id} variant="outlined" sx={{ p: 1 }}>
                  <Stack spacing={1}>
                    <TextField
                      size="small"
                      label="Location code"
                      value={loc.location_code}
                      onChange={(e) => {
                        if (editingLocationId !== loc.id) setEditingLocationId(loc.id);
                        qc.setQueryData<CustomerLocationRow[]>(['customer-locations', selectedRow.id], (prev = []) =>
                          prev.map((x) => (x.id === loc.id ? { ...x, location_code: e.target.value } : x))
                        );
                      }}
                    />
                    <TextField
                      size="small"
                      label="Location name"
                      value={loc.location_name}
                      onChange={(e) => {
                        if (editingLocationId !== loc.id) setEditingLocationId(loc.id);
                        qc.setQueryData<CustomerLocationRow[]>(['customer-locations', selectedRow.id], (prev = []) =>
                          prev.map((x) => (x.id === loc.id ? { ...x, location_name: e.target.value } : x))
                        );
                      }}
                    />
                    <FormControl size="small">
                      <InputLabel id={`loc-type-${loc.id}`}>Type</InputLabel>
                      <Select
                        labelId={`loc-type-${loc.id}`}
                        label="Type"
                        value={loc.location_type}
                        onChange={(e) => {
                          if (editingLocationId !== loc.id) setEditingLocationId(loc.id);
                          qc.setQueryData<CustomerLocationRow[]>(['customer-locations', selectedRow.id], (prev = []) =>
                            prev.map((x) => (x.id === loc.id ? { ...x, location_type: String(e.target.value) } : x))
                          );
                        }}
                      >
                        {LOCATION_TYPE_OPTIONS.map((opt) => (
                          <MenuItem key={opt} value={opt}>
                            {opt}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                    <Stack direction="row" spacing={1}>
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => patchLocation.mutate(loc)}
                        disabled={patchLocation.isPending}
                      >
                        Save
                      </Button>
                      <Button
                        size="small"
                        color="error"
                        onClick={() => deleteLocation.mutate(loc.id)}
                        disabled={deleteLocation.isPending}
                      >
                        Delete
                      </Button>
                    </Stack>
                  </Stack>
                </Paper>
              ))}
              <Paper variant="outlined" sx={{ p: 1 }}>
                <Stack spacing={1}>
                  <Typography variant="body2" fontWeight={600}>
                    Add location
                  </Typography>
                  <TextField
                    size="small"
                    label="Location code"
                    value={locationDraft.location_code}
                    onChange={(e) => setLocationDraft((s) => ({ ...s, location_code: e.target.value }))}
                  />
                  <TextField
                    size="small"
                    label="Location name"
                    value={locationDraft.location_name}
                    onChange={(e) => setLocationDraft((s) => ({ ...s, location_name: e.target.value }))}
                  />
                  <FormControl size="small">
                    <InputLabel id="new-loc-type">Type</InputLabel>
                    <Select
                      labelId="new-loc-type"
                      label="Type"
                      value={locationDraft.location_type}
                      onChange={(e) => setLocationDraft((s) => ({ ...s, location_type: String(e.target.value) }))}
                    >
                      {LOCATION_TYPE_OPTIONS.map((opt) => (
                        <MenuItem key={opt} value={opt}>
                          {opt}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <Button
                    size="small"
                    variant="contained"
                    onClick={() => createLocation.mutate()}
                    disabled={createLocation.isPending || !locationDraft.location_code.trim() || !locationDraft.location_name.trim()}
                  >
                    Add location
                  </Button>
                </Stack>
              </Paper>
              <Typography variant="subtitle2" sx={{ pt: 1 }}>
                Contacts
              </Typography>
              {contactsLoading ? <Typography variant="body2">Loading contacts…</Typography> : null}
              {(contacts ?? []).map((contact) => (
                <Paper key={contact.id} variant="outlined" sx={{ p: 1 }}>
                  <Stack spacing={1}>
                    <TextField
                      size="small"
                      label="Contact name"
                      value={contact.contact_name}
                      onChange={(e) => {
                        if (editingContactId !== contact.id) setEditingContactId(contact.id);
                        qc.setQueryData<CustomerContactRow[]>(['customer-contacts', selectedRow.id], (prev = []) =>
                          prev.map((x) => (x.id === contact.id ? { ...x, contact_name: e.target.value } : x))
                        );
                      }}
                    />
                    <FormControl size="small">
                      <InputLabel id={`contact-role-${contact.id}`}>Role</InputLabel>
                      <Select
                        labelId={`contact-role-${contact.id}`}
                        label="Role"
                        value={contact.contact_role}
                        onChange={(e) => {
                          if (editingContactId !== contact.id) setEditingContactId(contact.id);
                          qc.setQueryData<CustomerContactRow[]>(['customer-contacts', selectedRow.id], (prev = []) =>
                            prev.map((x) => (x.id === contact.id ? { ...x, contact_role: String(e.target.value) } : x))
                          );
                        }}
                      >
                        {CONTACT_ROLE_OPTIONS.map((opt) => (
                          <MenuItem key={opt} value={opt}>
                            {opt}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                    <TextField
                      size="small"
                      label="Email"
                      value={contact.email ?? ''}
                      onChange={(e) => {
                        if (editingContactId !== contact.id) setEditingContactId(contact.id);
                        qc.setQueryData<CustomerContactRow[]>(['customer-contacts', selectedRow.id], (prev = []) =>
                          prev.map((x) => (x.id === contact.id ? { ...x, email: e.target.value } : x))
                        );
                      }}
                    />
                    <TextField
                      size="small"
                      label="Phone"
                      value={contact.phone ?? ''}
                      onChange={(e) => {
                        if (editingContactId !== contact.id) setEditingContactId(contact.id);
                        qc.setQueryData<CustomerContactRow[]>(['customer-contacts', selectedRow.id], (prev = []) =>
                          prev.map((x) => (x.id === contact.id ? { ...x, phone: e.target.value } : x))
                        );
                      }}
                    />
                    <Stack direction="row" spacing={1}>
                      <Button size="small" variant="outlined" onClick={() => patchContact.mutate(contact)}>
                        Save
                      </Button>
                      <Button size="small" color="error" onClick={() => deleteContact.mutate(contact.id)}>
                        Delete
                      </Button>
                    </Stack>
                  </Stack>
                </Paper>
              ))}
              <Paper variant="outlined" sx={{ p: 1 }}>
                <Stack spacing={1}>
                  <Typography variant="body2" fontWeight={600}>
                    Add contact
                  </Typography>
                  <TextField
                    size="small"
                    label="Contact name"
                    value={contactDraft.contact_name}
                    onChange={(e) => setContactDraft((s) => ({ ...s, contact_name: e.target.value }))}
                  />
                  <FormControl size="small">
                    <InputLabel id="new-contact-role">Role</InputLabel>
                    <Select
                      labelId="new-contact-role"
                      label="Role"
                      value={contactDraft.contact_role}
                      onChange={(e) => setContactDraft((s) => ({ ...s, contact_role: String(e.target.value) }))}
                    >
                      {CONTACT_ROLE_OPTIONS.map((opt) => (
                        <MenuItem key={opt} value={opt}>
                          {opt}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <TextField
                    size="small"
                    label="Email"
                    value={contactDraft.email}
                    onChange={(e) => setContactDraft((s) => ({ ...s, email: e.target.value }))}
                  />
                  <TextField
                    size="small"
                    label="Phone"
                    value={contactDraft.phone}
                    onChange={(e) => setContactDraft((s) => ({ ...s, phone: e.target.value }))}
                  />
                  <Button
                    size="small"
                    variant="contained"
                    onClick={() => createContact.mutate()}
                    disabled={createContact.isPending || !contactDraft.contact_name.trim()}
                  >
                    Add contact
                  </Button>
                </Stack>
              </Paper>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => router.push('/admin/imports?template=customer_master')}
                >
                  Import customer master
                </Button>
              </Stack>
            </Stack>
          )}
        </Box>
      </Drawer>
    </>
  );
}

export default function AdminCustomersPage() {
  return (
    <Suspense fallback={<Typography color="text.secondary">Loading customers workspace…</Typography>}>
      <AdminCustomersPageContent />
    </Suspense>
  );
}
