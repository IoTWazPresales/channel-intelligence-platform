'use client';

import { useTheme } from '@mui/material/styles';
import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

import { rowCategoryLabel } from './formatters';
import type { SeriesPoint, WidgetVisual } from './types';

echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

type Props = {
  visual: Extract<WidgetVisual, 'bar' | 'line' | 'area'>;
  series: SeriesPoint[] | null;
  rows: Record<string, unknown>[] | null;
};

export function WidgetChart({ visual, series, rows }: Props) {
  const theme = useTheme();
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    const chart = echarts.init(el);
    chartRef.current = chart;
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const fromSeries = (series ?? []).map((p) => ({
      label: p.bucket_key,
      value: Number(p.value),
    }));
    const fromRows = (rows ?? []).map((r) => ({
      label: rowCategoryLabel(r),
      value: Number(r.value ?? 0),
    }));
    const points = fromSeries.length ? fromSeries : fromRows;
    const color = theme.palette.primary.main;
    const text = theme.palette.text.secondary;
    const isBar = visual === 'bar';
    chart.setOption(
      {
        color: [color],
        tooltip: { trigger: 'axis' },
        grid: { left: 48, right: 16, top: 16, bottom: 32 },
        xAxis: {
          type: 'category',
          data: points.map((p) => p.label),
          axisLabel: { color: text, hideOverlap: true },
        },
        yAxis: { type: 'value', axisLabel: { color: text } },
        series: [
          {
            type: isBar ? 'bar' : 'line',
            data: points.map((p) => p.value),
            areaStyle: visual === 'area' ? { opacity: 0.18 } : undefined,
            smooth: !isBar,
            showSymbol: points.length <= 24,
          },
        ],
      },
      true
    );
  }, [visual, series, rows, theme]);

  return <div ref={hostRef} data-testid="dashboard-widget-chart" style={{ width: '100%', height: '100%' }} />;
}
