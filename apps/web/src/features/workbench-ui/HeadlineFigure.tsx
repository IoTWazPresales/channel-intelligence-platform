'use client';

import { Box, Paper, Skeleton, Stack, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import type { ReactNode } from 'react';

import { Sparkline } from './charts';

export type Severity = 'neutral' | 'good' | 'warn' | 'bad';

/** Data state of a tile. `ready` is the default; the others replace or annotate the value. */
export type FigureState = 'ready' | 'loading' | 'empty' | 'stale';

/**
 * The one KPI tile: legible numerals (28px), tabular figures, severity in two
 * channels (colour + glyph/caption), optional delta and click-through. Used for domain headline
 * strips and the dashboard `kpi` widget body.
 *
 * N-0109 (mockup-report-system): optional `target`, `delta.period`, `sparkline`, `lead` (larger
 * value) and `state` (loading / empty / stale with `stateNote`). All optional; existing callers
 * render exactly as before.
 */
export function HeadlineFigure({
  label,
  value,
  unit,
  delta,
  caption,
  severity = 'neutral',
  onClick,
  compact = false,
  dense = false,
  target,
  sparkline,
  state = 'ready',
  stateNote,
  lead = false,
  testId,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  delta?: {
    text: string;
    direction: 'up' | 'down' | 'flat';
    /** Which direction is good. `neutral` colours the delta as secondary text. Default `up`. */
    goodWhen?: 'up' | 'down' | 'neutral';
    /** Comparison period, e.g. "W38" → "▼ 0.6w vs W38". */
    period?: string;
  };
  caption?: string;
  severity?: Severity;
  onClick?: () => void;
  compact?: boolean;
  dense?: boolean;
  /** Plain target line beside the delta, e.g. "target ≥ 4 weeks". */
  target?: string;
  /** Trend under the value; `label` is the accessible description. */
  sparkline?: { values: number[]; label: string };
  state?: FigureState;
  /** Why the tile is empty or stale, in plain words ("No plan lines in P09."). */
  stateNote?: string;
  /** Lead tile in a strip: larger value. */
  lead?: boolean;
  testId?: string;
}) {
  const theme = useTheme();
  const sevColor =
    severity === 'bad'
      ? theme.palette.error.main
      : severity === 'warn'
        ? theme.palette.warning.main
        : severity === 'good'
          ? theme.palette.success.main
          : theme.palette.text.primary;
  const deltaGood =
    delta && delta.direction !== 'flat' && delta.goodWhen !== 'neutral'
      ? (delta.goodWhen ?? 'up') === delta.direction
      : undefined;
  const deltaColor =
    deltaGood === undefined ? theme.palette.text.secondary : deltaGood ? theme.palette.success.main : theme.palette.error.main;
  const arrow = delta?.direction === 'up' ? '▲' : delta?.direction === 'down' ? '▼' : '■';
  const loading = state === 'loading';
  const empty = state === 'empty';
  const stale = state === 'stale';
  const valueSize = dense ? 20 : compact ? 24 : lead ? 34 : 28;
  const showValueRow = !loading;
  const showDeltaRow = !loading && !empty && (delta || caption || target);

  return (
    <Paper
      elevation={0}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => (e.key === 'Enter' || e.key === ' ') && onClick() : undefined}
      aria-busy={loading ? true : undefined}
      data-testid={testId}
      data-state={state}
      sx={{
        p: dense ? 1.25 : compact ? 1.5 : 2,
        height: '100%',
        cursor: onClick ? 'pointer' : 'default',
        borderLeft: severity !== 'neutral' ? `3px solid ${sevColor}` : undefined,
        boxShadow: 'none',
        bgcolor: severity !== 'neutral' ? alpha(sevColor, 0.06) : 'background.paper',
        transition: 'border-color 120ms',
        '&:hover': onClick ? { borderColor: 'primary.main' } : undefined,
        '&:focus-visible': { outline: `2px solid ${theme.palette.primary.main}`, outlineOffset: 2 },
      }}
    >
      <Typography variant="caption" sx={{ display: 'block', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: 11 }}>
        {label}
      </Typography>
      {loading ? (
        <>
          <Skeleton variant="rounded" width="60%" height={valueSize + 4} sx={{ mt: 0.5 }} />
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
            {stateNote ?? 'Loading…'}
          </Typography>
        </>
      ) : null}
      {showValueRow ? (
        <Stack direction="row" alignItems="baseline" spacing={0.75} sx={{ mt: 0.25 }}>
          <Typography
            component="span"
            sx={{
              fontSize: valueSize,
              lineHeight: 1.15,
              fontWeight: 600,
              fontVariantNumeric: 'tabular-nums',
              color: empty ? 'text.secondary' : severity === 'neutral' ? 'text.primary' : sevColor,
            }}
          >
            {empty ? '—' : value}
          </Typography>
          {unit && !empty ? (
            <Typography component="span" variant="body2" color="text.secondary">
              {unit}
            </Typography>
          ) : null}
        </Stack>
      ) : null}
      {empty && stateNote ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5, lineHeight: 1.35 }} data-testid="figure-empty-note">
          {stateNote}
        </Typography>
      ) : null}
      {showDeltaRow ? (
        <Box sx={{ mt: 0.5, display: 'flex', gap: 1, alignItems: 'flex-start', flexWrap: 'wrap', minHeight: 18 }}>
          {delta ? (
            <Typography variant="caption" sx={{ color: deltaColor, fontVariantNumeric: 'tabular-nums' }}>
              {arrow} {delta.text}
              {delta.period ? ` vs ${delta.period}` : ''}
            </Typography>
          ) : null}
          {target ? (
            <Typography variant="caption" color="text.secondary" sx={{ fontVariantNumeric: 'tabular-nums' }}>
              {target}
            </Typography>
          ) : null}
          {caption ? (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', lineHeight: 1.3 }}
            >
              {caption}
            </Typography>
          ) : null}
        </Box>
      ) : null}
      {stale ? (
        <Typography
          variant="caption"
          sx={{ display: 'block', mt: 0.5, color: theme.palette.warning.main, lineHeight: 1.35 }}
          data-testid="figure-stale-note"
        >
          ◷ {stateNote ?? 'This figure may be out of date.'}
        </Typography>
      ) : null}
      {sparkline && !loading && !empty && sparkline.values.length > 1 ? (
        <Sparkline values={sparkline.values} label={sparkline.label} tone={severity === 'bad' ? 'danger' : severity === 'warn' ? 'warning' : 'primary'} />
      ) : null}
    </Paper>
  );
}

/**
 * Responsive strip of headline figures; wraps to 2-up at 390px. Strips wider than three
 * columns split in half at md so a two-line DualMoney figure is not clipped at ~1024px,
 * and only reach the full column count at lg.
 */
export function HeadlineStrip({ children, columns }: { children: ReactNode; columns?: number }) {
  const full = columns ? `repeat(${columns}, minmax(0, 1fr))` : 'repeat(auto-fit, minmax(180px, 1fr))';
  const mid = columns && columns > 3 ? `repeat(${Math.ceil(columns / 2)}, minmax(0, 1fr))` : full;
  return (
    <Box
      sx={{
        display: 'grid',
        gap: 1.5,
        gridTemplateColumns: {
          xs: 'repeat(2, minmax(0, 1fr))',
          md: mid,
          lg: full,
        },
      }}
    >
      {children}
    </Box>
  );
}
