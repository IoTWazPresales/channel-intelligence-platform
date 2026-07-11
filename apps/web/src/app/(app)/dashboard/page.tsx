'use client';

import { Alert, Box, Link, Paper, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import NextLink from 'next/link';

import { KpiCard } from '@/components/KpiCard';
import { PageHeader } from '@/components/PageHeader';
import { apiGet } from '@/lib/api';
import { isCommercialPlannerEnabled } from '@/features/shell/navConfig';
import { useUiStore } from '@/stores/uiStore';

type Summary = {
  kpis: {
    open_exceptions: number;
    open_budget_requests: number;
    inbound_shipments_tracked: number;
    commercial_planner?: {
      plan_count: number;
      plans_not_ready: number;
      plans_with_lines: number;
    } | null;
  };
  stock_health: Record<string, number>;
  recommended_actions: { title: string; href: string; reason: string }[];
};

export default function DashboardPage() {
  const openDrawer = useUiStore((s) => s.openDrawer);
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-summary'],
    queryFn: ({ signal }) => apiGet<Summary>('/api/v1/dashboard/summary', { signal }),
  });

  return (
    <>
      <PageHeader crumbs={[{ label: 'Overview' }]} title="Control tower" />
      {isLoading ? (
        <Typography color="text.secondary">Loading…</Typography>
      ) : (
        <>
          <Alert severity="info" sx={{ mb: 2 }}>
            New here? Start with{' '}
            <Link component={NextLink} href="/getting-started" fontWeight={600}>
              Getting started
            </Link>{' '}
            (upload → map → modules), then use <strong>Data & imports</strong> under Admin.
          </Alert>
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
              {data?.stock_health && Object.keys(data.stock_health).length > 0 ? (
                <Stack spacing={0.75}>
                  {Object.entries(data.stock_health)
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([state, count]) => (
                      <Stack key={state} direction="row" justifyContent="space-between" spacing={2}>
                        <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>
                          {state.replace(/_/g, ' ')}
                        </Typography>
                        <Typography variant="body2" fontWeight={600}>
                          {count.toLocaleString()}
                        </Typography>
                      </Stack>
                    ))}
                </Stack>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  No stock-health rows derived yet. Live inventory and weeks-of-cover live on{' '}
                  <Link component={NextLink} href="/sell-out" fontWeight={600}>
                    Channel Operations
                  </Link>
                  .
                </Typography>
              )}
            </Paper>
            <Paper sx={{ p: 2, flex: 1 }}>
              <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                Recommended actions
              </Typography>
              {data?.recommended_actions.map((a) => (
                <Box key={a.title} sx={{ mb: 1.5 }}>
                  <Typography variant="body2" fontWeight={600}>
                    {a.title}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
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
