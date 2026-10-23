'use client';

import { Box, Stack, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useEffect, useState, type ReactNode } from 'react';
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Line,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Cell,
} from 'recharts';

import { CONTROLS_MIN_ROWS, ChartControls, useChartControls, type ChartControlsProp } from './ChartControls';
import { applyTopN, sortRows, topNCaption, type RowSort, type TopN } from './chartRows';

/**
 * Shared Recharts primitives with theme-bound axes/tooltips.
 * Ported from design-lab/primitives/charts.tsx so production containers inherit the same grammar.
 *
 * N-0109 adds what reports need: number/unit formatting helpers, threshold state, `RankedBars`
 * (horizontal, sorted, direct-labelled, threshold line, state colour from theme tokens),
 * `Sparkline`, an opt-in last-point label on `TrendChart`, and `ChartFigure` (accessible name +
 * visually-hidden data table). Existing exports keep their defaults.
 *
 * N-0114 (chart fixes): `unit` drives ticks, labels, tooltips and the hidden table
 * (`formatChartValue`); axis titles (`xAxisTitle` = the category or time axis, `yAxisTitle` = the
 * value axis, whatever the orientation) render as HTML captions so they wrap at 390 px; an HTML
 * legend (`ChartLegend`) whenever there is more than one series; long names wrap or angle and keep
 * the full name on hover and in the tooltip; category charts go horizontal when labels are long or
 * many; the chart toolbar (`ChartControls`) sets top N and sort; `ShareChart` draws pies and donuts.
 * Only formatting and layout change: every number is the caller's.
 */

/* ------------------------------------------------------------------------------------------------
 * Number and unit formatting
 * ---------------------------------------------------------------------------------------------- */

export type MeasureUnit = 'zar' | 'weeks' | 'units' | 'percent' | 'usd' | 'count' | 'days' | 'quarters' | 'number';

/** No-break space: groups ("1 092") and symbol/suffix gaps ("R 1.2 M") never wrap apart. */
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
    case 'zar':
      return 'R';
    case 'weeks':
      return 'weeks';
    case 'units':
      return 'units';
    case 'percent':
      return '%';
    case 'usd':
      return 'US$';
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
    case 'usd':
    case 'zar': {
      const n = formatNumber(v, { digits: Math.abs(v) < 100 ? 2 : 0 });
      return style === 'bare' ? n : `${unit === 'usd' ? 'US$' : 'R'}${GROUP}${n}`;
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

export type ChartValueStyle = 'tick' | 'label' | 'full';

/** Compact magnitude (no sign): full grouping under 10 000, then k (1 decimal under 100 k), M, bn. */
function compactMagnitude(a: number): string {
  if (a < 10_000) return formatNumber(a, { digits: a < 10 ? 2 : a < 100 ? 1 : 0 });
  if (a < 1e6) {
    const digits = a < 1e5 ? 1 : 0;
    const k = Number((a / 1e3).toFixed(digits));
    // 999 999 rounds to "1 000 k": say "1 M" instead.
    if (k < 1000) return `${formatNumber(k, { digits })}${GROUP}k`;
  }
  if (a < 1e9) {
    const m = Number((a / 1e6).toFixed(1));
    if (m < 1000) return `${formatNumber(m, { digits: 1 })}${GROUP}M`;
  }
  return `${formatNumber(a / 1e9, { digits: 1 })}${GROUP}bn`;
}

/**
 * Chart text for a value by unit (N-0114). `tick` is compact for axes, `label` for bar ends and the
 * last point, `full` for tooltips and the hidden data table. Decimal point, space for thousands
 * ("R 1.2 M", "US$ 1 234 567"); the sign goes before the symbol ("-R 1.2 M"); percent takes ratios.
 * Formatting only: the value itself is never rounded upstream of the text.
 */
export function formatChartValue(v: number | null | undefined, unit: MeasureUnit = 'number', style: ChartValueStyle = 'full'): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const sign = v < 0 ? '-' : '';
  const a = Math.abs(v);
  switch (unit) {
    case 'zar':
    case 'usd': {
      const symbol = unit === 'zar' ? 'R' : 'US$';
      if (style !== 'full') return `${sign}${symbol}${GROUP}${compactMagnitude(a)}`;
      const d = a < 100 ? 2 : 0;
      return `${sign}${symbol}${GROUP}${formatNumber(a, { digits: d, minDigits: d })}`;
    }
    case 'units':
      return style === 'full' ? `${formatNumber(v, { digits: Number.isInteger(v) ? 0 : 1 })} units` : `${sign}${compactMagnitude(a)}`;
    case 'count':
      return style === 'full' ? formatNumber(v, { digits: Number.isInteger(v) ? 0 : 1 }) : `${sign}${compactMagnitude(a)}`;
    case 'percent': {
      // Ticks drop the decimal unless the tick sits between whole points (a step under 1 pp).
      const p = v * 100;
      return style === 'tick' ? `${formatNumber(p, { digits: 1 })}%` : `${formatNumber(p, { digits: 1, minDigits: 1 })}%`;
    }
    case 'weeks': {
      if (style === 'tick') return formatNumber(v, { digits: 1 });
      const n = formatNumber(v, { digits: 1, minDigits: 1 });
      return style === 'label' ? `${n}w` : `${n} weeks`;
    }
    case 'days': {
      const n = formatNumber(v, { digits: 0 });
      return style === 'tick' ? n : style === 'label' ? `${n}d` : `${n} days`;
    }
    case 'quarters': {
      const n = formatNumber(v, { digits: 1 });
      return style === 'tick' ? n : style === 'label' ? `${n}q` : `${n} quarters`;
    }
    case 'number':
    default:
      return style === 'full' ? formatNumber(v, { digits: 2 }) : `${sign}${compactMagnitude(a)}`;
  }
}

/**
 * Axis title with its unit: "Sales value (R)", "Fill rate (%)". No bracket when the label already
 * names the unit as a word ("Weeks of cover"), the same rule as report column headers.
 */
export function axisTitle(label: string, unit?: MeasureUnit | null): string {
  const w = unit ? unitWord(unit) : null;
  if (!w) return label;
  const esc = w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  if (new RegExp(`(^|[^a-z])${esc}($|[^a-z])`, 'i').test(label)) return label;
  return `${label} (${w})`;
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

type ValueFormatters = { tick: (v: number) => string; label: (v: number) => string; full: (v: number) => string };

/** `unit` drives every text; an explicit `format` / `axisFormat` still overrides (back-compat). */
function chartFormatters(unit?: MeasureUnit, format?: (v: number) => string, axisFormat?: (v: number) => string): ValueFormatters {
  const u = unit ?? 'number';
  return {
    tick: axisFormat ?? format ?? ((v) => formatChartValue(v, u, 'tick')),
    label: format ?? ((v) => formatChartValue(v, u, 'label')),
    full: format ?? ((v) => formatChartValue(v, u, 'full')),
  };
}

function toNumber(v: unknown): number | null {
  if (v == null || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

const cellText = (f: (v: number) => string, v: unknown) => {
  const n = toNumber(v);
  return n == null ? '—' : f(n);
};

/* ------------------------------------------------------------------------------------------------
 * Long category names and layout
 * ---------------------------------------------------------------------------------------------- */

/** Average glyph width at the 11 px axis size; used to estimate label widths without measuring text. */
const CHAR_PX = 6.4;
/** Width assumed before the first measurement (and in jsdom). */
const FALLBACK_WIDTH = 640;

/**
 * Bars run horizontal when there are more than 8 categories or a label over 14 characters.
 * A time axis is never flipped; `force` wins over the rule.
 */
export function chooseCategoryLayout(
  labels: string[],
  opts: { timeAxis?: boolean; force?: 'vertical' | 'horizontal' } = {},
): 'vertical' | 'horizontal' {
  if (opts.force) return opts.force;
  if (opts.timeAxis) return 'vertical';
  const longest = labels.reduce((m, l) => Math.max(m, l.length), 0);
  return labels.length > 8 || longest > 14 ? 'horizontal' : 'vertical';
}

/**
 * Break a label at word boundaries into at most `maxLines` lines; words longer than a line are
 * hard-broken. When text is left over, the last line ends with "…" (the full name stays on hover).
 */
export function wrapLabel(text: string, maxCharsPerLine: number, maxLines = 2): string[] {
  const max = Math.max(1, Math.floor(maxCharsPerLine));
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return [''];
  const lines: string[] = [];
  let cur = '';
  for (let w of words) {
    while (w.length > max) {
      if (cur) {
        lines.push(cur);
        cur = '';
      }
      lines.push(w.slice(0, max));
      w = w.slice(max);
    }
    if (!w) continue;
    if (!cur) cur = w;
    else if (cur.length + 1 + w.length <= max) cur = `${cur} ${w}`;
    else {
      lines.push(cur);
      cur = w;
    }
  }
  if (cur) lines.push(cur);
  if (lines.length <= maxLines) return lines;
  const kept = lines.slice(0, maxLines);
  const last = kept[maxLines - 1];
  kept[maxLines - 1] = `${last.length >= max ? last.slice(0, max - 1) : last}…`;
  return kept;
}

/** Label column for horizontal bars: wide enough for the longest name, at least 64 px, at most 45% of the chart. */
export function horizontalLabelWidth(labels: string[], chartWidth: number): number {
  const longest = labels.reduce((m, l) => Math.max(m, l.length), 0);
  return Math.floor(Math.max(64, Math.min(longest * CHAR_PX + 12, 0.45 * chartWidth)));
}

/** Width of an element, kept current with a ResizeObserver (0 until measured). */
export function useElementWidth<T extends HTMLElement>(): [(el: T | null) => void, number] {
  const [el, setEl] = useState<T | null>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!el) return;
    setWidth(el.getBoundingClientRect().width);
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w != null) setWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [el]);
  return [setEl, width];
}

type TickProps = { x?: number | string; y?: number | string; payload?: { value?: unknown } };

/**
 * Category tick: up to two wrapped lines (vertical bars) or a wrapped label column (horizontal
 * bars); one angled line when the band is too narrow. Every tick carries the full name in <title>.
 */
function categoryTick(opts: { orientation: 'bottom' | 'left'; maxChars: number; angled?: boolean; fill: string; fontSize?: number }) {
  const fontSize = opts.fontSize ?? 11;
  return function CategoryTick(props: TickProps) {
    const full = String(props.payload?.value ?? '');
    const x = Number(props.x);
    const y = Number(props.y);
    if (opts.angled) {
      return (
        <text x={x} y={y} dy={8} textAnchor="end" transform={`rotate(-35, ${x}, ${y})`} fill={opts.fill} fontSize={fontSize} data-testid="chart-category-tick">
          <title>{full}</title>
          {wrapLabel(full, opts.maxChars, 1)[0]}
        </text>
      );
    }
    const lines = wrapLabel(full, opts.maxChars, 2);
    if (opts.orientation === 'left') {
      const first = lines.length > 1 ? -2.5 : 4;
      return (
        <text x={x} y={y} textAnchor="end" fill={opts.fill} fontSize={fontSize} data-testid="chart-category-tick">
          <title>{full}</title>
          {lines.map((l, i) => (
            <tspan key={i} x={x} dy={i === 0 ? first : 13}>
              {l}
            </tspan>
          ))}
        </text>
      );
    }
    return (
      <text x={x} y={y} textAnchor="middle" fill={opts.fill} fontSize={fontSize} data-testid="chart-category-tick">
        <title>{full}</title>
        {lines.map((l, i) => (
          <tspan key={i} x={x} dy={i === 0 ? '0.71em' : 13}>
            {l}
          </tspan>
        ))}
      </text>
    );
  };
}

/** Bottom category axis: band width → characters per line, wrapped line count, axis height. */
function bottomAxisLayout(labels: string[], plotWidth: number) {
  const band = plotWidth / Math.max(1, labels.length);
  // Under 40 px even two lines are unreadable: one angled line instead.
  const angled = band < 40;
  const maxChars = angled ? 18 : Math.max(3, Math.floor(band / CHAR_PX));
  const longest = labels.reduce((m, l) => Math.max(m, l.length), 0);
  const lines = angled ? 1 : Math.max(1, ...labels.map((l) => wrapLabel(l, maxChars).length));
  const height = angled ? Math.round(16 + Math.min(18, longest) * CHAR_PX * 0.574) : Math.max(30, 14 + 13 * lines);
  return { angled, maxChars, height };
}

/** Left label column for horizontal bars: width, characters per line, row height for wrapped labels. */
function leftAxisLayout(labels: string[], chartWidth: number, labelWidth?: number, minRow = 26) {
  const width = labelWidth ?? horizontalLabelWidth(labels, chartWidth);
  const maxChars = Math.max(4, Math.floor((width - 12) / CHAR_PX));
  const lines = Math.max(1, ...labels.map((l) => wrapLabel(l, maxChars).length));
  return { width, maxChars, rowHeight: Math.max(minRow, lines * 14 + 10) };
}

const warnedUntitled = new Set<string>();

/** Development-only nudge: a chart with axes should title both. No effect in production. */
function useUntitledWarning(chart: string, xAxisTitle?: string, yAxisTitle?: string) {
  useEffect(() => {
    if (process.env.NODE_ENV !== 'development' || (xAxisTitle && yAxisTitle) || warnedUntitled.has(chart)) return;
    warnedUntitled.add(chart);
    console.warn(`${chart}: pass xAxisTitle and yAxisTitle (with the unit) so every axis is titled.`);
  }, [chart, xAxisTitle, yAxisTitle]);
}

/* ------------------------------------------------------------------------------------------------
 * Theme
 * ---------------------------------------------------------------------------------------------- */

export type ChartTone = 'primary' | 'secondary' | 'muted' | 'success' | 'warning' | 'danger';

/** Categorical slots in fixed order (validated light/dark pairs, moved from the dashboard widget chart). */
const SERIES_LIGHT = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
const SERIES_DARK = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'];

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
    paper: theme.palette.background.paper,
    /** Hover band behind the active category; visible in light and dark. */
    cursor: theme.palette.action.hover,
    series: theme.palette.mode === 'dark' ? SERIES_DARK : SERIES_LIGHT,
    tooltip: {
      contentStyle: {
        background: theme.palette.background.default,
        border: `1px solid ${theme.palette.divider}`,
        borderRadius: 8,
        fontSize: 12,
        maxWidth: 280,
        whiteSpace: 'normal' as const,
      },
      labelStyle: { color: theme.palette.text.primary, fontWeight: 600 },
      itemStyle: { color: theme.palette.text.secondary },
      // The full category name: the touch path, since <title> does not show on touch.
      labelFormatter: (label: unknown) => String(label ?? ''),
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
    // overflowX clip: Recharts keeps its hidden tooltip box beside the plot, which must not widen a 390 page.
    <Box component="figure" sx={{ m: 0, position: 'relative', overflowX: 'clip' }} data-testid={testId}>
      <Box role="img" aria-label={summary}>
        {children}
      </Box>
      {table ? (
        // The hidden box is a div: a table ignores width 1px and would widen the page at 390.
        <Box sx={visuallyHiddenSx}>
        <table>
          <caption>{table.caption}</caption>
          <thead>
            <tr>
              {table.columns.map((c, i) => (
                <th key={`${c}-${i}`} scope="col">
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
        </table>
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

/** Swatch legend above the plot: full names, wrapping, series colours. */
export function ChartLegend({ items }: { items: { label: string; color: string; value?: string; share?: string }[] }) {
  return (
    <Box component="ul" sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.75, rowGap: 0.5, m: 0, mb: 1, p: 0, listStyle: 'none' }} data-testid="chart-legend">
      {items.map((it, i) => (
        <Box component="li" key={`${it.label}-${i}`} sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75, minWidth: 0 }}>
          <Box component="span" aria-hidden sx={{ width: 10, height: 10, borderRadius: '2px', bgcolor: it.color, flexShrink: 0 }} />
          <Typography variant="caption" color="text.secondary" sx={{ overflowWrap: 'anywhere' }}>
            {it.label}
            {it.value || it.share ? ` · ${[it.value, it.share].filter(Boolean).join(' · ')}` : ''}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

function AxisCaption({ children, align = 'left', inset = 0, testId }: { children?: string; align?: 'left' | 'center'; inset?: number; testId: string }) {
  if (!children) return null;
  return (
    <Typography
      variant="caption"
      component="div"
      color="text.secondary"
      sx={{ display: 'block', lineHeight: 1.35, textAlign: align, pl: `${inset}px`, overflowWrap: 'anywhere' }}
      data-testid={testId}
    >
      {children}
    </Typography>
  );
}

/** Chart summary when the caller gave none: the titles say what is drawn. */
function autoSummary(summary: string | undefined, xAxisTitle?: string, yAxisTitle?: string): string | undefined {
  if (summary) return summary;
  if (!yAxisTitle) return undefined;
  return xAxisTitle ? `${yAxisTitle} by ${xAxisTitle}` : yAxisTitle;
}

/**
 * Common chart chrome: toolbar (or a standalone "Top N of M" caption), legend, then the figure with
 * the top axis caption, the plot and the bottom axis caption. Controls and legend sit outside the
 * role="img" box so they stay reachable by assistive technology.
 */
function ChartShell({
  widthRef,
  testId,
  toolbar,
  caption,
  legend,
  summary,
  table,
  top,
  bottom,
  children,
}: {
  widthRef?: (el: HTMLDivElement | null) => void;
  testId?: string;
  toolbar?: ReactNode;
  caption?: string | null;
  legend?: ReactNode;
  summary?: string;
  table?: ChartDataTable;
  top?: ReactNode;
  bottom?: ReactNode;
  children: ReactNode;
}) {
  const body = (
    <>
      {top}
      {children}
      {bottom}
    </>
  );
  return (
    <Box ref={widthRef} sx={{ minWidth: 0 }} data-testid={testId}>
      {toolbar}
      {!toolbar && caption ? (
        <Typography variant="caption" color="text.secondary" component="div" sx={{ textAlign: 'right', mb: 0.5 }} data-testid="chart-topn-caption">
          {caption}
        </Typography>
      ) : null}
      {legend}
      {summary ? (
        <ChartFigure summary={summary} table={table}>
          {body}
        </ChartFigure>
      ) : (
        body
      )}
    </Box>
  );
}

const isMoney = (unit?: MeasureUnit) => unit === 'zar' || unit === 'usd';

/* ------------------------------------------------------------------------------------------------
 * CategoryBars: one value per category; vertical or horizontal by label length and count.
 * ---------------------------------------------------------------------------------------------- */

type Row = Record<string, unknown>;

export function CategoryBars({
  data,
  x,
  y,
  height,
  colorBy,
  format,
  unit,
  xAxisTitle,
  yAxisTitle,
  layout = 'auto',
  horizontal = false,
  timeAxis = false,
  controls = true,
  legend = false,
  summary,
  onRowClick,
  testId,
}: {
  data: Row[];
  x: string;
  y: string;
  /** Plot height for vertical bars; horizontal bars grow with the row count (at least this). */
  height?: number;
  colorBy?: (row: Row) => string;
  /** Override for every value text; prefer `unit`. */
  format?: (v: number) => string;
  unit?: MeasureUnit;
  /** Title of the category axis (`x`), whatever the orientation. */
  xAxisTitle?: string;
  /** Title of the value axis, unit included ("Outstanding (R)"). */
  yAxisTitle?: string;
  layout?: 'auto' | 'vertical' | 'horizontal';
  /** Always horizontal (same as `layout="horizontal"`). */
  horizontal?: boolean;
  /** Categories are periods: never flipped, no toolbar. */
  timeAxis?: boolean;
  /** Top N / sort toolbar; pass `false` for ordered buckets. */
  controls?: ChartControlsProp;
  /** Legend for the single series (off by default). */
  legend?: boolean;
  summary?: string;
  onRowClick?: (row: Row) => void;
  testId?: string;
}) {
  const c = useChartTheme();
  const [widthRef, measured] = useElementWidth<HTMLDivElement>();
  const width = measured || FALLBACK_WIDTH;
  useUntitledWarning('CategoryBars', xAxisTitle, yAxisTitle);
  const name = (r: Row) => String(r[x] ?? '');
  const ctl = useChartControls({ topN: 10, sort: { by: 'value', dir: 'desc' } }, timeAxis ? false : controls);
  const { shown, total } = ctl.enabled
    ? applyTopN(sortRows(data, ctl.state.sort, { name, value: (r) => toNumber(r[y]) }), ctl.state.topN)
    : { shown: data, total: data.length };
  const labels = shown.map(name);
  const isHorizontal =
    chooseCategoryLayout(labels, { timeAxis, force: horizontal ? 'horizontal' : layout === 'auto' ? undefined : layout }) === 'horizontal';
  const fmt = chartFormatters(unit, format);
  const titled = Boolean(xAxisTitle || yAxisTitle);
  const valueWidth = isMoney(unit) ? 68 : 56;
  const bottom = bottomAxisLayout(labels, Math.max(40, width - valueWidth - 12));
  const left = leftAxisLayout(labels, width);
  const plotHeight = isHorizontal ? Math.max(height ?? 0, 96, shown.length * left.rowHeight + 36) : height;
  const figureSummary = autoSummary(summary, xAxisTitle, yAxisTitle);
  const table: ChartDataTable | undefined = figureSummary
    ? {
        caption: figureSummary,
        columns: [xAxisTitle ?? x, yAxisTitle ?? y],
        rows: shown.map((r) => [name(r), cellText(fmt.full, r[y])]),
      }
    : undefined;
  const click = onRowClick
    ? (state: unknown) => {
        const payload = (state as { payload?: Row }).payload;
        if (payload) onRowClick(payload);
      }
    : undefined;
  return (
    <ChartShell
      widthRef={widthRef}
      testId={testId}
      toolbar={
        ctl.enabled && total >= CONTROLS_MIN_ROWS ? (
          <ChartControls value={ctl.state} onChange={ctl.setState} shown={shown.length} total={total} />
        ) : null
      }
      caption={topNCaption(shown.length, total)}
      legend={legend ? <ChartLegend items={[{ label: yAxisTitle ?? y, color: c.primary }]} /> : null}
      summary={figureSummary}
      table={table}
      top={<AxisCaption testId="chart-axis-title-top">{isHorizontal ? xAxisTitle : yAxisTitle}</AxisCaption>}
      bottom={
        <AxisCaption testId="chart-axis-title-bottom" align="center" inset={isHorizontal ? left.width : valueWidth}>
          {isHorizontal ? yAxisTitle : xAxisTitle}
        </AxisCaption>
      }
    >
      <ChartFrame height={plotHeight}>
        <BarChart
          data={shown}
          layout={isHorizontal ? 'vertical' : 'horizontal'}
          margin={{ top: 8, right: 12, left: isHorizontal ? 8 : titled ? 0 : -12, bottom: 0 }}
        >
          <CartesianGrid stroke={c.grid} vertical={isHorizontal} horizontal={!isHorizontal} strokeDasharray="2 4" />
          {/* Recharts does not traverse Fragments — axes must be direct children. */}
          {isHorizontal ? (
            <XAxis type="number" tick={{ fill: c.axis, fontSize: 11 }} tickFormatter={fmt.tick} axisLine={false} tickLine={false} />
          ) : (
            <XAxis
              dataKey={x}
              tick={categoryTick({ orientation: 'bottom', maxChars: bottom.maxChars, angled: bottom.angled, fill: c.axis, fontSize: 10.5 })}
              height={bottom.height}
              axisLine={false}
              tickLine={false}
              interval={0}
            />
          )}
          {isHorizontal ? (
            <YAxis
              type="category"
              dataKey={x}
              tick={categoryTick({ orientation: 'left', maxChars: left.maxChars, fill: c.axis })}
              width={left.width}
              axisLine={false}
              tickLine={false}
              interval={0}
            />
          ) : (
            <YAxis tick={{ fill: c.axis, fontSize: 11 }} tickFormatter={fmt.tick} axisLine={false} tickLine={false} width={valueWidth} />
          )}
          <Tooltip {...c.tooltip} formatter={(v) => fmt.full(Number(v))} cursor={{ fill: c.cursor }} />
          <Bar
            isAnimationActive={false}
            dataKey={y}
            name={yAxisTitle ?? y}
            radius={isHorizontal ? [0, 3, 3, 0] : [3, 3, 0, 0]}
            fill={c.primary}
            maxBarSize={44}
            cursor={onRowClick ? 'pointer' : undefined}
            onClick={click}
          >
            {colorBy ? shown.map((row, i) => <Cell key={i} fill={colorBy(row)} />) : null}
          </Bar>
        </BarChart>
      </ChartFrame>
    </ChartShell>
  );
}

/* ------------------------------------------------------------------------------------------------
 * PairedBars: two values per category (plan vs shipped, last year vs this year).
 * ---------------------------------------------------------------------------------------------- */

export function PairedBars({
  data,
  x,
  a,
  b,
  aLabel,
  bLabel,
  height,
  format,
  unit,
  xAxisTitle,
  yAxisTitle,
  layout = 'auto',
  timeAxis = false,
  controls = true,
  summary,
  testId,
}: {
  data: Row[];
  x: string;
  a: string;
  b: string;
  aLabel: string;
  bLabel: string;
  height?: number;
  format?: (v: number) => string;
  unit?: MeasureUnit;
  /** Title of the category axis (`x`), whatever the orientation. */
  xAxisTitle?: string;
  /** Title of the value axis, unit included. */
  yAxisTitle?: string;
  layout?: 'auto' | 'vertical' | 'horizontal';
  /** Categories are periods (quarters): never flipped, no toolbar. */
  timeAxis?: boolean;
  /** Top N / sort toolbar (sorts by the `b` series); starts in the caller's order. */
  controls?: ChartControlsProp;
  summary?: string;
  testId?: string;
}) {
  const c = useChartTheme();
  const [widthRef, measured] = useElementWidth<HTMLDivElement>();
  const width = measured || FALLBACK_WIDTH;
  useUntitledWarning('PairedBars', xAxisTitle, yAxisTitle);
  const name = (r: Row) => String(r[x] ?? '');
  // Callers order these rows on purpose (strategic customers first): start "As listed".
  const ctl = useChartControls({ topN: 10, sort: { by: 'period' } }, timeAxis ? false : controls);
  const { shown, total } = ctl.enabled
    ? applyTopN(sortRows(data, ctl.state.sort, { name, value: (r) => toNumber(r[b]) }), ctl.state.topN)
    : { shown: data, total: data.length };
  const labels = shown.map(name);
  const isHorizontal = chooseCategoryLayout(labels, { timeAxis, force: layout === 'auto' ? undefined : layout }) === 'horizontal';
  const fmt = chartFormatters(unit, format);
  const titled = Boolean(xAxisTitle || yAxisTitle);
  const valueWidth = isMoney(unit) ? 68 : 56;
  const bottom = bottomAxisLayout(labels, Math.max(40, width - valueWidth - 12));
  const left = leftAxisLayout(labels, width, undefined, 34);
  const plotHeight = isHorizontal ? Math.max(height ?? 0, 96, shown.length * left.rowHeight + 36) : height;
  const figureSummary = autoSummary(summary, xAxisTitle, yAxisTitle);
  const table: ChartDataTable | undefined = figureSummary
    ? {
        caption: figureSummary,
        columns: [xAxisTitle ?? x, aLabel, bLabel],
        rows: shown.map((r) => [name(r), cellText(fmt.full, r[a]), cellText(fmt.full, r[b])]),
      }
    : undefined;
  return (
    <ChartShell
      widthRef={widthRef}
      testId={testId}
      toolbar={
        ctl.enabled && total >= CONTROLS_MIN_ROWS ? (
          <ChartControls value={ctl.state} onChange={ctl.setState} shown={shown.length} total={total} />
        ) : null
      }
      caption={topNCaption(shown.length, total)}
      legend={
        <ChartLegend
          items={[
            { label: aLabel, color: c.muted },
            { label: bLabel, color: c.primary },
          ]}
        />
      }
      summary={figureSummary}
      table={table}
      top={<AxisCaption testId="chart-axis-title-top">{isHorizontal ? xAxisTitle : yAxisTitle}</AxisCaption>}
      bottom={
        <AxisCaption testId="chart-axis-title-bottom" align="center" inset={isHorizontal ? left.width : valueWidth}>
          {isHorizontal ? yAxisTitle : xAxisTitle}
        </AxisCaption>
      }
    >
      <ChartFrame height={plotHeight}>
        <BarChart
          data={shown}
          layout={isHorizontal ? 'vertical' : 'horizontal'}
          margin={{ top: 8, right: 12, left: isHorizontal ? 8 : titled ? 0 : -12, bottom: 0 }}
        >
          <CartesianGrid stroke={c.grid} vertical={isHorizontal} horizontal={!isHorizontal} strokeDasharray="2 4" />
          {isHorizontal ? (
            <XAxis type="number" tick={{ fill: c.axis, fontSize: 11 }} tickFormatter={fmt.tick} axisLine={false} tickLine={false} />
          ) : (
            <XAxis
              dataKey={x}
              tick={categoryTick({ orientation: 'bottom', maxChars: bottom.maxChars, angled: bottom.angled, fill: c.axis, fontSize: 10.5 })}
              height={bottom.height}
              axisLine={false}
              tickLine={false}
              interval={0}
            />
          )}
          {isHorizontal ? (
            <YAxis
              type="category"
              dataKey={x}
              tick={categoryTick({ orientation: 'left', maxChars: left.maxChars, fill: c.axis })}
              width={left.width}
              axisLine={false}
              tickLine={false}
              interval={0}
            />
          ) : (
            <YAxis tick={{ fill: c.axis, fontSize: 11 }} tickFormatter={fmt.tick} axisLine={false} tickLine={false} width={valueWidth} />
          )}
          <Tooltip {...c.tooltip} formatter={(v) => fmt.full(Number(v))} cursor={{ fill: c.cursor }} />
          <Bar isAnimationActive={false} dataKey={a} name={aLabel} fill={c.muted} radius={isHorizontal ? [0, 3, 3, 0] : [3, 3, 0, 0]} maxBarSize={isHorizontal ? 12 : 28} />
          <Bar isAnimationActive={false} dataKey={b} name={bLabel} fill={c.primary} radius={isHorizontal ? [0, 3, 3, 0] : [3, 3, 0, 0]} maxBarSize={isHorizontal ? 12 : 28} />
        </BarChart>
      </ChartFrame>
    </ChartShell>
  );
}

/* ------------------------------------------------------------------------------------------------
 * TrendChart: values over a time axis; line, area and bar series, optionally stacked.
 * ---------------------------------------------------------------------------------------------- */

export function TrendChart({
  data,
  x,
  series,
  height,
  format,
  unit,
  xAxisTitle,
  yAxisTitle,
  yScale = 'zero',
  lastPointLabel = false,
  legend,
  stack = false,
  summary,
  table,
  testId,
}: {
  data: Row[];
  x: string;
  series: { key: string; label: string; kind: 'line' | 'area' | 'bar'; tone?: ChartTone }[];
  height?: number;
  format?: (v: number) => string;
  unit?: MeasureUnit;
  /** Title of the time axis ("Week", "Quarter"). */
  xAxisTitle?: string;
  /** Title of the value axis, unit included ("Sell-out (units)"). */
  yAxisTitle?: string;
  /** 'zero' (default) anchors the axis at 0 — right for volumes. 'fit' zooms to the data — right for prices/rates. */
  yScale?: 'zero' | 'fit';
  /** Direct-label the last point of the first line/area series (reports). Off by default. */
  lastPointLabel?: boolean;
  /** Legend; on by default only when there is more than one series. */
  legend?: boolean;
  /** Stack bars with bars and areas with areas (dashboards: each period split by a category). */
  stack?: boolean;
  /** Accessible name; defaults to the axis titles. With a name the chart also gets a hidden data table. */
  summary?: string;
  table?: ChartDataTable;
  testId?: string;
}) {
  const c = useChartTheme();
  useUntitledWarning('TrendChart', xAxisTitle, yAxisTitle);
  const fmt = chartFormatters(unit, format);
  const showLegend = legend ?? series.length > 1;
  const colorOf = (s: (typeof series)[number], i: number) =>
    s.tone ? toneColor(c, s.tone) : series.length > 1 ? c.series[i % c.series.length] : c.primary;
  const labelled = lastPointLabel ? series.find((s) => s.kind !== 'bar')?.key : undefined;
  const lastIndex = data.length - 1;
  const titled = Boolean(xAxisTitle || yAxisTitle);
  const valueWidth = isMoney(unit) ? 68 : yScale === 'fit' ? 64 : 60;
  const figureSummary = autoSummary(summary, xAxisTitle, yAxisTitle);
  const figureTable: ChartDataTable | undefined =
    table ??
    (figureSummary
      ? {
          caption: figureSummary,
          columns: [xAxisTitle ?? x, ...series.map((s) => s.label)],
          rows: data.map((r) => [String(r[x] ?? ''), ...series.map((s) => cellText(fmt.full, r[s.key]))]),
        }
      : undefined);
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
                {fmt.label(Number(props.value))}
              </text>
            );
          }}
        />
      )
    : null;
  return (
    <ChartShell
      testId={testId}
      legend={showLegend ? <ChartLegend items={series.map((s, i) => ({ label: s.label, color: colorOf(s, i) }))} /> : null}
      summary={figureSummary}
      table={figureTable}
      top={<AxisCaption testId="chart-axis-title-top">{yAxisTitle}</AxisCaption>}
      bottom={
        <AxisCaption testId="chart-axis-title-bottom" align="center" inset={valueWidth}>
          {xAxisTitle}
        </AxisCaption>
      }
    >
      <ChartFrame height={height}>
        <ComposedChart data={data} margin={{ top: lastPointLabel ? 18 : 8, right: 12, left: titled ? 0 : -12, bottom: 0 }}>
          <CartesianGrid stroke={c.grid} vertical={false} strokeDasharray="2 4" />
          <XAxis dataKey={x} tick={{ fill: c.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis
            tick={{ fill: c.axis, fontSize: 11 }}
            tickFormatter={fmt.tick}
            axisLine={false}
            tickLine={false}
            width={valueWidth}
            domain={yScale === 'fit' ? ['auto', 'auto'] : [0, 'auto']}
          />
          <Tooltip {...c.tooltip} formatter={(v) => fmt.full(Number(v))} cursor={{ fill: c.cursor }} />
          {series.map((s, i) =>
            s.kind === 'bar' ? (
              <Bar
                isAnimationActive={false}
                key={`${s.key}-${i}`}
                dataKey={s.key}
                name={s.label}
                fill={colorOf(s, i)}
                stackId={stack ? 'bar' : undefined}
                radius={stack ? undefined : [3, 3, 0, 0]}
                maxBarSize={22}
              />
            ) : s.kind === 'area' ? (
              <Area
                isAnimationActive={false}
                key={`${s.key}-${i}`}
                dataKey={s.key}
                name={s.label}
                type="monotone"
                stroke={colorOf(s, i)}
                fill={colorOf(s, i)}
                fillOpacity={stack ? 0.25 : 0.12}
                strokeWidth={2}
                dot={false}
                stackId={stack ? 'area' : undefined}
              >
                {s.key === labelled ? lastLabel : null}
              </Area>
            ) : (
              <Line
                isAnimationActive={false}
                key={`${s.key}-${i}`}
                dataKey={s.key}
                name={s.label}
                type="monotone"
                stroke={colorOf(s, i)}
                strokeWidth={2}
                dot={
                  s.key === labelled
                    ? (p: { index?: number; cx?: number; cy?: number }) =>
                        p.index === lastIndex && p.cx != null && p.cy != null ? (
                          <circle key="last" cx={p.cx} cy={p.cy} r={3} fill={colorOf(s, i)} />
                        ) : (
                          <g key={`d${p.index}`} />
                        )
                    : false
                }
              >
                {s.key === labelled ? lastLabel : null}
              </Line>
            ),
          )}
        </ComposedChart>
      </ChartFrame>
    </ChartShell>
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

const RANK_SORT: Record<'asc' | 'desc' | 'none', RowSort> = {
  asc: { by: 'value', dir: 'asc' },
  desc: { by: 'value', dir: 'desc' },
  none: { by: 'period' },
};

export function RankedBars({
  data,
  format,
  axisFormat,
  unit,
  threshold,
  sort = 'desc',
  max = 10,
  summary,
  labelHeader = 'Item',
  valueHeader = 'Value',
  xAxisTitle,
  yAxisTitle,
  labelWidth,
  rowHeight = 34,
  controls = true,
  onRowClick,
  testId = 'ranked-bars',
}: {
  data: RankedBarDatum[];
  /** Direct label + tooltip formatter; overrides `unit`. */
  format?: (v: number) => string;
  /** Axis tick formatter; defaults to `format`. */
  axisFormat?: (v: number) => string;
  unit?: MeasureUnit;
  threshold?: { value: number; label: string };
  /** Starting sort ('none' keeps the caller's order). */
  sort?: 'asc' | 'desc' | 'none';
  /** Starting top N. */
  max?: TopN;
  /** Accessible name of the drawing. */
  summary: string;
  labelHeader?: string;
  valueHeader?: string;
  /** Title of the category (label) axis, e.g. "Customer". */
  xAxisTitle?: string;
  /** Title of the value axis, unit included, e.g. "Units sold (units)". */
  yAxisTitle?: string;
  /** Explicit label column width; otherwise sized to the names, at most 45% of the chart. */
  labelWidth?: number;
  rowHeight?: number;
  controls?: ChartControlsProp;
  onRowClick?: (d: RankedBarDatum) => void;
  testId?: string;
}) {
  const c = useChartTheme();
  const [widthRef, measured] = useElementWidth<HTMLDivElement>();
  const width = measured || FALLBACK_WIDTH;
  useUntitledWarning('RankedBars', xAxisTitle, yAxisTitle);
  const ctl = useChartControls({ topN: max, sort: RANK_SORT[sort] }, controls);
  const valued = data.filter((d) => d.value != null && Number.isFinite(d.value));
  const { shown, total } = applyTopN(
    sortRows(valued, ctl.state.sort, { name: (d) => d.label, value: (d) => d.value }),
    ctl.state.topN,
  );
  const fmt = chartFormatters(unit, format, axisFormat);
  const maxValue = Math.max(0, ...shown.map((d) => d.value ?? 0), threshold?.value ?? 0);
  const axis = niceAxis(maxValue);
  const left = leftAxisLayout(
    shown.map((d) => d.label),
    width,
    labelWidth,
    rowHeight,
  );
  const height = shown.length * left.rowHeight + (threshold ? 56 : 36);
  const table: ChartDataTable = {
    caption: summary,
    columns: [xAxisTitle ?? labelHeader, yAxisTitle ?? valueHeader],
    rows: shown.map((d) => [d.label, fmt.full(d.value as number)]),
  };
  return (
    <ChartShell
      widthRef={widthRef}
      testId={testId}
      toolbar={
        ctl.enabled && total >= CONTROLS_MIN_ROWS ? (
          <ChartControls value={ctl.state} onChange={ctl.setState} shown={shown.length} total={total} />
        ) : null
      }
      caption={topNCaption(shown.length, total)}
      summary={summary}
      table={table}
      top={<AxisCaption testId="chart-axis-title-top">{xAxisTitle}</AxisCaption>}
      bottom={
        <AxisCaption testId="chart-axis-title-bottom" align="center" inset={left.width}>
          {yAxisTitle}
        </AxisCaption>
      }
    >
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
            tickFormatter={(v: number) => fmt.tick(v)}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="label"
            width={left.width}
            // Wrapped to two lines with the full name in <title>; rows grow so lines never overlap.
            tick={categoryTick({ orientation: 'left', maxChars: left.maxChars, fill: c.axis, fontSize: 11.5 })}
            axisLine={false}
            tickLine={false}
            interval={0}
          />
          <Tooltip {...c.tooltip} formatter={(v) => fmt.full(Number(v))} cursor={{ fill: c.cursor }} />
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
            name={yAxisTitle ?? valueHeader}
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
              formatter={(v: unknown) => fmt.label(Number(v))}
              style={{ fill: c.text, fontSize: 11.5, fontWeight: 500 }}
            />
          </Bar>
        </BarChart>
      </ChartFrame>
    </ChartShell>
  );
}

/* ------------------------------------------------------------------------------------------------
 * ShareChart: pie or donut with a legend of full names, values and shares of the full total.
 * ---------------------------------------------------------------------------------------------- */

export type ShareDatum = { label: string; value: number };

export function ShareChart({
  data,
  unit = 'number',
  variant = 'pie',
  summary,
  total: totalOverride,
  labelHeader = 'Category',
  valueHeader = 'Value',
  height = 220,
  controls = true,
  testId = 'share-chart',
}: {
  /** Every category: shares are computed against all of them, not only the slices shown. */
  data: ShareDatum[];
  unit?: MeasureUnit;
  variant?: 'pie' | 'donut';
  summary: string;
  /** The whole, when the caller knows it better than the sum of `data`. */
  total?: number;
  labelHeader?: string;
  valueHeader?: string;
  height?: number;
  controls?: ChartControlsProp;
  testId?: string;
}) {
  const c = useChartTheme();
  const whole = totalOverride ?? data.reduce((s, d) => s + (Number.isFinite(d.value) ? d.value : 0), 0);
  const ctl = useChartControls({ topN: data.length <= 9 ? 'all' : 5, sort: { by: 'value', dir: 'desc' } }, controls);
  const accessors = { name: (d: ShareDatum) => d.label, value: (d: ShareDatum) => d.value };
  const { shown, total } = applyTopN(sortRows(data, ctl.state.sort, accessors), ctl.state.topN);
  const share = (v: number) => (whole ? `${formatNumber((v / whole) * 100, { digits: 1, minDigits: 1 })}%` : '—');
  const full = (v: number) => formatChartValue(v, unit, 'full');
  const color = (i: number) => c.series[i % c.series.length];
  const caption = shown.length < total ? `Top ${shown.length} of ${total} shown · shares are of the full total` : null;
  const table: ChartDataTable = {
    caption: summary,
    columns: [labelHeader, valueHeader, 'Share'],
    rows: sortRows(data, { by: 'value', dir: 'desc' }, accessors).map((d) => [d.label, full(d.value), share(d.value)]),
  };
  return (
    <ChartShell
      testId={testId}
      toolbar={
        ctl.enabled && total >= CONTROLS_MIN_ROWS ? (
          <ChartControls value={ctl.state} onChange={ctl.setState} shown={shown.length} total={total} caption={caption} />
        ) : null
      }
      caption={caption}
      summary={summary}
      table={table}
    >
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ xs: 'stretch', sm: 'center' }}>
        <Box sx={{ flex: { sm: '0 0 40%' }, width: { xs: '100%', sm: 'auto' }, height }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={shown}
                dataKey="value"
                nameKey="label"
                innerRadius={variant === 'donut' ? '55%' : 0}
                outerRadius="90%"
                stroke={c.paper}
                strokeWidth={2}
                isAnimationActive={false}
              >
                {shown.map((d, i) => (
                  <Cell key={`${d.label}-${i}`} fill={color(i)} />
                ))}
              </Pie>
              <Tooltip {...c.tooltip} formatter={(v) => `${full(Number(v))} · ${share(Number(v))}`} />
            </PieChart>
          </ResponsiveContainer>
        </Box>
        <Stack component="ul" spacing={0.75} sx={{ flex: 1, minWidth: 0, m: 0, p: 0, listStyle: 'none' }} data-testid="share-chart-legend">
          {shown.map((d, i) => (
            <Stack component="li" key={`${d.label}-${i}`} direction="row" spacing={1} alignItems="flex-start">
              <Box aria-hidden sx={{ width: 10, height: 10, mt: 0.5, borderRadius: '2px', flexShrink: 0, bgcolor: color(i) }} />
              <Typography variant="caption" sx={{ flex: 1, minWidth: 0, overflowWrap: 'anywhere' }}>
                {d.label}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>
                {full(d.value)} · {share(d.value)}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </Stack>
    </ChartShell>
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
