'use client';

import { Box, Chip, Paper, Stack, Typography } from '@mui/material';
import type { ColDef } from 'ag-grid-community';
import React, { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';

/**
 * Design-lab render for the density audit (2026-09-20). NOT shipped app-wide.
 *
 * ONE proposed change, shown beside current: the comfortable "operator data scale" —
 *   grid rows 42 → 36px, header 42 → 36px, grid type 14 → 13px.
 * Everything else (panel padding, headline figures, controls) is rendered at current values in
 * both columns so the delta is isolated. Rendered at 1280x800 for the audit doc.
 *
 * Where the values live today (all inside apps/web change_paths unless noted):
 *   - rows/header: components/EnterpriseDataGrid.tsx (42/34, 42/36) and
 *     features/plan-vs-executed/gridPagination.ts (STANDARD_/COMPACT_ constants) — duplicated.
 *     packages/ui/agGridMuiTheme.ts also emits --ag-row-height/--ag-header-height (out of scope; the
 *     explicit AgGridReact props win, so the in-scope values are authoritative).
 *   - grid type: --ag-font-size ← theme.typography.body2.fontSize (MUI default 0.875rem) via
 *     packages/ui/agGridMuiTheme.ts; overridable inline from EnterpriseDataGrid's shellSx.
 */

type Row = {
  id: number;
  distributor: string;
  customer: string;
  product: string;
  state: string;
  units: number;
  value: number;
  eta: string;
};

const DISTRIBUTORS = ['Pinnacle', 'Rectron', 'Mustek', 'Firsttech', 'DCC', 'Pepkor'];
const CUSTOMERS = ['Channel partner', 'Open Channel', 'Evetech', 'Eshop', 'Incredible Connection', 'Takealot'];
const PRODUCTS = ['S5452MA-I716512S0W', 'H7607BA-ON12810B0X', 'X1652DA-516512S0W', 'FA506NCG-78512B0W', 'GX651AX-U96420G0W'];

function sampleRows(n: number): Row[] {
  const out: Row[] = [];
  for (let i = 0; i < n; i += 1) {
    out.push({
      id: 120000 + i,
      distributor: DISTRIBUTORS[i % DISTRIBUTORS.length]!,
      customer: CUSTOMERS[(i * 7) % CUSTOMERS.length]!,
      product: PRODUCTS[(i * 3) % PRODUCTS.length]!,
      state: i % 5 === 0 ? 'shipped' : 'open_order',
      units: 12 + ((i * 37) % 400),
      value: 18_500 + ((i * 9_137) % 420_000),
      eta: `2026-${String(9 + (i % 3)).padStart(2, '0')}-${String(1 + (i % 27)).padStart(2, '0')}`,
    });
  }
  return out;
}

const COLS: ColDef<Row>[] = [
  { field: 'id', headerName: 'ID', width: 96 },
  { field: 'distributor', headerName: 'Distributor', minWidth: 120, flex: 1 },
  { field: 'customer', headerName: 'Channel partner', minWidth: 140, flex: 1.2 },
  { field: 'product', headerName: 'Product (sales model)', minWidth: 170, flex: 1.4 },
  { field: 'state', headerName: 'Line state', width: 110 },
  { field: 'units', headerName: 'Units', width: 90, type: 'rightAligned', valueFormatter: (p) => p.value.toLocaleString() },
  {
    field: 'value',
    headerName: 'USD',
    width: 120,
    type: 'rightAligned',
    valueFormatter: (p) => p.value.toLocaleString(undefined, { maximumFractionDigits: 0 }),
  },
  { field: 'eta', headerName: 'ETA', width: 110 },
];

/** 800 window − 20 pad − 32 title row − 12 gap − ~100 headline strip − 12 gap − 32 panel pad − 28 panel title − 20 pad. */
const GRID_HEIGHT = 540;

function Column({
  title,
  chip,
  rowHeight,
  headerHeight,
  fontSize,
  rows,
}: {
  title: string;
  chip: string;
  rowHeight: number;
  headerHeight: number;
  fontSize: string;
  rows: Row[];
}) {
  const visibleRows = Math.floor((GRID_HEIGHT - headerHeight) / rowHeight);
  return (
    <Stack spacing={1.5} sx={{ minWidth: 0 }}>
      <Stack direction="row" alignItems="center" spacing={1}>
        <Typography variant="subtitle1" fontWeight={600}>
          {title}
        </Typography>
        <Chip size="small" label={chip} />
        <Typography variant="caption" color="text.secondary">
          {visibleRows} rows visible in a {GRID_HEIGHT}px grid
        </Typography>
      </Stack>
      <HeadlineStrip columns={3}>
        <HeadlineFigure label="Pipeline value" value="$46.6M" caption="72,144 units · 1,010 lines" />
        <HeadlineFigure label="Arriving this week" value="3,230" unit="units" severity="good" delta={{ text: '67 lines', direction: 'flat' }} />
        <HeadlineFigure label="Overdue" value="588" severity="bad" caption="promise passed, not landed" />
      </HeadlineStrip>
      <Paper sx={{ p: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          Shipment lines
        </Typography>
        {/* The grid root carries --ag-font-size as an inline style; re-declare one level down. */}
        <Box sx={{ '& .ag-root-wrapper': { '--ag-font-size': fontSize, fontSize } }}>
          <EnterpriseDataGrid<Row>
            rowData={rows}
            columnDefs={COLS}
            height={GRID_HEIGHT}
            gridOptions={{ rowHeight, headerHeight }}
          />
        </Box>
      </Paper>
    </Stack>
  );
}

/** Reference window for the audit; the AppShell rail (252px) is reserved so content width is honest. */
const FRAME_W = 1280;
const FRAME_H = 800;
const APP_RAIL_W = 252;

function Frame({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Stack spacing={1} sx={{ width: FRAME_W, flexShrink: 0 }}>
      <Typography variant="subtitle2" color="text.secondary">
        {title} — {FRAME_W}×{FRAME_H} window, {APP_RAIL_W}px rail reserved
      </Typography>
      <Box
        sx={{
          width: FRAME_W,
          height: FRAME_H,
          display: 'flex',
          border: '1px solid',
          borderColor: 'divider',
          overflow: 'hidden',
          bgcolor: 'background.default',
        }}
      >
        <Box sx={{ width: APP_RAIL_W, flexShrink: 0, borderRight: '1px solid', borderColor: 'divider', bgcolor: 'background.default' }} />
        <Box sx={{ flex: 1, minWidth: 0, p: 2.5, overflow: 'hidden' }}>{children}</Box>
      </Box>
    </Stack>
  );
}

export function DensitySurface() {
  const rows = useMemo(() => sampleRows(60), []);
  return (
    <Box sx={{ p: 3, minWidth: 0 }} data-testid="design-lab-density">
      <Typography variant="h5" fontWeight={600} gutterBottom>
        Density proposal — operator data scale (comfortable)
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: 900 }}>
        One change, isolated: grid rows 42 → 36px, header 42 → 36px, grid type 14 → 13px. Panel padding,
        headline figures and controls are unchanged in both frames. Lab render only — not shipped.
      </Typography>
      <Stack spacing={4} sx={{ overflowX: 'auto', pb: 2 }}>
        <Frame title="Current">
          <Column title="Current" chip="42px rows · 14px type" rowHeight={42} headerHeight={42} fontSize="0.875rem" rows={rows} />
        </Frame>
        <Frame title="Proposed">
          <Column title="Proposed" chip="36px rows · 13px type" rowHeight={36} headerHeight={36} fontSize="0.8125rem" rows={rows} />
        </Frame>
      </Stack>
    </Box>
  );
}
