'use client';

import { Box, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';

import { CapabilityStatus } from '@/features/shell/CapabilityStatus';
import { inRail, leafStatusLabel, navGroups } from '@/features/shell/navConfig';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';
import { apiGet } from '@/lib/api';

import { adminWorkflowHref } from './adminPaths';
import { fmtInt } from './format';
import type { AdministrationOverview } from './types';
import { useClientReady } from './useClientReady';

function operationSeverity(status: string): 'info' | 'danger' | 'neutral' {
  if (status === 'failed') return 'danger';
  if (status === 'running') return 'info';
  return 'neutral';
}

export function AdminOverview() {
  const router = useRouter();
  const ready = useClientReady();
  const { data: summary, isLoading, isError } = useQuery({
    queryKey: ['administration', 'overview'],
    queryFn: ({ signal }) => apiGet<AdministrationOverview>('/api/v1/administration/overview', { signal }),
    staleTime: 30_000,
  });
  const data = ready ? summary : undefined;
  const awaiting = !ready || isLoading;
  const unavailable = !awaiting && Boolean(isError || !data || data.data_unavailable);
  const figures = Boolean(data && !awaiting && !unavailable);
  const admin = navGroups.find((g) => g.id === 'admin');
  const workflows = (admin?.items ?? []).filter(inRail);
  const notInRail = (admin?.items ?? []).filter((l) => !inRail(l));
  const failed24 = data?.failed_24h ?? 0;
  const failedOpen = data?.failed_open ?? 0;
  const pending = data?.jobs_pending ?? 0;
  const attentionCount =
    (failed24 > 0 ? 1 : 0) + (failedOpen > 0 && failed24 === 0 ? 1 : 0) + (pending > 0 ? 1 : 0);

  return (
    <Box data-testid="domain-admin">
      {awaiting ? (
        <Typography color="text.secondary" sx={{ px: 1, py: 1 }} data-testid="admin-overview-loading">
          Loading Administration…
        </Typography>
      ) : unavailable ? (
        <Typography color="text.secondary" sx={{ px: 1, py: 1 }} data-testid="admin-overview-empty">
          Administration headlines are not available yet.
        </Typography>
      ) : (
        <HeadlineStrip columns={4}>
          <HeadlineFigure
            label={data?.labels.users ?? 'Users'}
            value={data ? fmtInt(data.users) : '—'}
            compact
            caption={data?.captions.users}
            onClick={() => router.push('/admin/users/list')}
          />
          <HeadlineFigure
            label={data?.labels.jobs_running ?? 'Background jobs running'}
            value={data ? fmtInt(data.jobs_running) : '—'}
            compact
            caption={data?.captions.jobs_running}
            onClick={() => router.push('/admin/ops')}
          />
          <HeadlineFigure
            label={data?.labels.failed_24h ?? 'Failed jobs (24h)'}
            value={data ? fmtInt(data.failed_24h) : '—'}
            compact
            severity={failed24 > 0 ? 'warn' : undefined}
            caption={data?.captions.failed_24h}
            onClick={() => router.push('/admin/ops')}
          />
          <HeadlineFigure
            label={data?.labels.sql_queries_7d ?? 'Audited SQL queries (7d)'}
            value={data ? fmtInt(data.sql_queries_7d) : '—'}
            compact
            caption={data?.captions.sql_queries_7d}
            onClick={() => router.push('/admin/sql-viewer')}
          />
        </HeadlineStrip>
      )}
      <Box
        sx={{
          display: 'grid',
          gap: 2,
          gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'minmax(0, 3fr) minmax(280px, 2fr)' },
          mt: 2,
          alignItems: 'start',
        }}
      >
        <Stack spacing={2}>
          {figures ? (
            <Panel
              title="Operations"
              subtitle="Background tasks register with the activity feed; nothing runs silently"
              flush
            >
              <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
                {data?.operations?.length ? (
                  data.operations.map((row) => (
                    <PanelRow
                      key={row.id}
                      severity={operationSeverity(row.status)}
                      primary={`${row.template_slug ?? 'import'} · job ${row.id}`}
                      secondary={`${row.status} · ${row.stage}${row.error_summary ? ` · ${row.error_summary}` : ''}`}
                      figure={row.status}
                      href="/admin/ops"
                    />
                  ))
                ) : (
                  <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }}>
                    No running, pending, or failed import jobs.
                  </Typography>
                )}
              </Stack>
            </Panel>
          ) : null}
        </Stack>
        <Stack spacing={2}>
          {figures ? (
            <Panel
              title="Needs attention in this area"
              subtitle={attentionCount ? `${attentionCount} live signal${attentionCount === 1 ? '' : 's'}` : 'Nothing outstanding'}
              flush
            >
              <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
                {failed24 > 0 ? (
                  <PanelRow
                    severity="danger"
                    primary={`${fmtInt(failed24)} import jobs failed in the last 24 hours`}
                    secondary={data?.captions.failed_24h}
                    href="/admin/ops"
                  />
                ) : null}
                {failedOpen > 0 && failed24 === 0 ? (
                  <PanelRow
                    severity="warning"
                    primary={`${fmtInt(failedOpen)} failed import jobs still open`}
                    secondary="Open failed import_job rows (not the 24h headline grain)"
                    href="/admin/ops"
                  />
                ) : null}
                {pending > 0 ? (
                  <PanelRow
                    severity="info"
                    primary={`${fmtInt(pending)} import jobs pending`}
                    secondary="Queued import_job.status='pending'; not counted as running"
                    href="/admin/ops"
                  />
                ) : null}
                {attentionCount === 0 ? (
                  <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }}>
                    No signals for Administration right now.
                  </Typography>
                ) : null}
              </Stack>
            </Panel>
          ) : null}
          <Panel title="Workflows" subtitle="What you can do here" flush>
            <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
              {workflows.map((l) => (
                <PanelRow
                  key={l.href}
                  severity="neutral"
                  primary={
                    <Stack direction="row" spacing={0.75} alignItems="center" component="span">
                      <span>{l.label}</span>
                      <CapabilityStatus status={l.status} size="inline" />
                    </Stack>
                  }
                  secondary={l.what}
                  href={adminWorkflowHref(l.href)}
                />
              ))}
              {notInRail.length ? (
                <Typography variant="caption" color="text.disabled" sx={{ px: 1.5, pt: 1 }}>
                  Not in navigation yet:{' '}
                  {notInRail
                    .map((l) => `${l.label} (${leafStatusLabel[l.status ?? 'live'].toLowerCase()})`)
                    .join(', ')}{' '}
                  — listed in the capability directory. Platform audit log is planned; this is not steward-audit.
                </Typography>
              ) : null}
            </Stack>
          </Panel>
        </Stack>
      </Box>
    </Box>
  );
}
