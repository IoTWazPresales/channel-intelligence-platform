'use client';

/**
 * What a v2 widget shows for one answer (spec s.4, s.6): a KPI with compare and trend, a table with
 * colour rules, or one of the shared N-0114 charts, plus every state (skeleton, refused, error with
 * Retry, empty with Clear filters). Used by the dashboard card, full screen and the editor preview.
 */

import { Alert, Box, Button, Skeleton, Stack, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { useMemo, type ReactNode } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { HeadlineFigure } from '@/features/workbench-ui/HeadlineFigure';
import {
  CategoryBars,
  RankedBars,
  ScatterPlot,
  ShareChart,
  TrendChart,
  axisTitle,
  formatChartValue,
  type ChartClickEvent,
  type MeasureUnit,
} from '@/features/workbench-ui/charts';
import { safeDisplayError } from '@/lib/api';

import type { WidgetVisual } from '../types';
import { breakdownLabel, chartUnit, definitionMeasures, measureOf, measureUnit, isRatio, isAdditive } from './catalog';
import { ComparisonChart } from './ComparisonChart';
import { mergeComparison, type ComparisonData } from './comparison';
import type { SelectDatum } from './clickFilters';
import { kpiDelta } from './dates';
import { effectiveVisualV2 } from './fit';
import { dualSeries, grainRows, measureHeading, pivotRows, scatterRows } from './advancedShape';
import { PivotTable } from './PivotTable';
import { breakdownColumns, categoryPoints, catOf, periodByCategory, periodRows, type Cat } from './shape';
import { cellValue, matchRule, ruleText, tableCols, type TableCol } from './table';
import type { CatalogV2, ColourRule, DefinitionV2, V2Response, V2Row } from './types';

export type KpiExtras = {
  compare?: V2Response;
  /** "vs previous period" */
  compareLabel?: string;
  sparkline?: V2Response;
};

export type V2WidgetBodyProps = {
  def: DefinitionV2;
  visual: WidgetVisual;
  catalog: CatalogV2 | null | undefined;
  result: V2Response | undefined;
  loading: boolean;
  error: unknown;
  onRetry?: () => void;
  kpi?: KpiExtras;
  comparison?: ComparisonData;
  /** Caption under a KPI ("Latest report on or before 2026-10-09."). */
  caption?: string;
  onSelect?: (d: SelectDatum, additive: boolean) => void;
  /** Chip keys ("customer:18") that are active, to mark selected legend items. */
  selectedKeys?: string[];
  /** Shown in the empty state: "for Makro in the last 13 weeks". */
  emptyContext?: string;
  onClearFilters?: () => void;
  testKey: string | number;
  chartHeight?: number;
};

const additiveClick = (e: ChartClickEvent) => Boolean(e && ('ctrlKey' in e || 'metaKey' in e) && ((e as MouseEvent).ctrlKey || (e as MouseEvent).metaKey));

function LoadingSkeleton({ visual, height }: { visual: WidgetVisual; height: number }) {
  const label = 'Loading';
  if (visual === 'kpi') {
    return (
      <Box role="status" aria-label={label} aria-busy sx={{ p: 1 }} data-testid="widget-skeleton" data-shape="kpi">
        <Skeleton variant="text" width="40%" />
        <Skeleton variant="rounded" width="60%" height={32} sx={{ mt: 0.5 }} />
        <Skeleton variant="text" width="30%" />
      </Box>
    );
  }
  if (visual === 'hbar' || visual === 'table') {
    return (
      <Stack role="status" aria-label={label} aria-busy spacing={1} sx={{ p: 1 }} data-testid="widget-skeleton" data-shape={visual}>
        {[92, 76, 64, 48, 36, 24].map((w) => (
          <Skeleton key={w} variant="rounded" height={14} width={`${w}%`} />
        ))}
      </Stack>
    );
  }
  if (visual === 'pie' || visual === 'donut') {
    return (
      <Stack role="status" aria-label={label} aria-busy direction="row" spacing={2} alignItems="center" sx={{ p: 1 }} data-testid="widget-skeleton" data-shape="share">
        <Skeleton variant="circular" width={Math.min(140, height - 40)} height={Math.min(140, height - 40)} />
        <Stack spacing={1} sx={{ flex: 1 }}>
          {[80, 60, 50, 40].map((w) => (
            <Skeleton key={w} variant="text" width={`${w}%`} />
          ))}
        </Stack>
      </Stack>
    );
  }
  return (
    <Box role="status" aria-label={label} aria-busy sx={{ p: 1, display: 'flex', alignItems: 'flex-end', gap: 1, height: Math.max(120, height - 40) }} data-testid="widget-skeleton" data-shape="chart">
      {[40, 65, 50, 80, 55, 70, 45, 90, 60, 75].map((h, i) => (
        <Skeleton key={i} variant="rounded" sx={{ flex: 1 }} height={`${h}%`} />
      ))}
    </Box>
  );
}

function StatePanel({ tone, title, children, testId, action }: { tone: 'warning' | 'error' | 'info'; title?: string; children: ReactNode; testId: string; action?: ReactNode }) {
  return (
    <Alert severity={tone} variant="outlined" action={action} data-testid={testId} sx={{ '& .MuiAlert-message': { minWidth: 0, overflowWrap: 'anywhere' } }}>
      {title ? (
        <Typography variant="body2" fontWeight={700} component="div">
          {title}
        </Typography>
      ) : null}
      {children}
    </Alert>
  );
}

function ToneCell(props: ICellRendererParams & { rules?: ColourRule[]; measureId: string; unit: MeasureUnit }) {
  const theme = useTheme();
  const v = typeof props.value === 'number' ? props.value : null;
  const rule = matchRule(props.rules, props.measureId, v);
  const text = formatChartValue(v, props.unit, 'full');
  if (!rule) return <span>{text}</span>;
  const color = rule.tone === 'good' ? theme.palette.success.main : rule.tone === 'warn' ? theme.palette.warning.main : theme.palette.error.main;
  const marker = ruleText(rule);
  return (
    <Box
      component="span"
      aria-label={`${text}. ${marker}`}
      title={marker}
      data-tone={rule.tone}
      data-testid="table-tone-cell"
      sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75, width: '100%', justifyContent: 'flex-end', px: 0.75, borderRadius: 0.5, bgcolor: alpha(color, theme.palette.mode === 'dark' ? 0.22 : 0.14) }}
    >
      <Box component="span" aria-hidden sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: color, flexShrink: 0 }} />
      <Box component="span" aria-hidden sx={{ color: 'text.primary', fontVariantNumeric: 'tabular-nums' }}>
        {text}
      </Box>
    </Box>
  );
}

/** AG Grid columns for a v2 answer: names only, units in headers, tone cells for colour rules. */
export function gridColumns(cols: TableCol[], rules: ColourRule[] | undefined): ColDef<V2Row>[] {
  return cols.map((c) => {
    if (c.kind !== 'measure') {
      return { field: c.field, headerName: c.header, flex: 1, minWidth: 120, valueGetter: (p) => (p.data ? cellValue(p.data, c) : null) };
    }
    const unit = c.unit ?? 'number';
    const hasRule = (rules ?? []).some((r) => r.measure === c.id);
    return {
      field: c.field,
      headerName: c.header,
      type: 'numericColumn',
      flex: 0.7,
      minWidth: 110,
      valueGetter: (p) => (p.data ? cellValue(p.data, c) : null),
      valueFormatter: (p) => formatChartValue(typeof p.value === 'number' ? p.value : null, unit, 'full'),
      ...(hasRule ? { cellRenderer: ToneCell, cellRendererParams: { rules, measureId: c.id, unit } } : {}),
    } as ColDef<V2Row>;
  });
}

export function V2WidgetBody(props: V2WidgetBodyProps) {
  const { def, catalog, result, loading, error, onRetry, kpi, caption, onSelect, selectedKeys, emptyContext, onClearFilters, testKey } = props;
  const height = props.chartHeight ?? 240;
  const measures = definitionMeasures(catalog, def);
  const breakdowns = def.query.breakdowns ?? [];
  const visual = effectiveVisualV2(props.visual, measures, breakdowns);
  const measureIds = def.query.measures;
  const first = measures[0] ?? measureOf(catalog, measureIds[0] ?? '');
  const unit = measureUnit(first);
  const firstLabel = first?.label ?? measureIds[0] ?? 'Value';
  const compared = useMemo(() => props.comparison?.result?.ok && result?.ok
    ? mergeComparison(result, props.comparison.result, def, props.comparison.window, props.comparison.previousWindow, props.comparison.label) : null,
    [result, props.comparison, def]);
  const displayed = compared?.ok ? compared.response : result;
  const comparisonNote = props.comparison ? props.comparison.loading || props.comparison.stale ? 'Updating comparison…'
    : props.comparison.error ? `Comparison could not load: ${safeDisplayError(props.comparison.error)}`
    : compared?.note ?? (props.comparison.result && !props.comparison.result.ok ? 'Comparison was refused; current figures remain visible.' : undefined) : undefined;
  const tcols = useMemo(
    () => tableCols(displayed, (c) => measureOf(catalog, c.id) ? measureUnit(measureOf(catalog, c.id)) : chartUnit(c.unit)),
    [displayed, catalog],
  );
  const colDefs = useMemo(() => gridColumns(tcols, def.display?.table?.rules), [tcols, def.display?.table?.rules]);

  if (!catalog || measures.length !== measureIds.length) {
    return <StatePanel tone="warning" testId={`dashboard-widget-model-unavailable-${testKey}`}>
      The data model for this widget is unavailable. Reload the data model to see this figure.
    </StatePanel>;
  }
  if (loading && !result) return <LoadingSkeleton visual={visual} height={height} />;
  if (error && !result) {
    return (
      <StatePanel
        tone="error"
        title="This widget could not load."
        testId={`dashboard-widget-error-${testKey}`}
        action={
          onRetry ? (
            <Button color="inherit" size="small" onClick={onRetry} data-testid={`dashboard-widget-retry-${testKey}`}>
              Retry
            </Button>
          ) : undefined
        }
      >
        {safeDisplayError(error)}
      </StatePanel>
    );
  }
  if (!result) return null;
  if (!result.ok) {
    const reasons = [...new Set(result.refusals.map((r) => r.reason))];
    return (
      <StatePanel tone="warning" title="This figure is refused." testId={`dashboard-widget-refused-${testKey}`}>
        {reasons.length ? (
          <Box component="ul" sx={{ m: 0, pl: 2 }}>
            {reasons.map((r) => (
              <li key={r}>
                <Typography variant="body2">{r}</Typography>
              </li>
            ))}
          </Box>
        ) : (
          <Typography variant="body2">The server refused this query without a reason.</Typography>
        )}
      </StatePanel>
    );
  }

  const total = result.totals?.[measureIds[0] ?? ''];
  const totalNum = typeof total === 'number' ? total : total == null ? null : Number(total);
  const empty = visual === 'kpi' ? totalNum == null || (totalNum === 0 && result.rows.length === 0) : displayed?.rows.length === 0;
  if (empty) {
    return (
      <Box sx={{ p: 1 }} data-testid={`dashboard-widget-empty-${testKey}`}>
        <Typography variant="body2" color="text.secondary">
          No {firstLabel.charAt(0).toLowerCase() + firstLabel.slice(1)}
          {emptyContext ? ` ${emptyContext}` : ''}.
        </Typography>
        {onClearFilters ? (
          <Button size="small" sx={{ mt: 1 }} onClick={onClearFilters} data-testid={`dashboard-widget-clear-filters-${testKey}`}>
            Clear filters
          </Button>
        ) : null}
      </Box>
    );
  }

  const select = (c: Cat | null | undefined, e: ChartClickEvent) => {
    if (!c || !onSelect) return;
    onSelect({ breakdown: c.breakdown, value: c.value, label: c.label, window: c.window }, additiveClick(e));
  };
  const selectParts = (parts: Cat[], e: ChartClickEvent) => {
    for (const p of parts) select(p, e);
  };

  if (visual === 'kpi') {
    const prevRaw = kpi?.compare?.ok ? kpi.compare.totals?.[measureIds[0] ?? ''] : undefined;
    const prev = typeof prevRaw === 'number' ? prevRaw : null;
    const delta = kpi?.compare ? kpiDelta(totalNum, prev, { ratio: isRatio(first) }) : null;
    const spark = kpi?.sparkline?.ok ? periodRows(kpi.sparkline, [measureIds[0]]) : [];
    const values = spark.map((r) => (typeof r[measureIds[0]] === 'number' ? (r[measureIds[0]] as number) : 0));
    return (
      <HeadlineFigure
        compact
        label={firstLabel}
        value={formatChartValue(totalNum, unit, 'label')}
        delta={
          kpi?.compare
            ? delta
              ? { text: delta.text, direction: delta.direction, period: kpi.compareLabel }
              : { text: '—', direction: 'flat', goodWhen: 'neutral', period: kpi.compareLabel }
            : undefined
        }
        caption={caption}
        sparkline={values.length > 1 ? { values, label: `${firstLabel}, ${values.length} periods` } : undefined}
        testId={`dashboard-widget-value-${testKey}`}
      />
    );
  }

  if (visual === 'table') {
    const firstBd = breakdownColumns(result)[0];
    return (
      <Stack sx={{ height: '100%', minHeight: 160 }} data-testid={`dashboard-widget-table-${testKey}`}>
        <Box sx={{ flex: 1, minHeight: 120 }}>
        <EnterpriseDataGrid<V2Row>
          rowData={displayed?.rows ?? result.rows}
          columnDefs={colDefs}
          height="100%"
          gridOptions={
            onSelect && firstBd
              ? {
                  onRowClicked: (ev) => {
                    if (!ev.data) return;
                    select(catOf(ev.data, firstBd), ev.event as MouseEvent | undefined);
                  },
                }
              : undefined
          }
        />
        </Box>
        {comparisonNote ? <Typography variant="caption" data-testid="widget-comparison-note">{comparisonNote}</Typography> : null}
      </Stack>
    );
  }

  const plotHeight = Math.max(140, height - 64);
  const valueTitle = first ? measureHeading(first) : axisTitle(firstLabel, unit);
  const hasPeriod = breakdowns.includes('period');
  const catIds = breakdowns.filter((b) => b !== 'period');
  const categoryTitle = catIds.map((b) => breakdownLabel(catalog, b)).join(' · ') || 'Category';
  const periodTitle = `Period (${def.query.period?.grain ?? 'bucket'})`;
  const frame = (child: ReactNode, note?: string | null) => (
    <Box data-testid="dashboard-widget-chart" sx={{ height, overflowY: 'auto', overflowX: 'hidden' }}>
      {child}
      {comparisonNote ? <Typography variant="caption" display="block" data-testid="widget-comparison-note">{comparisonNote}</Typography> : null}
      {note ? (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
          {note}
        </Typography>
      ) : null}
    </Box>
  );

  if (compared?.ok && catalog && (visual === 'bar' || visual === 'line' || visual === 'area')) {
    return frame(<ComparisonChart response={compared.response} def={def} measures={measures} catalog={catalog} visual={visual}
      label={props.comparison!.label} height={plotHeight} selectedKeys={selectedKeys} onSelect={onSelect ? (cat, e) => select(cat, e) : undefined} />);
  }

  if (visual === 'pivot') {
    const shaped = pivotRows(result, measures, breakdowns);
    if (!shaped.ok) return <StatePanel tone="info" testId={`dashboard-widget-refused-${testKey}`}>{shaped.reason}</StatePanel>;
    return <Box sx={{ height }}><PivotTable model={shaped.value} rowTitle={breakdownLabel(catalog, breakdowns[0])}
      onSelect={onSelect ? (parts, e) => selectParts(parts, e) : undefined} /></Box>;
  }

  if (visual === 'dual_axis' || visual === 'scatter') {
    const shaped = grainRows(result, breakdowns[0]);
    if (!shaped.ok) return <StatePanel tone="info" testId={`dashboard-widget-refused-${testKey}`}>{shaped.reason}</StatePanel>;
    const rows = shaped.value;
    const keyboard = (items: Array<{ key: string; label: string; cat: Cat }>) => onSelect ? (
      <Box component="details" sx={{ mt: 1 }}>
        <Typography component="summary" variant="caption">Filter by category</Typography>
        <Box component="ul" sx={{ m: 0, pl: 2, maxHeight: 140, overflowY: 'auto' }}>
          {items.map((item) => <li key={item.key}>{item.cat.value != null || item.cat.window ? (
            <Button size="small" onClick={(e) => select(item.cat, e)} sx={{ textTransform: 'none', textAlign: 'left' }}>{item.label}</Button>
          ) : <Typography variant="caption">{item.label} — not filterable: no id</Typography>}</li>)}
        </Box>
      </Box>
    ) : null;
    if (visual === 'scatter') {
      const points = scatterRows(rows, measureIds[0], measureIds[1]);
      return frame(<>
        {points.data.length ? <ScatterPlot data={points.data}
          xUnit={measureUnit(measures[0])} yUnit={measureUnit(measures[1])}
          xAxisTitle={measureHeading(measures[0])} yAxisTitle={measureHeading(measures[1])}
          summary={`${measureHeading(measures[1])} against ${measureHeading(measures[0])} by ${breakdownLabel(catalog, breakdowns[0])}`}
          height={plotHeight} onPointClick={onSelect ? (d, e) => select(points.data.find((p) => p.key === d.key)?.cat, e) : undefined} />
          : <Typography>No categories have both measures reported.</Typography>}
        {keyboard(points.data.map((d) => ({ ...d, label: `${d.label}: ${formatChartValue(d.x, measureUnit(measures[0]))}, ${formatChartValue(d.y, measureUnit(measures[1]))}` })))}
      </>, points.omitted ? `${points.omitted} categories omitted: both measures must be reported.` : null);
    }
    const series = dualSeries(measures, def.display);
    const left = measures.find((m) => series.find((s) => s.key === m.id)?.axis === 'left')!;
    const right = measures.find((m) => series.find((s) => s.key === m.id)?.axis === 'right')!;
    return frame(<>
      <TrendChart data={rows} x="__key" series={series}
        xTickFormat={(key) => rows.find((r) => r.__key === String(key))?.__label ?? String(key ?? '')}
        xAxisTitle={breakdownLabel(catalog, breakdowns[0])}
        yAxisTitle={measureHeading(left)} yRightAxisTitle={measureHeading(right)} height={plotHeight} yScale="fit"
        table={{ caption: 'Values by category', columns: [breakdownLabel(catalog, breakdowns[0]), ...measures.map(measureHeading)],
          rows: rows.map((r) => [r.__label, ...measures.map((m) => formatChartValue(typeof r[m.id] === 'number' ? r[m.id] as number : null, measureUnit(m)))]) }}
        onPointClick={onSelect ? (r, _i, e) => select(r.__cat as Cat, e) : undefined} />
      {keyboard(rows.map((r) => ({ key: r.__key, label: r.__label, cat: r.__cat })))}
    </>);
  }

  if (visual === 'pie' || visual === 'donut') {
    const pts = categoryPoints(result, [measureIds[0]]);
    if (pts.some((p) => (p.value ?? 0) < 0)) {
      return (
        <StatePanel tone="info" testId={`dashboard-widget-refused-${testKey}`}>
          A pie needs values of zero or more. Use ranked bars for this figure.
        </StatePanel>
      );
    }
    const unassignedEntity = pts.some((p) => p.parts.some((c) => c.value == null));
    return frame(
      <ShareChart
        data={pts.filter((p) => (p.value ?? 0) > 0).map((p) => ({ label: p.label, value: p.value ?? 0, key: p.key, clickable: p.parts.every((c) => c.value != null) }))}
        unit={unit}
        variant={visual}
        height={Math.max(140, height - 96)}
        labelHeader={categoryTitle}
        valueHeader={valueTitle}
        summary={`${valueTitle}: share by ${categoryTitle}`}
        selectedKeys={selectedKeys}
        onSliceClick={onSelect ? (d, e) => selectParts(pts.find((p) => p.key === d.key)?.parts ?? [], e) : undefined}
      />,
      unassignedEntity && onSelect ? 'Unassigned is not filterable: it has no id.' : null,
    );
  }

  if (visual === 'hbar' || (visual === 'bar' && !hasPeriod && measureIds.length === 1)) {
    const pts = categoryPoints(result, [measureIds[0]]);
    const unassignedEntity = pts.some((p) => p.parts.some((c) => c.value == null));
    const onRow = onSelect
      ? (key: string | undefined, e: ChartClickEvent) => {
          const p = pts.find((x) => x.key === key);
          if (p && p.parts.every((c) => c.value != null)) selectParts(p.parts, e);
        }
      : undefined;
    const note = unassignedEntity && onSelect ? 'Unassigned is not filterable: it has no id.' : null;
    if (visual === 'hbar') {
      return frame(
        <RankedBars
          data={pts.map((p) => ({ label: p.label, value: p.value, key: p.key, tone: 'primary' as const }))}
          unit={unit}
          sort="desc"
          max={def.display?.top_n ?? 15}
          summary={`${valueTitle} by ${categoryTitle}, biggest first`}
          labelHeader={categoryTitle}
          valueHeader={valueTitle}
          xAxisTitle={categoryTitle}
          yAxisTitle={valueTitle}
          rowHeight={26}
          onRowClick={onRow ? (d, e) => onRow(d.key, e) : undefined}
        />,
        note,
      );
    }
    return frame(
      <CategoryBars
        data={pts.map((p) => ({ label: p.label, value: p.value, key: p.key }))}
        x="label"
        y="value"
        height={plotHeight}
        unit={unit}
        xAxisTitle={categoryTitle}
        yAxisTitle={valueTitle}
        onRowClick={onRow ? (row, e) => onRow(String(row.key), e) : undefined}
      />,
      note,
    );
  }

  // Over time split by one category: line, stacked area or stacked columns, a series per category.
  if (hasPeriod && catIds.length === 1 && measureIds.length === 1) {
    const m = periodByCategory(result, measureIds[0], def.display?.top_n ?? 7, isAdditive(first));
    const kind = visual === 'stacked_bar' || visual === 'bar' ? 'bar' : visual === 'area' ? 'area' : 'line';
    return frame(
      <TrendChart
        data={m.data}
        x="period"
        height={plotHeight}
        unit={unit}
        xAxisTitle={periodTitle}
        yAxisTitle={valueTitle}
        stack={kind !== 'line'}
        series={m.series.map((s) => ({ key: s.key, label: s.label, kind, clickable: Boolean(s.cat && s.cat.value != null), ...(s.other ? { tone: 'muted' as const } : {}) }))}
        selectedSeries={m.series.filter((s) => s.cat && selectedKeys?.includes(s.cat.key)).map((s) => s.key)}
        onSeriesClick={onSelect ? (key, e) => select(m.series.find((s) => s.key === key)?.cat, e) : undefined}
        onPointClick={onSelect ? (row, _i, e) => select(periodCat(row), e) : undefined}
      />,
      m.omittedSeries ? `${m.series.length} categories shown; ${m.omittedSeries} not shown. Narrow the filters to see the others.` : null,
    );
  }

  // One or two measures over periods, or two measures over one category (columns / combo).
  const seriesKinds = (i: number, id: string): 'bar' | 'line' | 'area' => {
    const stored = def.display?.series?.[id]?.kind;
    if (visual === 'combo') return stored ?? (i === 0 ? 'bar' : 'line');
    if (visual === 'bar' || visual === 'stacked_bar') return 'bar';
    if (visual === 'area') return 'area';
    return 'line';
  };
  const series = measureIds.map((id, i) => ({ key: id, label: measureOf(catalog, id)?.label ?? id, kind: seriesKinds(i, id) }));
  const valueAxis = measureIds.length > 1 ? axisTitle(series.map((s) => s.label).join(' / '), unit) : valueTitle;
  if (hasPeriod) {
    const data = periodRows(result, measureIds);
    return frame(
      <TrendChart
        data={data}
        x="period"
        height={plotHeight}
        unit={unit}
        xAxisTitle={periodTitle}
        yAxisTitle={valueAxis}
        series={series}
        onPointClick={onSelect ? (row, _i, e) => select(periodCat(row), e) : undefined}
      />,
    );
  }
  const pts = categoryPoints(result, measureIds);
  const data = pts.map((p) => ({ label: p.label, __key: p.key, ...p.values }));
  return frame(
    <TrendChart
      data={data}
      x="label"
      height={plotHeight}
      unit={unit}
      xAxisTitle={categoryTitle}
      yAxisTitle={valueAxis}
      series={series}
      onPointClick={
        onSelect
          ? (row, _i, e) => {
              const p = pts.find((x) => x.key === row.__key);
              if (p && p.parts.every((c) => c.value != null)) selectParts(p.parts, e);
            }
          : undefined
      }
    />,
  );
}

function periodCat(row: Record<string, unknown>): Cat | null {
  const from = typeof row.bucket_start === 'string' ? row.bucket_start : null;
  const to = typeof row.bucket_end === 'string' ? row.bucket_end : null;
  const k = String(row.period ?? '');
  if (!from || !to) return null;
  return { key: `period:${k}`, breakdown: 'period', value: k, label: k, window: { from, to } };
}
