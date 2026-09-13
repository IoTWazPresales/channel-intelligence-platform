'use client';

import { Box, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';

import { CapabilityStatus } from '@/features/shell/CapabilityStatus';
import { inRail, leafStatusLabel, navGroups } from '@/features/shell/navConfig';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';
import { PairedBars, ProportionBar } from '@/features/workbench-ui/charts';
import { apiGet } from '@/lib/api';

import { fmtInt, fmtPct } from './format';
import { planningWorkflowHref } from './planningPaths';
import type { PlanningOverview as PlanningOverviewPayload } from './types';
import { useClientReady } from './useClientReady';

export function PlanningOverview() {
  const router = useRouter();
  const ready = useClientReady();
  const { data: summary, isLoading, isError } = useQuery({
    queryKey: ['planning', 'overview'],
    queryFn: ({ signal }) => apiGet<PlanningOverviewPayload>('/api/v1/planning/overview', { signal }),
    staleTime: 30_000,
  });
  const data = ready ? summary : undefined;
  const awaiting = !ready || isLoading;
  const unavailable = !awaiting && Boolean(isError || !data || data.data_unavailable);
  const figures = Boolean(data && !awaiting && !unavailable);
  const planning = navGroups.find((g) => g.id === 'planning');
  const workflows = (planning?.items ?? []).filter(inRail);
  const notInRail = (planning?.items ?? []).filter((l) => !inRail(l));
  const missing = data?.readiness_missing ?? 0;
  const flagged = data?.economics_flagged ?? 0;
  const attentionCount = (missing > 0 ? 1 : 0) + (flagged > 0 ? 1 : 0);
  const rd = data?.readiness;
  const readinessRows: { label: string; ratio: number | null }[] = [
    { label: 'SKU assumptions present', ratio: rd?.sku_assumptions_ratio ?? null },
    { label: 'Customer terms resolved', ratio: rd?.customer_terms_ratio ?? null },
    { label: 'Distributor attribution', ratio: rd?.distributor_attribution_ratio ?? null },
    { label: 'Cost basis (controlled cost)', ratio: rd?.cost_basis_ratio ?? null },
  ];

  return (
    <Box data-testid="domain-planning">
      {awaiting ? (
        <Typography color="text.secondary" sx={{ px: 1, py: 1 }} data-testid="planning-overview-loading">
          Loading Planning…
        </Typography>
      ) : unavailable ? (
        <Typography color="text.secondary" sx={{ px: 1, py: 1 }} data-testid="planning-overview-empty">
          Planning headlines are not available yet — lineup cases are required.
        </Typography>
      ) : (
        <HeadlineStrip columns={5}>
          <HeadlineFigure
            label={data?.labels.cases ?? 'Lineup cases'}
            value={data ? fmtInt(data.cases) : '—'}
            compact
            caption={data?.captions.cases}
            onClick={() => router.push('/commercial-planner')}
          />
          <HeadlineFigure
            label={data?.labels.plan_units ?? 'Plan units'}
            value={data ? fmtInt(data.plan_units) : '—'}
            compact
            caption={data?.captions.plan_units}
            onClick={() => router.push('/commercial-planner')}
          />
          <HeadlineFigure
            label={data?.labels.shipped_vs_plan ?? 'Shipped vs plan'}
            value={data ? fmtPct(data.fill_rate_pct) : '—'}
            compact
            caption={data?.captions.shipped_vs_plan}
            onClick={() => router.push('/stock?lens=execution')}
          />
          <HeadlineFigure
            label={data?.labels.readiness_missing ?? 'Lines not ready'}
            value={data ? fmtInt(data.readiness_missing) : '—'}
            compact
            severity="warn"
            caption={data?.captions.readiness_missing}
            onClick={() => router.push('/commercial-planner')}
          />
          <HeadlineFigure
            label={data?.labels.economics_flagged ?? 'Economics flagged'}
            value={data ? fmtInt(data.economics_flagged) : '—'}
            compact
            severity="warn"
            caption={data?.captions.economics_flagged}
            onClick={() => router.push('/commercial-planner')}
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
            <>
              <Panel
                title="Shipped vs plan by customer"
                subtitle={
                  data?.execution_unavailable
                    ? 'Execution vs plan grain unavailable'
                    : `Strategic customers first · ${data?.execution_period ?? 'current execution period'} · same grain as Execution vs plan`
                }
              >
                {data?.by_customer?.length ? (
                  <PairedBars
                    data={data.by_customer as Record<string, unknown>[]}
                    x="customer"
                    a="plan"
                    b="shipped"
                    aLabel="Plan"
                    bLabel="Shipped"
                    height={260}
                    compact
                  />
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    No execution rows for the default lineup-linked period.
                  </Typography>
                )}
              </Panel>
              <Panel
                title="Readiness"
                subtitle="Before a case can be committed: SKU assumptions, customer terms, distributor attribution, cost basis"
              >
                <Stack spacing={1.25}>
                  {readinessRows.map((row) => (
                    <Box key={row.label}>
                      <Typography variant="caption" color="text.secondary">
                        {row.label}
                      </Typography>
                      <ProportionBar
                        value={row.ratio ?? 0}
                        tone={
                          row.ratio == null
                            ? 'warning'
                            : row.ratio > 0.95
                              ? 'success'
                              : row.ratio > 0.85
                                ? 'primary'
                                : 'warning'
                        }
                      />
                    </Box>
                  ))}
                </Stack>
              </Panel>
            </>
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
                {missing ? (
                  <PanelRow
                    severity="warning"
                    primary={`${fmtInt(missing)} Lineup lines missing SKU assumptions, terms or cost basis`}
                    secondary={data?.captions.readiness_missing}
                    href="/commercial-planner"
                  />
                ) : null}
                {flagged ? (
                  <PanelRow
                    severity="warning"
                    primary={`${fmtInt(flagged)} Planner lines with economics flags`}
                    secondary={data?.captions.economics_flagged}
                    href="/commercial-planner"
                  />
                ) : null}
                {!missing && !flagged ? (
                  <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }}>
                    No signals for Planning right now.
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
                  href={planningWorkflowHref(l.href)}
                />
              ))}
              {notInRail.length ? (
                <Typography variant="caption" color="text.disabled" sx={{ px: 1.5, pt: 1 }}>
                  Not in navigation yet:{' '}
                  {notInRail
                    .map((l) => `${l.label} (${leafStatusLabel[l.status ?? 'live'].toLowerCase()})`)
                    .join(', ')}{' '}
                  — listed in the capability directory.
                </Typography>
              ) : null}
            </Stack>
          </Panel>
        </Stack>
      </Box>
    </Box>
  );
}
