'use client';

import { Alert, Box, Chip, Link, Paper, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import NextLink from 'next/link';

import { KpiCard } from '@/components/KpiCard';
import { PageHeader } from '@/components/PageHeader';
import { apiGet } from '@/lib/api';
import { useUiStore } from '@/stores/uiStore';

type Summary = {
  kpis: { open_exceptions: number; open_budget_requests: number; inbound_shipments_tracked: number };
  stock_health: Record<string, number>;
  recommended_actions: { title: string; href: string; reason: string }[];
};

type Overview = {
  kpis: {
    inbound_shipments: number;
    sellout_lines: number;
    active_distributors: number;
    active_customers: number;
  };
  data_coverage: Record<string, { loaded: boolean; row_count: number }>;
};

const MODULE_LABELS: Record<string, string> = {
  product_master: 'Product Master',
  inbound_shipments: 'Inbound Shipments',
  distributor_sellout: 'Distributor Sell-out',
  customer_sales: 'Customer Sales',
};

export default function DashboardPage() {
  const openDrawer = useUiStore((s) => s.openDrawer);
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-summary'],
    queryFn: ({ signal }) => apiGet<Summary>('/api/v1/dashboard/summary', { signal }),
  });
  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ['dashboard-overview'],
    queryFn: ({ signal }) => apiGet<Overview>('/api/v1/dashboard/overview', { signal }),
  });

  const loading = isLoading || overviewLoading;

  return (
    <>
      <PageHeader crumbs={[{ label: 'Overview' }]} title="Control tower" />
      {loading ? (
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
                label="Inbound shipments"
                value={overview?.kpis.inbound_shipments ?? '—'}
                hint="Total tracked shipments"
              />
            </Box>
            <Box sx={{ flex: 1 }}>
              <KpiCard
                label="Sell-out lines"
                value={overview?.kpis.sellout_lines ?? '—'}
                hint="Distributor sell-out records"
              />
            </Box>
            <Box sx={{ flex: 1 }}>
              <KpiCard
                label="Active distributors"
                value={overview?.kpis.active_distributors ?? '—'}
                hint="Distributors with activity"
              />
            </Box>
            <Box sx={{ flex: 1 }}>
              <KpiCard
                label="Active customers"
                value={overview?.kpis.active_customers ?? '—'}
                hint="Customers with activity"
              />
            </Box>
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
          </Stack>

          {overview?.data_coverage ? (
            <Paper sx={{ p: 2, mb: 2 }}>
              <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                Data coverage
              </Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} flexWrap="wrap" useFlexGap>
                {Object.entries(overview.data_coverage).map(([key, mod]) => (
                  <Paper key={key} variant="outlined" sx={{ p: 1.5, minWidth: 180 }}>
                    <Typography variant="body2" fontWeight={600}>
                      {MODULE_LABELS[key] ?? key}
                    </Typography>
                    <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
                      <Chip
                        size="small"
                        label={mod.loaded ? 'Loaded' : 'Empty'}
                        color={mod.loaded ? 'success' : 'default'}
                      />
                      <Typography variant="caption" color="text.secondary">
                        {mod.row_count.toLocaleString()} rows
                      </Typography>
                    </Stack>
                  </Paper>
                ))}
              </Stack>
            </Paper>
          ) : null}

          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
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

          <Paper
            variant="outlined"
            sx={{
              p: 3,
              textAlign: 'center',
              border: '2px dashed',
              borderColor: 'divider',
            }}
          >
            <Typography variant="body1" color="text.secondary">
              Analytics coming soon — load historical sell-out data to unlock trends and forecasting
            </Typography>
          </Paper>
        </>
      )}
    </>
  );
}
