'use client';

import { Box, Button, Paper } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { apiDelete, apiGet, apiPost, apiUrl } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type Row = {
  id: number;
  entity_type: string;
  raw_value: string;
  status: string;
  confidence_score: number | null;
  job_id: number | null;
};

export default function AdminMappingsPage() {
  const qc = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['mapping-queue'],
    queryFn: ({ signal }) => apiGet<Row[]>('/api/v1/mappings/queue', { signal }),
  });

  const approve = useMutation({
    mutationFn: async ({ id, entityId }: { id: number; entityId: number }) => {
      const res = await fetch(apiUrl(`/api/v1/mappings/queue/${id}/approve?entity_id=${entityId}`), {
        method: 'POST',
        headers: { 'X-User-Role': 'data_steward' },
      });
      return res.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['mapping-queue'] }),
  });

  const delRow = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/mappings/queue/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['mapping-queue'] }),
  });
  const clearAll = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/mappings/queue/clear-all', { confirm: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['mapping-queue'] }),
  });

  const colDefs: ColDef<Row>[] = useMemo(() => {
    const busyDel = delRow.isPending || clearAll.isPending;
    return [
      { field: 'entity_type', headerName: 'Entity' },
      { field: 'raw_value', headerName: 'Raw' },
      { field: 'status', headerName: 'Status' },
      { field: 'confidence_score', headerName: 'Confidence' },
      { field: 'job_id', headerName: 'Job' },
      {
        headerName: 'Quick approve (demo)',
        width: 220,
        cellRenderer: (p: { data: Row }) => (
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button size="small" onClick={() => approve.mutate({ id: p.data.id, entityId: 1 })}>
              Map → id 1
            </Button>
          </Box>
        ),
      },
      gridDeleteColumn<Row>((id) => void delRow.mutate(id), { busy: busyDel }),
    ];
  }, [approve, delRow, delRow.isPending, clearAll.isPending]);

  const rows = data ?? [];

  return (
    <>
      <PageHeader crumbs={[{ label: 'Admin' }, { label: 'Mappings' }]} title="Manual mapping queue" />
      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          intro={
            <>
              After an import runs, unresolved entity matches land here for <strong>data stewards</strong>. Approve
              with a known master id (demo button maps to id 1). If this queue is empty, either imports have not
              produced gaps yet or everything auto-mapped—try a new import from{' '}
              <strong>Data & imports</strong>.
            </>
          }
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={rows.length === 0}
          empty={{
            title: 'Mapping queue is empty',
            description:
              'Nothing is waiting for manual resolution. Upload a file that triggers ambiguous SKUs or aliases, then refresh this page.',
            primary: { label: 'Data & imports', href: '/admin/imports' },
            secondary: { label: 'Getting started', href: '/getting-started' },
          }}
          toolbar={
            <ModuleGridToolbar
              onRefresh={() => qc.invalidateQueries({ queryKey: ['mapping-queue'] })}
              onClearAll={() => {
                if (!window.confirm('Delete every mapping queue row? This cannot be undone.')) return;
                void clearAll.mutate();
              }}
              importsHref="/admin/imports"
              busy={approve.isPending || delRow.isPending || clearAll.isPending}
            />
          }
        >
          <EnterpriseDataGrid rowData={rows} columnDefs={colDefs} height={480} />
        </ModuleDataSection>
      </Paper>
    </>
  );
}
