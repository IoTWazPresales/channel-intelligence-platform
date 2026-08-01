'use client';

import { Alert, Box, Chip, Link, Paper, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import NextLink from 'next/link';

import { KpiCard } from '@/components/KpiCard';
import { PageHeader } from '@/components/PageHeader';
import { apiGet } from '@/lib/api';
import { isCommercialPlannerEnabled } from '@/features/shell/navConfig';
import { useCurrentUser } from '@/features/shell/useCurrentUser';
import { useUiStore } from '@/stores/uiStore';

type FreshnessTemplate = {
  template_slug: string;
  completed_at: string;
  import_job_id: number | null;
  age_hours: number;
  stale: boolean;
};

type Summary = {
  kpis: {
    open_exceptions: number;
    open_budget_requests: number;
    inbound_shipments_tracked: number;
    failed_import_jobs?: number;
    commercial_planner?: {
      plan_count: number;
      plans_not_ready: number;
      plans_with_lines: number;
    } | null;
  };
  freshness?: {
    tenant_id: string;
    as_of: string;
    newest_completed_at: string | null;
    newest_age_hours: number | null;
    stale_after_hours: number;
    is_stale: boolean;
    by_template: FreshnessTemplate[];
  };
  stock_health: Record<string, number>;
  recommended_actions: { title: string; href: string; reason: string }[];
};

function formatAgeHours(hours: number | null | undefined): string {
  if (hours == null) return 'no completed imports yet';
  if (hours < 1) return 'less than 1 hour ago';
  if (hours < 48) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function DashboardPage() {
  const openDrawer = useUiStore((s) => s.openDrawer);
  const { data: me } = useCurrentUser();
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-summary'],
    queryFn: ({ signal }) => apiGet<Summary>('/api/v1/dashboard/summary', { signal }),
  });

  const freshness = data?.freshness;
  const greetingName = me?.display_name || me?.email || 'there';

  return (
    <>
      <PageHeader crumbs={[{ label: 'Overview' }]} title="Control tower" />
      {isLoading ? (
        <Typography color="text.secondary">Loading…</Typography>
      ) : (
        <>
          <Typography variant="body1" sx={{ mb: 1.5 }}>
            Welcome{me ? `, ${greetingName}` : ''}. This is your landing surface — freshness, attention items, and
            shortcuts into the rest of the platform.
          </Typography>

          {freshness ? (
            <Alert
              severity={freshness.is_stale ? 'warning' : 'success'}
              sx={{ mb: 2 }}
              data-testid="data-freshness-banner"
            >
              <Typography variant="subtitle2" fontWeight={700} gutterBottom>
                Data freshness
              </Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                Newest successful import:{' '}
                <strong>{formatAgeHours(freshness.newest_age_hours)}</strong>
                {freshness.newest_completed_at ? ` (${freshness.newest_completed_at})` : ''}. Stale after{' '}
                {freshness.stale_after_hours}h.
              </Typography>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                {(freshness.by_template ?? []).slice(0, 6).map((t) => (
                  <Chip
                    key={t.template_slug}
                    size="small"
                    color={t.stale ? 'warning' : 'default'}
                    label={`${t.template_slug}: ${formatAgeHours(t.age_hours)}`}
                    component={NextLink}
                    href={t.import_job_id ? `/admin/imports?jobId=${t.import_job_id}` : '/admin/imports'}
                    clickable
                  />
                ))}
                {(freshness.by_template ?? []).length === 0 ? (
                  <Chip size="small" label="No completed imports for this tenant yet" />
                ) : null}
              </Stack>
            </Alert>
          ) : null}

          <Alert severity="info" sx={{ mb: 2 }}>
            New here? Start with{' '}
            <Link component={NextLink} href="/getting-started" fontWeight={600}>
              Getting started
            </Link>{' '}
            (upload → map → modules), then use <strong>Data & imports</strong> under Admin.
          </Alert>

          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ mb: 2 }} useFlexGap flexWrap="wrap">
            <Chip component={NextLink} href="/commercial-planner/cpor-cases" label="CPOR Cases" clickable />
            <Chip component={NextLink} href="/sell-out" label="Channel Operations" clickable />
            <Chip component={NextLink} href="/shipping" label="Inbound shipments" clickable />
            <Chip component={NextLink} href="/admin/imports" label="Import Center" clickable />
            <Chip component={NextLink} href="/admin/ops" label="Ops / monitoring" clickable />
            <Chip component={NextLink} href="/getting-started" label="Getting started" clickable />
            <Chip component={NextLink} href="/admin/steward-audit" label="Steward audit" clickable />
          </Stack>

          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
            <Box sx={{ flex: 1 }}>
              <KpiCard
                label="Open exceptions"
                value={data?.kpis.open_exceptions ?? '—'}
                hint="Central action queue"
                onExplain={() =>
                  openDrawer(
                    'Exceptions',
                    'Exceptions aggregate stock, pricing, mapping, and budget gaps with explicit triggers.'
                  )
                }
              />
            </Box>
            <Box sx={{ flex: 1 }}>
              <KpiCard
                label="Budget requests in flight"
                value={data?.kpis.open_budget_requests ?? '—'}
                hint="Draft / submitted / in review"
              />
            </Box>
            <Box sx={{ flex: 1 }}>
              <KpiCard
                label="Inbound shipments tracked"
                value={data?.kpis.inbound_shipments_tracked ?? '—'}
                hint="Not yet received"
              />
            </Box>
            {isCommercialPlannerEnabled() && data?.kpis.commercial_planner ? (
              <Box sx={{ flex: 1 }}>
                <KpiCard
                  label="Commercial plans not ready"
                  value={data.kpis.commercial_planner.plans_not_ready}
                  hint={`${data.kpis.commercial_planner.plan_count} plan(s) scanned — open Commercial planner`}
                />
              </Box>
            ) : null}
          </Stack>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            <Paper sx={{ p: 2, flex: 1 }}>
              <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                Stock health snapshot
              </Typography>
              <Typography variant="body2" color="text.secondary" component="pre" sx={{ whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(data?.stock_health ?? {}, null, 2)}
              </Typography>
            </Paper>
            <Paper sx={{ p: 2, flex: 1 }}>
              <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                Needs attention
              </Typography>
              {data?.recommended_actions.map((a) => (
                <Box key={a.title} sx={{ mb: 1.5 }}>
                  <Typography
                    variant="body2"
                    fontWeight={600}
                    component={NextLink}
                    href={a.href}
                    sx={{ color: 'primary.main', textDecoration: 'none' }}
                  >
                    {a.title}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block">
                    {a.reason}
                  </Typography>
                </Box>
              ))}
            </Paper>
          </Stack>
        </>
      )}
    </>
  );
}
