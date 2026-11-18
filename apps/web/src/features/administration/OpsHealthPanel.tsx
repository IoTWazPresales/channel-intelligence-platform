'use client';

import { Chip, Paper, Stack, Typography } from '@mui/material';

/** GET /admin/ops/overview `health` (apps/api/app/services/ops_health.py). */
export type OpsServiceRow = {
  name: string;
  state: string | null;
  launches: number | null;
  launches_30m: number;
  flapping: boolean;
  last_healthy: string | null;
  detail: string | null;
};

export type OpsHealth = {
  services: {
    state: string;
    detail: string;
    heartbeat_age_seconds?: number | null;
    flap_limit_30m?: number;
    components: OpsServiceRow[];
  };
  backups: {
    state: string;
    backup: { state: string; detail: string; finished?: string | null; bytes?: number | null };
    restore: { state: string; detail: string; finished?: string | null };
  };
  reports: {
    state: string;
    detail: string;
    late: number;
    missing: number;
    expected_customers: number;
    newest_received: string | null;
    days_since_newest: number | null;
  };
};

type ChipColor = 'success' | 'warning' | 'error' | 'default';

export function healthColor(state: string | null | undefined): ChipColor {
  if (state === 'ok' || state === 'healthy') return 'success';
  if (state === 'failed' || state === 'flapping' || state === 'missing') return 'error';
  if (state === 'stale' || state === 'degraded' || state === 'late') return 'warning';
  return 'default';
}

function StateChip({ state, testId }: { state: string | null | undefined; testId?: string }) {
  return <Chip size="small" color={healthColor(state)} label={state ?? 'unknown'} data-testid={testId} />;
}

export function OpsHealthPanel({ health }: { health: OpsHealth | null | undefined }) {
  if (!health) {
    return (
      <Paper sx={{ p: 2, mb: 2 }} data-testid="ops-health-panel">
        <Typography variant="subtitle2">Operations health</Typography>
        <Typography variant="body2" color="text.secondary">
          Not reported by this API version.
        </Typography>
      </Paper>
    );
  }
  const { services, backups, reports } = health;
  return (
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }} data-testid="ops-health-panel">
      <Paper sx={{ p: 2, flex: 1 }} data-testid="ops-health-services">
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <Typography variant="subtitle2">Services</Typography>
          <StateChip state={services.state} testId="ops-health-services-state" />
        </Stack>
        <Typography variant="body2" color="text.secondary">
          {services.detail}
        </Typography>
        {services.components.map((c) => (
          <Typography key={c.name} variant="caption" display="block">
            {c.name}: {c.state ?? 'unknown'} · {c.launches_30m} launches in 30 min{c.flapping ? ' (flapping)' : ''}
          </Typography>
        ))}
      </Paper>
      <Paper sx={{ p: 2, flex: 1 }} data-testid="ops-health-backups">
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <Typography variant="subtitle2">Backups</Typography>
          <StateChip state={backups.state} testId="ops-health-backups-state" />
        </Stack>
        <Typography variant="body2">Nightly backup: {backups.backup.detail}</Typography>
        <Typography variant="body2">Restore test: {backups.restore.detail}</Typography>
      </Paper>
      <Paper sx={{ p: 2, flex: 1 }} data-testid="ops-health-reports">
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <Typography variant="subtitle2">Weekly reports (due Monday)</Typography>
          <StateChip state={reports.state} testId="ops-health-reports-state" />
        </Stack>
        <Typography variant="body2">{reports.detail}</Typography>
        <Typography variant="caption" display="block">
          Customers expected to report: {reports.expected_customers}
          {reports.days_since_newest != null ? ` · newest report ${reports.days_since_newest} days ago` : ''}
        </Typography>
      </Paper>
    </Stack>
  );
}