'use client';

import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import { Alert, Autocomplete, Box, Paper, Stack, TextField } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { useLineIdentifierPreference } from '@/features/tenant/useLineIdentifierPreference';
import { FactColumnPicker, FactColumnsButton } from '@/features/workbench-ui/FactColumnPicker';
import { useFactColumns } from '@/features/workbench-ui/useFactColumns';
import { apiGet } from '@/lib/api';

import { depthAtLeast, type IntelDepth } from './intelDepth';

type DistHit = { id: number; distributor_code: string; distributor_name: string };

type InvRow = {
  distributor_id: number;
  distributor_name: string | null;
  distributor_code?: string | null;
  product_id: number;
  sku: string | null;
  sales_model_name: string | null;
  product_name: string | null;
  snapshot_date?: string | null;
  reported_soh: number;
  sell_out_since?: number;
  landed_since?: number;
  derived_stock?: number;
  calculated_soh: number | null;
  variance_units: number | null;
  variance_pct: number | null;
  reconciliation_status: string | null;
  velocity_52wk: number | null;
  weeks_of_cover: number | null;
  computed_through_date: string | null;
  replenishment_flag?: boolean;
  replenishment_threshold_weeks?: number;
  reorder_signal: boolean;
  demand_forecast_units_13w?: number | null;
};

export function ChannelOpsInventoryTab({ depth }: { depth: IntelDepth }) {
  const [distributorPick, setDistributorPick] = useState<DistHit | null>(null);
  const lineId = useLineIdentifierPreference();
  const factColumns = useFactColumns<InvRow>('channel-ops.inventory');

  const { data: filterOptions } = useQuery({
    queryKey: ['sellout-filter-options'],
    queryFn: ({ signal }) =>
      apiGet<{ distributors: DistHit[] }>('/api/v1/sellout/filter-options', { signal }),
  });

  const distId = distributorPick?.id;
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['channel-ops-inventory', distId],
    queryFn: ({ signal }) =>
      apiGet<{ items: InvRow[] }>(`/api/v1/channel-ops/inventory?distributor_id=${distId}`, { signal }),
    enabled: distId != null,
  });

  const operational = depthAtLeast(depth, 'operational');
  const strategic = depthAtLeast(depth, 'strategic');
  const invCols = useMemo<ColDef<InvRow>[]>(() => {
    const cols: ColDef<InvRow>[] = [
      { field: 'product_name', headerName: 'Product', flex: 1, minWidth: 160 },
      {
        colId: 'line_identifier',
        headerName: lineId.header,
        minWidth: 120,
        valueGetter: (p) => lineId.value(p.data?.sku, p.data?.sales_model_name),
      },
      {
        field: 'reported_soh',
        headerName: 'Reported SOH',
        type: 'numericColumn',
        minWidth: 120,
        valueFormatter: (p) => (p.value != null ? Number(p.value).toLocaleString() : '—'),
      },
      {
        headerName: 'Derived stock',
        type: 'numericColumn',
        minWidth: 120,
        valueGetter: (p) => p.data?.derived_stock ?? p.data?.reported_soh,
        valueFormatter: (p) => (p.value != null ? Number(p.value).toLocaleString() : '—'),
      },
    ];
    if (operational) {
      cols.push(
        {
          field: 'calculated_soh',
          headerName: 'Calculated SOH',
          type: 'numericColumn',
          minWidth: 130,
          valueFormatter: (p) => (p.value != null ? Number(p.value).toLocaleString() : '—'),
        },
        {
          field: 'variance_units',
          headerName: 'Variance',
          type: 'numericColumn',
          minWidth: 110,
          valueFormatter: (p) => (p.value != null ? Number(p.value).toLocaleString() : '—'),
        },
        { field: 'reconciliation_status', headerName: 'Recon status', minWidth: 130, valueFormatter: (p) => p.value ?? '—' },
      );
    }
    if (strategic) {
      cols.push(
        {
          field: 'velocity_52wk',
          headerName: 'Velocity 52wk',
          type: 'numericColumn',
          minWidth: 120,
          valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(2) : '—'),
        },
        {
          field: 'weeks_of_cover',
          headerName: 'Weeks of cover',
          type: 'numericColumn',
          minWidth: 130,
          valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(1) : 'n/a'),
        },
        {
          field: 'demand_forecast_units_13w',
          headerName: 'Demand fcst 13w',
          type: 'numericColumn',
          minWidth: 140,
          cellRenderer: (p: { data?: InvRow }) => (
            <span data-testid="channel-ops-demand-forecast">
              {p.data?.demand_forecast_units_13w != null
                ? p.data.demand_forecast_units_13w.toLocaleString(undefined, { maximumFractionDigits: 2 })
                : '—'}
            </span>
          ),
        },
        {
          headerName: 'Replenish',
          minWidth: 100,
          sortable: false,
          filter: false,
          cellRenderer: (p: { data?: InvRow }) =>
            p.data?.replenishment_flag || p.data?.reorder_signal ? (
              <WarningAmberIcon
                color="warning"
                fontSize="small"
                titleAccess={`Below ${p.data.replenishment_threshold_weeks ?? 4}w cover — replenishment flag`}
                data-testid="channel-ops-replenish-row"
              />
            ) : (
              '—'
            ),
        },
      );
    }
    // Depth already shows some registry fields as default cells; do not add them twice.
    const shown = new Set(cols.map((c) => c.field).filter(Boolean));
    return [...cols, ...factColumns.optionalColDefs.filter((c) => !shown.has(c.field))];
  }, [operational, strategic, lineId, factColumns.optionalColDefs]);

  return (
    <Box>
      <Stack direction="row" spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <Autocomplete
          sx={{ minWidth: 320 }}
          size="small"
          options={filterOptions?.distributors ?? []}
          value={distributorPick}
          onChange={(_e, v) => setDistributorPick(v)}
          getOptionLabel={(o) => `${o.distributor_name} (${o.distributor_code})`}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={(params) => <TextField {...params} label="Distributor" required />}
        />
      </Stack>
      {distId == null ? (
        <Alert severity="info">
          Select a distributor to view inventory intelligence for that channel.
        </Alert>
      ) : (
        <>
          <Paper variant="outlined">
            <Box sx={{ p: 2 }}>
              <ModuleDataSection
                isLoading={isLoading}
                isError={isError}
                error={isError ? new Error((error as Error)?.message ?? 'Failed to load inventory.') : null}
                onRetry={() => void refetch()}
                toolbar={
                  <Stack direction="row" sx={{ mb: 1 }}>
                    <FactColumnsButton
                      gridId="channel-ops.inventory"
                      onClick={factColumns.openPicker}
                      count={factColumns.optionalFields.length}
                    />
                  </Stack>
                }
                isEmpty={(data?.items ?? []).length === 0}
                empty={{
                  title: 'No distributor inventory rows for this selection',
                  description: 'Distributor stock rows appear here once a DSI import has been applied.',
                  primary: { label: 'Import Center', href: '/admin/imports?template=distributor_inventory' },
                }}
              >
                <EnterpriseDataGrid rowData={data?.items ?? []} columnDefs={invCols} height={480} />
              </ModuleDataSection>
            </Box>
          </Paper>
        </>
      )}
      <FactColumnPicker {...factColumns.pickerProps} />
    </Box>
  );
}
