'use client';

import { Paper } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PlanningChrome } from '@/features/planning/PlanningChrome';
import { FactColumnPicker, FactColumnsButton } from '@/features/workbench-ui/FactColumnPicker';
import { ScopeBar } from '@/features/workbench-ui/controls';
import { useFactGridChrome } from '@/features/workbench-ui/gridFind';
import { useFactColumns } from '@/features/workbench-ui/useFactColumns';
import { apiDelete, apiGet, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type Row = {
  id: number;
  sku: string | null;
  sales_model_name: string | null;
  lifecycle_phase: string;
  whitespace_flag: boolean;
  overlap_flag: boolean;
  launch_target: string | null;
};

const LINE_IDENTITY = { sku: 'sku', salesModel: 'sales_model_name' } as const;
const PINNED_LEFT: Partial<ColDef<Row>> = { pinned: 'left' };

export default function RoadmapPage() {
  const qc = useQueryClient();
  const factColumns = useFactColumns<Row>('roadmap', { lineIdentifier: LINE_IDENTITY, lineIdentifierColDef: PINNED_LEFT });
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['roadmap'],
    queryFn: ({ signal }) => apiGet<Row[]>('/api/v1/roadmap', { signal }),
  });

  const delRow = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/roadmap/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['roadmap'] }),
  });
  const clearAll = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/roadmap/clear-all', { confirm: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['roadmap'] }),
  });

  const colDefs: ColDef<Row>[] = useMemo(() => {
    const busyDel = delRow.isPending || clearAll.isPending;
    return [
      ...factColumns.identityColDefs,
      { field: 'lifecycle_phase', headerName: 'Phase' },
      { field: 'whitespace_flag', headerName: 'Whitespace' },
      { field: 'overlap_flag', headerName: 'Overlap' },
      { field: 'launch_target', headerName: 'Launch target' },
      ...factColumns.optionalColDefs,
      gridDeleteColumn<Row>((id) => void delRow.mutate(id), { busy: busyDel }),
    ];
  }, [delRow, delRow.isPending, clearAll.isPending, factColumns.identityColDefs, factColumns.optionalColDefs]);

  const rows = data ?? [];
  const gridChrome = useFactGridChrome('roadmap', { exportDisabled: rows.length === 0 });

  return (
    <PlanningChrome>
      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          intro={
            <>
              Portfolio roadmap rows describe lifecycle, launch targets, and whitespace/overlap flags per SKU. For{' '}
              <strong>customer/channel lineup</strong> (assortment and volumes), use{' '}
              <strong>Lineup cases</strong> in the nav—that is a separate module.
            </>
          }
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={rows.length === 0}
          empty={{
            title: 'No roadmap rows',
            description: 'Roadmap facts load when product strategy data is available through your ingestion pipelines.',
            primary: { label: 'Import Center', href: '/admin/imports' },
            secondary: { label: 'Lineup cases', href: '/lineup/cases' },
          }}
          toolbar={
            <>
            <ScopeBar
              chips={[]}
              savedViews={gridChrome.viewNames}
              savedView={gridChrome.active}
              onSavedView={gridChrome.selectView}
              filters={gridChrome.filters}
              trailing={
                <>
                <FactColumnsButton
                  gridId="roadmap"
                  onClick={factColumns.openPicker}
                  count={factColumns.optionalFields.length}
                />
                {gridChrome.trailing}
                </>
              }
            />
            <ModuleGridToolbar
              onRefresh={() => qc.invalidateQueries({ queryKey: ['roadmap'] })}
              onClearAll={() => {
                if (!window.confirm('Delete every roadmap row? This cannot be undone.')) return;
                void clearAll.mutate();
              }}
              importsHref="/admin/imports"
              busy={delRow.isPending || clearAll.isPending}
            />
            </>
          }
        >
          <EnterpriseDataGrid ref={gridChrome.gridRef} quickFilterText={gridChrome.query} rowData={rows} columnDefs={colDefs} />
        </ModuleDataSection>
      </Paper>
      <FactColumnPicker {...factColumns.pickerProps} />
    </PlanningChrome>
  );
}
