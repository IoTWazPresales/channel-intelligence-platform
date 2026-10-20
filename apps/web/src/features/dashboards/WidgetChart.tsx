'use client';

import { Box, Stack, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { RankedBars, type MeasureUnit } from '@/features/workbench-ui/charts';

import type { SeriesPoint, WidgetVisual } from './types';
import {
  PIE_SLICES,
  TOP_N,
  categoryPoints,
  formatValue,
  periodByCategory,
  periodPoints,
  topWithOther,
} from './widgetModel';

/** Categorical slots in fixed order (validated light/dark pairs); "Other" is always neutral grey. */
const SERIES_LIGHT = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
const SERIES_DARK = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'];

type Props = {
  visual: WidgetVisual;
  grains: string[];
  series: SeriesPoint[] | null;
  rows: Record<string, unknown>[] | null;
  unit?: MeasureUnit;
  height?: number;
};

export function WidgetChart({ visual, grains, series, rows, unit = 'number', height = 240 }: Props) {
  const theme = useTheme();
  const dark = theme.palette.mode === 'dark';
  const palette = dark ? SERIES_DARK : SERIES_LIGHT;
  const other = theme.palette.text.disabled;
  const axis = { fill: theme.palette.text.secondary, fontSize: 11 };
  const grid = theme.palette.divider;
  const fmt = (v: number) => formatValue(v, unit);
  const tooltip = {
    contentStyle: {
      background: theme.palette.background.paper,
      border: `1px solid ${theme.palette.divider}`,
      borderRadius: 8,
      fontSize: 12,
    },
    labelStyle: { color: theme.palette.text.primary, fontWeight: 600 },
    itemStyle: { color: theme.palette.text.secondary },
    formatter: (v: unknown) => fmt(Number(v)),
  };
  const hasPeriod = grains.includes('period');
  const hasCategory = grains.some((g) => g !== 'period');

  if (!(rows?.length || series?.length)) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="dashboard-widget-chart">
        No data for this selection.
      </Typography>
    );
  }

  // Share of a whole: one category, few slices, labelled in the legend with value and %.
  if (visual === 'pie' || visual === 'donut') {
    const pts = topWithOther(categoryPoints(rows), PIE_SLICES).filter((p) => p.value > 0);
    const total = pts.reduce((a, p) => a + p.value, 0) || 1;
    return (
      <Stack direction="row" spacing={2} alignItems="center" data-testid="dashboard-widget-chart" sx={{ height }}>
        <Box sx={{ flex: '0 0 50%', height: '100%' }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={pts}
                dataKey="value"
                nameKey="label"
                innerRadius={visual === 'donut' ? '55%' : 0}
                outerRadius="90%"
                stroke={theme.palette.background.paper}
                strokeWidth={2}
                isAnimationActive={false}
              >
                {pts.map((p, i) => (
                  <Cell key={p.label} fill={p.other ? other : palette[i % palette.length]} />
                ))}
              </Pie>
              <Tooltip {...tooltip} />
            </PieChart>
          </ResponsiveContainer>
        </Box>
        <Stack spacing={0.5} sx={{ flex: 1, minWidth: 0 }} aria-label="Share by category">
          {pts.map((p, i) => (
            <Stack key={p.label} direction="row" spacing={1} alignItems="center">
              <Box sx={{ width: 10, height: 10, borderRadius: '2px', flexShrink: 0, bgcolor: p.other ? other : palette[i % palette.length] }} />
              <Typography variant="caption" noWrap sx={{ flex: 1, minWidth: 0 }} title={p.label}>
                {p.label}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
                {fmt(p.value)} · {((p.value / total) * 100).toFixed(0)}%
              </Typography>
            </Stack>
          ))}
        </Stack>
      </Stack>
    );
  }

  // Ranked bars: one category, biggest first, names readable.
  if (visual === 'hbar' || (visual === 'bar' && hasCategory && !hasPeriod)) {
    const pts = topWithOther(categoryPoints(rows), TOP_N);
    if (visual === 'hbar') {
      return (
        <Box data-testid="dashboard-widget-chart">
          <RankedBars
            data={pts.map((p) => ({ label: p.label, value: p.value, tone: p.other ? 'muted' : 'primary' }))}
            format={fmt}
            sort="none"
            max={TOP_N}
            summary="Values by category, biggest first"
            rowHeight={26}
          />
        </Box>
      );
    }
    return (
      <Box data-testid="dashboard-widget-chart" sx={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={pts} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={grid} vertical={false} strokeDasharray="2 4" />
            <XAxis dataKey="label" tick={axis} interval={0} tickFormatter={(v: string) => (v.length > 12 ? `${v.slice(0, 11)}…` : v)} />
            <YAxis tick={axis} tickFormatter={fmt} width={56} />
            <Tooltip {...tooltip} cursor={{ fill: 'rgba(127,127,127,0.08)' }} />
            <Bar dataKey="value" name="Value" isAnimationActive={false} radius={[4, 4, 0, 0]} maxBarSize={32}>
              {pts.map((p) => (
                <Cell key={p.label} fill={p.other ? other : palette[0]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Box>
    );
  }

  // Over time, split by one category: a line or stacked column per category.
  if (hasPeriod && hasCategory && (visual === 'line' || visual === 'stacked_bar' || visual === 'area')) {
    const m = periodByCategory(rows);
    const color = (i: number, isOther?: boolean) => (isOther ? other : palette[i % palette.length]);
    const common = (
      <>
        <CartesianGrid stroke={grid} vertical={false} strokeDasharray="2 4" />
        <XAxis dataKey="period" tick={axis} minTickGap={16} />
        <YAxis tick={axis} tickFormatter={fmt} width={56} />
        <Tooltip {...tooltip} />
        <Legend wrapperStyle={{ fontSize: 12, color: theme.palette.text.secondary }} />
      </>
    );
    return (
      <Box data-testid="dashboard-widget-chart" sx={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          {visual === 'stacked_bar' ? (
            <BarChart data={m.data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              {common}
              {m.keys.map((k, i) => (
                <Bar key={k.key} dataKey={k.key} name={k.label} stackId="s" fill={color(i, k.other)} stroke={theme.palette.background.paper} isAnimationActive={false} />
              ))}
            </BarChart>
          ) : visual === 'area' ? (
            <AreaChart data={m.data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              {common}
              {m.keys.map((k, i) => (
                <Area key={k.key} dataKey={k.key} name={k.label} stackId="s" stroke={color(i, k.other)} fill={color(i, k.other)} fillOpacity={0.25} strokeWidth={2} isAnimationActive={false} />
              ))}
            </AreaChart>
          ) : (
            <LineChart data={m.data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              {common}
              {m.keys.map((k, i) => (
                <Line key={k.key} dataKey={k.key} name={k.label} stroke={color(i, k.other)} strokeWidth={2} dot={false} isAnimationActive={false} />
              ))}
            </LineChart>
          )}
        </ResponsiveContainer>
      </Box>
    );
  }

  // Over time, one series.
  const pts = periodPoints(series, rows);
  return (
    <Box data-testid="dashboard-widget-chart" sx={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        {visual === 'bar' || visual === 'stacked_bar' ? (
          <BarChart data={pts} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={grid} vertical={false} strokeDasharray="2 4" />
            <XAxis dataKey="label" tick={axis} minTickGap={16} />
            <YAxis tick={axis} tickFormatter={fmt} width={56} />
            <Tooltip {...tooltip} cursor={{ fill: 'rgba(127,127,127,0.08)' }} />
            <Bar dataKey="value" name="Value" fill={palette[0]} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
          </BarChart>
        ) : visual === 'area' ? (
          <AreaChart data={pts} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={grid} vertical={false} strokeDasharray="2 4" />
            <XAxis dataKey="label" tick={axis} minTickGap={16} />
            <YAxis tick={axis} tickFormatter={fmt} width={56} />
            <Tooltip {...tooltip} />
            <Area dataKey="value" name="Value" stroke={palette[0]} fill={palette[0]} fillOpacity={0.2} strokeWidth={2} isAnimationActive={false} />
          </AreaChart>
        ) : (
          <LineChart data={pts} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={grid} vertical={false} strokeDasharray="2 4" />
            <XAxis dataKey="label" tick={axis} minTickGap={16} />
            <YAxis tick={axis} tickFormatter={fmt} width={56} />
            <Tooltip {...tooltip} />
            <Line dataKey="value" name="Value" stroke={palette[0]} strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        )}
      </ResponsiveContainer>
    </Box>
  );
}
