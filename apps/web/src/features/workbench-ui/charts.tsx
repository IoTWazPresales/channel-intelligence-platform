'use client';

import { Box, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import type { ReactNode } from 'react';
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Cell,
} from 'recharts';

/**
 * Shared Recharts primitives with theme-bound axes/tooltips.
 * Ported from design-lab/primitives/charts.tsx so production containers inherit the same grammar.
 *
 * N-0109 adds what reports need: number/unit formatting helpers, threshold state, `RankedBars`
 * (horizontal, sorted, direct-labelled, threshold line, state colour from theme tokens),
 * `Sparkline`, an opt-in last-point label on `TrendChart`, and `ChartFigure` (accessible name +
 * visually-hidden data table). Existing exports keep their defaults.
 */

/* ------------------------------------------------------------------------------------------------
 * Number and unit formatting
 * ---------------------------------------------------------------------------------------------- */

export type MeasureUnit = 'weeks' | 'units' | 'percent' | 'usd' | 'count' | 'days' | 'quarters' | 'number';

const GROUP = ' ';

/**
 * Locale-stable grouping: "1 092", "5.4". `en-ZA` in ICU uses a decimal comma, which would turn
 * 4.37 into "4,37"; reports use a decimal point and a space for thousands (same as the lab).
 */
export function formatNumber(v: number | null | undefined, opts: { digits?: number; minDigits?: number } = {}): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const digits = opts.digits ?? 2;
  const s = v.toLocaleString('en-US', {
    maximumFractionDigits: digits,
    minimumFractionDigits: opts.minDigits ?? 0,
  });
  return s.replace(/,/g, GROUP);
}

/** Plain unit word for a measure; used in column headers ("Cover (weeks)") and KPI tiles. */
export function unitWord(unit: MeasureUnit): string | null {
  switch (unit) {
    case 'weeks':
      return 'weeks';
    case 'units':
      return 'units';
    case 'percent':
      return '%';
    case 'usd':
      return 'USD';
    case 'days':
      return 'days';
    case 'quarters':
      return 'quarters';
    case 'count':
    case 'number':
    default:
      return null;
  }
}

/**
 * Format a governed value by unit. `style: 'bare'` returns the number only (for tiles whose unit
 * sits beside the value); `'short'` uses compact suffixes for chart labels ("5.4w").
 */
export function formatMeasure(
  v: number | null | undefined,
  unit: MeasureUnit,
  style: 'bare' | 'short' | 'long' = 'bare',
): string {
  if (v == null || !Number.isFinite(v)) return '—';
  switch (unit) {
    case 'weeks': {
      const n = formatNumber(v, { digits: 1, minDigits: 1 });
      return style === 'short' ? `${n}w` : style === 'long' ? `${n} weeks` : n;
    }
    case 'percent': {
      // Governed rates are ratios (0.86 → 86.0%).
      return `${formatNumber(v * 100, { digits: 1, minDigits: 1 })}%`;
    }
    case 'usd': {
      const n = formatNumber(v, { digits: Math.abs(v) < 100 ? 2 : 0 });
      return style === 'bare' ? n : `$${n}`;
    }
    case 'units':
    case 'count': {
      const n = formatNumber(v, { digits: Number.isInteger(v) ? 0 : 1 });
      return style === 'long' && unit === 'units' ? `${n} units` : n;
    }
    case 'days': {
      const n = formatNumber(v, { digits: 0 });
      return style === 'short' ? `${n}d` : style === 'long' ? `${n} days` : n;
    }
    case 'quarters': {
      const n = formatNumber(v, { digits: 1 });
      return style === 'short' ? `${n}q` : style === 'long' ? `${n} quarters` : n;
    }
    case 'number':
    default:
      return formatNumber(v, { digits: 2 });
  }
}

/**
 * Lower-is-worse state against two thresholds (cover-type measures). Warren 2026-10-09:
 * stop (red) under 2 weeks, warn (amber) under 4 weeks, otherwise ok (blue).
 */
export type ThresholdState = 'stop' | 'warn' | 'ok';

export function thresholdState(
  value: number | null | undefined,
  limits: { stop: number; warn: number } = { stop: 2, warn: 4 },
): ThresholdState | null {
  if (value == null || !Number.isFinite(value)) return null;
  if (value < limits.stop) return 'stop';
  if (value < limits.warn) return 'warn';
  return 'ok';
}

/* ------------------------------------------------------------------------------------------------
 * Theme
 * ---------------------------------------------------------------------------------------------- */

export type ChartTone = 'primary' | 'secondary' | 'muted' | 'success' | 'warning' | 'danger';

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
    text: theme.palette.text.primary,
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

function toneColor(c: ReturnType<typeof useChartTheme>, t?: ChartTone): string {
  switch (t) {
    case 'secondary':
      return c.secondary;
    case 'muted':
      return c.muted;
    case 'success':
      return c.success;
    case 'warning':
      return c.warning;
    case 'danger':
      return c.danger;
    case 'primary':
    default:
      return c.primary;
  }
}

/* ------------------------------------------------------------------------------------------------
 * Accessible chart wrapper: an accessible name for the drawing plus a visually-hidden data table.
 * ---------------------------------------------------------------------------------------------- */

const visuallyHiddenSx = {
  border: 0,
  clip: 'rect(0 0 0 0)',
  height: '1px',
  margin: '-1px',
  overflow: 'hidden',
  padding: 0,
  position: 'absolute',
  whiteSpace: 'nowrap',
  width: '1px',
} as const;

export type ChartDataTable = { caption: string; columns: string[]; rows: string[][] };

export function ChartFigure({
  summary,
  table,
  children,
  testId,
}: {
  /** Accessible name of the drawing: what it shows, in one sentence. */
  summary: string;
  /** The same numbers as a table for screen readers (visually hidden). */
  table?: ChartDataTable;
  children: ReactNode;
  testId?: string;
}) {
  return (
    <Box component="figure" sx={{ m: 0, position: 'relative' }} data-testid={testId}>
      <Box role="img" aria-label={summary}>
        {children}
      </Box>
      {table ? (
        <Box component="table" sx={visuallyHiddenSx}>
          <caption>{table.caption}</caption>
          <thead>
            <tr>
              {table.columns.map((c) => (
                <th key={c} scope="col">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((r, i) => (
              <tr key={i}>
                {r.map((cell, j) =>
                  j === 0 ? (
                    <th key={j} scope="row">
                      {cell}
                    </th>
                  ) : (
                    <td key={j}>{cell}</td>
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </Box>
      ) : null}
    </Box>
  );
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
  lastPointLabel = false,
  legend = true,
  summary,
  table,
}: {
  data: Record<string, unknown>[];
  x: string;
  series: { key: string; label: string; kind: 'line' | 'area' | 'bar'; tone?: 'primary' | 'secondary' | 'muted' | 'warning' }[];
  height?: number;
  format?: (v: number) => string;
  /** 'zero' (default) anchors the axis at 0 — right for volumes. 'fit' zooms to the data — right for prices/rates. */
  yScale?: 'zero' | 'fit';
  /** Direct-label the last point of the first line/area series (reports). Off by default. */
  lastPointLabel?: boolean;
  /** Hide the legend for a single, already-titled series. On by default. */
  legend?: boolean;
  /** When set, the chart gets this accessible name and `table` as a visually-hidden data table. */
  summary?: string;
  table?: ChartDataTable;
}) {
  const c = useChartTheme();
  const fmt = format ?? ((v: number) => v.toLocaleString('en-ZA'));
  const toneColor = (t?: string) => (t === 'secondary' ? c.secondary : t === 'muted' ? c.muted : t === 'warning' ? c.warning : c.primary);
  const labelled = lastPointLabel ? series.find((s) => s.kind !== 'bar')?.key : undefined;
  const lastIndex = data.length - 1;
  const lastLabel = labelled
    ? (
        <LabelList
          dataKey={labelled}
          content={(props: { index?: number; x?: number | string; y?: number | string; value?: unknown }) => {
            if (props.index !== lastIndex || props.value == null) return null;
            return (
              <text
                x={Number(props.x)}
                y={Number(props.y) - 8}
                textAnchor="end"
                fill={c.text}
                fontSize={11}
                fontWeight={600}
                data-testid="trend-last-label"
              >
                {fmt(Number(props.value))}
              </text>
            );
          }}
        />
      )
    : null;
  const chart = (
    <ChartFrame height={height}>
      <ComposedChart data={data} margin={{ top: lastPointLabel ? 18 : 8, right: 12, left: -12, bottom: 0 }}>
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
        {legend ? <Legend wrapperStyle={{ fontSize: 12, color: c.axis }} /> : null}
        {series.map((s) =>
          s.kind === 'bar' ? (
            <Bar isAnimationActive={false} key={s.key} dataKey={s.key} name={s.label} fill={toneColor(s.tone)} radius={[3, 3, 0, 0]} maxBarSize={22} />
          ) : s.kind === 'area' ? (
            <Area isAnimationActive={false} key={s.key} dataKey={s.key} name={s.label} type="monotone" stroke={toneColor(s.tone)} fill={toneColor(s.tone)} fillOpacity={0.12} strokeWidth={2} dot={false}>
              {s.key === labelled ? lastLabel : null}
            </Area>
          ) : (
            <Line
              isAnimationActive={false}
              key={s.key}
              dataKey={s.key}
              name={s.label}
              type="monotone"
              stroke={toneColor(s.tone)}
              strokeWidth={2}
              dot={
                s.key === labelled
                  ? (p: { index?: number; cx?: number; cy?: number }) =>
                      p.index === lastIndex && p.cx != null && p.cy != null ? (
                        <circle key="last" cx={p.cx} cy={p.cy} r={3} fill={toneColor(s.tone)} />
                      ) : (
                        <g key={`d${p.index}`} />
                      )
                  : false
              }
            >
              {s.key === labelled ? lastLabel : null}
            </Line>
          )
        )}
      </ComposedChart>
    </ChartFrame>
  );
  if (!summary) return chart;
  return (
    <ChartFigure summary={summary} table={table}>
      {chart}
    </ChartFigure>
  );
}

/* ------------------------------------------------------------------------------------------------
 * RankedBars: horizontal bars, sorted, directly labelled, optional threshold line and state colour.
 * ---------------------------------------------------------------------------------------------- */

export type RankedBarDatum = { label: string; value: number | null; tone?: ChartTone; key?: string };

/** Sort, drop rows without a value, and cap — pure so reports can test it without a renderer. */
export function rankBars(
  data: RankedBarDatum[],
  { sort = 'desc', max = 20 }: { sort?: 'asc' | 'desc' | 'none'; max?: number } = {},
): { shown: RankedBarDatum[]; total: number; withoutValue: number } {
  const valued = data.filter((d): d is RankedBarDatum & { value: number } => d.value != null && Number.isFinite(d.value));
  const sorted =
    sort === 'none'
      ? valued
      : [...valued].sort((a, b) => (sort === 'asc' ? a.value - b.value : b.value - a.value));
  return { shown: sorted.slice(0, max), total: valued.length, withoutValue: data.length - valued.length };
}

/** Round axis: 3–6 ticks on a 1/2/2.5/5 × 10ⁿ step, ending at or just above `max` (0, 2, 4, 6, 8). */
export function niceAxis(max: number, target = 4): { max: number; ticks: number[] } {
  if (!Number.isFinite(max) || max <= 0) return { max: 1, ticks: [0, 1] };
  const raw = max / target;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 2.5, 5, 10].find((m) => m * mag >= raw) ?? 10) * mag;
  const top = Math.ceil(max / step - 1e-9) * step;
  const ticks: number[] = [];
  for (let t = 0; t <= top + step / 2; t += step) ticks.push(Math.round(t * 1e6) / 1e6);
  return { max: ticks[ticks.length - 1], ticks };
}

export function RankedBars({
  data,
  format,
  axisFormat,
  threshold,
  sort = 'desc',
  max = 20,
  summary,
  labelHeader = 'Item',
  valueHeader = 'Value',
  labelWidth,
  rowHeight = 34,
  onRowClick,
  testId = 'ranked-bars',
}: {
  data: RankedBarDatum[];
  /** Direct label + tooltip formatter. */
  format: (v: number) => string;
  /** Axis tick formatter; defaults to `format`. */
  axisFormat?: (v: number) => string;
  threshold?: { value: number; label: string };
  sort?: 'asc' | 'desc' | 'none';
  max?: number;
  /** Accessible name of the drawing. */
  summary: string;
  labelHeader?: string;
  valueHeader?: string;
  labelWidth?: number;
  rowHeight?: number;
  onRowClick?: (d: RankedBarDatum) => void;
  testId?: string;
}) {
  const c = useChartTheme();
  const { shown } = rankBars(data, { sort, max });
  const maxValue = Math.max(0, ...shown.map((d) => d.value ?? 0), threshold?.value ?? 0);
  const axis = niceAxis(maxValue);
  const longest = shown.reduce((m, d) => Math.max(m, d.label.length), 0);
  const yWidth = labelWidth ?? Math.min(240, Math.max(96, Math.round(longest * 6.4) + 12));
  const truncate = (s: string) => {
    const maxChars = Math.floor((yWidth - 12) / 6.4);
    return s.length > maxChars ? `${s.slice(0, Math.max(1, maxChars - 1))}…` : s;
  };
  const height = shown.length * rowHeight + (threshold ? 56 : 36);
  const tick = axisFormat ?? format;
  const table: ChartDataTable = {
    caption: summary,
    columns: [labelHeader, valueHeader],
    rows: shown.map((d) => [d.label, format(d.value as number)]),
  };
  return (
    <ChartFigure summary={summary} table={table} testId={testId}>
      <ChartFrame height={height}>
        <BarChart
          data={shown}
          layout="vertical"
          margin={{ top: threshold ? 22 : 4, right: 56, left: 4, bottom: 0 }}
          barCategoryGap={8}
        >
          <CartesianGrid stroke={c.grid} horizontal={false} vertical strokeDasharray="2 4" />
          <XAxis
            type="number"
            domain={[0, axis.max]}
            ticks={axis.ticks}
            tick={{ fill: c.axis, fontSize: 11 }}
            tickFormatter={(v: number) => tick(v)}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="label"
            width={yWidth}
            // One line per row: Recharts' default tick wraps long names into overlapping lines.
            tick={(props: { x?: number | string; y?: number | string; payload?: { value?: unknown } }) => {
              const full = String(props.payload?.value ?? '');
              return (
                <text x={Number(props.x)} y={Number(props.y)} dy={4} textAnchor="end" fill={c.axis} fontSize={11.5}>
                  <title>{full}</title>
                  {truncate(full)}
                </text>
              );
            }}
            axisLine={false}
            tickLine={false}
            interval={0}
          />
          <Tooltip {...c.tooltip} formatter={(v) => format(Number(v))} cursor={{ fill: c.grid, fillOpacity: 0.4 }} />
          {threshold ? (
            <ReferenceLine
              x={threshold.value}
              stroke={c.warning}
              strokeDasharray="3 3"
              ifOverflow="extendDomain"
              label={{ value: threshold.label, position: 'top', fill: c.warning, fontSize: 11 }}
            />
          ) : null}
          <Bar
            isAnimationActive={false}
            dataKey="value"
            name={valueHeader}
            radius={[0, 3, 3, 0]}
            maxBarSize={26}
            cursor={onRowClick ? 'pointer' : undefined}
            onClick={
              onRowClick
                ? (state) => {
                    const payload = (state as { payload?: RankedBarDatum }).payload;
                    if (payload) onRowClick(payload);
                  }
                : undefined
            }
          >
            {shown.map((d, i) => (
              <Cell key={d.key ?? i} fill={toneColor(c, d.tone)} />
            ))}
            <LabelList
              dataKey="value"
              position="right"
              formatter={(v: unknown) => format(Number(v))}
              style={{ fill: c.text, fontSize: 11.5, fontWeight: 500 }}
            />
          </Bar>
        </BarChart>
      </ChartFrame>
    </ChartFigure>
  );
}

/** Swatch key for state-coloured bars (colour is never the only channel: labels + this key). */
export function StateKey({ items }: { items: { tone: ChartTone; label: string }[] }) {
  const c = useChartTheme();
  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.75, mt: 0.5 }} data-testid="chart-state-key">
      {items.map((it) => (
        <Box key={it.label} sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75 }}>
          <Box component="span" aria-hidden sx={{ width: 10, height: 10, borderRadius: '2px', bgcolor: toneColor(c, it.tone) }} />
          <Typography variant="caption" color="text.secondary">
            {it.label}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

/* ------------------------------------------------------------------------------------------------
 * Sparkline: a 12-point trend for KPI tiles. Plain SVG (no axes), last point marked.
 * ---------------------------------------------------------------------------------------------- */

export function sparklinePoints(values: number[], width = 200, height = 28, pad = 3): { points: string; last: { x: number; y: number } | null } {
  const v = values.filter((n) => Number.isFinite(n));
  if (v.length === 0) return { points: '', last: null };
  const min = Math.min(...v);
  const max = Math.max(...v);
  const span = max - min || 1;
  const step = v.length > 1 ? width / (v.length - 1) : 0;
  const pts = v.map((n, i) => ({ x: Math.round(i * step * 10) / 10, y: Math.round((pad + (1 - (n - min) / span) * (height - 2 * pad)) * 10) / 10 }));
  return { points: pts.map((p) => `${p.x},${p.y}`).join(' '), last: pts[pts.length - 1] };
}

export function Sparkline({
  values,
  label,
  tone = 'primary',
  height = 28,
}: {
  values: number[];
  /** Accessible description, e.g. "12-week trend, 6.3 to 5.4 weeks". */
  label: string;
  tone?: ChartTone;
  height?: number;
}) {
  const c = useChartTheme();
  const color = toneColor(c, tone);
  const W = 200;
  const { points, last } = sparklinePoints(values, W, height);
  if (!points) return null;
  return (
    <Box sx={{ position: 'relative', width: '100%', height, mt: 1 }} data-testid="sparkline">
      <svg viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" width="100%" height={height} role="img" aria-label={label}>
        <polyline fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" points={points} />
      </svg>
      {last ? (
        <Box
          aria-hidden
          sx={{
            position: 'absolute',
            left: `calc(${(last.x / W) * 100}% - 3px)`,
            top: last.y - 3,
            width: 6,
            height: 6,
            borderRadius: '50%',
            bgcolor: color,
          }}
        />
      ) : null}
    </Box>
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
