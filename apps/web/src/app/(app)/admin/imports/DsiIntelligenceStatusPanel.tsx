'use client';

import { Alert, Box, Stack, Typography } from '@mui/material';

type LayerStatus = 'active' | 'degraded' | 'initialising' | 'inactive';

type IntelligenceBanner = {
  level?: string;
  message?: string;
  layer?: string;
};

export type DsiIntelligenceState = {
  prior_applied_job_count?: number;
  auto_resolution_tier?: string;
  detected_mode?: string;
  intelligence_layers?: Record<string, LayerStatus>;
  banners?: IntelligenceBanner[];
};

function statusDotColor(status: LayerStatus | undefined): string {
  if (status === 'active') return 'success.main';
  if (status === 'degraded' || status === 'initialising') return 'warning.main';
  return 'error.main';
}

const LAYER_LABELS: Record<string, string> = {
  token_auto_resolution: 'Token auto-resolution',
  soh_reconciliation: 'SOH reconciliation',
  velocity_learning: 'Velocity learning',
  pricing_intelligence: 'Pricing intelligence',
  forecasting: 'Forecasting',
};

export function DsiIntelligenceStatusPanel({
  intelligenceState,
}: {
  intelligenceState: DsiIntelligenceState | null | undefined;
}) {
  if (!intelligenceState || typeof intelligenceState !== 'object') {
    return null;
  }

  const layers = intelligenceState.intelligence_layers ?? {};
  const banners = Array.isArray(intelligenceState.banners) ? intelligenceState.banners : [];
  const tier = intelligenceState.auto_resolution_tier ?? 'none';

  return (
    <Stack spacing={1.5} data-testid="dsi-intelligence-status-panel">
      <Typography variant="subtitle2">Import intelligence</Typography>
      <Typography variant="caption" color="text.secondary">
        Mode: {intelligenceState.detected_mode ?? '—'} · Auto-resolution tier: {tier}
        {typeof intelligenceState.prior_applied_job_count === 'number'
          ? ` · Prior applied jobs: ${intelligenceState.prior_applied_job_count}`
          : null}
      </Typography>
      <Stack direction="row" flexWrap="wrap" useFlexGap spacing={2}>
        {Object.entries(LAYER_LABELS).map(([key, label]) => {
          const status = layers[key as keyof typeof layers];
          return (
            <Stack key={key} direction="row" spacing={1} alignItems="center" data-testid={`dsi-layer-${key}`}>
              <Box
                sx={{
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  bgcolor: statusDotColor(status),
                  flexShrink: 0,
                }}
                aria-hidden
              />
              <Typography variant="body2">
                {label}
                {status ? ` (${status})` : ''}
              </Typography>
            </Stack>
          );
        })}
      </Stack>
      {banners.map((b, i) => (
        <Alert
          key={`${b.layer ?? 'banner'}-${i}`}
          severity={b.level === 'warning' ? 'warning' : 'info'}
          data-testid="dsi-intelligence-banner"
        >
          {b.message}
        </Alert>
      ))}
    </Stack>
  );
}
