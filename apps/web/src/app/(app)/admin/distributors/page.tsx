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
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { CellValueChangedEvent, ColDef, GridOptions } from 'ag-grid-community';
import { type ReactNode, useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { apiDelete, apiGet, apiPatch, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type DistributorRow = { id: number; code: string; name: string };

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

function TabPanel({ value, index, children }: { value: number; index: number; children: ReactNode }) {
  if (value !== index) return null;
  return <Box sx={{ pt: 2 }}>{children}</Box>;
}

export default function AdminDistributorsPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState(0);
  const [addOpen, setAddOpen] = useState(false);
  const [code, setCode] = useState('');
  const [name, setName] = useState('');

  const {
    data: distributors,
    isLoading: distLoading,
    isError: distIsError,
    error: distErr,
    refetch: refetchDist,
  } = useQuery({
    queryKey: ['admin-distributors'],
    queryFn: ({ signal }) => apiGet<DistributorRow[]>('/api/v1/distributors', { signal }),
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

  const distCodes = useMemo(() => ['', ...(distributors ?? []).map((d) => d.code)], [distributors]);

  const createDist = useMutation({
    mutationFn: () => apiPost<DistributorRow>('/api/v1/distributors', { code: code.trim(), name: name.trim() }),
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

  const onDistCell = useCallback(
    async (e: CellValueChangedEvent<DistributorRow>) => {
      const id = e.data?.id;
      if (id == null || e.colDef.field !== 'name' || e.oldValue === e.newValue) return;
      try {
        await apiPatch(`/api/v1/distributors/${id}`, { name: String(e.newValue ?? '') });
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
      const d = (distributors ?? []).find((x) => x.code === codeVal);
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
      const d = (distributors ?? []).find((x) => x.code === codeVal);
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
      { field: 'code', headerName: 'Code', pinned: 'left', minWidth: 120, editable: false },
      { field: 'name', headerName: 'Name', flex: 1, minWidth: 200, editable: true },
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
          headerName: 'Distributor (sell-through)',
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
          headerName: 'Distributor (ship-to)',
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

  const drows = distributors ?? [];

  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Admin' }, { label: 'Distributors' }]}
        title="Distributors & route mapping"
      />
      <Alert severity="info" sx={{ mb: 2 }}>
        Maintain <strong>dim_distributor</strong>, then map <strong>sell-out</strong> facts and <strong>inbound</strong>{' '}
        shipments to the distributor that best represents how the data was collected or where product lands.
      </Alert>
      <Paper sx={{ px: 2, pt: 1 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}>
          <Tab label="Distributors" />
          <Tab label="Sell-out → distributor" />
          <Tab label="Inbound → distributor" />
        </Tabs>
      </Paper>

      <TabPanel value={tab} index={0}>
        <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
          <Button variant="contained" onClick={() => setAddOpen(true)}>
            Add distributor
          </Button>
        </Stack>
        <Paper sx={{ p: 2 }}>
          <ModuleDataSection
            intro={<>Distributor codes are referenced by inventory, sell-in, and routing screens.</>}
            isLoading={distLoading}
            isError={distIsError}
            error={toQueryError(distErr)}
            onRetry={() => void refetchDist()}
            isEmpty={drows.length === 0}
            empty={{
              title: 'No distributors',
              description: 'Use Add distributor above, or load starter rows via Data imports.',
              primary: { label: 'Getting started', href: '/getting-started' },
            }}
            toolbar={
              <ModuleGridToolbar
                onRefresh={() => qc.invalidateQueries({ queryKey: ['admin-distributors'] })}
                importsHref="/admin/imports"
                busy={delDist.isPending || createDist.isPending}
              />
            }
          >
            <EnterpriseDataGrid rowData={drows} columnDefs={distCols} gridOptions={distGrid} height={440} />
          </ModuleDataSection>
        </Paper>
      </TabPanel>

      <TabPanel value={tab} index={1}>
        <Paper sx={{ p: 2 }}>
          <ModuleDataSection
            intro={<>Rows from <strong>fact_sales_sellout</strong>. Optional distributor indicates who reported or fulfilled the sell-through.</>}
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
            intro={<>Rows from <strong>fact_inbound_shipment</strong>. Assign the receiving distributor for each shipment.</>}
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
    </>
  );
}
