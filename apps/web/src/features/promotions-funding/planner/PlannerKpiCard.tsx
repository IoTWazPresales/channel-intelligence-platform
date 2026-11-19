'use client';

import { Box, Paper, Skeleton, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import type { ReactNode } from 'react';

/**
 * Four states that must never look alike:
 * - ready: the value is a real figure;
 * - loading: the request is in flight;
 * - empty: the request FAILED (the legacy name used by the other cards on this page), shown with a retry note;
 * - unavailable: no endpoint carries this figure yet ("Not available yet" plus the reason). Never a number.
 */
export type KpiState = 'ready' | 'loading' | 'empty' | 'unavailable';

export const NOT_AVAILABLE_YET = 'Not available yet';

export function PlannerKpiCard({
  testId,
  label,
  value,
  unit,
  caption,
  state = 'ready',
  failureNote = 'Could not be loaded. Click to retry.',
  severity = 'neutral',
  onClick,
}: {
  testId: string;
  label: string;
  value?: ReactNode;
  unit?: string;
  /** The small line under the value. For `unavailable` it is the one-line reason. */
  caption: string;
  state?: KpiState;
  failureNote?: string;
  severity?: 'neutral' | 'good' | 'warn';
  onClick?: () => void;
}) {
  const theme = useTheme();
  const sev = severity === 'warn' ? theme.palette.warning.main : severity === 'good' ? theme.palette.success.main : null;
  const interactive = Boolean(onClick) && state !== 'unavailable';
  return (
    <Paper
      elevation={0}
      data-testid={testId}
      data-state={state}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={interactive ? onClick : undefined}
      onKeyDown={interactive ? (e) => (e.key === 'Enter' || e.key === ' ') && onClick?.() : undefined}
      aria-busy={state === 'loading' ? true : undefined}
      sx={{
        p: 1.5,
        height: '100%',
        boxShadow: 'none',
        minWidth: 0,
        cursor: interactive ? 'pointer' : 'default',
        borderLeft: sev ? `3px solid ${sev}` : undefined,
        bgcolor: sev ? alpha(sev, 0.06) : 'background.paper',
        '&:hover': interactive ? { borderColor: 'primary.main' } : undefined,
        '&:focus-visible': { outline: `2px solid ${theme.palette.primary.main}`, outlineOffset: 2 },
      }}
    >
      <Typography
        variant="caption"
        data-testid="kpi-label"
        sx={{ display: 'block', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: 11 }}
      >
        {label}
      </Typography>
      {state === 'loading' ? (
        <Skeleton variant="rounded" width="60%" height={28} sx={{ mt: 0.5 }} />
      ) : (
        <Box sx={{ mt: 0.25, display: 'flex', alignItems: 'baseline', gap: 0.75, flexWrap: 'wrap' }}>
          <Typography
            component="span"
            data-testid="kpi-value"
            sx={{
              fontSize: state === 'unavailable' ? 16 : 24,
              lineHeight: 1.3,
              fontWeight: 600,
              fontVariantNumeric: 'tabular-nums',
              color: state === 'ready' ? (sev ?? 'text.primary') : 'text.secondary',
            }}
          >
            {state === 'unavailable' ? NOT_AVAILABLE_YET : state === 'empty' ? '—' : value}
          </Typography>
          {unit && state === 'ready' ? (
            <Typography component="span" variant="body2" color="text.secondary">
              {unit}
            </Typography>
          ) : null}
        </Box>
      )}
      <Typography
        variant="caption"
        color="text.secondary"
        data-testid="kpi-caption"
        sx={{ display: 'block', mt: 0.5, lineHeight: 1.3 }}
      >
        {state === 'empty' ? failureNote : state === 'loading' ? 'Loading…' : caption}
      </Typography>
    </Paper>
  );
}
