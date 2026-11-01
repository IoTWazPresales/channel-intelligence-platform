'use client';

import { Alert, Box, Skeleton, Typography } from '@mui/material';
import type { ColDef } from 'ag-grid-community';
import { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ChartControls, useChartControls } from '@/features/workbench-ui/ChartControls';
import { applyTopN, sortRows } from '@/features/workbench-ui/chartRows';
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
  fitHeight?: number;
};

/** What a widget shows for one query result: a number, a table or a chart. Shared by the canvas and the editor preview. */
export function WidgetBody({ metricKey, metricLabel, formula, visual: saved, grains, result, loading, error, testKey, chartHeight, fitHeight }: Props) {
  const unit = metricUnit(metricKey, formula);
  // A saved visual that does not suit the breakdown (e.g. a line over customers) falls back to one that does.
  const visual = effectiveVisual(saved, grains);
  const colDefs = useMemo<ColDef[]>(
    () =>
      tableColumns(result?.rows ?? null, metricLabel).map((c) => ({
        ...c,
        flex: c.field === 'value' ? 0.6 : 1,
        ...(c.field === 'value' ? { type: 'numericColumn', valueFormatter: (p: { value: unknown }) => formatValue(p.value, unit) } : {}),
      })),
    [metricLabel, result?.rows, unit],
  );
  const tableCtl = useChartControls({ topN: 10, sort: { by: 'value', dir: 'desc' } }, visual === 'table');
  const tableView = useMemo(() => {
    const rows = result?.rows ?? [];
    const sorted = sortRows(rows, tableCtl.state.sort, {
      name: (r) => String(r.customer_name ?? r.distributor_name ?? r.product_name ?? r.bucket_key ?? ''),
      value: (r) => (typeof r.value === 'number' ? r.value : Number(r.value)),
    });
    return applyTopN(sorted, tableCtl.state.topN);
  }, [result?.rows, tableCtl.state]);

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
    return (
      <Box data-testid={`dashboard-widget-table-${testKey}`}>
        <ChartControls value={tableCtl.state} onChange={tableCtl.setState} shown={tableView.shown.length} total={tableView.total} testId={`dashboard-table-controls-${testKey}`} />
        <EnterpriseDataGrid rowData={tableView.shown} columnDefs={colDefs} height="100%" />
      </Box>
    );
  }
  return <WidgetChart visual={visual} grains={grains} series={result.series} rows={result.rows} unit={unit} metricLabel={metricLabel} height={chartHeight} fitHeight={fitHeight} />;
}
