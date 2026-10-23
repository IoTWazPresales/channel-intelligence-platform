'use client';

import { Box, Typography } from '@mui/material';
import type { ReactNode } from 'react';

import { dimensionLabel } from '@/features/reports/reportPresentation';
import { CategoryBars, RankedBars, ShareChart, TrendChart, axisTitle, type MeasureUnit } from '@/features/workbench-ui/charts';

import type { SeriesPoint, WidgetVisual } from './types';
import { TOP_N, categoryPoints, periodByCategory, periodPoints } from './widgetModel';

type Props = {
  visual: WidgetVisual;
  grains: string[];
  series: SeriesPoint[] | null;
  rows: Record<string, unknown>[] | null;
  unit?: MeasureUnit;
  /** Metric name for the value axis ("Sell-out units"); the unit is added to it. */
  metricLabel?: string;
  height?: number;
};

/**
 * A dashboard widget drawn with the shared charts (N-0114): axis titles from the breakdown and the
 * metric, the viewer's own top N and sort on category bars and pies (no folded "Other" there; pie
 * shares are of the full total), a legend whenever there is more than one series. Charts over time
 * split by a category keep the seven-series colour cap with "Other" (`periodByCategory`).
 */
export function WidgetChart({ visual, grains, series, rows, unit = 'number', metricLabel = 'Value', height = 240 }: Props) {
  const hasPeriod = grains.includes('period');
  const categoryGrains = grains.filter((g) => g !== 'period');
  const hasCategory = categoryGrains.length > 0;
  const categoryTitle = categoryGrains.map(dimensionLabel).join(' · ') || 'Category';
  const valueTitle = axisTitle(metricLabel, unit);
  // Toolbar, legend and axis captions sit above and below the plot; the widget box scrolls rather than clips.
  const plotHeight = Math.max(140, height - 64);

  if (!(rows?.length || series?.length)) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="dashboard-widget-chart">
        No data for this selection.
      </Typography>
    );
  }

  const frame = (child: ReactNode) => (
    <Box data-testid="dashboard-widget-chart" sx={{ height, overflowY: 'auto', overflowX: 'hidden' }}>
      {child}
    </Box>
  );

  // Share of a whole: one category, legend with full names, value and share of the full total.
  if (visual === 'pie' || visual === 'donut') {
    const pts = categoryPoints(rows).filter((p) => p.value > 0);
    return frame(
      <ShareChart
        data={pts}
        unit={unit}
        variant={visual}
        height={Math.max(140, height - 96)}
        labelHeader={categoryTitle}
        valueHeader={valueTitle}
        summary={`${valueTitle}: share by ${categoryTitle}`}
      />,
    );
  }

  // Ranked bars or columns: one category, the viewer picks how many and in which order.
  if (visual === 'hbar' || (visual === 'bar' && hasCategory && !hasPeriod)) {
    const pts = categoryPoints(rows);
    if (visual === 'hbar') {
      return frame(
        <RankedBars
          data={pts.map((p) => ({ label: p.label, value: p.value, tone: 'primary' as const }))}
          unit={unit}
          sort="desc"
          max={TOP_N}
          summary={`${valueTitle} by ${categoryTitle}, biggest first`}
          labelHeader={categoryTitle}
          valueHeader={valueTitle}
          xAxisTitle={categoryTitle}
          yAxisTitle={valueTitle}
          rowHeight={26}
        />,
      );
    }
    return frame(
      <CategoryBars
        data={pts}
        x="label"
        y="value"
        height={plotHeight}
        unit={unit}
        xAxisTitle={categoryTitle}
        yAxisTitle={valueTitle}
      />,
    );
  }

  // Over time, split by one category: a line, stacked area or stacked column per category.
  if (hasPeriod && hasCategory && (visual === 'line' || visual === 'stacked_bar' || visual === 'area')) {
    const m = periodByCategory(rows);
    const kind = visual === 'stacked_bar' ? 'bar' : visual === 'area' ? 'area' : 'line';
    return frame(
      <TrendChart
        data={m.data}
        x="period"
        height={plotHeight}
        unit={unit}
        xAxisTitle="Period"
        yAxisTitle={valueTitle}
        stack={kind !== 'line'}
        series={m.keys.map((k) => ({ key: k.key, label: k.label, kind, ...(k.other ? { tone: 'muted' as const } : {}) }))}
      />,
    );
  }

  // Over time, one series.
  const pts = periodPoints(series, rows);
  const kind = visual === 'bar' || visual === 'stacked_bar' ? 'bar' : visual === 'area' ? 'area' : 'line';
  return frame(
    <TrendChart
      data={pts}
      x="label"
      height={plotHeight}
      unit={unit}
      xAxisTitle="Period"
      yAxisTitle={valueTitle}
      series={[{ key: 'value', label: metricLabel, kind }]}
    />,
  );
}
