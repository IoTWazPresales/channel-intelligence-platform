'use client';

import { Box, Button, Paper, Tab, Tabs } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { apiDelete, apiGet, apiPost, apiUrl, authHeaders } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type MapRow = {
  id: number;
  internal_sku: string | null;
  competitor_sku: string | null;
  score: number;
  explanation: string;
  approval_status: string;
};

type PriceRow = {
  id: number;
  competitor_sku: string | null;
  observed_at: string;
  price: number;
  channel: string | null;
};

export default function CompetitionPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState(0);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['competition-mappings'],
    queryFn: ({ signal }) => apiGet<MapRow[]>('/api/v1/competition/mappings', { signal }),
  });
  const {
    data: prices,
    isLoading: pricesLoading,
    isError: pricesIsError,
    error: pricesErr,
    refetch: refetchPrices,
  } = useQuery({
    queryKey: ['competition-prices'],
    queryFn: ({ signal }) => apiGet<PriceRow[]>('/api/v1/competition/prices', { signal }),
    enabled: tab === 1,
  });

  const approve = useMutation({
    mutationFn: async (id: number) => {
      const res = await fetch(apiUrl(`/api/v1/competition/mappings/${id}/approve`), {
        method: 'POST',
        headers: authHeaders(undefined, false),
      });
      return res.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['competition-mappings'] }),
  });

  const delMap = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/competition/mappings/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['competition-mappings'] }),
  });
  const clearMaps = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/competition/mappings/clear-all', { confirm: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['competition-mappings'] }),
  });
  const delPrice = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/competition/prices/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['competition-prices'] }),
  });
  const clearPrices = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/competition/prices/clear-all', { confirm: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['competition-prices'] }),
  });

  const colDefs: ColDef<MapRow>[] = useMemo(() => {
    const busyDel = delMap.isPending || clearMaps.isPending;
    return [
      { field: 'internal_sku', headerName: 'Our SKU', pinned: 'left' },
      { field: 'competitor_sku', headerName: 'Comp SKU' },
      { field: 'score', headerName: 'Score', type: 'numericColumn' },
      { field: 'approval_status', headerName: 'Status' },
      { field: 'explanation', headerName: 'Why', flex: 1, minWidth: 260 },
      {
        headerName: 'Actions',
        width: 200,
        cellRenderer: (p: { data: MapRow }) => (
          <Box sx={{ display: 'flex', gap: 1, py: 0.5 }}>
            <Button size="small" variant="outlined" onClick={() => approve.mutate(p.data.id)}>
              Approve
            </Button>
          </Box>
        ),
      },
      gridDeleteColumn<MapRow>((id) => void delMap.mutate(id), { busy: busyDel }),
    ];
  }, [delMap, delMap.isPending, clearMaps.isPending]);

  const priceCols: ColDef<PriceRow>[] = useMemo(() => {
    const busyDel = delPrice.isPending || clearPrices.isPending;
    return [
      { field: 'competitor_sku', headerName: 'Comp SKU', pinned: 'left' },
      { field: 'observed_at', headerName: 'Observed' },
      { field: 'price', headerName: 'Price', type: 'numericColumn' },
      { field: 'channel', headerName: 'Channel' },
      gridDeleteColumn<PriceRow>((id) => void delPrice.mutate(id), { busy: busyDel }),
    ];
  }, [delPrice, delPrice.isPending, clearPrices.isPending]);

  const rows = data ?? [];
  const priceRows = prices ?? [];

  return (
    <>
      <PageHeader crumbs={[{ label: 'Competition' }]} title="Competitor mapping" />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Mappings" />
        <Tab label="Competitor prices" />
      </Tabs>
      <Paper sx={{ p: 2 }}>
        {tab === 0 ? (
          <ModuleDataSection
            intro={
              <>
                Competitor mappings are scored matches between your catalog and competitor SKUs, with human approval.
                Rows come from the API when competition facts exist.
              </>
            }
            introWhen="always"
            isLoading={isLoading}
            isError={isError}
            error={toQueryError(error)}
            onRetry={() => void refetch()}
            isEmpty={rows.length === 0}
            empty={{
              title: 'No competitor mappings',
              description: 'Mappings appear when competition facts exist. Use Data imports when a competitor feed is wired.',
              primary: { label: 'Data imports', href: '/admin/imports' },
              secondary: { label: 'Overview', href: '/dashboard' },
            }}
            toolbar={
              <ModuleGridToolbar
                onRefresh={() => qc.invalidateQueries({ queryKey: ['competition-mappings'] })}
                onClearAll={() => {
                  if (!window.confirm('Delete every competitor mapping row? This cannot be undone.')) return;
                  void clearMaps.mutate();
                }}
                importsHref="/admin/imports"
                busy={approve.isPending || delMap.isPending || clearMaps.isPending}
              />
            }
          >
            <EnterpriseDataGrid rowData={rows} columnDefs={colDefs} height={520} />
          </ModuleDataSection>
        ) : (
          <ModuleDataSection
            intro="Observed competitor price points from fact_competitor_price."
            introWhen="always"
            isLoading={pricesLoading}
            isError={pricesIsError}
            error={toQueryError(pricesErr)}
            onRetry={() => void refetchPrices()}
            isEmpty={priceRows.length === 0}
            empty={{
              title: 'No competitor prices',
              description: 'Load competitor price feeds via Data imports when available.',
              primary: { label: 'Data imports', href: '/admin/imports' },
            }}
            toolbar={
              <ModuleGridToolbar
                onRefresh={() => qc.invalidateQueries({ queryKey: ['competition-prices'] })}
                onClearAll={() => {
                  if (!window.confirm('Delete every competitor price row? This cannot be undone.')) return;
                  void clearPrices.mutate();
                }}
                clearAllLabel="Clear all price rows"
                importsHref="/admin/imports"
                busy={delPrice.isPending || clearPrices.isPending}
              />
            }
          >
            <EnterpriseDataGrid rowData={priceRows} columnDefs={priceCols} height={520} />
          </ModuleDataSection>
        )}
      </Paper>
    </>
  );
}
