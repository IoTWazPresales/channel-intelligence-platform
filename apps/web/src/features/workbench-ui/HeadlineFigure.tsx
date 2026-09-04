'use client';

import { Box, Paper, Stack, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import type { ReactNode } from 'react';

export type Severity = 'neutral' | 'good' | 'warn' | 'bad';

/**
 * Evolution of `components/KpiCard.tsx`: legible numerals (28px), tabular figures, severity in two
 * channels (colour + glyph/caption), optional delta and click-through. Used for domain headline
 * strips and the dashboard `kpi` widget body.
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
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  delta?: { text: string; direction: 'up' | 'down' | 'flat'; goodWhen?: 'up' | 'down' };
  caption?: string;
  severity?: Severity;
  onClick?: () => void;
  compact?: boolean;
  dense?: boolean;
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
    delta && delta.direction !== 'flat' ? (delta.goodWhen ?? 'up') === delta.direction : undefined;
  const deltaColor =
    deltaGood === undefined ? theme.palette.text.secondary : deltaGood ? theme.palette.success.main : theme.palette.error.main;
  const arrow = delta?.direction === 'up' ? '▲' : delta?.direction === 'down' ? '▼' : '■';

  return (
    <Paper
      elevation={0}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => (e.key === 'Enter' || e.key === ' ') && onClick() : undefined}
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
      <Stack direction="row" alignItems="baseline" spacing={0.75} sx={{ mt: 0.25 }}>
        <Typography
          component="span"
          sx={{
            fontSize: dense ? 20 : compact ? 24 : 28,
            lineHeight: 1.15,
            fontWeight: 600,
            fontVariantNumeric: 'tabular-nums',
            color: severity === 'neutral' ? 'text.primary' : sevColor,
          }}
        >
          {value}
        </Typography>
        {unit ? (
          <Typography component="span" variant="body2" color="text.secondary">
            {unit}
          </Typography>
        ) : null}
      </Stack>
      {delta || caption ? (
        <Box sx={{ mt: 0.5, display: 'flex', gap: 1, alignItems: 'flex-start', flexWrap: 'wrap', minHeight: 18 }}>
          {delta ? (
            <Typography variant="caption" sx={{ color: deltaColor, fontVariantNumeric: 'tabular-nums' }}>
              {arrow} {delta.text}
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
    </Paper>
  );
}

/** Responsive strip of headline figures; wraps to 2-up at 390px. */
export function HeadlineStrip({ children, columns }: { children: ReactNode; columns?: number }) {
  return (
    <Box
      sx={{
        display: 'grid',
        gap: 1.5,
        gridTemplateColumns: {
          xs: 'repeat(2, minmax(0, 1fr))',
          md: columns ? `repeat(${columns}, minmax(0, 1fr))` : 'repeat(auto-fit, minmax(180px, 1fr))',
        },
      }}
    >
      {children}
    </Box>
  );
}
