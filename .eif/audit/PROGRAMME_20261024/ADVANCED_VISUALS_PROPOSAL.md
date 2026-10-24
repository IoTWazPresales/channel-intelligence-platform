# N-0116 advanced visuals implementation proposal

Run: `RUN-20261024-N0116-VISUAL-PROPOSAL`. Date: 2026-10-24. Branch observed:
`feat/ns-2-brief-nav-collapse`, HEAD `a380b9fa3935ada99db6cd5339cffb59b35cb8fa`.
Owning lenses: frontend-engineer, test-engineering-specialist (unit/component), accessibility-specialist.
PROPOSAL ONLY: this artifact is the only write. No product source, programme ledger, services or databases changed.
Root owns application and tests. The operator execution instruction retains the original 23 October scope,
including S15. This does not defer the three visuals or claim implementation/verification.

## Path and canonical target

| UI / trigger | API route | Celery task | Sync writer | Commit model |
|---|---|---|---|---|
| Editor visual tile, card, full screen | existing `POST /api/v1/query/v2/execute` | none | none (read) | no database write |
| Editor Save / Add | existing dashboard widget POST/PATCH | none | existing dashboard widget service | existing one-widget transaction; unchanged |
| CSV / PNG menu | existing client export helpers | none | browser download | no database write |

Observed: `builder/fit.ts` explicitly refuses all three via `NOT_BUILT`;
`V2WidgetBody.tsx` groups all three with plain table. The stored visual union and 0048 API visual
allowlist already contain them. There is no separate chart writer or query needed.
Canonical targets: extend `features/workbench-ui/charts.tsx::TrendChart` for dual axes; add
`ScatterPlot` alongside it; add one bounded builder reshape module and pivot renderer. Wire through
`fit.ts`, `BuilderEditorDialog.tsx`, `V2WidgetBody.tsx`; retain card/preview/full-screen common body.
One direction: **extend the existing chart path and wire the saved visual to it**.

Source evidence read: original spec sections 2/4/5/6, operator execution, builder types/catalog/shape/fit/
body/editor/card/table/clickFilters/exportPng and shared chart wrappers/TrendChart. Existing tree changes
are inherited and preserved. Legacy `.cursor/rules/engineering-rules.mdc` is absent; reported to root.

## Contracts and small required changes

* `dual_axis`: exactly two measures, one breakdown (period or category), distinct **semantic** units.
  Each query row is already at the drawn grain. Never sum these rows on the client. Default first
  measure bars/left, second line/right; allow swapping the right-axis measure. Exactly one measure
  belongs to each axis. Distinct axes remain independent and visibly titled. No stacking across axes.
* `scatter`: exactly one non-period breakdown and two measures, query order x then y. A dot is one
  grouped category row. Zero/negative values stay; a row missing either finite coordinate is omitted
  with an explicit count. Names, never entity ids/codes, appear in tooltips and keyboard actions.
* `pivot`: exactly two ordered breakdowns, one or more measures. First is rows, second is columns;
  period may be either. Cap **distinct column categories** at 24, not individual measure subcolumns.
  At 25 refuse with `Too many columns; filter or swap`. Preserve every cell including null and zero.
  Reject duplicate grain rows rather than summing already calculated measures. Marginals only for
  additive measures, and only from a complete response. Grand totals always come from response.totals.
  When truncated, show cells, suppress marginals and say why; keep authoritative server grand totals.
* Response column order need not equal query order: resolve breakdown columns by id. Measure fields
  remain keyed by measure id under the current execute contract. Use positional safe pivot fields
  (`v0_0`), because measure ids contain dots and AG Grid's field path parsing must not reinterpret them.
* `measureUnit()` is a formatter mapping, **not semantic equality**: it collapses units_per_week to
  units and usd_per_unit to usd. Use `semanticUnit` below for fit and `measureHeading` for titles.
  Apply this heading to CSV headers for these visuals too; this needs no new stored unit field.
* Existing `WidgetDisplay.series[id].axis` is sufficient; no new API/query/type schema is required.
  Do not store formatter functions. Resolve all formatters at render time from the catalog.

## Ready-to-apply new module: `builder/advancedShape.ts`

```ts
import { axisTitle, type MeasureUnit } from '@/features/workbench-ui/charts';
import { isAdditive, measureUnit } from './catalog';
import { catOf, num, type Cat } from './shape';
import type { V2Measure, V2Response, V2Row, WidgetDisplay } from './types';

export function semanticUnit(m: V2Measure): string {
  return m.unit ?? measureUnit(m);
}

export function measureHeading(m: V2Measure): string {
  if (m.unit === 'units_per_week') return `${m.label} (units/week)`;
  if (m.unit === 'usd_per_unit') return `${m.label} (US$/unit)`;
  const known = ['units', 'count', 'usd', 'zar', 'ratio'];
  if (m.unit && !known.includes(m.unit)) return `${m.label} (${m.unit.replace(/_/g, ' ')})`;
  return axisTitle(m.label, measureUnit(m));
}

export type AdvancedSeries = {
  key: string; label: string; kind: 'bar' | 'line' | 'area';
  axis: 'left' | 'right'; unit: MeasureUnit;
};

// Normalize old/invalid stored assignments to exactly one measure on each axis.
export function dualSeries(ms: V2Measure[], display?: WidgetDisplay): AdvancedSeries[] {
  const right = ms.find((m) => display?.series?.[m.id]?.axis === 'right')?.id ?? ms[1]?.id;
  return ms.map((m, i) => ({
    key: m.id, label: m.label,
    kind: display?.series?.[m.id]?.kind ?? (i === 0 ? 'bar' : 'line'),
    axis: m.id === right ? 'right' : 'left', unit: measureUnit(m),
  }));
}

export type GrainRow = V2Row & { __key: string; __label: string; __cat: Cat };
export type ShapeResult<T> = { ok: true; value: T } | { ok: false; reason: string };

export function grainRows(resp: V2Response, breakdownId: string): ShapeResult<GrainRow[]> {
  const col = resp.columns.find((c) => c.kind === 'breakdown' && c.id === breakdownId);
  if (!col) return { ok: false, reason: 'The answer is missing the selected breakdown.' };
  const seen = new Set<string>();
  const out: GrainRow[] = [];
  for (const row of resp.rows) {
    const cat = catOf(row, col);
    if (seen.has(cat.key)) return { ok: false, reason: 'The answer has repeated categories. Use a table to inspect it.' };
    seen.add(cat.key);
    out.push({ ...row, __key: cat.key, __label: cat.label, __cat: cat });
  }
  // Period query sort can be by value. Draw time in chronological order.
  if (breakdownId === 'period') out.sort((a, b) =>
    String(a.__cat.window?.from ?? a.__cat.label).localeCompare(String(b.__cat.window?.from ?? b.__cat.label)));
  return { ok: true, value: out };
}

export type ScatterDatum = { key: string; label: string; x: number; y: number; cat: Cat };
export function scatterRows(rows: GrainRow[], x: string, y: string) {
  const data: ScatterDatum[] = [];
  for (const row of rows) {
    const xv = num(row[x]);
    const yv = num(row[y]);
    if (xv != null && yv != null) data.push({ key: row.__key, label: row.__label, x: xv, y: yv, cat: row.__cat });
  }
  return { data, omitted: rows.length - data.length };
}

export type PivotField = { field: string; category: Cat; measure: V2Measure };
export type PivotRow = { key: string; cat: Cat; values: Record<string, number | null>; totals: Record<string, number | null> };
export type Pivot = {
  columns: Cat[]; fields: PivotField[]; rows: PivotRow[];
  columnTotals: Record<string, number | null>; grand: Record<string, number | null>;
  additive: V2Measure[]; partial: boolean;
};

const sumPresent = (values: (number | null)[]): number | null => {
  const finite = values.filter((v): v is number => v != null);
  return finite.length ? finite.reduce((a, b) => a + b, 0) : null;
};

export function pivotRows(resp: V2Response, ms: V2Measure[], ids: string[]): ShapeResult<Pivot> {
  if (ids.length !== 2 || ms.length === 0) return { ok: false, reason: 'Pivot needs two breakdowns and at least one measure.' };
  const bds = ids.map((id) => resp.columns.find((c) => c.kind === 'breakdown' && c.id === id));
  const [rcol, ccol] = bds;
  if (!rcol || !ccol) return { ok: false, reason: 'The answer is missing a pivot breakdown.' };
  const columns = new Map<string, Cat>();
  const rows = new Map<string, PivotRow>();
  const seen = new Set<string>();
  const raw = resp.rows.map((row) => ({ row, r: catOf(row, rcol), c: catOf(row, ccol) }));
  for (const { r, c } of raw) {
    const key = JSON.stringify([r.key, c.key]);
    if (seen.has(key)) return { ok: false, reason: 'The answer has repeated pivot cells. Use a table to inspect it.' };
    seen.add(key);
    columns.set(c.key, c);
    if (!rows.has(r.key)) rows.set(r.key, { key: r.key, cat: r, values: {}, totals: {} });
  }
  if (columns.size > 24) return { ok: false, reason: 'Too many columns; filter or swap' };
  // Preserve API category order; period headings must be chronological.
  const cols = [...columns.values()];
  if (ids[1] === 'period') cols.sort((a, b) => String(a.window?.from ?? a.label).localeCompare(String(b.window?.from ?? b.label)));
  const fieldMap = new Map<string, string>();
  const fields = cols.flatMap((category, ci) => ms.map((measure, mi) => {
    const field = `v${ci}_${mi}`;
    fieldMap.set(JSON.stringify([category.key, measure.id]), field);
    return { field, category, measure };
  }));
  for (const r of rows.values()) for (const f of fields) r.values[f.field] = null;
  for (const { row, r, c } of raw) for (const m of ms) {
    const field = fieldMap.get(JSON.stringify([c.key, m.id]))!;
    rows.get(r.key)!.values[field] = num(row[m.id]);
  }
  const additive = resp.truncated ? [] : ms.filter(isAdditive);
  for (const r of rows.values()) for (const m of additive)
    r.totals[m.id] = sumPresent(fields.filter((f) => f.measure.id === m.id).map((f) => r.values[f.field]));
  const columnTotals: Record<string, number | null> = {};
  for (const f of fields) if (additive.some((m) => m.id === f.measure.id))
    columnTotals[f.field] = sumPresent([...rows.values()].map((r) => r.values[f.field]));
  const rr = [...rows.values()];
  if (ids[0] === 'period') rr.sort((a, b) => String(a.cat.window?.from ?? a.cat.label).localeCompare(String(b.cat.window?.from ?? b.cat.label)));
  return { ok: true, value: {
    columns: cols, fields, rows: rr, additive, columnTotals,
    grand: Object.fromEntries(ms.map((m) => [m.id, num(resp.totals[m.id])])), partial: resp.truncated,
  } };
}
```

## Shared charts: exact extension points

Extend the existing `TrendChart`, keeping all added props optional so current callers keep working:

```ts
// Add to series item type:
axis?: 'left' | 'right';
unit?: MeasureUnit;
// Add to props and destructuring:
yRightAxisTitle?: string;
xTickFormat?: (v: unknown) => string;
```

Use these locals immediately after `const fmt = chartFormatters(unit, format)`:

```ts
const seriesFmt = (s: (typeof series)[number]) => chartFormatters(s.unit ?? unit, format);
const rightSeries = series.filter((s) => s.axis === 'right');
const leftSeries = series.filter((s) => s.axis !== 'right');
const hasRight = rightSeries.length > 0;
const leftUnit = leftSeries[0]?.unit ?? unit;
const rightUnit = rightSeries[0]?.unit ?? unit;
const leftFmt = chartFormatters(leftUnit, format);
const rightFmt = chartFormatters(rightUnit, format);
// All first-axis consumers remain unchanged when no per-series unit is passed.
```

Replace the hidden table's series-cell mapping with
`series.map((s) => cellText(seriesFmt(s).full, r[s.key]))` and its headings with
`series.map((s) => axisTitle(s.label, s.unit ?? unit))`. For new dual-axis calls pass an explicit
`table` with `measureHeading` headings to preserve rate denominators. `lastLabel` uses the formatter
of `series.find(s => s.key === labelled)` (or existing `fmt` as fallback).

Give **both** axes ids only when needed: the existing YAxis gets
`yAxisId={hasRight ? 'left' : 0}`, `tickFormatter={hasRight ? leftFmt.tick : fmt.tick}`;
when hasRight render a second YAxis:

```tsx
{hasRight ? <YAxis yAxisId="right" orientation="right"
  tick={{ fill: c.axis, fontSize: 11 }} tickFormatter={rightFmt.tick}
  axisLine={false} tickLine={false} width={isMoney(rightUnit) ? 68 : 60}
  domain={yScale === 'fit' ? ['auto', 'auto'] : [0, 'auto']} /> : null}
```

On every `Bar`, `Area`, `Line` add
`yAxisId={hasRight ? (s.axis ?? 'left') : 0}`. Set `stackId` only when `stack && !hasRight`.
Retain current zero-domain behaviour for existing callers. New dual-axis calls use `yScale="fit"`
so signed sales/returns and rates aren't clipped; on each axis use `['dataMin', 'dataMax']` with
`allowDataOverflow={false}` or current auto domain (test negatives in real Recharts).
For new bar-series calls include zero in that axis domain: `[Math.min(0,dataMin), Math.max(0,dataMax)]`
using Recharts function domains. A bar must have a zero baseline; a line-only axis may fit tightly.

Tooltip becomes:

```tsx
<Tooltip {...c.tooltip}
  labelFormatter={(v) => xTickFormat ? xTickFormat(v) : String(v ?? '')}
  formatter={(v, name, item) => {
    const s = series.find((s) => s.key === String(item.dataKey));
    return [(s ? seriesFmt(s) : fmt).full(Number(v)), String(name)];
  }} cursor={{ fill: c.cursor }} />
```

XAxis adds `tickFormatter={xTickFormat}`. Its dataKey is the stable category key for new dual-axis
calls; labels are looked up from the supplied rows. This preserves separate equal-named categories.
The top caption becomes a wrapping flex row with existing `yAxisTitle` at left and
`yRightAxisTitle` at right. Include both in autoSummary. Legend entries use
`label: hasRight ? `${s.label} (${s.axis ?? 'left'} axis)` : s.label`.
New axis titles remain HTML to match current small-screen grammar; see PNG correction below.

## Ready-to-apply `ScatterPlot` in `charts.tsx`

Add `Scatter` and `ScatterChart` to existing Recharts imports. This component shares private
`useChartTheme`, `ChartShell`, `AxisCaption`, exported ChartFrame, and formatting from the same file.
It accepts generic category payloads without depending on the dashboard feature.

```tsx
export type ScatterPoint = { key: string; label: string; x: number; y: number };
export function ScatterPlot({ data, xUnit, yUnit, xAxisTitle, yAxisTitle, summary,
  height = 220, onPointClick, testId = 'scatter-plot',
}: {
  data: ScatterPoint[]; xUnit: MeasureUnit; yUnit: MeasureUnit;
  xAxisTitle: string; yAxisTitle: string; summary: string; height?: number;
  onPointClick?: (point: ScatterPoint, e?: ChartClickEvent) => void; testId?: string;
}) {
  const c = useChartTheme();
  const table: ChartDataTable = { caption: summary,
    columns: ['Category', xAxisTitle, yAxisTitle],
    rows: data.map((d) => [d.label, formatChartValue(d.x, xUnit), formatChartValue(d.y, yUnit)]),
  };
  return <ChartShell testId={testId} summary={summary} table={table}
    top={<AxisCaption testId="chart-axis-title-top">{yAxisTitle}</AxisCaption>}
    bottom={<AxisCaption testId="chart-axis-title-bottom" align="center">{xAxisTitle}</AxisCaption>}>
    <ChartFrame height={height}>
      <ScatterChart margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
        <CartesianGrid stroke={c.grid} strokeDasharray="2 4" />
        <XAxis type="number" dataKey="x" name={xAxisTitle} domain={['auto', 'auto']}
          tick={{ fill: c.axis, fontSize: 11 }} tickFormatter={(v: number) => formatChartValue(v, xUnit, 'tick')}
          axisLine={false} tickLine={false} />
        <YAxis type="number" dataKey="y" name={yAxisTitle} domain={['auto', 'auto']}
          tick={{ fill: c.axis, fontSize: 11 }} tickFormatter={(v: number) => formatChartValue(v, yUnit, 'tick')}
          width={isMoney(yUnit) ? 68 : 60} axisLine={false} tickLine={false} />
        <Tooltip content={({ active, payload }) => {
          const d = payload?.[0]?.payload as ScatterPoint | undefined;
          if (!active || !d) return null;
          return <Box sx={{ p: 1, border: 1, borderColor: 'divider', borderRadius: 1,
            bgcolor: 'background.paper', color: 'text.primary', maxWidth: 280, overflowWrap: 'anywhere' }}>
            <Typography variant="caption" fontWeight={700} display="block">{d.label}</Typography>
            <Typography variant="caption" display="block">{xAxisTitle}: {formatChartValue(d.x, xUnit)}</Typography>
            <Typography variant="caption" display="block">{yAxisTitle}: {formatChartValue(d.y, yUnit)}</Typography>
          </Box>;
        }} />
        <Scatter data={data} fill={c.primary} isAnimationActive={false}
          cursor={onPointClick ? 'pointer' : undefined}
          onClick={onPointClick ? (entry: unknown, _i: number, e?: ChartClickEvent) => {
            const d = (entry as { payload?: ScatterPoint }).payload;
            if (d) onPointClick(d, e);
          } : undefined} />
      </ScatterChart>
    </ChartFrame>
  </ChartShell>;
}
```

## Ready-to-apply pivot renderer: `builder/PivotTable.tsx`

This uses AG Grid Community's ordinary flat column definitions, never its enterprise pivot mode.
Headers join category and measure names; safe numeric colIds resolve cells. Keyboard Enter on a focused
data cell uses the same action as pointer click. Row-header Enter filters just that row category.
No action fires on totals. All external callbacks remain the body's existing SelectDatum contract.

```tsx
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
  </Box>;
}
```

Render server grand totals separately below the grid with **all** measures and `measureHeading`:
`Grand total: ${measureHeading(m)} ${formatChartValue(model.grand[m.id], measureUnit(m))}`.
Do not place server totals into the intersection of the client row/column subtotals. This avoids
suggesting non-additive marginals and makes truncated/full scope differences explicit.
For keyboard Ctrl/Cmd support on pivot, change action's event type to mouse-or-keyboard or pass an
explicit additive boolean; do not cast KeyboardEvent to MouseEvent. The minimal renderer above
supports Enter as replace/toggle; existing mouse modifiers remain intact.

## Fit/editor/body wiring (precise)

1. In `fit.ts`, remove `NOT_BUILT` and its early return. Add tiles for `dual_axis` (Two axes),
   `scatter` (Scatter), `pivot` (Pivot table). Add switch cases:

```ts
case 'dual_axis':
  if (n !== 2 || breakdowns.length !== 1) return no('Two axes need two measures and one category or period.');
  if (semanticUnit(measures[0]) === semanticUnit(measures[1])) return no('Two axes need different units; use bar + line for one unit.');
  return { id: visual, fits: true };
case 'scatter':
  if (n !== 2 || hasPeriod || cats.length !== 1) return no('Scatter needs one category and two measures (x, then y).');
  return { id: visual, fits: true };
case 'pivot':
  if (n < 1 || breakdowns.length !== 2) return no('Pivot needs two breakdowns and at least one measure.');
  return { id: visual, fits: true };
```

   For combo use `semanticUnit`, replacing the old “two axes are not built yet” reason with
   “Bar + line needs the same unit; choose Two axes for different units.” Add dual_axis to the
   two-measure/one-breakdown ranks, scatter to the two-measure/one-category rank, pivot to all
   exactly-two-breakdown ranks. The visual must appear in both fitsAll and visualsForV2; changing
   tiles alone leaves effectiveVisual fallback wrong. Preserve existing first-choice order.

2. In `BuilderEditorDialog.tsx`, serialize `display.series` for combo **and dual_axis**, pruning
   stale measure ids and normalizing through `dualSeries`. Existing `definition` currently drops
   all non-combo series options. Show one `Right axis` labelled Select containing the two chosen
   measures; on change assign right to selected id, left to the other id. Reuse combo's series-kind
   choice or default bar/line. Show `x: first measure / y: second measure` for scatter and a Swap axes
   button that swaps the two query measure ids. For pivot show `Rows: breakdown[0] / Columns:
   breakdown[1]` and Swap rows and columns button: `setBreakdowns(([a,b]) => [b,a])`.
   Keep these controls labelled, keyboard reachable, and serialized by existing onSave.

3. In `V2WidgetBody`, change the table branch to **only** `visual === 'table'`.
   Place the advanced branches after ordinary refused/error/empty states, before generic chart
   shaping. Build them with requested breakdown ids. Display shape refusals through existing
   StatePanel, not an unnoticed fallback to table. Use the same frame/height helpers in all three.
   Require catalog metadata for all selected measures before advanced rendering. If missing, show
   a metadata/loading refusal rather than dereferencing missing measures or guessing their units.

```tsx
// Imports: advancedShape helpers, PivotTable, ScatterPlot.
if (visual === 'pivot') {
  const shaped = pivotRows(result, measures, breakdowns);
  if (!shaped.ok) return <StatePanel tone="info" testId={`dashboard-widget-refused-${testKey}`}>{shaped.reason}</StatePanel>;
  return <Box sx={{ height }}>
    <PivotTable model={shaped.value} rowTitle={breakdownLabel(catalog, breakdowns[0])}
      onSelect={onSelect ? (parts, e) => selectParts(parts, e) : undefined} />
    {/* Integrator: put grand-total line INSIDE PivotTable's flex box, after grid, so height stays bounded. */}
  </Box>;
}
if (visual === 'dual_axis' || visual === 'scatter') {
  const shaped = grainRows(result, breakdowns[0]);
  if (!shaped.ok) return <StatePanel tone="info" testId={`dashboard-widget-refused-${testKey}`}>{shaped.reason}</StatePanel>;
  const rows = shaped.value;
  if (visual === 'scatter') {
    const points = scatterRows(rows, measureIds[0], measureIds[1]);
    return frame(<>
      {points.data.length ? <ScatterPlot data={points.data}
        xUnit={measureUnit(measures[0])} yUnit={measureUnit(measures[1])}
        xAxisTitle={measureHeading(measures[0])} yAxisTitle={measureHeading(measures[1])}
        summary={`${measureHeading(measures[1])} against ${measureHeading(measures[0])} by ${breakdownLabel(catalog, breakdowns[0])}`}
        height={plotHeight} onPointClick={onSelect ? (d, e) => select(points.data.find((p) => p.key === d.key)?.cat, e) : undefined}
      /> : <Typography>No categories have both measures reported.</Typography>}
      {/* Keyboard row actions, below. */}
    </>, points.omitted ? `${points.omitted} categories omitted: both measures must be reported.` : null);
  }
  const series = dualSeries(measures, def.display);
  const left = measures.find((m) => series.find((s) => s.key === m.id)?.axis === 'left')!;
  const right = measures.find((m) => series.find((s) => s.key === m.id)?.axis === 'right')!;
  const labelOf = (key: unknown) => rows.find((r) => r.__key === String(key))?.__label ?? String(key ?? '');
  return frame(<>
    <TrendChart data={rows} x="__key" xTickFormat={labelOf} series={series}
      xAxisTitle={breakdownLabel(catalog, breakdowns[0])}
      yAxisTitle={measureHeading(left)} yRightAxisTitle={measureHeading(right)}
      height={plotHeight} yScale="fit"
      table={{ caption: 'Values by category', columns: [breakdownLabel(catalog, breakdowns[0]), ...measures.map(measureHeading)],
        rows: rows.map((r) => [r.__label, ...measures.map((m) => formatChartValue(num(r[m.id]), measureUnit(m)))]) }}
      onPointClick={onSelect ? (r, _i, e) => select(r.__cat as Cat, e) : undefined} />
    {/* Keyboard row actions, below. */}
  </>);
}
```

`frame`, `plotHeight` currently appear after the table branch: move only these small declarations
above advanced branches. Render scatter/dual keyboard action list outside ChartFigure's role=img:
a visible native `<details><summary>Filter by category</summary>` holding a scrollable `<ul>` of
MUI Buttons, one per selectable drawn row, full label plus both formatted values. Pass e to `select`
so native Enter/Space and Ctrl/Cmd-click use the existing callback. Use the stable key, not name;
null entity ids get plain text “Not filterable: no id”. Do not treat the present hidden data table
as keyboard filter support: source inspection shows plain th/td only.
Scatter keyboard actions list only drawn points; omitted rows cannot be selected via an invisible dot.

4. Menu/export: disable PNG for pivot in `V2WidgetCard` alongside KPI/table. CSV remains existing
   long-form response rows (document in toast “Exported grouped rows”; users can reconstruct pivot).
   This matches original S12, whose CSV contract explicitly uses response.columns and fetched rows.
   No second CSV serializer. If a wide pivot CSV is desired later, that is separate from S12.
   Correct advanced CSV headings by replacing measure TableCol.header with measureHeading(catalog
   measure), leaving all formula guards and raw numbers in `toCsv` intact.

5. PNG: existing export copies the Recharts SVG and HTML legend but **does not copy HTML axis
   captions**. To preserve both units, collect `[data-testid^="chart-axis-title-"]` text and add it
   to the existing wrapped canvas caption (deduplicated). E.g. `const axes = [...root.querySelectorAll
   <HTMLElement>('[data-testid^="chart-axis-title-"]')].map(el => el.textContent?.trim()).filter(Boolean)`;
   `wrapLines(ctx, [frame.caption, ...new Set(axes)].filter(Boolean).join(' · '), width)`.
   Dual-axis HTML legend already serializes through existing chart-legend selector. Scatter has
   one series, no legend is needed. Both still have exactly one `svg.recharts-surface`.

## Meaningful tests ready for `builder/advancedShape.test.ts`

These use synthetic grouped response fixtures, no database. The assertions catch bad aggregation,
id/name collapse, dimension ordering, null/zero handling and misleading totals.

```ts
import { describe, expect, it } from 'vitest';
import { builderCatalog } from '@/design-lab/fixtures/builder';
import { dualSeries, grainRows, measureHeading, pivotRows, scatterRows, semanticUnit } from './advancedShape';
import type { V2Column, V2Measure, V2Response, V2Row } from './types';
const base = builderCatalog.measures.find((m) => m.id === 'dsi_sellout.units')!;
const units: V2Measure = { ...base, id: 'm.units', label: 'Units', unit: 'units', additivity: 'additive' };
const rate: V2Measure = { ...base, id: 'm.rate', label: 'Rate', unit: 'ratio', additivity: 'non_additive' };
const stock: V2Measure = { ...base, id: 'm.stock', label: 'Stock', unit: 'units', additivity: 'semi_additive' };
const customer: V2Column = { id: 'customer', kind: 'breakdown', label: 'Customer', fields: ['customer_id', 'customer_name'] };
const channel: V2Column = { id: 'channel', kind: 'breakdown', label: 'Channel', fields: ['channel'] };
const period: V2Column = { id: 'period', kind: 'breakdown', label: 'Period', fields: ['bucket_key', 'bucket_start', 'bucket_end'] };
const answer = (rows: V2Row[], columns = [customer, channel]): V2Response => ({
  ok: true, columns, rows, totals: { 'm.units': 123, 'm.rate': 0.6, 'm.stock': 80 }, truncated: false, refusals: [],
});
const row = (id: number, name: string, ch: string, u: unknown, r: unknown = null): V2Row =>
  ({ customer_id: id, customer_name: name, channel: ch, 'm.units': u, 'm.rate': r, 'm.stock': 20 });
const value = <T,>(r: { ok: true; value: T } | { ok: false; reason: string }): T => {
  if (!r.ok) throw new Error(r.reason); return r.value;
};
describe('advanced grouped visuals', () => {
  it('preserves two customers with the same name without summing a rate', () => {
    const rs = value(grainRows(answer([row(1,'Same','A',10,0.2),row(2,'Same','A',30,0.8)], [customer]), 'customer'));
    expect(rs.map((r) => r.__key)).toEqual(['customer:1','customer:2']);
    expect(rs.map((r) => r['m.rate'])).toEqual([0.2,0.8]);
  });
  it('never adds duplicate grouped rows together', () => {
    const resp = answer([row(1,'One','A',10),row(1,'One','A',20)]);
    expect(grainRows(resp, 'customer').ok).toBe(false);
    expect(pivotRows(resp,[units],['customer','channel']).ok).toBe(false);
  });
  it('scatter keeps signed values and zero and counts missing coordinate rows', () => {
    const rs = value(grainRows(answer([row(1,'Zero','A',0,0),row(2,'Credit','A',-3,0.2),row(3,'Missing','A',null,0.3)], [customer]),'customer'));
    const shaped = scatterRows(rs,'m.units','m.rate');
    expect(shaped.data.map((p) => [p.x,p.y])).toEqual([[0,0],[-3,0.2]]);
    expect(shaped.omitted).toBe(1);
  });
  it('uses requested pivot order rather than response column order', () => {
    const p = value(pivotRows(answer([row(1,'One','Retail',0)], [channel,customer]),[units],['customer','channel']));
    expect(p.rows[0].cat.label).toBe('One'); expect(p.columns[0].label).toBe('Retail');
    expect(p.rows[0].values.v0_0).toBe(0);
    const swapped = value(pivotRows(answer([row(1,'One','Retail',0)]),[units],['channel','customer']));
    expect(swapped.rows[0].cat.label).toBe('Retail'); expect(swapped.columns[0].label).toBe('One');
  });
  it('keeps null cells distinct from reported zero and uses safe fields for dotted ids', () => {
    const p = value(pivotRows(answer([row(1,'One','A',0),row(2,'Two','B',3)]),[units],['customer','channel']));
    expect(p.fields.map((f) => f.field)).toEqual(['v0_0','v1_0']);
    expect(p.rows[0].values).toEqual({ v0_0: 0, v1_0: null });
  });
  it('has additive marginals and server grand totals, never summed rates or stock', () => {
    const p = value(pivotRows(answer([row(1,'One','A',10,0.2),row(1,'One','B',20,0.8)]),[units,rate,stock],['customer','channel']));
    expect(p.rows[0].totals).toEqual({ 'm.units': 30 });
    expect(p.columnTotals).toEqual({ v0_0: 10, v1_0: 20 });
    expect(p.grand).toEqual({ 'm.units': 123, 'm.rate': 0.6, 'm.stock': 80 });
  });
  it('does not turn an all-null additive total into zero', () => {
    const p = value(pivotRows(answer([row(1,'One','A',null)]),[units],['customer','channel']));
    expect(p.rows[0].totals['m.units']).toBeNull(); expect(p.columnTotals.v0_0).toBeNull();
  });
  it('suppresses marginals from truncated input, keeping server totals', () => {
    const p = value(pivotRows({ ...answer([row(1,'One','A',10)]), truncated: true },[units],['customer','channel']));
    expect(p.additive).toEqual([]); expect(p.columnTotals).toEqual({}); expect(p.grand['m.units']).toBe(123);
  });
  it('allows 24 column categories, refuses 25 (even equal labels keyed separately)', () => {
    const resp = answer(Array.from({length:25},(_,i) => row(i,'Same','A',i)));
    expect(pivotRows({ ...resp, rows: resp.rows.slice(0,24) },[units],['channel','customer']).ok).toBe(true);
    expect(pivotRows(resp,[units],['channel','customer'])).toEqual({ok:false,reason:'Too many columns; filter or swap'});
  });
  it('sorts periods by bucket dates rather than value-sort order', () => {
    const resp = answer([
      {bucket_key:'2026-W02',bucket_start:'2026-01-05',bucket_end:'2026-01-11','m.units':30},
      {bucket_key:'2026-W01',bucket_start:'2025-12-29',bucket_end:'2026-01-04','m.units':5},
    ],[period]);
    expect(value(grainRows(resp,'period')).map((r) => r.__label)).toEqual(['2026-W01','2026-W02']);
  });
  it('keeps semantic rates separate from formatter units and titles the denominator', () => {
    const perWeek = { ...units, unit:'units_per_week', label:'Velocity' };
    expect(semanticUnit(perWeek)).not.toBe(semanticUnit(units));
    expect(measureHeading(perWeek)).toBe('Velocity (units/week)');
  });
  it('normalizes stale axis assignments and honors a swapped right axis', () => {
    expect(dualSeries([units,rate]).map((s) => s.axis)).toEqual(['left','right']);
    expect(dualSeries([units,rate],{series:{'m.units':{axis:'right'},'m.rate':{axis:'right'}}}).map((s) => s.axis)).toEqual(['right','left']);
  });
});
```

Extend existing `fit.test.ts`: replace “SHOULD visuals are not offered yet” with fit acceptance
for `[units, rate]/[period]` dual, `[units, rate]/[customer]` scatter, `[units]/[customer,channel]`
pivot. Assert rejects: dual with equal raw units, three measures, two breakdowns; scatter period,
one measure, two categories; pivot one/three breakdowns. Assert `effectiveVisualV2('dual_axis',...)`
retains dual and all three appear in `visualsForV2` when valid. Use measures of the same model for
integration fixtures; pure fit tests are not permission to mix query models.

Component tests after application must prove:

* Real `V2WidgetBody` dispatch renders a scatter SVG, two differently titled axes, and a reshaped
  pivot, rather than the old shared table fallback. Render actual Recharts with a deterministic
  640x320 ResizeObserver mock; do not mock all three components and call it chart proof.
* Dual test uses units=10 and ratio=.25, then asserts 25% in tooltip/hidden table and no unit mixing.
  A negative bar remains visible; right axis belongs to the correct swapped measure after save/reopen.
* Scatter full-name tooltip, numeric X/Y axes, zero/negative dots, omitted count. Keyboard details
  button Enter calls onSelect with the exact id; a null entity never invokes it; same labels retain
  separate targets. Click through real mark payload to catch Recharts' payload wrapping behavior.
* Pivot uses AG Grid's normal columns with at least two measures and two equal-named identities;
  distinct row ids; filter a focused cell with Enter and pointer, grand/marginal rows no-op. At 25
  categories refusal text is visible. Period selection contains bucket start/end.
* Editor save/reopen retains right-axis assignment, scatter axes order and swapped pivot breakdowns.
* PNG caption text contains both axis titles/units; pivot PNG action disabled; CSV remains guarded
  raw long-form data with rate denominator headings.

Suggested focused invocation once source is applied:
`pnpm --filter @cip/web exec vitest run src/features/dashboards/builder/advancedShape.test.ts src/features/dashboards/builder/fit.test.ts`;
then new component files, TypeScript and normal web checks. The four complete code blocks were
extracted in memory: TypeScript transpileModule reported zero syntax diagnostics for advancedShape.ts,
ScatterPlot.tsx, PivotTable.tsx and advancedShape.test.ts. This is syntax checking only, not test
execution or a type-check PASS. No product tests were executed against proposed code. No UI claim
is made from source inspection.
Rendered acceptance still requires browser automation on the live lab/app (390px and desktop, both
themes, Tab/Enter/Esc, re-open persistence, export), handled by root's later independent verification.
