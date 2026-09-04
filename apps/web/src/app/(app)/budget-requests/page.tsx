'use client';

import { Paper } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { apiDelete, apiGet, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type Row = {
  id: number;
  owner: string | null;
  amount: number;
  initiative_type: string;
  status: string;
  justification_summary: string;
  expected_impact: string | null;
  risk_of_not_funding: string | null;
};

export default function BudgetRequestsPage() {
  const qc = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['budget-requests'],
    queryFn: ({ signal }) => apiGet<Row[]>('/api/v1/budgets/requests', { signal }),
  });

  const delRow = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/budgets/requests/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budget-requests'] }),
  });
  const clearAll = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/budgets/requests/clear-all', { confirm: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budget-requests'] }),
  });

  const colDefs: ColDef<Row>[] = useMemo(() => {
    const busyDel = delRow.isPending || clearAll.isPending;
    return [
      { field: 'owner', headerName: 'Owner' },
      { field: 'amount', headerName: 'Amount', type: 'numericColumn' },
      { field: 'initiative_type', headerName: 'Initiative' },
      { field: 'status', headerName: 'Status' },
      { field: 'justification_summary', headerName: 'Summary', flex: 1, minWidth: 220 },
      gridDeleteColumn<Row>((id) => void delRow.mutate(id), { busy: busyDel }),
    ];
  }, [delRow, delRow.isPending, clearAll.isPending]);

  const rows = data ?? [];

  return (
    <>
      <PageHeader crumbs={[{ label: 'Budget requests' }]} title="Justification workflow" />
      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          intro={
            <>
              Budget requests link commercial initiatives (promos, products, roadmap) to finance justification. Data
              comes from <strong>fact_budget_request</strong> via the API—populate through imports or future submission
              flows.
            </>
          }
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={rows.length === 0}
          empty={{
            title: 'No budget requests',
            description: 'Submit flows are not fully built in the UI yet; use Import Center when a pipeline exists.',
            primary: { label: 'Import Center', href: '/admin/imports' },
            secondary: { label: 'Budgets', href: '/budgets' },
          }}
          toolbar={
            <ModuleGridToolbar
              onRefresh={() => qc.invalidateQueries({ queryKey: ['budget-requests'] })}
              onClearAll={() => {
                if (!window.confirm('Delete every budget request row? This cannot be undone.')) return;
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
