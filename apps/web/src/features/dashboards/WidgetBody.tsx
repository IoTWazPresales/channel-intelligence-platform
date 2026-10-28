'use client';

import { Alert, Box, Skeleton, Typography } from '@mui/material';
import type { ColDef } from 'ag-grid-community';
import { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { HeadlineFigure } from '@/features/workbench-ui/HeadlineFigure';
import { safeDisplayError } from '@/lib/api';

import type { QueryResult, WidgetVisual } from './types';
import { WidgetChart } from './WidgetChart';
import { effectiveVisual, formatValue, metricUnit, tableColumns } from './widgetModel';

type Props = {
  metricKey: string;
  metricLabel: string;
  formula?: string;
  visual: WidgetVisual;
  grains: string[];
  result: QueryResult | undefined;
  loading: boolean;
  error: unknown;
  /** Suffix for test ids: the widget id on the canvas, "preview" in the editor. */
  testKey: string | number;
  chartHeight?: number;
};

/** What a widget shows for one query result: a number, a table or a chart. Shared by the canvas and the editor preview. */
export function WidgetBody({ metricKey, metricLabel, formula, visual: saved, grains, result, loading, error, testKey, chartHeight }: Props) {
  const unit = metricUnit(metricKey, formula);
  // A saved visual that does not suit the breakdown (e.g. a line over customers) falls back to one that does.
  const visual = effectiveVisual(saved, grains);
  const colDefs = useMemo<ColDef[]>(
    () =>
      tableColumns(result?.rows ?? null).map((c) => ({
        ...c,
        flex: c.field === 'value' ? 0.6 : 1,
        ...(c.field === 'value' ? { type: 'numericColumn', valueFormatter: (p: { value: unknown }) => formatValue(p.value, unit) } : {}),
      })),
    [result?.rows, unit],
  );

  if (loading) {
    return (
      <Box
        role="status"
        aria-label="Loading"
        aria-busy
        data-testid={`dashboard-widget-loading-${testKey}`}
        sx={{ p: 1, display: 'flex', alignItems: 'flex-end', gap: 1, height: Math.max(96, (chartHeight ?? 180) - 24) }}
      >
        {(visual === 'table' ? [88, 72, 60, 48] : [40, 65, 50, 80, 55, 70, 45, 90]).map((h, i) => (
          <Skeleton key={i} animation="wave" variant="rounded" sx={{ flex: visual === 'table' ? undefined : 1, width: visual === 'table' ? `${h}%` : undefined }} height={visual === 'table' ? 12 : `${h}%`} />
        ))}
      </Box>
    );
  }
  if (error) return <Alert severity="error">{safeDisplayError(error)}</Alert>;
  if (!result) return null;
  if (!result.ok) {
    return (
      <Alert severity="warning" data-testid={`dashboard-widget-refused-${testKey}`}>
        {result.message || result.validation?.message || result.status}
      </Alert>
    );
  }
  if (visual === 'kpi') {
    return <HeadlineFigure compact label={metricLabel} value={formatValue(result.value, unit)} testId={`dashboard-widget-value-${testKey}`} />;
  }
  if (visual === 'table') {
    return <EnterpriseDataGrid rowData={result.rows ?? []} columnDefs={colDefs} height="100%" />;
  }
  return <WidgetChart visual={visual} grains={grains} series={result.series} rows={result.rows} unit={unit} metricLabel={metricLabel} height={chartHeight} />;
}
