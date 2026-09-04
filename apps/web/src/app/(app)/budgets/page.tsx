'use client';

import { Paper, Stack, Tab, Tabs, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import type { ColDef } from 'ag-grid-community';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { FundingChrome } from '@/features/promotions-funding/FundingChrome';
import { CapabilityStatus } from '@/features/shell/CapabilityStatus';
import { Panel } from '@/features/workbench-ui/Panel';
import { apiDelete, apiGet, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type Alloc = { id: number; owner: string | null; category: string; allocated_amount: number; period_start: string };
type Health = { id: number; owner: string | null; remaining_amount: number; pressure_state: string };

export default function BudgetsPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState(0);
  const {
    data: allocs,
    isLoading: allocsLoading,
    isError: allocsError,
    error: allocsErr,
    refetch: refetchAllocs,
  } = useQuery({
    queryKey: ['budget-allocations'],
    queryFn: ({ signal }) => apiGet<Alloc[]>('/api/v1/budgets/allocations', { signal }),
  });
  const {
    data: health,
    isLoading: healthLoading,
    isError: healthIsError,
    error: healthErr,
    refetch: refetchHealth,
  } = useQuery({
    queryKey: ['budget-health'],
    queryFn: ({ signal }) => apiGet<Health[]>('/api/v1/budgets/health', { signal }),
  });

  const delAlloc = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/budgets/allocations/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budget-allocations'] }),
  });
  const clearAllocs = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/budgets/allocations/clear-all', { confirm: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budget-allocations'] }),
  });
  const delHealth = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/budgets/health/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budget-health'] }),
  });
  const clearHealth = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/budgets/health/clear-all', { confirm: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budget-health'] }),
  });

  const aCols: ColDef<Alloc>[] = useMemo(() => {
    const busyDel = delAlloc.isPending || clearAllocs.isPending;
    return [
      { field: 'owner', headerName: 'Owner' },
      { field: 'category', headerName: 'Category' },
      { field: 'allocated_amount', headerName: 'Allocated', type: 'numericColumn' },
      { field: 'period_start', headerName: 'Period' },
      gridDeleteColumn<Alloc>((id) => void delAlloc.mutate(id), { busy: busyDel }),
    ];
  }, [delAlloc, delAlloc.isPending, clearAllocs.isPending]);

  const hCols: ColDef<Health>[] = useMemo(() => {
    const busyDel = delHealth.isPending || clearHealth.isPending;
    return [
      { field: 'owner', headerName: 'Owner' },
      { field: 'remaining_amount', headerName: 'Remaining', type: 'numericColumn' },
      { field: 'pressure_state', headerName: 'Pressure' },
      gridDeleteColumn<Health>((id) => void delHealth.mutate(id), { busy: busyDel }),
    ];
  }, [delHealth, delHealth.isPending, clearHealth.isPending]);

  const allocRows = allocs ?? [];
  const healthRows = health ?? [];

  return (
    <>
      <FundingChrome />
      <Panel
        title={
          <Stack direction="row" spacing={1} alignItems="center">
            <span>Budget ledger — data only</span>
            <CapabilityStatus status="substrate" />
          </Stack>
        }
      >
        <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 760, mb: 1 }}>
          Allocation → commitment → actual tables exist with no writer and typically no rows. The planner’s
          budget check uses the lineup-derived profit reservation instead, and says so on the figure.
        </Typography>
      </Panel>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1, maxWidth: 900 }}>
        Allocations show planned envelopes by owner/category; Health summarizes remaining budget pressure. Both read
        from curated finance facts—use Import Center or internal finance feeds when available.
      </Typography>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Allocations" />
        <Tab label="Health" />
      </Tabs>
      <Paper sx={{ p: 2 }}>
        {tab === 0 ? (
          <ModuleDataSection
            intro="Allocation rows are empty until fact_budget_allocation exists for your owners and periods."
            isLoading={allocsLoading}
            isError={allocsError}
            error={toQueryError(allocsErr)}
            onRetry={() => void refetchAllocs()}
            isEmpty={allocRows.length === 0}
            empty={{
              title: 'No allocations',
              description: 'Connect finance pipelines or use Import Center when a source exists for allocations.',
              primary: { label: 'Import Center', href: '/admin/imports' },
              secondary: { label: 'Budget requests', href: '/budget-requests' },
            }}
            toolbar={
              <ModuleGridToolbar
                onRefresh={() => qc.invalidateQueries({ queryKey: ['budget-allocations'] })}
                onClearAll={() => {
                  if (!window.confirm('Delete every budget allocation row? This cannot be undone.')) return;
                  void clearAllocs.mutate();
                }}
                importsHref="/admin/imports"
                busy={delAlloc.isPending || clearAllocs.isPending}
              />
            }
          >
            <EnterpriseDataGrid rowData={allocRows} columnDefs={aCols} />
          </ModuleDataSection>
        ) : (
          <ModuleDataSection
            intro="Health rows summarize remaining envelope vs pressure state per owner."
            isLoading={healthLoading}
            isError={healthIsError}
            error={toQueryError(healthErr)}
            onRetry={() => void refetchHealth()}
            isEmpty={healthRows.length === 0}
            empty={{
              title: 'No budget health rows',
              description: 'Health is derived when allocations and actuals exist in the database.',
              primary: { label: 'Import Center', href: '/admin/imports' },
              secondary: { label: 'Attention', href: '/brief' },
            }}
            toolbar={
              <ModuleGridToolbar
                onRefresh={() => qc.invalidateQueries({ queryKey: ['budget-health'] })}
                onClearAll={() => {
                  if (!window.confirm('Delete every budget health row? This cannot be undone.')) return;
                  void clearHealth.mutate();
                }}
                clearAllLabel="Clear all health rows"
                importsHref="/admin/imports"
                busy={delHealth.isPending || clearHealth.isPending}
              />
            }
          >
            <EnterpriseDataGrid rowData={healthRows} columnDefs={hCols} />
          </ModuleDataSection>
        )}
      </Paper>
    </>
  );
}
