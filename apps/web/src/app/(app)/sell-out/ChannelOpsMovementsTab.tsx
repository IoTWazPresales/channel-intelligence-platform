'use client';

import { Alert, Autocomplete, Box, Paper, Stack, TextField, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { useLineIdentifierPreference } from '@/features/tenant/useLineIdentifierPreference';
import { FactColumnPicker, FactColumnsButton } from '@/features/workbench-ui/FactColumnPicker';
import { factGridLayout, useFactGridChrome } from '@/features/workbench-ui/gridFind';
import { ScopeBar } from '@/features/workbench-ui/controls';
import { useFactColumns } from '@/features/workbench-ui/useFactColumns';
import { apiGet } from '@/lib/api';

import { depthAtLeast, type IntelDepth } from './intelDepth';

type DistHit = { id: number; distributor_code: string; distributor_name: string };

type MovementRow = {
  product_id: number | null;
  sku: string | null;
  sales_model_name: string | null;
  product_name: string | null;
  order_no: string | null;
  delivery_no: string | null;
  ship_date: string | null;
  units_shipped: number | null;
  line_state: string;
  distributor_name: string | null;
  distributor_code?: string | null;
};

type ProductTotal = {
  productId: number;
  sku: string;
  sales_model_name: string;
  name: string;
  inbound: number;
};

const LINE_IDENTITY = { sku: 'sku', salesModel: 'sales_model_name' } as const;
const LINE_IDENTITY_COL: Partial<ColDef<MovementRow>> = { minWidth: 110 };

export function ChannelOpsMovementsTab({ depth }: { depth: IntelDepth }) {
  const [distributorPick, setDistributorPick] = useState<DistHit | null>(null);
  const lineId = useLineIdentifierPreference();
  const factColumns = useFactColumns<MovementRow>('channel-ops.movements', {
    lineIdentifier: LINE_IDENTITY,
    lineIdentifierColDef: LINE_IDENTITY_COL,
  });
  const gridChrome = useFactGridChrome('channel-ops.movements', { layout: factGridLayout(factColumns) });
  const distId = distributorPick?.id;

  const { data: filterOptions } = useQuery({
    queryKey: ['sellout-filter-options'],
    queryFn: ({ signal }) =>
      apiGet<{ distributors: DistHit[] }>('/api/v1/sellout/filter-options', { signal }),
  });

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['channel-ops-movements', distId],
    queryFn: ({ signal }) =>
      apiGet<{ items: MovementRow[]; total: number }>(
        `/api/v1/channel-ops/movements?distributor_id=${distId}&page_size=50`,
        { signal }
      ),
    enabled: distId != null,
  });

  const productTotals = useMemo(() => {
    if (!depthAtLeast(depth, 'strategic') || !data?.items?.length) return [];
    const map = new Map<number, ProductTotal>();
    for (const r of data.items) {
      if (r.product_id == null) continue;
      const cur = map.get(r.product_id) ?? {
        productId: r.product_id,
        sku: r.sku ?? '',
        sales_model_name: r.sales_model_name ?? '',
        name: r.product_name ?? '—',
        inbound: 0,
      };
      cur.inbound += r.units_shipped ?? 0;
      map.set(r.product_id, cur);
    }
    return [...map.values()];
  }, [data?.items, depth]);

  const movementCols = useMemo<ColDef<MovementRow>[]>(
    () => [
      { field: 'ship_date', headerName: 'Ship date', minWidth: 120, valueFormatter: (p) => p.value ?? '—' },
      { field: 'product_name', headerName: 'Product', flex: 1, minWidth: 140, valueFormatter: (p) => p.value ?? '—' },
      ...factColumns.identityColDefs,
      { field: 'order_no', headerName: 'Order no', minWidth: 120, valueFormatter: (p) => p.value ?? '—' },
      { field: 'delivery_no', headerName: 'Delivery no', minWidth: 120, valueFormatter: (p) => p.value ?? '—' },
      {
        field: 'units_shipped',
        headerName: 'Units',
        type: 'numericColumn',
        minWidth: 90,
        valueFormatter: (p) => (p.value != null ? Number(p.value).toLocaleString() : '—'),
      },
      { field: 'line_state', headerName: 'Status', minWidth: 110 },
      ...factColumns.optionalColDefs,
    ],
    [factColumns.identityColDefs, factColumns.optionalColDefs],
  );
  const totalCols = useMemo<ColDef<ProductTotal>[]>(
    () => [
      ...lineId.columns<ProductTotal>(LINE_IDENTITY, { minWidth: 110 }),
      { field: 'name', headerName: 'Product', flex: 1, minWidth: 160 },
      {
        field: 'inbound',
        headerName: 'Inbound units',
        type: 'numericColumn',
        minWidth: 130,
        valueFormatter: (p) => Number(p.value ?? 0).toLocaleString(),
      },
    ],
    [lineId],
  );

  return (
    <Box>
      <Autocomplete
        sx={{ minWidth: 320, mb: 2 }}
        size="small"
        options={filterOptions?.distributors ?? []}
        value={distributorPick}
        onChange={(_e, v) => setDistributorPick(v)}
        getOptionLabel={(o) => `${o.distributor_name} (${o.distributor_code})`}
        isOptionEqualToValue={(a, b) => a.id === b.id}
        renderInput={(params) => <TextField {...params} label="Distributor" required />}
      />
      {distId == null ? (
        <Alert severity="info">Select a distributor to view inbound shipment movements.</Alert>
      ) : (
        <>
          <Paper variant="outlined">
            <Box sx={{ p: 2 }}>
              <ModuleDataSection
                isLoading={isLoading}
                isError={isError}
                error={isError ? new Error((error as Error)?.message ?? 'Failed to load movements.') : null}
                onRetry={() => void refetch()}
                toolbar={
                  <ScopeBar
                    chips={[]}
                    savedViews={gridChrome.viewNames}
                    savedView={gridChrome.active}
                    onSavedView={gridChrome.selectView}
                    filters={gridChrome.filters}
                    trailing={
                      <>
                      {gridChrome.trailing}
                      <FactColumnsButton
                        gridId="channel-ops.movements"
                        onClick={factColumns.openPicker}
                        count={factColumns.optionalFields.length}
                      />
                      </>
                    }
                  />
                }
                isEmpty={(data?.items ?? []).length === 0}
                empty={{
                  title: 'No shipment evidence lines for this distributor',
                  description: 'Inbound shipment lines appear here once a shipment evidence import has been applied.',
                  primary: { label: 'Import Center', href: '/admin/imports?template=inbound_shipments' },
                }}
              >
                <EnterpriseDataGrid ref={gridChrome.gridRef} quickFilterText={gridChrome.query} rowData={data?.items ?? []} columnDefs={movementCols} height={420} />
              </ModuleDataSection>
            </Box>
          </Paper>
          {depthAtLeast(depth, 'strategic') && productTotals.length > 0 && (
            <Paper variant="outlined" sx={{ mt: 2, p: 2 }}>
              <Typography variant="subtitle2" gutterBottom>
                Inbound totals by product (filtered page)
              </Typography>
              <EnterpriseDataGrid rowData={productTotals} columnDefs={totalCols} height={280} />
            </Paper>
          )}
        </>
      )}
      <FactColumnPicker {...factColumns.pickerProps} />
    </Box>
  );
}
