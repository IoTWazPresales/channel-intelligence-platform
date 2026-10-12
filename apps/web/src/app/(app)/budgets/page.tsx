'use client';

import type { ColDef } from 'ag-grid-community';
import { Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { FundingChrome } from '@/features/promotions-funding/FundingChrome';
import { apiGet } from '@/lib/api';

type PositionRow = {
  product_line: string;
  landed_quarter: string;
  reserved: number;
  committed: number;
  consumed: number;
  released: number;
  paid: number;
  remaining: number;
};

type EntryRow = {
  id: number;
  entry_type: string;
  product_line: string;
  landed_quarter: string;
  amount_usd: number | null;
  case_id: number | null;
  source_tag: string | null;
  created_at: string | null;
};

export default function BudgetsPage() {
  const [picked, setPicked] = useState<PositionRow | null>(null);
  const position = useQuery({
    queryKey: ['budgets', 'ledger'],
    queryFn: ({ signal }) => apiGet<{ data_unavailable: boolean; items: PositionRow[] }>('/api/v1/budgets/ledger', { signal }),
  });
  const entries = useQuery({
    queryKey: ['budgets', 'entries', picked?.product_line, picked?.landed_quarter],
    enabled: picked != null,
    queryFn: ({ signal }) =>
      apiGet<{ items: EntryRow[] }>(
        `/api/v1/budgets/ledger/entries?product_line=${encodeURIComponent(picked?.product_line ?? '')}&landed_quarter=${encodeURIComponent(picked?.landed_quarter ?? '')}`,
        { signal },
      ),
  });
  const positionCols = useMemo<ColDef<PositionRow>[]>(
    () => [
      { field: 'product_line', headerName: 'Product line', flex: 1 },
      { field: 'landed_quarter', headerName: 'Quarter', width: 120 },
      { field: 'reserved', headerName: 'Reserved', width: 120 },
      { field: 'committed', headerName: 'Committed', width: 130 },
      { field: 'consumed', headerName: 'Consumed', width: 130 },
      { field: 'released', headerName: 'Released', width: 120 },
      { field: 'paid', headerName: 'Paid', width: 110 },
      { field: 'remaining', headerName: 'Remaining', width: 130 },
    ],
    [],
  );
  const entryCols = useMemo<ColDef<EntryRow>[]>(
    () => [
      { field: 'created_at', headerName: 'When', flex: 1 },
      { field: 'entry_type', headerName: 'Type', width: 140 },
      { field: 'amount_usd', headerName: 'USD', width: 120 },
      { field: 'case_id', headerName: 'Case', width: 100 },
      { field: 'source_tag', headerName: 'Source', width: 160 },
    ],
    [],
  );
  const rows = position.data?.items ?? [];

  return (
    <FundingChrome>
      <Stack spacing={2} sx={{ mt: 2 }}>
        <Typography variant="body2" color="text.secondary">
          Product line by quarter. Amounts are sums of ledger rows. A correction is a reversing row. Caps flag and do not block.
        </Typography>
        <ModuleDataSection
          isLoading={position.isLoading}
          isError={position.isError || position.data?.data_unavailable === true}
          error={position.isError || position.data?.data_unavailable ? new Error('Budget ledger is not available.') : null}
          isEmpty={!position.isLoading && rows.length === 0}
          empty={{ title: 'No budget entries', description: 'Approved lineup reserves and settled cases will appear here.' }}
        >
          <EnterpriseDataGrid<PositionRow>
            rowData={rows}
            columnDefs={positionCols}
            height={360}
            gridOptions={{ onRowClicked: (event) => setPicked(event.data ?? null) }}
          />
        </ModuleDataSection>
        {picked ? (
          <Stack spacing={1}>
            <Typography variant="subtitle2">
              {picked.product_line || 'No product line'} · {picked.landed_quarter || 'No quarter'}
            </Typography>
            <EnterpriseDataGrid<EntryRow>
              rowData={entries.data?.items ?? []}
              columnDefs={entryCols}
              height={280}
            />
          </Stack>
        ) : null}
      </Stack>
    </FundingChrome>
  );
}
