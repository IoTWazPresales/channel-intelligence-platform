'use client';

import { Box, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';

import { CapabilityStatus } from '@/features/shell/CapabilityStatus';
import { inRail, navGroups } from '@/features/shell/navConfig';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';
import { CategoryBars, ProportionBar } from '@/features/workbench-ui/charts';
import { apiGet } from '@/lib/api';

import { fmtInt, fmtPctRatio } from './format';
import type { SupplyOverview as SupplyOverviewPayload } from './types';
import { useClientReady } from './useClientReady';

export function SupplyOverview() {
  const router = useRouter();
  const ready = useClientReady();
  const { data: summary } = useQuery({
    queryKey: ['supply', 'overview'],
    queryFn: ({ signal }) => apiGet<SupplyOverviewPayload>('/api/v1/supply/overview', { signal }),
    staleTime: 30_000,
  });
  const data = ready ? summary : undefined;
  const supply = navGroups.find((g) => g.id === 'supply');
  const workflows = (supply?.items ?? []).filter(inRail);
  const etaPast = data?.eta_past_no_pod_lines ?? 0;

  return (
    <Box data-testid="domain-supply">
      <HeadlineStrip columns={5}>
        <HeadlineFigure
          label={data?.labels.open_lines ?? 'Open shipments'}
          value={data ? fmtInt(data.open_lines) : '—'}
          compact
          caption={data?.captions.open_lines}
          onClick={() => router.push('/supply/shipments')}
        />
        <HeadlineFigure
          label={data?.labels.eta_past_no_pod_lines ?? 'Unreceived past ETA'}
          value={data ? fmtInt(data.eta_past_no_pod_lines) : '—'}
          compact
          severity="bad"
          caption={data?.captions.eta_past_no_pod_lines}
          onClick={() => router.push('/admin/shipment-evidence')}
        />
        <HeadlineFigure
          label={data?.labels.landed_pod_iso_week ?? 'Received this week'}
          value={data ? fmtInt(data.landed_pod_iso_week) : '—'}
          compact
          severity="good"
          caption={data?.captions.landed_pod_iso_week}
        />
        <HeadlineFigure
          label={data?.labels.po_coverage ?? 'PO coverage'}
          value={data ? fmtPctRatio(data.po_coverage_ratio) : '—'}
          compact
          caption={data?.captions.po_coverage}
          onClick={() => router.push('/admin/po-management')}
        />
        <HeadlineFigure
          label={data?.labels.pipeline_units ?? 'Backlog units'}
          value={data ? fmtInt(data.pipeline_units) : '—'}
          compact
          severity="warn"
          caption={data?.captions.pipeline_units}
        />
      </HeadlineStrip>
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
          <Panel
            title="Shipment lifecycle"
            subtitle="Disjoint buckets from line_state + POD. Unreceived past ETA overlaps pipeline and shipped — not a fifth bar. Arrived is not a stored state."
          >
            <CategoryBars
              data={(data?.lifecycle ?? []) as Record<string, unknown>[]}
              x="state"
              y="count"
              height={230}
              horizontal
            />
          </Panel>
          <Panel
            title="PO coverage by distributor"
            subtitle="Share of observed POs linked to an active lineup case — not P09 plan units. Plan-unit coverage is uncovered."
          >
            <Stack spacing={1.25}>
              {(data?.po_by_distributor ?? []).map((r) => (
                <Box key={r.distributor}>
                  <Stack direction="row" justifyContent="space-between">
                    <Typography variant="caption" color="text.secondary">
                      {r.distributor}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {fmtInt(r.linked_pos)} linked / {fmtInt(r.observed_pos)} observed
                    </Typography>
                  </Stack>
                  <ProportionBar
                    value={r.covered}
                    tone={r.covered > 0.85 ? 'success' : r.covered > 0.75 ? 'primary' : 'warning'}
                  />
                </Box>
              ))}
              {!data?.po_by_distributor?.length ? (
                <Typography variant="body2" color="text.secondary">
                  No observed purchase orders to group.
                </Typography>
              ) : null}
            </Stack>
          </Panel>
        </Stack>
        <Stack spacing={2}>
          <Panel
            title="Needs attention in this area"
            subtitle={etaPast ? '1 live signal' : 'Nothing outstanding'}
            flush
          >
            <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
              {etaPast ? (
                <PanelRow
                  severity="warning"
                  primary={`${fmtInt(etaPast)} Inbound shipments unreceived past ETA`}
                  secondary={
                    data?.oldest_days_past_eta != null
                      ? `Oldest ${fmtInt(data.oldest_days_past_eta)} days${
                          data.oldest_eta_past ? ` (${data.oldest_eta_past})` : ''
                        }`
                      : data?.captions.eta_past_no_pod_lines
                  }
                  href="/admin/shipment-evidence"
                />
              ) : (
                <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }}>
                  No signals for Supply & Inbound right now.
                </Typography>
              )}
            </Stack>
          </Panel>
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
                  href={l.href}
                />
              ))}
            </Stack>
          </Panel>
        </Stack>
      </Box>
    </Box>
  );
}
