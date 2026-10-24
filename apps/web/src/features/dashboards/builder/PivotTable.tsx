'use client';
import { Alert, Box, Typography } from '@mui/material';
import type { ColDef } from 'ag-grid-community';
import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { formatChartValue, type ChartClickEvent } from '@/features/workbench-ui/charts';
import { measureUnit } from './catalog';
import { measureHeading, type Pivot, type PivotRow } from './advancedShape';
import type { Cat } from './shape';

type GridRow = PivotRow & { totalRow?: boolean };
export function PivotTable({ model, rowTitle, onSelect }: {
  model: Pivot; rowTitle: string;
  onSelect?: (parts: Cat[], e?: ChartClickEvent) => void;
}) {
  const action = (row: GridRow | undefined, colId: string, e?: ChartClickEvent) => {
    if (!row || row.totalRow || !onSelect) return;
    const f = model.fields.find((f) => f.field === colId);
    const parts = colId === 'row' ? [row.cat] : f ? [row.cat, f.category] : [];
    const selectable = parts.filter((c) => c.breakdown === 'period' ? Boolean(c.window) : c.value != null);
    if (selectable.length) onSelect(selectable, e);
  };
  const defs: ColDef<GridRow>[] = [
    { colId: 'row', headerName: rowTitle, pinned: 'left', minWidth: 150, flex: 1,
      valueGetter: (p) => p.data?.totalRow ? 'Column totals' : p.data?.cat.label },
    ...model.fields.map((f): ColDef<GridRow> => ({
        colId: f.field, headerName: `${f.category.label} · ${measureHeading(f.measure)}`, type: 'numericColumn', minWidth: 130,
        wrapHeaderText: true, autoHeaderHeight: true,
        valueGetter: (p) => p.data?.values[f.field] ?? null,
        valueFormatter: (p) => formatChartValue(typeof p.value === 'number' ? p.value : null, measureUnit(f.measure)),
    })),
    ...model.additive.map((m): ColDef<GridRow> => ({
      colId: `total:${m.id}`, headerName: `Row total: ${measureHeading(m)}`, type: 'numericColumn', minWidth: 150,
      valueGetter: (p) => p.data?.totalRow ? null : p.data?.totals[m.id] ?? null,
      valueFormatter: (p) => formatChartValue(typeof p.value === 'number' ? p.value : null, measureUnit(m)),
    })),
  ];
  const pinned: GridRow[] = model.additive.length ? [{
    key: '__totals', totalRow: true,
    cat: { key: '__totals', label: 'Column totals', breakdown: '', value: null },
    values: model.columnTotals, totals: {},
  }] : [];
  return <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 160 }} data-testid="builder-pivot">
    {model.partial ? <Alert severity="info">This pivot shows only the fetched rows. Row and column totals are hidden. Narrow the filters for a complete pivot.</Alert> : null}
    <Typography variant="caption" color="text.secondary">Enter on a cell filters its row and column; Enter on a row name filters that row.</Typography>
    <Box sx={{ flex: 1, minHeight: 120 }}>
      <EnterpriseDataGrid<GridRow> rowData={model.rows} columnDefs={defs} height="100%"
        gridOptions={{ getRowId: (p) => p.data.key, pinnedBottomRowData: pinned,
          onCellClicked: (e) => action(e.data, e.column.getColId(), e.event as MouseEvent | undefined),
          onCellKeyDown: (e) => {
            if ('column' in e && (e.event as KeyboardEvent | undefined)?.key === 'Enter') action(e.data, e.column.getColId());
          },
        }} />
    </Box>
    <Typography variant="caption" sx={{ mt: 1 }} data-testid="pivot-grand-total">
      Grand total (server): {model.fields.filter((f, i, a) => a.findIndex((x) => x.measure.id === f.measure.id) === i)
        .map(({ measure: m }) => `${measureHeading(m)}: ${formatChartValue(model.grand[m.id], measureUnit(m))}`).join(' · ')}
    </Typography>
  </Box>;
}
