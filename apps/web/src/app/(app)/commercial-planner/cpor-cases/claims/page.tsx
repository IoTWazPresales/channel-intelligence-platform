'use client';

import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import type { ColDef, RowClickedEvent } from 'ag-grid-community';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { fmtCompact, fmtInt } from '@/features/promotions-funding/format';
import { FundingChrome } from '@/features/promotions-funding/FundingChrome';
import { STAGE_LABEL, stageTone, type PlanStage } from '@/features/promotions-funding/lifecycle';
import type { CporCaseListRow, CporCasesPage } from '@/features/promotions-funding/types';
import { apiGet } from '@/lib/api';
import { StatusChip } from '@/features/workbench-ui/controls';

export default function CporClaimsPage() {
  const router = useRouter();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['cpor', 'cases', 'claims'],
    queryFn: ({ signal }) => apiGet<CporCasesPage>('/api/v1/cpor/cases?page=1&page_size=200', { signal }),
  });

  const rows = useMemo(() => {
    const items = data?.items ?? [];
    return items.filter((r) => ['ended', 'settled', 'active'].includes(r.status));
  }, [data]);

  const columnDefs = useMemo<ColDef<CporCaseListRow>[]>(
    () => [
      { field: 'case_code', headerName: 'Case', width: 130, pinned: 'left' },
      { field: 'customer_name', headerName: 'Customer', minWidth: 160, flex: 1 },
      {
        field: 'status',
        headerName: 'Stage',
        width: 120,
        cellRenderer: (p: { data?: CporCaseListRow }) =>
          p.data ? (
            <StatusChip label={STAGE_LABEL[p.data.status as PlanStage] ?? p.data.status} tone={stageTone(p.data.status)} />
          ) : null,
      },
      {
        colId: 'claims',
        headerName: 'Claim rows',
        type: 'rightAligned',
        width: 120,
        valueGetter: (p) => p.data?.settle_readiness?.claim_evidence_count ?? 0,
        valueFormatter: (p) => fmtInt(p.value as number),
      },
      {
        field: 'ttl_support_zar',
        headerName: 'Support',
        type: 'rightAligned',
        width: 120,
        valueFormatter: (p) => fmtCompact(p.value as number | null, p.data?.currency_code),
      },
      {
        field: 'outstanding_amount',
        headerName: 'Outstanding',
        type: 'rightAligned',
        width: 130,
        valueFormatter: (p) => fmtCompact(p.value as number | null, p.data?.currency_code),
      },
    ],
    [],
  );

  return (
    <Box data-testid="funding-claims">
      <FundingChrome counts={{ claims: rows.length }} />
      <Stack spacing={2} sx={{ mt: 2 }}>
        <Alert severity="info" variant="outlined">
          Claim files are matched per case. Apply still happens on the settlement desk — this lens lists
          cases in the settlement half of the same lifecycle so you can see who is waiting on evidence.
        </Alert>
        <ModuleDataSection
          isLoading={isLoading}
          isError={isError}
          error={error as Error | null}
          onRetry={() => void refetch()}
          isEmpty={rows.length === 0}
          empty={{
            title: 'No cases in the settlement half yet',
            description:
              'Claim evidence is imported on a case (Settlement tab) or via Import Center (cpor_claim_evidence). Nothing is invented here.',
            primary: { label: 'Open Import Center', href: '/admin/imports' },
            secondary: { label: 'Case book', href: '/commercial-planner/cpor-cases' },
          }}
        >
          <EnterpriseDataGrid<CporCaseListRow>
            rowData={rows}
            columnDefs={columnDefs}
            height={420}
            gridOptions={{
              getRowId: (p) => String(p.data.id),
              onRowClicked: (e: RowClickedEvent<CporCaseListRow>) =>
                e.data && router.push(`/commercial-planner/cpor-cases/${e.data.id}`),
            }}
          />
        </ModuleDataSection>
        <Typography variant="caption" color="text.secondary">
          Out-of-window and unresolved product tokens are flagged on the case settlement payload — open the
          case to apply a file.
        </Typography>
        <Button size="small" variant="outlined" href="/admin/imports">
          Import Center
        </Button>
      </Stack>
    </Box>
  );
}
