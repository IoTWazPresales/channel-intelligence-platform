'use client';

import { Chip, Paper } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { apiDelete, apiGet, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';
import { useUiStore } from '@/stores/uiStore';
import type { ColDef } from 'ag-grid-community';

type Row = {
  id: number;
  exception_type: string;
  severity: string;
  title: string;
  explanation_summary: string | null;
  status: string;
};

export default function ExceptionsPage() {
  const qc = useQueryClient();
  const openDrawer = useUiStore((s) => s.openDrawer);
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['exceptions'],
    queryFn: ({ signal }) => apiGet<Row[]>('/api/v1/exceptions', { signal }),
  });

  const delRow = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/exceptions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exceptions'] }),
  });
  const clearAll = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/exceptions/clear-all', { confirm: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exceptions'] }),
  });

  const colDefs: ColDef<Row>[] = useMemo(() => {
    const busyDel = delRow.isPending || clearAll.isPending;
    return [
      { field: 'exception_type', headerName: 'Type', minWidth: 160 },
      { field: 'severity', headerName: 'Severity', minWidth: 110 },
      { field: 'title', headerName: 'Title', flex: 1, minWidth: 220 },
      { field: 'status', headerName: 'Status', minWidth: 100 },
      {
        headerName: '',
        width: 90,
        cellRenderer: (p: { data: Row }) => (
          <Chip
            size="small"
            label="Why"
            onClick={() => openDrawer(p.data.title, p.data.explanation_summary || 'No explanation captured.')}
          />
        ),
      },
      gridDeleteColumn<Row>((id) => void delRow.mutate(id), { busy: busyDel }),
    ];
  }, [delRow, delRow.isPending, clearAll.isPending]);

  const rows = data ?? [];

  return (
    <>
      <PageHeader crumbs={[{ label: 'Exceptions' }]} title="Exceptions inbox" />
      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          intro={
            <>
              Each row is an actionable exception with explainable context. Use <strong>Why</strong> to open the detail
              drawer. Items are created by planning and validation services when upstream facts trigger them.
            </>
          }
          introWhen="always"
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={rows.length === 0}
          empty={{
            title: 'No open exceptions',
            description:
              'Nothing is flagged yet, or the database has no derived exception rows. Load upstream facts (inventory, inbound, mappings) and refresh.',
            primary: { label: 'Data imports', href: '/admin/imports' },
            secondary: { label: 'Overview', href: '/dashboard' },
          }}
          toolbar={
            <ModuleGridToolbar
              onRefresh={() => qc.invalidateQueries({ queryKey: ['exceptions'] })}
              onClearAll={() => {
                if (!window.confirm('Delete every exception inbox row? This cannot be undone.')) return;
                void clearAll.mutate();
              }}
              importsHref="/admin/imports"
              busy={delRow.isPending || clearAll.isPending}
            />
          }
        >
          <EnterpriseDataGrid rowData={rows} columnDefs={colDefs} height={520} />
        </ModuleDataSection>
      </Paper>
    </>
  );
}
