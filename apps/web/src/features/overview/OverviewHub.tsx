'use client';

import { Box, Button, Stack, Typography, useMediaQuery } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useQuery } from '@tanstack/react-query';
import NextLink from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';

import type { BriefSignal } from '@/features/brief/BriefSignalRow';
import { DashboardWidgetCard } from '@/features/dashboards/DashboardWidgetCard';
import type { CatalogResponse, Dashboard } from '@/features/dashboards/types';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';
import { apiGet } from '@/lib/api';

import { overviewAttentionFirst } from './overviewPaths';
import { useClientReady } from './useClientReady';

type BriefSignalsResponse = {
  as_of: string;
  read: string;
  signals: BriefSignal[];
  signal_count?: number;
};

type SavedReportItem = {
  id: number;
  name: string;
  metric_key?: string;
  visibility?: string;
};

function signalSeverity(s: BriefSignal): 'danger' | 'warning' | 'info' | 'neutral' {
  if (s.severity === 'stop') return 'danger';
  if (s.severity === 'warn') return 'warning';
  if (s.severity === 'ok') return 'info';
  return 'neutral';
}

export function OverviewHub() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const search = useSearchParams();
  const router = useRouter();
  const ready = useClientReady();
  const attentionFirst = overviewAttentionFirst(isMobile, search?.get('zone'));

  const briefQ = useQuery({
    queryKey: ['brief', 'signals'],
    queryFn: ({ signal }) => apiGet<BriefSignalsResponse>('/api/v1/brief/signals', { signal }),
    staleTime: 30_000,
  });
  const dashQ = useQuery({
    queryKey: ['dashboards'],
    queryFn: ({ signal }) => apiGet<{ items: Dashboard[] }>('/api/v1/dashboards', { signal }),
    retry: false,
  });
  const catalogQ = useQuery({
    queryKey: ['semantics-catalog'],
    queryFn: ({ signal }) => apiGet<CatalogResponse>('/api/v1/semantics/catalog', { signal }),
    staleTime: 60_000,
  });
  const reportsQ = useQuery({
    queryKey: ['saved-reports'],
    queryFn: ({ signal }) => apiGet<{ items: SavedReportItem[]; count: number }>('/api/v1/saved-reports', { signal }),
    retry: false,
  });

  const brief = ready ? briefQ.data : undefined;
  const dashboards = ready ? dashQ.data?.items ?? [] : [];
  const reports = ready ? reportsQ.data?.items ?? [] : [];
  const metrics = catalogQ.data?.metrics ?? [];

  const signals = brief?.signals ?? [];
  const urgent = signals.filter((s) => s.severity === 'stop' || s.severity === 'warn');
  const informational = signals.filter((s) => s.severity === 'ok');
  const active = dashboards[0];
  const widgets = active?.widgets ?? [];

  const awaitingBrief = !ready || briefQ.isLoading;
  const briefUnavailable = !awaitingBrief && Boolean(briefQ.isError);

  const dashboard = (
    <Panel
      title="Business dashboard"
      subtitle={
        active
          ? `${active.name} · ${widgets.length} widget${widgets.length === 1 ? '' : 's'} over governed metrics · live query, not lab fixtures`
          : 'No tenant dashboard yet — create one on the dashboard leaf. Lab fixture widgets are not copied.'
      }
      actions={
        <Button size="small" variant="outlined" component={NextLink} href="/dashboards" data-testid="overview-edit-dashboard">
          Edit
        </Button>
      }
      flush
    >
      <Box data-testid="dashboard-zone" sx={{ px: 2, pb: 2 }}>
        {dashQ.isError ? (
          <Typography color="text.secondary" variant="body2">
            Dashboards are not available right now. The editor at /dashboards is still reachable.
          </Typography>
        ) : !active ? (
          <Typography color="text.secondary" variant="body2">
            No dashboards yet. Open Business dashboard to create one — this hub does not invent fixture KPIs.
          </Typography>
        ) : widgets.length === 0 ? (
          <Typography color="text.secondary" variant="body2">
            {active.name} has no widgets yet. Add them on /dashboards.
          </Typography>
        ) : (
          <Stack spacing={1.5}>
            {widgets.map((w) => (
              <DashboardWidgetCard
                key={w.id}
                widget={w}
                metric={metrics.find((m) => m.key === w.metric_key)}
                onEdit={() => router.push('/dashboards')}
                onDelete={() => router.push('/dashboards')}
                onPromote={() => router.push('/dashboards')}
              />
            ))}
          </Stack>
        )}
      </Box>
    </Panel>
  );

  const attention = (
    <Stack spacing={1.5} data-testid="attention-zone">
      <Panel
        title="Needs attention"
        subtitle={
          awaitingBrief
            ? 'Loading live signals…'
            : briefUnavailable
              ? 'Attention signals are not available yet'
              : `${urgent.length} urgent · ${informational.length} informational · live from /api/v1/brief/signals`
        }
        flush
      >
        <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
          {awaitingBrief ? (
            <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }}>
              Loading attention…
            </Typography>
          ) : briefUnavailable ? (
            <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }}>
              Could not load attention signals.
            </Typography>
          ) : signals.length === 0 ? (
            <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }}>
              Nothing outstanding.
            </Typography>
          ) : (
            <>
              {urgent.map((s) => (
                <PanelRow
                  key={s.id}
                  severity={signalSeverity(s)}
                  primary={s.title}
                  secondary={s.detail || s.meta || undefined}
                  figure={s.meta ?? undefined}
                  href={s.action_href}
                />
              ))}
              {informational.length ? (
                <Typography variant="caption" color="text.secondary" sx={{ px: 1.5, pt: 1 }}>
                  Informational
                </Typography>
              ) : null}
              {informational.map((s) => (
                <PanelRow
                  key={s.id}
                  severity="info"
                  primary={s.title}
                  secondary={s.detail || undefined}
                  figure={s.meta ?? undefined}
                  href={s.action_href}
                />
              ))}
            </>
          )}
        </Stack>
      </Panel>
      <Panel
        title="Pinned reports"
        subtitle="Saved governed reports listed here. Pinning a saved report onto this Overview as a widget is not built."
        actions={
          <Button size="small" component={NextLink} href="/reports" data-testid="overview-all-reports">
            All reports
          </Button>
        }
        flush
      >
        <Stack spacing={0.25} sx={{ px: 1, pb: 1 }} data-testid="pinned-reports">
          {reportsQ.isError ? (
            <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }}>
              Saved reports are not available right now.
            </Typography>
          ) : reports.length === 0 ? (
            <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }}>
              No saved reports yet. The report builder is at /reports.
            </Typography>
          ) : (
            reports.map((r) => (
              <PanelRow
                key={r.id}
                severity="neutral"
                primary={r.name}
                secondary={r.metric_key ? `${r.metric_key}${r.visibility ? ` · ${r.visibility}` : ''}` : r.visibility}
                href="/reports"
              />
            ))
          )}
        </Stack>
      </Panel>
    </Stack>
  );

  return (
    <Box data-testid="overview-surface">
      <Box
        sx={{
          display: 'grid',
          gap: 2,
          gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'minmax(0, 1fr) 312px' },
          alignItems: 'start',
        }}
      >
        {attentionFirst ? (
          <>
            {attention}
            {dashboard}
          </>
        ) : (
          <>
            {dashboard}
            {attention}
          </>
        )}
      </Box>
    </Box>
  );
}
