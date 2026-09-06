'use client';

import { Box, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Cell,
} from 'recharts';

/**
 * Shared Recharts primitives with theme-bound axes/tooltips.
 * Ported from design-lab/primitives/charts.tsx so production containers inherit the same grammar.
 */

function useChartTheme() {
  const theme = useTheme();
  return {
    grid: theme.palette.divider,
    axis: theme.palette.text.secondary,
    primary: theme.palette.primary.main,
    secondary: theme.palette.secondary.main,
    success: theme.palette.success.main,
    warning: theme.palette.warning.main,
    danger: theme.palette.error.main,
    muted: theme.palette.text.disabled,
    tooltip: {
      contentStyle: {
        background: theme.palette.background.default,
        border: `1px solid ${theme.palette.divider}`,
        borderRadius: 8,
        fontSize: 12,
      },
      labelStyle: { color: theme.palette.text.primary, fontWeight: 600 },
      itemStyle: { color: theme.palette.text.secondary },
    },
  };
}

export function ChartFrame({ height = 220, children }: { height?: number; children: React.ReactElement }) {
  return (
    <Box sx={{ width: '100%', height }}>
      <ResponsiveContainer width="100%" height="100%">
        {children}
      </ResponsiveContainer>
    </Box>
  );
}

export function CategoryBars({
  data,
  x,
  y,
  height,
  colorBy,
  format,
  horizontal = false,
  compact = false,
  onRowClick,
}: {
  data: Record<string, unknown>[];
  x: string;
  y: string;
  height?: number;
  colorBy?: (row: Record<string, unknown>) => string;
  format?: (v: number) => string;
  horizontal?: boolean;
  /** Narrow containers (dashboard widgets): angle category labels so they never collide. */
  compact?: boolean;
  onRowClick?: (row: Record<string, unknown>) => void;
}) {
  const c = useChartTheme();
  const fmt = format ?? ((v: number) => v.toLocaleString('en-ZA'));
  return (
    <ChartFrame height={height}>
      <BarChart data={data} layout={horizontal ? 'vertical' : 'horizontal'} margin={{ top: 8, right: 12, left: horizontal ? 8 : -12, bottom: 0 }}>
        <CartesianGrid stroke={c.grid} vertical={horizontal} horizontal={!horizontal} strokeDasharray="2 4" />
        {/* Recharts does not traverse Fragments — axes must be direct children. */}
        {horizontal ? (
          <XAxis type="number" tick={{ fill: c.axis, fontSize: 11 }} tickFormatter={fmt} axisLine={false} tickLine={false} />
        ) : (
          <XAxis
            dataKey={x}
            tick={{ fill: c.axis, fontSize: 10.5, ...(compact ? { angle: -32, textAnchor: 'end' } : {}) }}
            height={compact ? 40 : 30}
            axisLine={false}
            tickLine={false}
            interval={0}
          />
        )}
        {horizontal ? (
          <YAxis type="category" dataKey={x} tick={{ fill: c.axis, fontSize: 11 }} width={150} axisLine={false} tickLine={false} />
        ) : (
          <YAxis tick={{ fill: c.axis, fontSize: 11 }} tickFormatter={fmt} axisLine={false} tickLine={false} width={56} />
        )}
        <Tooltip {...c.tooltip} formatter={(v) => fmt(Number(v))} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
        <Bar
          isAnimationActive={false}
          dataKey={y}
          radius={[3, 3, 0, 0]}
          fill={c.primary}
          maxBarSize={44}
          cursor={onRowClick ? 'pointer' : undefined}
          onClick={onRowClick ? (state) => {
            const payload = (state as { payload?: Record<string, unknown> }).payload;
            if (payload) onRowClick(payload);
          } : undefined}
        >
          {colorBy ? data.map((row, i) => <Cell key={i} fill={colorBy(row)} />) : null}
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

export function PairedBars({
  data,
  x,
  a,
  b,
  aLabel,
  bLabel,
  height,
  format,
  compact = false,
}: {
  data: Record<string, unknown>[];
  x: string;
  a: string;
  b: string;
  aLabel: string;
  bLabel: string;
  height?: number;
  format?: (v: number) => string;
  compact?: boolean;
}) {
  const c = useChartTheme();
  const fmt = format ?? ((v: number) => v.toLocaleString('en-ZA'));
  return (
    <ChartFrame height={height}>
      <BarChart data={data} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
        <CartesianGrid stroke={c.grid} vertical={false} strokeDasharray="2 4" />
        <XAxis
          dataKey={x}
          tick={{ fill: c.axis, fontSize: 10.5, ...(compact ? { angle: -32, textAnchor: 'end' } : {}) }}
          height={compact ? 44 : 30}
          axisLine={false}
          tickLine={false}
          interval={0}
          tickFormatter={(v: string) => (v.length > 11 ? `${v.slice(0, 10)}…` : v)}
        />
        <YAxis tick={{ fill: c.axis, fontSize: 11 }} tickFormatter={fmt} axisLine={false} tickLine={false} />
        <Tooltip {...c.tooltip} formatter={(v) => fmt(Number(v))} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
        <Legend wrapperStyle={{ fontSize: 12, color: c.axis }} />
        <Bar isAnimationActive={false} dataKey={a} name={aLabel} fill={c.muted} radius={[3, 3, 0, 0]} maxBarSize={28} />
        <Bar isAnimationActive={false} dataKey={b} name={bLabel} fill={c.primary} radius={[3, 3, 0, 0]} maxBarSize={28} />
      </BarChart>
    </ChartFrame>
  );
}

export function TrendChart({
  data,
  x,
  series,
  height,
  format,
  yScale = 'zero',
}: {
  data: Record<string, unknown>[];
  x: string;
  series: { key: string; label: string; kind: 'line' | 'area' | 'bar'; tone?: 'primary' | 'secondary' | 'muted' | 'warning' }[];
  height?: number;
  format?: (v: number) => string;
  /** 'zero' (default) anchors the axis at 0 — right for volumes. 'fit' zooms to the data — right for prices/rates. */
  yScale?: 'zero' | 'fit';
}) {
  const c = useChartTheme();
  const fmt = format ?? ((v: number) => v.toLocaleString('en-ZA'));
  const toneColor = (t?: string) => (t === 'secondary' ? c.secondary : t === 'muted' ? c.muted : t === 'warning' ? c.warning : c.primary);
  return (
    <ChartFrame height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
        <CartesianGrid stroke={c.grid} vertical={false} strokeDasharray="2 4" />
        <XAxis dataKey={x} tick={{ fill: c.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis
          tick={{ fill: c.axis, fontSize: 11 }}
          tickFormatter={fmt}
          axisLine={false}
          tickLine={false}
          width={yScale === 'fit' ? 64 : 60}
          domain={yScale === 'fit' ? ['auto', 'auto'] : [0, 'auto']}
        />
        <Tooltip {...c.tooltip} formatter={(v) => fmt(Number(v))} />
        <Legend wrapperStyle={{ fontSize: 12, color: c.axis }} />
        {series.map((s) =>
          s.kind === 'bar' ? (
            <Bar isAnimationActive={false} key={s.key} dataKey={s.key} name={s.label} fill={toneColor(s.tone)} radius={[3, 3, 0, 0]} maxBarSize={22} />
          ) : s.kind === 'area' ? (
            <Area isAnimationActive={false} key={s.key} dataKey={s.key} name={s.label} type="monotone" stroke={toneColor(s.tone)} fill={toneColor(s.tone)} fillOpacity={0.12} strokeWidth={2} dot={false} />
          ) : (
            <Line isAnimationActive={false} key={s.key} dataKey={s.key} name={s.label} type="monotone" stroke={toneColor(s.tone)} strokeWidth={2} dot={false} />
          )
        )}
      </ComposedChart>
    </ChartFrame>
  );
}

/** Inline proportion bar for grid cells and compact panels (e.g. PO coverage %). */
export function ProportionBar({ value, tone = 'primary', label }: { value: number; tone?: 'primary' | 'success' | 'warning' | 'danger'; label?: string }) {
  const c = useChartTheme();
  const color = tone === 'success' ? c.success : tone === 'warning' ? c.warning : tone === 'danger' ? c.danger : c.primary;
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
      <Box sx={{ flex: 1, height: 6, borderRadius: 3, bgcolor: 'action.hover', overflow: 'hidden' }}>
        <Box sx={{ width: `${Math.max(0, Math.min(1, value)) * 100}%`, height: '100%', bgcolor: color }} />
      </Box>
      <Typography variant="caption" sx={{ fontVariantNumeric: 'tabular-nums', minWidth: 36, textAlign: 'right' }}>
        {label ?? `${Math.round(value * 100)}%`}
      </Typography>
    </Box>
  );
}
