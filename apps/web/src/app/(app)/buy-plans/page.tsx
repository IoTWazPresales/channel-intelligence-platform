'use client';

import { Alert, Box, Paper, Stack, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { navPageChrome } from '@/features/shell/navPageChrome';
import { apiDelete, apiGet, apiPost, HttpConflictError } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';
import { useUiStore } from '@/stores/uiStore';

type Row = {
  id: number;
  sku: string | null;
  recommended_qty: number;
  window_start: string;
  window_end: string;
  rationale: string;
  risk_if_not_ordered: string | null;
};

export default function BuyPlansPage() {
  const qc = useQueryClient();
  const openDrawer = useUiStore((s) => s.openDrawer);
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['buy-plans'],
    queryFn: ({ signal }) => apiGet<Row[]>('/api/v1/buy-plans', { signal }),
  });

  const delRow = useMutation({
    mutationFn: async (id: number) => {
      try {
        await apiDelete(`/api/v1/buy-plans/id/${id}`);
      } catch (err) {
        if (HttpConflictError.is(err)) throw err;
        const msg = err instanceof Error ? err.message : String(err);
        if (/referenced|constraint|409\b/i.test(msg)) {
          try {
            const data = await apiGet<{ references?: { label: string; count?: number | string }[] }>(
              `/api/v1/buy-plans/references?plan_id=${encodeURIComponent(id)}`
            );
            const refs = (data.references ?? [])
              .map((r) => {
                const n =
                  typeof r.count === 'number' ? r.count : typeof r.count === 'string' ? Number(r.count) : NaN;
                if (!Number.isFinite(n) || typeof r.label !== 'string') return null;
                return { label: r.label, count: n };
              })
              .filter((r): r is { label: string; count: number } => r !== null);
            if (refs.length) {
              throw new HttpConflictError(
                'Buy plan could not be deleted; dependent rows are still blocking it.',
                refs
              );
            }
          } catch (enriched) {
            if (HttpConflictError.is(enriched)) throw enriched;
          }
        }
        throw err;
      }
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['buy-plans'] });
      void qc.invalidateQueries({ queryKey: ['lineup-items'] });
    },
  });
  const clearAll = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/buy-plans/clear-all', { confirm: true }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['buy-plans'] });
      void qc.invalidateQueries({ queryKey: ['lineup-items'] });
    },
  });

  const colDefs: ColDef<Row>[] = useMemo(() => {
    const busyDel = delRow.isPending || clearAll.isPending;
    return [
      { field: 'sku', headerName: 'SKU', pinned: 'left' },
      { field: 'recommended_qty', headerName: 'Buy qty', type: 'numericColumn' },
      { field: 'window_start', headerName: 'Window start' },
      { field: 'window_end', headerName: 'Window end' },
      {
        headerName: 'Rationale',
        flex: 1,
        minWidth: 200,
        valueGetter: (p) => p.data?.rationale,
        onCellClicked: (e) => {
          if (e.data) openDrawer('Buy rationale', e.data.rationale);
        },
      },
      gridDeleteColumn<Row>((id) => void delRow.mutate(id), { busy: busyDel }),
    ];
  }, [delRow, delRow.isPending, clearAll.isPending]);

  const rows = data ?? [];
  const busy = delRow.isPending || clearAll.isPending;

  return (
    <>
      <PageHeader {...navPageChrome('/lineup')} />
      {(delRow.isError || clearAll.isError) && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          onClose={() => {
            delRow.reset();
            clearAll.reset();
          }}
        >
          {delRow.isError && HttpConflictError.is(delRow.error) ? (
            <Stack spacing={1}>
              <Typography variant="body2">{delRow.error.message}</Typography>
              <Typography variant="subtitle2" component="div">
                Still referenced in:
              </Typography>
              <Box component="ul" sx={{ m: 0, pl: 2 }}>
                {delRow.error.references.map((r) => (
                  <Typography key={r.label} component="li" variant="body2">
                    {r.label} ({r.count})
                  </Typography>
                ))}
              </Box>
            </Stack>
          ) : delRow.isError ? (
            <Typography variant="body2">{(delRow.error as Error).message}</Typography>
          ) : clearAll.isError ? (
            <Typography variant="body2">{(clearAll.error as Error).message}</Typography>
          ) : null}
        </Alert>
      )}
      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          intro={
            <>
              Buy plans are generated from inventory and forecast signals in the backend. Click <strong>Rationale</strong>{' '}
              to read the full text in the side panel. Populate upstream facts (inventory, forecasts), then refresh.
              Deleting a plan clears nullable cross-links from lineup and buy-recommendation rows so you are not stuck
              behind a silent 409.
            </>
          }
          introWhen="always"
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={rows.length === 0}
          empty={{
            title: 'No buy plans yet',
            description:
              'The planning engine writes recommendations when underlying facts exist. Add inventory and forecast rows (or use Import Center), then refresh.',
            primary: { label: 'Cover', href: '/stock?lens=cover' },
            secondary: { label: 'Forecast', href: '/forecasts' },
          }}
          toolbar={
            <ModuleGridToolbar
              onRefresh={() => qc.invalidateQueries({ queryKey: ['buy-plans'] })}
              onClearAll={() => {
                if (!window.confirm('Delete every buy plan row? This cannot be undone.')) return;
                void clearAll.mutate();
              }}
              importsHref="/admin/imports"
              busy={busy}
            />
          }
        >
          <EnterpriseDataGrid rowData={rows} columnDefs={colDefs} />
        </ModuleDataSection>
      </Paper>
    </>
  );
}
