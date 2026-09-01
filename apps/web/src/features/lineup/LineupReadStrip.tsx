'use client';

import { Box, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useQuery } from '@tanstack/react-query';

import { isPendingApproval, type LineupPlanRow } from '@/features/lineup/lineupTypes';
import { apiGet } from '@/lib/api';

export function LineupReadStrip() {
  const theme = useTheme();

  const { data: items } = useQuery({
    queryKey: ['lineup-items'],
    queryFn: ({ signal }) => apiGet<LineupPlanRow[]>('/api/v1/lineup/items', { signal }),
    staleTime: 30_000,
  });

  const { data: pve } = useQuery({
    queryKey: ['plan-vs-executed', 'lineup-read'],
    queryFn: ({ signal }) =>
      apiGet<{ scorecard?: { fill_rate?: number | null }; data_unavailable?: boolean }>(
        '/api/v1/plan-vs-executed',
        { signal },
      ),
    staleTime: 120_000,
  });

  const rows = items ?? [];
  const pendingCount = rows.filter((r) => isPendingApproval(r.approval_status)).length;
  const fillPct =
    pve?.data_unavailable || pve?.scorecard?.fill_rate == null
      ? null
      : Math.round((pve.scorecard.fill_rate ?? 0) * 100);

  return (
    <Box data-testid="lineup-read-strip" sx={{ display: 'flex', alignItems: 'baseline', gap: 1.25, mb: 1.25 }}>
      <Typography
        component="span"
        sx={{
          fontFamily: '"IBM Plex Mono", monospace',
          fontSize: '9px',
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: '#3db8e8',
          border: `1px solid ${alpha('#3db8e8', 0.35)}`,
          borderRadius: '3px',
          px: 0.75,
          py: 0.25,
        }}
      >
        Read
      </Typography>
      <Typography sx={{ fontSize: '12px', color: alpha(theme.palette.text.primary, 0.75), m: 0 }}>
        {fillPct != null ? (
          <>
            <Box component="span" sx={{ fontWeight: 600, color: alpha(theme.palette.text.primary, 0.96) }}>
              {fillPct}% plan coverage
            </Box>{' '}
            shipped against 26Q3 lineup (Q1+Q2 combined).{' '}
          </>
        ) : null}
        <Box component="span" sx={{ fontWeight: 600, color: alpha(theme.palette.text.primary, 0.96) }}>
          {pendingCount} item{pendingCount === 1 ? '' : 's'}
        </Box>{' '}
        still pending approval before Stock can trust Fill vs plan.
      </Typography>
    </Box>
  );
}
