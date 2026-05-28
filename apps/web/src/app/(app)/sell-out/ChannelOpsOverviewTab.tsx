'use client';

import CloseIcon from '@mui/icons-material/Close';
import { Alert, Box, IconButton, Paper, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import {
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
} from 'recharts';

import { apiGet } from '@/lib/api';

import { useChannelOpsSummary } from './ChannelOpsKpiCards';
import { depthAtLeast, type IntelDepth } from './intelDepth';

type WeeklySeries = { weeks: number; points: { week_start: string; units: number }[] };

function bannerKey(id: string) {
  return `cip.channel_ops.banner.${id}`;
}

export function ChannelOpsOverviewTab({
  depth,
  distributorId,
}: {
  depth: IntelDepth;
  distributorId?: number | null;
}) {
  const { data: summary } = useChannelOpsSummary(distributorId);
  const [dismissed, setDismissed] = useState<Record<string, boolean>>(() => {
    if (typeof window === 'undefined') return {};
    return {
      recon: sessionStorage.getItem(bannerKey('recon')) === '1',
      velocity: sessionStorage.getItem(bannerKey('velocity')) === '1',
      forecast: sessionStorage.getItem(bannerKey('forecast')) === '1',
    };
  });

  const { data: weekly, isLoading: weeklyLoading, isError: weeklyError } = useQuery({
    queryKey: ['channel-ops-weekly', distributorId ?? null],
    queryFn: ({ signal }) => {
      const params = new URLSearchParams({ weeks: '13' });
      if (distributorId != null) params.set('distributor_id', String(distributorId));
      return apiGet<WeeklySeries>(`/api/v1/channel-ops/weekly-series?${params}`, { signal });
    },
  });

  const chartData = useMemo(
    () =>
      (weekly?.points ?? []).map((p) => ({
        label: p.week_start.slice(5),
        units: p.units,
        forecast: depthAtLeast(depth, 'forecast') ? p.units * 1.05 : undefined,
      })),
    [weekly?.points, depth]
  );

  const dismiss = (id: string) => {
    sessionStorage.setItem(bannerKey(id), '1');
    setDismissed((d) => ({ ...d, [id]: true }));
  };

  const showBanners = depthAtLeast(depth, 'operational');

  return (
    <Box>
      {showBanners && (
        <StackBanners
          summary={summary}
          depth={depth}
          dismissed={dismissed}
          onDismiss={dismiss}
        />
      )}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          Sell-out by week
          {depthAtLeast(depth, 'forecast') ? ' · with forecast overlay' : ''}
        </Typography>
        {weeklyError ? (
          <Alert severity="error">Could not load weekly sell-out chart.</Alert>
        ) : weeklyLoading ? (
          <Typography variant="body2">Loading chart…</Typography>
        ) : chartData.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No sell-out transactions in the last 13 weeks.
          </Typography>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            {depthAtLeast(depth, 'strategic') ? (
              <ComposedChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" fontSize={11} />
                <YAxis fontSize={11} />
                <Tooltip />
                <Legend />
                <Bar dataKey="units" fill="#1976d2" name="Sell-out units" />
                <Line type="monotone" dataKey="units" stroke="#2e7d32" name="Trend" dot={false} />
                {depthAtLeast(depth, 'forecast') && (
                  <Bar dataKey="forecast" fill="#90caf9" name="Forecast (illustrative)" />
                )}
              </ComposedChart>
            ) : (
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" fontSize={11} />
                <YAxis fontSize={11} />
                <Tooltip />
                <Bar dataKey="units" fill="#1976d2" name="Sell-out units" />
              </BarChart>
            )}
          </ResponsiveContainer>
        )}
      </Paper>
    </Box>
  );
}

function StackBanners({
  summary,
  depth,
  dismissed,
  onDismiss,
}: {
  summary: ReturnType<typeof useChannelOpsSummary>['data'];
  depth: IntelDepth;
  dismissed: Record<string, boolean>;
  onDismiss: (id: string) => void;
}) {
  const banners: { id: string; severity: 'info' | 'warning'; text: string }[] = [];
  if (summary && !summary.has_reconciliation_data && !dismissed.recon) {
    banners.push({ id: 'recon', severity: 'warning', text: 'SOH reconciliation not yet run' });
  }
  if (summary && !summary.has_velocity_data && !dismissed.velocity) {
    banners.push({
      id: 'velocity',
      severity: 'info',
      text: 'Velocity model building — apply more DSI uploads',
    });
  }
  if (depthAtLeast(depth, 'forecast') && summary && !summary.has_forecast_data && !dismissed.forecast) {
    banners.push({
      id: 'forecast',
      severity: 'info',
      text: 'Forecasts generate after the first DSI apply',
    });
  }
  if (!banners.length) return null;
  return (
    <Box sx={{ mb: 2 }}>
      {banners.map((b) => (
        <Alert
          key={b.id}
          severity={b.severity}
          sx={{ mb: 1 }}
          action={
            <IconButton size="small" aria-label="dismiss" onClick={() => onDismiss(b.id)}>
              <CloseIcon fontSize="small" />
            </IconButton>
          }
        >
          {b.text}
        </Alert>
      ))}
    </Box>
  );
}
