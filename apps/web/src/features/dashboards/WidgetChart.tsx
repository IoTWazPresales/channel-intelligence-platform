'use client';

import { CategoryBars, TrendChart } from '@/features/workbench-ui/charts';

import { rowCategoryLabel } from './formatters';
import type { SeriesPoint, WidgetVisual } from './types';

type Props = {
  visual: Extract<WidgetVisual, 'bar' | 'line' | 'area'>;
  series: SeriesPoint[] | null;
  rows: Record<string, unknown>[] | null;
};

export function WidgetChart({ visual, series, rows }: Props) {
  const fromSeries = (series ?? []).map((p) => ({
    label: p.bucket_key,
    value: Number(p.value),
  }));
  const fromRows = (rows ?? []).map((r) => ({
    label: rowCategoryLabel(r),
    value: Number(r.value ?? 0),
  }));
  const points = fromSeries.length ? fromSeries : fromRows;

  if (visual === 'bar') {
    return (
      <div data-testid="dashboard-widget-chart">
        <CategoryBars data={points} x="label" y="value" height={220} compact />
      </div>
    );
  }

  return (
    <div data-testid="dashboard-widget-chart">
      <TrendChart
        data={points}
        x="label"
        height={220}
        legend={false}
        series={[{ key: 'value', label: 'Value', kind: visual === 'area' ? 'area' : 'line' }]}
      />
    </div>
  );
}
