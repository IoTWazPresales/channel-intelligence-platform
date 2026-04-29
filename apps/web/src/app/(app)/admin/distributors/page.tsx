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
  Drawer,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Paper,
  Stack,
  Select,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { CellValueChangedEvent, ColDef, GridOptions } from 'ag-grid-community';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Suspense, type ReactNode, useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { DistributorCommercialTermsPanel } from '@/features/admin/DistributorCommercialTermsPanel';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { apiDelete, apiGet, apiPatch, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type DistributorRow = {
  id: number;
  distributor_code: string;
  distributor_name: string;
  linked_sellout_rows: number;
  linked_inbound_rows: number;
  total_sellout_rows: number;
  total_inbound_rows: number;
  latest_sellout_period_start: string | null;
  latest_inbound_eta_date: string | null;
  linkage_status: 'healthy' | 'partial' | 'unmapped' | 'no_fact_links';
  location_count?: number;
  contact_count?: number;
};
type DistributorListResponse = {
  items: DistributorRow[];
  page: number;
  page_size: number;
  total: number;
  sort_by: string;
  sort_dir: 'asc' | 'desc';
};
type ImportTemplate = {
  slug: string;
  display_name: string;
  pipeline_ready: boolean;
};
type DistributorLocationRow = {
  id: number;
  distributor_id: number;
  location_code: string;
  location_name: string;
  location_type: string;
  country_code: string | null;
  address_summary: string | null;
  is_active: boolean;
  notes_summary: string | null;
};
type DistributorContactRow = {
  id: number;
  distributor_id: number;
  contact_name: string;
  contact_role: string;
  email: string | null;
  phone: string | null;
  is_primary: boolean;
  is_active: boolean;
  notes_summary: string | null;
};

type SelloutRow = {
  id: number;
  product_sku: string | null;
  customer_code: string | null;
  period_start: string;
  units: number;
  revenue: number;
  distributor_id: number | null;
  distributor_code: string | null;
};

type InboundRow = {
  id: number;
  product_sku: string | null;
  eta_date: string;
  quantity: number;
  reference: string | null;
  status: string;
  distributor_id: number | null;
  distributor_code: string | null;
};

const DISTRIBUTOR_LOCATION_TYPE_OPTIONS = ['hq', 'branch', 'warehouse', 'office', 'store', 'other'];
const DISTRIBUTOR_CONTACT_ROLE_OPTIONS = ['general', 'executive', 'sales', 'operations', 'finance', 'support', 'other'];

function TabPanel({ value, index, children }: { value: number; index: number; children: ReactNode }) {
  if (value !== index) return null;
  return <Box sx={{ pt: 2 }}>{children}</Box>;
}

function AdminDistributorsPageContent() {
  const qc = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [tab, setTab] = useState(0);
  const [addOpen, setAddOpen] = useState(false);
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [drawerRow, setDrawerRow] = useState<DistributorRow | null>(null);
  const [locationDraft, setLocationDraft] = useState({
    location_code: '',
    location_name: '',
    location_type: 'branch',
    country_code: '',
    address_summary: '',
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

  const page = Number(searchParams.get('page') || '1') || 1;
  const pageSize = Number(searchParams.get('page_size') || '25') || 25;
  const q = searchParams.get('q') ?? '';
  const sortBy = searchParams.get('sort_by') ?? 'distributor_code';
  const sortDir = (searchParams.get('sort_dir') as 'asc' | 'desc' | null) ?? 'asc';
  const linkageFilter = searchParams.get('linkage_status') ?? '';

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

  const {
    data: distributors,
    isLoading: distLoading,
    isError: distIsError,
    error: distErr,
    refetch: refetchDist,
  } = useQuery({
    queryKey: ['admin-distributors', page, pageSize, q, sortBy, sortDir, linkageFilter],
    queryFn: ({ signal }) =>
      apiGet<DistributorListResponse>(
        `/api/v1/distributors?page=${page}&page_size=${pageSize}&q=${encodeURIComponent(q)}&sort_by=${encodeURIComponent(sortBy)}&sort_dir=${sortDir}&linkage_status=${encodeURIComponent(linkageFilter)}`,
        { signal }
      ),
  });
  const selectedDistributorId = drawerRow?.id ?? null;
  const { data: distributorLocations } = useQuery({
    queryKey: ['distributor-locations', selectedDistributorId],
    queryFn: ({ signal }) =>
      apiGet<DistributorLocationRow[]>(`/api/v1/distributors/${selectedDistributorId}/locations`, { signal }),
    enabled: selectedDistributorId != null,
  });
  const { data: distributorContacts } = useQuery({
    queryKey: ['distributor-contacts', selectedDistributorId],
    queryFn: ({ signal }) =>
      apiGet<DistributorContactRow[]>(`/api/v1/distributors/${selectedDistributorId}/contacts`, { signal }),
    enabled: selectedDistributorId != null,
  });
  const { data: templates } = useQuery({
    queryKey: ['import-templates-distributors'],
    queryFn: ({ signal }) => apiGet<ImportTemplate[]>('/api/v1/imports/templates', { signal }),
  });
  const {
    data: sellout,
    isLoading: sellLoading,
    isError: sellIsError,
    error: sellErr,
    refetch: refetchSell,
  } = useQuery({
    queryKey: ['admin-sellout'],
    queryFn: ({ signal }) => apiGet<SelloutRow[]>('/api/v1/sellout', { signal }),
    enabled: tab === 1,
  });
  const {
    data: inbound,
    isLoading: inboundLoading,
    isError: inboundIsError,
    error: inboundErr,
    refetch: refetchInbound,
  } = useQuery({
    queryKey: ['admin-inbound'],
    queryFn: ({ signal }) => apiGet<InboundRow[]>('/api/v1/inbound-shipments', { signal }),
    enabled: tab === 2,
  });

  const distCodes = useMemo(
    () => ['', ...((distributors?.items ?? []).map((d) => d.distributor_code) ?? [])],
    [distributors?.items]
  );

  const createDist = useMutation({
    mutationFn: () =>
      apiPost<DistributorRow>('/api/v1/distributors', {
        distributor_code: code.trim(),
        distributor_name: name.trim(),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-distributors'] });
      setAddOpen(false);
      setCode('');
      setName('');
    },
  });

  const delDist = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/distributors/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-distributors'] }),
  });
  const delSell = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/sellout/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-sellout'] }),
  });
  const clearSell = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/sellout/clear-all', { confirm: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-sellout'] }),
  });
  const delInbound = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/inbound-shipments/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-inbound'] }),
  });
  const clearInbound = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/inbound-shipments/clear-all', { confirm: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-inbound'] }),
  });
  const createLocation = useMutation({
    mutationFn: async () =>
      apiPost<DistributorLocationRow>(`/api/v1/distributors/${selectedDistributorId}/locations`, {
        location_code: locationDraft.location_code.trim(),
        location_name: locationDraft.location_name.trim(),
        location_type: locationDraft.location_type,
        country_code: locationDraft.country_code.trim() || null,
        address_summary: locationDraft.address_summary.trim() || null,
        is_active: locationDraft.is_active,
        notes_summary: locationDraft.notes_summary.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['distributor-locations', selectedDistributorId] });
      qc.invalidateQueries({ queryKey: ['admin-distributors'] });
      setLocationDraft({
        location_code: '',
        location_name: '',
        location_type: 'branch',
        country_code: '',
        address_summary: '',
        is_active: true,
        notes_summary: '',
      });
    },
  });
  const patchLocation = useMutation({
    mutationFn: async (locationId: number) =>
      apiPatch<DistributorLocationRow>(`/api/v1/distributors/${selectedDistributorId}/locations/${locationId}`, {
        location_code: locationDraft.location_code.trim(),
        location_name: locationDraft.location_name.trim(),
        location_type: locationDraft.location_type,
        country_code: locationDraft.country_code.trim() || null,
        address_summary: locationDraft.address_summary.trim() || null,
        is_active: locationDraft.is_active,
        notes_summary: locationDraft.notes_summary.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['distributor-locations', selectedDistributorId] });
      qc.invalidateQueries({ queryKey: ['admin-distributors'] });
      setEditingLocationId(null);
      setLocationDraft({
        location_code: '',
        location_name: '',
        location_type: 'branch',
        country_code: '',
        address_summary: '',
        is_active: true,
        notes_summary: '',
      });
    },
  });
  const deleteLocation = useMutation({
    mutationFn: async (locationId: number) =>
      apiDelete(`/api/v1/distributors/${selectedDistributorId}/locations/${locationId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['distributor-locations', selectedDistributorId] });
      qc.invalidateQueries({ queryKey: ['admin-distributors'] });
    },
  });
  const createContact = useMutation({
    mutationFn: async () =>
      apiPost<DistributorContactRow>(`/api/v1/distributors/${selectedDistributorId}/contacts`, {
        contact_name: contactDraft.contact_name.trim(),
        contact_role: contactDraft.contact_role,
        email: contactDraft.email.trim() || null,
        phone: contactDraft.phone.trim() || null,
        is_primary: contactDraft.is_primary,
        is_active: contactDraft.is_active,
        notes_summary: contactDraft.notes_summary.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['distributor-contacts', selectedDistributorId] });
      qc.invalidateQueries({ queryKey: ['admin-distributors'] });
      setContactDraft({
        contact_name: '',
        contact_role: 'general',
        email: '',
        phone: '',
        is_primary: false,
        is_active: true,
        notes_summary: '',
      });
    },
  });
  const patchContact = useMutation({
    mutationFn: async (contactId: number) =>
      apiPatch<DistributorContactRow>(`/api/v1/distributors/${selectedDistributorId}/contacts/${contactId}`, {
        contact_name: contactDraft.contact_name.trim(),
        contact_role: contactDraft.contact_role,
        email: contactDraft.email.trim() || null,
        phone: contactDraft.phone.trim() || null,
        is_primary: contactDraft.is_primary,
        is_active: contactDraft.is_active,
        notes_summary: contactDraft.notes_summary.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['distributor-contacts', selectedDistributorId] });
      qc.invalidateQueries({ queryKey: ['admin-distributors'] });
      setEditingContactId(null);
      setContactDraft({
        contact_name: '',
        contact_role: 'general',
        email: '',
        phone: '',
        is_primary: false,
        is_active: true,
        notes_summary: '',
      });
    },
  });
  const deleteContact = useMutation({
    mutationFn: async (contactId: number) =>
      apiDelete(`/api/v1/distributors/${selectedDistributorId}/contacts/${contactId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['distributor-contacts', selectedDistributorId] });
      qc.invalidateQueries({ queryKey: ['admin-distributors'] });
    },
  });

  const onDistCell = useCallback(
    async (e: CellValueChangedEvent<DistributorRow>) => {
      const id = e.data?.id;
      if (id == null || e.colDef.field !== 'distributor_name' || e.oldValue === e.newValue) return;
      try {
        await apiPatch(`/api/v1/distributors/${id}`, { distributor_name: String(e.newValue ?? '') });
        await qc.invalidateQueries({ queryKey: ['admin-distributors'] });
      } catch (err) {
        console.error(err);
        await qc.invalidateQueries({ queryKey: ['admin-distributors'] });
      }
    },
    [qc]
  );

  const onSellCell = useCallback(
    async (e: CellValueChangedEvent<SelloutRow>) => {
      const id = e.data?.id;
      if (id == null || e.colDef.field !== 'distributor_code' || e.oldValue === e.newValue) return;
      const codeVal = String(e.newValue ?? '');
      const d = (distributors?.items ?? []).find((x) => x.distributor_code === codeVal);
      try {
        await apiPatch(`/api/v1/sellout/${id}`, { distributor_id: d ? d.id : null });
        await qc.invalidateQueries({ queryKey: ['admin-sellout'] });
      } catch (err) {
        console.error(err);
        await qc.invalidateQueries({ queryKey: ['admin-sellout'] });
      }
    },
    [distributors, qc]
  );

  const onInboundCell = useCallback(
    async (e: CellValueChangedEvent<InboundRow>) => {
      const id = e.data?.id;
      if (id == null || e.colDef.field !== 'distributor_code' || e.oldValue === e.newValue) return;
      const codeVal = String(e.newValue ?? '');
      const d = (distributors?.items ?? []).find((x) => x.distributor_code === codeVal);
      try {
        await apiPatch(`/api/v1/inbound-shipments/${id}`, { distributor_id: d ? d.id : null });
        await qc.invalidateQueries({ queryKey: ['admin-inbound'] });
      } catch (err) {
        console.error(err);
        await qc.invalidateQueries({ queryKey: ['admin-inbound'] });
      }
    },
    [distributors, qc]
  );

  const distCols: ColDef<DistributorRow>[] = useMemo(
    () => [
      { field: 'distributor_code', headerName: 'Code', pinned: 'left', minWidth: 140, editable: false },
      { field: 'distributor_name', headerName: 'Canonical name', flex: 1, minWidth: 220, editable: true },
      {
        field: 'linkage_status',
        headerName: 'Linkage status',
        minWidth: 150,
        editable: false,
        cellRenderer: ({ value }: { value: DistributorRow['linkage_status'] }) => {
          const color =
            value === 'healthy' ? 'success' : value === 'partial' ? 'warning' : value === 'unmapped' ? 'error' : 'default';
          return <Chip size="small" color={color} label={value.replace(/_/g, ' ')} />;
        },
      },
      { field: 'linked_sellout_rows', headerName: 'Sell-out linked', minWidth: 130, editable: false },
      { field: 'linked_inbound_rows', headerName: 'Inbound linked', minWidth: 130, editable: false },
      { field: 'latest_sellout_period_start', headerName: 'Latest sell-out', minWidth: 140, editable: false },
      { field: 'latest_inbound_eta_date', headerName: 'Latest inbound', minWidth: 130, editable: false },
      {
        headerName: 'Details',
        minWidth: 110,
        editable: false,
        cellRenderer: ({ data }: { data: DistributorRow }) =>
          data ? (
            <Button size="small" onClick={() => setDrawerRow(data)}>
              Open
            </Button>
          ) : null,
      },
      gridDeleteColumn<DistributorRow>((id) => void delDist.mutate(id), { busy: delDist.isPending }),
    ],
    [delDist, delDist.isPending]
  );

  const sellCols: ColDef<SelloutRow>[] = useMemo(
    () => {
      const busyDel = delSell.isPending || clearSell.isPending;
      return [
        { field: 'product_sku', headerName: 'SKU', minWidth: 130, editable: false },
        { field: 'customer_code', headerName: 'Customer', minWidth: 120, editable: false },
        { field: 'period_start', headerName: 'Period', minWidth: 120, editable: false },
        { field: 'units', headerName: 'Units', type: 'numericColumn', editable: false },
        {
          field: 'distributor_code',
          headerName: 'Distributor',
          minWidth: 180,
          editable: true,
          cellEditor: 'agSelectCellEditor',
          cellEditorParams: { values: distCodes },
        },
        gridDeleteColumn<SelloutRow>((id) => void delSell.mutate(id), { busy: busyDel }),
      ];
    },
    [distCodes, delSell, delSell.isPending, clearSell.isPending]
  );

  const inboundCols: ColDef<InboundRow>[] = useMemo(
    () => {
      const busyDel = delInbound.isPending || clearInbound.isPending;
      return [
        { field: 'product_sku', headerName: 'SKU', minWidth: 130, editable: false },
        { field: 'eta_date', headerName: 'ETA', minWidth: 120, editable: false },
        { field: 'quantity', headerName: 'Qty', type: 'numericColumn', editable: false },
        { field: 'status', headerName: 'Status', minWidth: 100, editable: false },
        {
          field: 'distributor_code',
          headerName: 'Distributor',
          minWidth: 180,
          editable: true,
          cellEditor: 'agSelectCellEditor',
          cellEditorParams: { values: distCodes },
        },
        gridDeleteColumn<InboundRow>((id) => void delInbound.mutate(id), { busy: busyDel }),
      ];
    },
    [distCodes, delInbound, delInbound.isPending, clearInbound.isPending]
  );

  const distGrid: GridOptions<DistributorRow> = useMemo(
    () => ({ singleClickEdit: true, onCellValueChanged: onDistCell }),
    [onDistCell]
  );
  const sellGrid: GridOptions<SelloutRow> = useMemo(
    () => ({ singleClickEdit: true, onCellValueChanged: onSellCell }),
    [onSellCell]
  );
  const inboundGrid: GridOptions<InboundRow> = useMemo(
    () => ({ singleClickEdit: true, onCellValueChanged: onInboundCell }),
    [onInboundCell]
  );

  const drows = distributors?.items ?? [];
  const distributorMasterTemplate = (templates ?? []).find((t) => t.slug === 'distributor_master');
  const distributorInventoryTemplate = (templates ?? []).find((t) => t.slug === 'distributor_inventory');
  const hasDistributorMasterImport = Boolean(distributorMasterTemplate?.pipeline_ready);
  const hasDistributorInventoryImport = Boolean(distributorInventoryTemplate?.pipeline_ready);

  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Admin' }, { label: 'Distributors' }]}
        title="Distributors"
      />
      <Alert severity="info" sx={{ mb: 2 }}>
        Maintain distributor master records first, then monitor linkage health across sell-out and inbound feeds.
        Transitional fact-mapping tabs remain available below while import and routing maturity catches up.
      </Alert>
      <Paper sx={{ px: 2, pt: 1 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}>
          <Tab label="Distributor master" />
          <Tab label="Transitional: sell-out mapping" />
          <Tab label="Transitional: inbound mapping" />
        </Tabs>
      </Paper>

      <TabPanel value={tab} index={0}>
        <Stack direction="row" spacing={1} sx={{ mb: 1.5 }}>
          <Button variant="contained" onClick={() => setAddOpen(true)}>
            Add distributor
          </Button>
          {hasDistributorMasterImport ? (
            <Button variant="outlined" onClick={() => router.push('/admin/imports?template=distributor_master')}>
              Import distributor master
            </Button>
          ) : null}
          {hasDistributorInventoryImport ? (
            <Button variant="outlined" onClick={() => router.push('/admin/imports?template=distributor_inventory')}>
              Import distributor inventory
            </Button>
          ) : null}
        </Stack>
        <Paper sx={{ p: 2 }}>
          <ModuleDataSection
            intro={
              <>
                Distributor master and linkage health. Only operationally ready import paths are shown here; deferred
                templates stay hidden.
              </>
            }
            isLoading={distLoading}
            isError={distIsError}
            error={toQueryError(distErr)}
            onRetry={() => void refetchDist()}
            isEmpty={drows.length === 0}
            empty={{
              title: 'No distributors',
              description: hasDistributorMasterImport
                ? 'Use Add distributor above, or import distributor master data from your source feed.'
                : 'Use Add distributor above. Distributor master import is not currently ready.',
              primary: hasDistributorMasterImport
                ? { label: 'Import distributor master', href: '/admin/imports?template=distributor_master' }
                : { label: 'Getting started', href: '/getting-started' },
              secondary: hasDistributorInventoryImport
                ? { label: 'Import distributor inventory', href: '/admin/imports?template=distributor_inventory' }
                : undefined,
            }}
            toolbar={
              <Stack direction="row" spacing={1} alignItems="center">
                <TextField
                  size="small"
                  label="Search distributors"
                  value={q}
                  onChange={(e) => setParamState({ q: e.target.value || null }, true)}
                />
                <FormControl size="small" sx={{ minWidth: 170 }}>
                  <InputLabel id="dist-linkage-filter-label">Linkage status</InputLabel>
                  <Select
                    labelId="dist-linkage-filter-label"
                    label="Linkage status"
                    value={linkageFilter}
                    onChange={(e) => setParamState({ linkage_status: String(e.target.value) || null }, true)}
                  >
                    <MenuItem value="">All</MenuItem>
                    <MenuItem value="healthy">healthy</MenuItem>
                    <MenuItem value="partial">partial</MenuItem>
                    <MenuItem value="unmapped">unmapped</MenuItem>
                    <MenuItem value="no_fact_links">no fact links</MenuItem>
                  </Select>
                </FormControl>
                <FormControl size="small" sx={{ minWidth: 170 }}>
                  <InputLabel id="dist-sort-by-label">Sort by</InputLabel>
                  <Select
                    labelId="dist-sort-by-label"
                    label="Sort by"
                    value={sortBy}
                    onChange={(e) => setParamState({ sort_by: String(e.target.value) }, false)}
                  >
                    <MenuItem value="distributor_code">Code</MenuItem>
                    <MenuItem value="distributor_name">Name</MenuItem>
                    <MenuItem value="latest_sellout_period_start">Latest sell-out</MenuItem>
                    <MenuItem value="latest_inbound_eta_date">Latest inbound</MenuItem>
                    <MenuItem value="linked_sellout_rows">Sell-out linked</MenuItem>
                    <MenuItem value="linked_inbound_rows">Inbound linked</MenuItem>
                  </Select>
                </FormControl>
                <FormControl size="small" sx={{ minWidth: 130 }}>
                  <InputLabel id="dist-sort-dir-label">Direction</InputLabel>
                  <Select
                    labelId="dist-sort-dir-label"
                    label="Direction"
                    value={sortDir}
                    onChange={(e) => setParamState({ sort_dir: String(e.target.value) }, false)}
                  >
                    <MenuItem value="asc">Asc</MenuItem>
                    <MenuItem value="desc">Desc</MenuItem>
                  </Select>
                </FormControl>
                <FormControl size="small" sx={{ minWidth: 120 }}>
                  <InputLabel id="dist-page-size-label">Page size</InputLabel>
                  <Select
                    labelId="dist-page-size-label"
                    label="Page size"
                    value={String(pageSize)}
                    onChange={(e) => setParamState({ page_size: String(e.target.value) }, true)}
                  >
                    <MenuItem value="25">25</MenuItem>
                    <MenuItem value="50">50</MenuItem>
                    <MenuItem value="100">100</MenuItem>
                  </Select>
                </FormControl>
                <ModuleGridToolbar
                  onRefresh={() => qc.invalidateQueries({ queryKey: ['admin-distributors'] })}
                  importsHref={
                    hasDistributorMasterImport
                      ? '/admin/imports?template=distributor_master'
                      : hasDistributorInventoryImport
                        ? '/admin/imports?template=distributor_inventory'
                        : undefined
                  }
                  busy={delDist.isPending || createDist.isPending}
                />
              </Stack>
            }
          >
            <EnterpriseDataGrid rowData={drows} columnDefs={distCols} gridOptions={distGrid} height={440} />
            <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center" sx={{ mt: 1.5 }}>
              <Typography variant="body2" color="text.secondary">
                Page {distributors?.page ?? page} of {Math.max(1, Math.ceil((distributors?.total ?? 0) / pageSize))}
              </Typography>
              <Button
                size="small"
                onClick={() => setParamState({ page: String(Math.max(1, page - 1)) })}
                disabled={page <= 1}
              >
                Prev
              </Button>
              <Button
                size="small"
                onClick={() => setParamState({ page: String(page + 1) })}
                disabled={(distributors?.page ?? 1) * pageSize >= (distributors?.total ?? 0)}
              >
                Next
              </Button>
            </Stack>
          </ModuleDataSection>
        </Paper>
      </TabPanel>

      <TabPanel value={tab} index={1}>
        <Paper sx={{ p: 2 }}>
          <ModuleDataSection
            intro={
              <>
                Transitional mapper over <strong>fact_sales_sellout</strong>. Keep this for continuity while
                distributor linkage workflows are hardened.
              </>
            }
            isLoading={sellLoading}
            isError={sellIsError}
            error={toQueryError(sellErr)}
            onRetry={() => void refetchSell()}
            isEmpty={(sellout ?? []).length === 0}
            empty={{
              title: 'No sell-out rows',
              description: 'Load sales facts via Data imports or upstream connectors when available.',
              primary: { label: 'Data & imports', href: '/admin/imports' },
            }}
            toolbar={
              <ModuleGridToolbar
                onRefresh={() => qc.invalidateQueries({ queryKey: ['admin-sellout'] })}
                onClearAll={() => {
                  if (!window.confirm('Delete every sell-out fact row? This cannot be undone.')) return;
                  void clearSell.mutate();
                }}
                importsHref="/admin/imports"
                busy={delSell.isPending || clearSell.isPending}
              />
            }
          >
            <EnterpriseDataGrid rowData={sellout ?? []} columnDefs={sellCols} gridOptions={sellGrid} height={480} />
          </ModuleDataSection>
        </Paper>
      </TabPanel>

      <TabPanel value={tab} index={2}>
        <Paper sx={{ p: 2 }}>
          <ModuleDataSection
            intro={
              <>
                Transitional mapper over <strong>fact_inbound_shipment</strong> to keep current operations running.
              </>
            }
            isLoading={inboundLoading}
            isError={inboundIsError}
            error={toQueryError(inboundErr)}
            onRetry={() => void refetchInbound()}
            isEmpty={(inbound ?? []).length === 0}
            empty={{
              title: 'No inbound rows',
              description: 'Inbound shipment facts appear when purchase-order or ASN data is loaded.',
              primary: { label: 'Data & imports', href: '/admin/imports' },
            }}
            toolbar={
              <ModuleGridToolbar
                onRefresh={() => qc.invalidateQueries({ queryKey: ['admin-inbound'] })}
                onClearAll={() => {
                  if (!window.confirm('Delete every inbound shipment row? This cannot be undone.')) return;
                  void clearInbound.mutate();
                }}
                importsHref="/admin/imports"
                busy={delInbound.isPending || clearInbound.isPending}
              />
            }
          >
            <EnterpriseDataGrid rowData={inbound ?? []} columnDefs={inboundCols} gridOptions={inboundGrid} height={480} />
          </ModuleDataSection>
        </Paper>
      </TabPanel>

      <Dialog open={addOpen} onClose={() => !createDist.isPending && setAddOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>New distributor</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Code" value={code} onChange={(e) => setCode(e.target.value)} required />
            <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} required />
          </Stack>
          {createDist.isError ? (
            <Alert severity="error" sx={{ mt: 2 }}>
              {(createDist.error as Error).message}
            </Alert>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)} disabled={createDist.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={createDist.isPending || !code.trim() || !name.trim()}
            onClick={() => createDist.mutate()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
      <Drawer anchor="right" open={Boolean(drawerRow)} onClose={() => setDrawerRow(null)}>
        <Box sx={{ width: 460, p: 2 }}>
          <Typography variant="h6" sx={{ mb: 1.5 }}>
            Distributor details
          </Typography>
          {drawerRow ? (
            <Stack spacing={1.25}>
              <Paper variant="outlined" sx={{ p: 1.25 }}>
                <Typography variant="subtitle2">Summary</Typography>
                <Typography variant="body2">
                  <strong>Code:</strong> {drawerRow.distributor_code}
                </Typography>
                <Typography variant="body2">
                  <strong>Canonical name:</strong> {drawerRow.distributor_name}
                </Typography>
                <Typography variant="body2">
                  <strong>Locations:</strong> {drawerRow.location_count ?? distributorLocations?.length ?? 0}
                </Typography>
                <Typography variant="body2">
                  <strong>Contacts:</strong> {drawerRow.contact_count ?? distributorContacts?.length ?? 0}
                </Typography>
              </Paper>
              <Paper variant="outlined" sx={{ p: 1.25 }}>
                <Typography variant="subtitle2">Linkage health</Typography>
                <Chip
                  sx={{ my: 0.75 }}
                  size="small"
                  color={
                    drawerRow.linkage_status === 'healthy'
                      ? 'success'
                      : drawerRow.linkage_status === 'partial'
                        ? 'warning'
                        : drawerRow.linkage_status === 'unmapped'
                          ? 'error'
                          : 'default'
                  }
                  label={drawerRow.linkage_status.replace(/_/g, ' ')}
                />
                <Typography variant="body2">
                  <strong>Sell-out linked:</strong> {drawerRow.linked_sellout_rows} / {drawerRow.total_sellout_rows}
                </Typography>
                <Typography variant="body2">
                  <strong>Inbound linked:</strong> {drawerRow.linked_inbound_rows} / {drawerRow.total_inbound_rows}
                </Typography>
                <Typography variant="body2">
                  <strong>Latest sell-out period:</strong> {drawerRow.latest_sellout_period_start ?? '—'}
                </Typography>
                <Typography variant="body2">
                  <strong>Latest inbound ETA:</strong> {drawerRow.latest_inbound_eta_date ?? '—'}
                </Typography>
              </Paper>
              <DistributorCommercialTermsPanel
                distributorId={drawerRow.id}
                distributorCode={drawerRow.distributor_code}
              />
              <Paper variant="outlined" sx={{ p: 1.25 }}>
                <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
                  Locations
                </Typography>
                <Stack spacing={1} sx={{ mb: 1 }}>
                  {(distributorLocations ?? []).map((loc) => (
                    <Paper key={loc.id} variant="outlined" sx={{ p: 0.75 }}>
                      <Typography variant="body2">
                        <strong>{loc.location_code}</strong> — {loc.location_name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" display="block">
                        {loc.location_type}
                        {loc.country_code ? ` · ${loc.country_code}` : ''} · {loc.is_active ? 'active' : 'inactive'}
                      </Typography>
                      <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                        <Button
                          size="small"
                          onClick={() => {
                            setEditingLocationId(loc.id);
                            setLocationDraft({
                              location_code: loc.location_code,
                              location_name: loc.location_name,
                              location_type: loc.location_type,
                              country_code: loc.country_code ?? '',
                              address_summary: loc.address_summary ?? '',
                              is_active: loc.is_active,
                              notes_summary: loc.notes_summary ?? '',
                            });
                          }}
                        >
                          Edit
                        </Button>
                        <Button size="small" color="error" onClick={() => void deleteLocation.mutate(loc.id)}>
                          Delete
                        </Button>
                      </Stack>
                    </Paper>
                  ))}
                </Stack>
                <Stack spacing={1}>
                  <TextField
                    size="small"
                    label="Location code"
                    value={locationDraft.location_code}
                    onChange={(e) => setLocationDraft((prev) => ({ ...prev, location_code: e.target.value }))}
                  />
                  <TextField
                    size="small"
                    label="Location name"
                    value={locationDraft.location_name}
                    onChange={(e) => setLocationDraft((prev) => ({ ...prev, location_name: e.target.value }))}
                  />
                  <FormControl size="small">
                    <InputLabel id="dist-location-type-label">Location type</InputLabel>
                    <Select
                      labelId="dist-location-type-label"
                      label="Location type"
                      value={locationDraft.location_type}
                      onChange={(e) => setLocationDraft((prev) => ({ ...prev, location_type: String(e.target.value) }))}
                    >
                      {DISTRIBUTOR_LOCATION_TYPE_OPTIONS.map((opt) => (
                        <MenuItem key={opt} value={opt}>
                          {opt}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <TextField
                    size="small"
                    label="Country code"
                    value={locationDraft.country_code}
                    onChange={(e) => setLocationDraft((prev) => ({ ...prev, country_code: e.target.value }))}
                  />
                  <TextField
                    size="small"
                    label="Address summary"
                    value={locationDraft.address_summary}
                    onChange={(e) => setLocationDraft((prev) => ({ ...prev, address_summary: e.target.value }))}
                  />
                  <TextField
                    size="small"
                    label="Notes"
                    value={locationDraft.notes_summary}
                    onChange={(e) => setLocationDraft((prev) => ({ ...prev, notes_summary: e.target.value }))}
                  />
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={locationDraft.is_active}
                        onChange={(_, checked) => setLocationDraft((prev) => ({ ...prev, is_active: checked }))}
                      />
                    }
                    label="Active location"
                  />
                  <Stack direction="row" spacing={1}>
                    {editingLocationId ? (
                      <>
                        <Button
                          size="small"
                          variant="contained"
                          onClick={() => void patchLocation.mutate(editingLocationId)}
                          disabled={!locationDraft.location_code.trim() || !locationDraft.location_name.trim()}
                        >
                          Save location
                        </Button>
                        <Button
                          size="small"
                          onClick={() => {
                            setEditingLocationId(null);
                            setLocationDraft({
                              location_code: '',
                              location_name: '',
                              location_type: 'branch',
                              country_code: '',
                              address_summary: '',
                              is_active: true,
                              notes_summary: '',
                            });
                          }}
                        >
                          Cancel
                        </Button>
                      </>
                    ) : (
                      <Button
                        size="small"
                        variant="contained"
                        onClick={() => void createLocation.mutate()}
                        disabled={!locationDraft.location_code.trim() || !locationDraft.location_name.trim()}
                      >
                        Add location
                      </Button>
                    )}
                  </Stack>
                </Stack>
              </Paper>
              <Paper variant="outlined" sx={{ p: 1.25 }}>
                <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
                  Contacts
                </Typography>
                <Stack spacing={1} sx={{ mb: 1 }}>
                  {(distributorContacts ?? []).map((contact) => (
                    <Paper key={contact.id} variant="outlined" sx={{ p: 0.75 }}>
                      <Typography variant="body2">
                        <strong>{contact.contact_name}</strong> — {contact.contact_role}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" display="block">
                        {[contact.email, contact.phone, contact.is_primary ? 'primary' : null, contact.is_active ? 'active' : 'inactive']
                          .filter(Boolean)
                          .join(' · ')}
                      </Typography>
                      <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                        <Button
                          size="small"
                          onClick={() => {
                            setEditingContactId(contact.id);
                            setContactDraft({
                              contact_name: contact.contact_name,
                              contact_role: contact.contact_role,
                              email: contact.email ?? '',
                              phone: contact.phone ?? '',
                              is_primary: contact.is_primary,
                              is_active: contact.is_active,
                              notes_summary: contact.notes_summary ?? '',
                            });
                          }}
                        >
                          Edit
                        </Button>
                        <Button size="small" color="error" onClick={() => void deleteContact.mutate(contact.id)}>
                          Delete
                        </Button>
                      </Stack>
                    </Paper>
                  ))}
                </Stack>
                <Stack spacing={1}>
                  <TextField
                    size="small"
                    label="Contact name"
                    value={contactDraft.contact_name}
                    onChange={(e) => setContactDraft((prev) => ({ ...prev, contact_name: e.target.value }))}
                  />
                  <FormControl size="small">
                    <InputLabel id="dist-contact-role-label">Contact role</InputLabel>
                    <Select
                      labelId="dist-contact-role-label"
                      label="Contact role"
                      value={contactDraft.contact_role}
                      onChange={(e) => setContactDraft((prev) => ({ ...prev, contact_role: String(e.target.value) }))}
                    >
                      {DISTRIBUTOR_CONTACT_ROLE_OPTIONS.map((opt) => (
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
                    onChange={(e) => setContactDraft((prev) => ({ ...prev, email: e.target.value }))}
                  />
                  <TextField
                    size="small"
                    label="Phone"
                    value={contactDraft.phone}
                    onChange={(e) => setContactDraft((prev) => ({ ...prev, phone: e.target.value }))}
                  />
                  <TextField
                    size="small"
                    label="Notes"
                    value={contactDraft.notes_summary}
                    onChange={(e) => setContactDraft((prev) => ({ ...prev, notes_summary: e.target.value }))}
                  />
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={contactDraft.is_primary}
                        onChange={(_, checked) => setContactDraft((prev) => ({ ...prev, is_primary: checked }))}
                      />
                    }
                    label="Primary contact"
                  />
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={contactDraft.is_active}
                        onChange={(_, checked) => setContactDraft((prev) => ({ ...prev, is_active: checked }))}
                      />
                    }
                    label="Active contact"
                  />
                  <Stack direction="row" spacing={1}>
                    {editingContactId ? (
                      <>
                        <Button
                          size="small"
                          variant="contained"
                          onClick={() => void patchContact.mutate(editingContactId)}
                          disabled={!contactDraft.contact_name.trim()}
                        >
                          Save contact
                        </Button>
                        <Button
                          size="small"
                          onClick={() => {
                            setEditingContactId(null);
                            setContactDraft({
                              contact_name: '',
                              contact_role: 'general',
                              email: '',
                              phone: '',
                              is_primary: false,
                              is_active: true,
                              notes_summary: '',
                            });
                          }}
                        >
                          Cancel
                        </Button>
                      </>
                    ) : (
                      <Button
                        size="small"
                        variant="contained"
                        onClick={() => void createContact.mutate()}
                        disabled={!contactDraft.contact_name.trim()}
                      >
                        Add contact
                      </Button>
                    )}
                  </Stack>
                </Stack>
              </Paper>
              <Paper variant="outlined" sx={{ p: 1.25 }}>
                <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
                  Imports
                </Typography>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  {hasDistributorMasterImport ? (
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => router.push('/admin/imports?template=distributor_master')}
                    >
                      Import distributor master
                    </Button>
                  ) : null}
                  {hasDistributorInventoryImport ? (
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => router.push('/admin/imports?template=distributor_inventory')}
                    >
                      Import distributor inventory
                    </Button>
                  ) : null}
                </Stack>
                {!hasDistributorMasterImport && !hasDistributorInventoryImport ? (
                  <Alert severity="info" sx={{ mt: 1 }}>
                    Distributor import templates are not currently ready in this environment.
                  </Alert>
                ) : null}
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.75 }}>
                  Master import updates `dim_distributor`; inventory import validates SKU/on-hand snapshots. Deferred
                  templates are intentionally not shown as ready paths.
                </Typography>
              </Paper>
            </Stack>
          ) : null}
        </Box>
      </Drawer>
    </>
  );
}

export default function AdminDistributorsPage() {
  return (
    <Suspense fallback={<Typography color="text.secondary">Loading distributors workspace…</Typography>}>
      <AdminDistributorsPageContent />
    </Suspense>
  );
}
