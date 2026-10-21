'use client';

import { Box, Button, Stack, ToggleButton, ToggleButtonGroup, Typography, useMediaQuery } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import NextLink from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import type { BriefSignal } from '@/features/brief/BriefSignalRow';
import { DashboardWidgetCard } from '@/features/dashboards/DashboardWidgetCard';
import type { CatalogResponse, Dashboard } from '@/features/dashboards/types';
import { StartWorkPanel } from '@/features/overview/StartWorkPanel';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';
import { apiDelete, apiGet } from '@/lib/api';

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
  visibility?: string;
  overview_pinned?: boolean;
};

const COLUMNS_KEY = 'cip.overview.dashboard.columns.v1';

/** Charts per row on the Attention dashboard (Warren 2026-10-19): 1, 2 or 3, kept in this browser. */
export function useDashboardColumns(): [1 | 2 | 3, (n: 1 | 2 | 3) => void] {
  const [cols, setCols] = useState<1 | 2 | 3>(2);
  useEffect(() => {
    try {
      const v = Number(window.localStorage.getItem(COLUMNS_KEY));
      if (v === 1 || v === 2 || v === 3) setCols(v);
    } catch {
      /* storage unavailable: keep the default */
    }
  }, []);
  const set = (n: 1 | 2 | 3) => {
    setCols(n);
    try {
      window.localStorage.setItem(COLUMNS_KEY, String(n));
    } catch {
      /* storage unavailable: the choice lasts for this visit */
    }
  };
  return [cols, set];
}

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
  const qc = useQueryClient();
  const unpin = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/saved-reports/${id}/overview-pin`),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['saved-reports'] });
    },
  });
  const attentionFirst = overviewAttentionFirst(isMobile, search?.get('zone'));
  const [columns, setColumns] = useDashboardColumns();

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
  const pinnedReports = reports.filter((r) => r.overview_pinned);
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
          : 'Editor lives on the Business dashboard leaf. Lab fixture widgets are not copied.'
      }
      actions={
        <Stack direction="row" spacing={1} alignItems="center">
          <ToggleButtonGroup
            size="small"
            exclusive
            value={columns}
            onChange={(_e, v: 1 | 2 | 3 | null) => v && setColumns(v)}
            aria-label="Charts per row"
            data-testid="overview-dashboard-columns"
          >
            {[1, 2, 3].map((n) => (
              <ToggleButton key={n} value={n} sx={{ px: 1, py: 0 }} aria-label={`${n} per row`}>
                {n}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
          <Button size="small" variant="outlined" component={NextLink} href="/dashboards" data-testid="overview-edit-dashboard">
            Edit
          </Button>
        </Stack>
      }
      flush
    >
      <Box data-testid="dashboard-zone" sx={{ px: 2, pb: 2 }}>
        {dashQ.isError ? (
          <Typography color="text.secondary" variant="body2">
            Dashboards are not available right now. The editor at /dashboards is still reachable.
          </Typography>
        ) : !active || widgets.length === 0 ? (
          <PanelRow
            severity="neutral"
            primary="Open Business dashboard"
            secondary={
              !active
                ? 'No tenant dashboard yet. This hub does not invent fixture KPIs.'
                : `${active.name} has no widgets yet.`
            }
            href="/dashboards"
          />
        ) : (
          <Box
            data-testid="dashboard-widget-grid"
            sx={{
              display: 'grid',
              gap: 1.5,
              gridTemplateColumns: { xs: '1fr', md: `repeat(${Math.min(columns, 2)}, minmax(0, 1fr))`, xl: `repeat(${columns}, minmax(0, 1fr))` },
            }}
          >
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
          </Box>
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
              : `${urgent.length} urgent · ${informational.length} informational`
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
        subtitle="Reports you pinned. Each person has their own list."
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
          ) : pinnedReports.length === 0 ? (
            <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }}>
              Nothing pinned. Open All reports and choose Pin to Overview.
            </Typography>
          ) : (
            pinnedReports.map((r) => (
              <Stack key={r.id} direction="row" alignItems="center" spacing={0.5} data-testid={`pinned-report-${r.id}`}>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <PanelRow
                    severity="neutral"
                    primary={r.name}
                    secondary={r.visibility === 'published' ? 'Shared' : 'Only you'}
                    href="/reports"
                  />
                </Box>
                <Button size="small" variant="text" onClick={() => unpin.mutate(r.id)} data-testid={`unpin-report-${r.id}`}>
                  Unpin
                </Button>
              </Stack>
            ))
          )}
        </Stack>
      </Panel>
    </Stack>
  );

  const start = <StartWorkPanel />;
  const stackAttention = isMobile || attentionFirst;

  return (
    <Box data-testid="overview-surface">
      <Stack spacing={2}>
        {start}
        {stackAttention ? (
          <>
            {attention}
            {dashboard}
          </>
        ) : (
          <Box
            data-testid="overview-body"
            sx={{
              display: 'grid',
              gap: 2,
              gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'minmax(0, 1fr) 312px' },
              alignItems: 'start',
            }}
          >
            {dashboard}
            {attention}
          </Box>
        )}
      </Stack>
    </Box>
  );
}
