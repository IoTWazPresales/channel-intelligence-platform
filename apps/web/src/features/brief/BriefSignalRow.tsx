'use client';

import Link from 'next/link';
import { Box, Button, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';

export type BriefSignal = {
  id: string;
  rank: number;
  severity: 'stop' | 'warn' | 'ok';
  title: string;
  detail: string;
  meta: string | null;
  meta_hot: boolean;
  action_label: string;
  action_href: string;
  suggested?: boolean;
  data_unavailable?: boolean;
};

export function BriefSignalRow({ signal }: { signal: BriefSignal }) {
  const theme = useTheme();
  const line = theme.palette.divider;
  const tickColor =
    signal.severity === 'stop'
      ? theme.palette.error.main
      : signal.severity === 'ok'
        ? theme.palette.success.main
        : theme.palette.warning.main;

  return (
    <Box
      data-testid={`brief-signal-${signal.id}`}
      sx={{
        display: 'grid',
        gridTemplateColumns: '20px minmax(0, 1fr) 88px 148px',
        gap: '12px 16px',
        alignItems: 'center',
        px: 2.75,
        py: 1.5,
        borderBottom: `1px solid ${line}`,
        opacity: signal.data_unavailable ? 0.65 : 1,
        '&:hover': { bgcolor: 'action.hover' },
      }}
    >
      <Box sx={{ width: 8, height: 8, borderRadius: '2px', bgcolor: tickColor, ml: 0.75 }} />
      <Typography sx={{ fontSize: '12.5px', color: alpha(theme.palette.text.primary, 0.72) }}>
        <Box component="span" sx={{ color: theme.palette.text.primary, fontWeight: 600 }}>
          {signal.title}
        </Box>
        {signal.detail ? ` — ${signal.detail}` : ''}
      </Typography>
      <Typography
        sx={{
          fontFamily: '"IBM Plex Mono", monospace',
          fontSize: '10.5px',
          color: signal.meta_hot ? 'warning.main' : alpha(theme.palette.text.primary, 0.5),
          textAlign: 'right',
        }}
      >
        {signal.meta ?? '—'}
      </Typography>
      <Box sx={{ textAlign: 'right', position: 'relative' }}>
        <Button
          component={Link}
          href={signal.action_href}
          size="small"
          variant={signal.suggested ? 'contained' : 'outlined'}
          sx={{
            fontSize: '12px',
            fontWeight: signal.suggested ? 600 : 500,
            textTransform: 'none',
            borderRadius: '4px',
            whiteSpace: 'nowrap',
            ...(signal.suggested
              ? {
                  bgcolor: alpha(theme.palette.primary.main, 0.16),
                  borderColor: alpha(theme.palette.primary.main, 0.55),
                  color: 'primary.main',
                  '&:hover': { bgcolor: alpha(theme.palette.primary.main, 0.22) },
                }
              : {}),
          }}
        >
          {signal.action_label}
        </Button>
        {signal.suggested ? (
          <Typography
            component="span"
            sx={{
              position: 'absolute',
              top: -7,
              right: -6,
              fontFamily: '"IBM Plex Mono", monospace',
              fontSize: '8px',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'primary.main',
              bgcolor: 'background.default',
              border: '1px solid',
              borderColor: alpha(theme.palette.primary.main, 0.45),
              borderRadius: '3px',
              px: 0.625,
              py: 0.125,
              lineHeight: 1.2,
            }}
          >
            Suggested
          </Typography>
        ) : null}
      </Box>
    </Box>
  );
}

export function BriefEmptyState() {
  const theme = useTheme();
  return (
    <Box data-testid="brief-empty-state" sx={{ flex: 1, px: 2.75, py: 3.5, maxWidth: '42em' }}>
      <Typography sx={{ fontSize: '13px', color: alpha(theme.palette.text.primary, 0.72) }}>
        No material signals for this period.
      </Typography>
    </Box>
  );
}
