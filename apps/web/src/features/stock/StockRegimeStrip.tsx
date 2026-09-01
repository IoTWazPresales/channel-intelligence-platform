'use client';

import { Box, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useQuery } from '@tanstack/react-query';

import type { ChannelOpsSummary } from '@/app/(app)/sell-out/ChannelOpsKpiCards';
import { apiGet } from '@/lib/api';

type RegimeTile = {
  label: string;
  value: string;
  tone?: 'risk' | 'neutral';
};

export function StockRegimeStrip() {
  const theme = useTheme();

  const { data: opsSummary } = useQuery({
    queryKey: ['channel-ops-summary', null],
    queryFn: ({ signal }) => apiGet<ChannelOpsSummary>('/api/v1/channel-ops/summary', { signal }),
    staleTime: 60_000,
  });

  const { data: coverDist } = useQuery({
    queryKey: ['channel-ops', 'cover-distribution'],
    queryFn: ({ signal }) =>
      apiGet<{ under_4w?: number; mean_woc?: number | null; data_unavailable?: boolean }>(
        '/api/v1/channel-ops/cover-distribution',
        { signal },
      ),
    staleTime: 60_000,
  });

  const { data: pve } = useQuery({
    queryKey: ['plan-vs-executed', 'regime'],
    queryFn: ({ signal }) =>
      apiGet<{ scorecard?: { fill_rate?: number | null }; data_unavailable?: boolean }>(
        '/api/v1/plan-vs-executed',
        { signal },
      ),
    staleTime: 120_000,
  });

  const { data: shipSummary } = useQuery({
    queryKey: ['shipping', 'summary', 'regime'],
    queryFn: ({ signal }) =>
      apiGet<{ total_lines?: number; by_line_state?: { key: string; count: number }[] }>(
        '/api/v1/shipping/summary',
        { signal },
      ),
    staleTime: 60_000,
  });

  const under4 =
    coverDist?.data_unavailable === false
      ? String(coverDist.under_4w ?? opsSummary?.replenishment_pairs_below_threshold ?? '—')
      : opsSummary?.replenishment_pairs_below_threshold != null
        ? String(opsSummary.replenishment_pairs_below_threshold)
        : '—';

  const meanWoc =
    coverDist?.mean_woc != null
      ? `${coverDist.mean_woc}w`
      : opsSummary?.weeks_of_cover != null
        ? `${opsSummary.weeks_of_cover.toFixed(1)}w`
        : '—';

  const fillRate =
    pve?.data_unavailable || pve?.scorecard?.fill_rate == null
      ? '—'
      : `${(pve.scorecard.fill_rate * 100).toFixed(1)}%`;

  const notReceived = (() => {
    const buckets = shipSummary?.by_line_state ?? [];
    const open = buckets.find((b) => b.key === 'open' || b.key === 'pipeline');
    if (open) return String(open.count);
    if (shipSummary?.total_lines != null) return String(shipSummary.total_lines);
    return '—';
  })();

  const tiles: RegimeTile[] = [
    { label: 'Under 4w', value: under4, tone: Number(under4) > 0 ? 'risk' : 'neutral' },
    { label: 'Book mean', value: meanWoc },
    { label: 'Fill vs plan', value: fillRate },
    { label: 'Not received', value: notReceived },
  ];

  return (
    <Box
      data-testid="stock-regime-strip"
      sx={{
        display: 'flex',
        gap: 3.25,
        ml: 'auto',
        flexWrap: 'wrap',
        justifyContent: 'flex-end',
      }}
    >
      {tiles.map((t) => (
        <Box key={t.label} sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.25 }}>
          <Typography sx={{ fontSize: '9.5px', letterSpacing: '0.09em', textTransform: 'uppercase', color: alpha(theme.palette.text.primary, 0.45) }}>
            {t.label}
          </Typography>
          <Typography
            sx={{
              fontFamily: '"IBM Plex Mono", monospace',
              fontSize: '13px',
              color: t.tone === 'risk' ? '#e8b4b4' : alpha(theme.palette.text.primary, 0.72),
            }}
          >
            {t.value}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}
