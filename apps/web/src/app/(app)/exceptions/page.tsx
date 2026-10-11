'use client';

import { Chip, Paper } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { StewardWriteNotice } from '@/components/StewardWriteGate';
import { navPageChrome } from '@/features/shell/navPageChrome';
import { useStewardWriteAccess } from '@/features/shell/stewardAccess';
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
  // N-0086: deleting or clearing inbox rows needs steward or admin (the API refuses other roles).
  const stewardAccess = useStewardWriteAccess();
  const canDelete = stewardAccess.allowed;
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
      ...(canDelete ? [gridDeleteColumn<Row>((id) => void delRow.mutate(id), { busy: busyDel })] : []),
    ];
  }, [canDelete, delRow, delRow.isPending, clearAll.isPending, openDrawer]);

  const rows = data ?? [];

  return (
    <>
      <PageHeader {...navPageChrome('/brief')} />
      <Paper sx={{ p: 2 }}>
        <StewardWriteNotice
          access={stewardAccess}
          extra="On this inbox that means Delete and Clear all rows are hidden; Why still opens the detail."
        />
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
            primary: { label: 'Import Center', href: '/admin/imports' },
            secondary: { label: 'Attention', href: '/brief' },
          }}
          toolbar={
            <ModuleGridToolbar
              onRefresh={() => qc.invalidateQueries({ queryKey: ['exceptions'] })}
              onClearAll={
                canDelete
                  ? () => {
                      if (!window.confirm('Delete every exception inbox row? This cannot be undone.')) return;
                      void clearAll.mutate();
                    }
                  : undefined
              }
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
