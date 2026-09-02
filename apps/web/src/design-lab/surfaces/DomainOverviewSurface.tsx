'use client';

import { Box, Button, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import NextLink from 'next/link';
import { useRouter } from 'next/navigation';
import type { ReactNode } from 'react';

import { fmtInt, tenant } from '../fixtures/entities';
import { lineupSummary, planVsShipped, poCoverage, shipmentLifecycle, signals } from '../fixtures/operations';
import { CapabilityStatus } from '../primitives/CapabilityStatus';
import { CategoryBars, PairedBars, ProportionBar, TrendChart } from '../primitives/charts';
import { DomainHeader } from '../primitives/DomainHeader';
import { HeadlineFigure, HeadlineStrip } from '../primitives/HeadlineFigure';
import { Panel, PanelRow } from '../primitives/Panel';
import { inRail, labDomains, leafStatusLabel, type LabDomain } from '../shell/labNav';

/**
 * Domain overview pattern (CONSULT gate: a domain must compose headline figures + its attention
 * items + workflow links, never a folder of routes). Planning / Supply / Admin use it.
 */
function DomainOverview({ domain, headline, analysis, extra }: { domain: LabDomain; headline: ReactNode; analysis: ReactNode; extra?: ReactNode }) {
  const router = useRouter();
  const mine = signals.filter((s) => s.area === domain.label);
  return (
    <Box data-testid={`domain-${domain.id}`}>
      <DomainHeader crumbs={[{ label: domain.label }]} title={domain.label} description={domain.what} meta={tenant.period} />
      {headline}
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'minmax(0, 3fr) minmax(280px, 2fr)' }, mt: 2, alignItems: 'start' }}>
        <Stack spacing={2}>{analysis}</Stack>
        <Stack spacing={2}>
          <Panel title="Needs attention in this area" subtitle={mine.length ? `${mine.length} live signals` : 'Nothing outstanding'} flush>
            <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
              {mine.length ? (
                mine.map((s) => <PanelRow key={s.id} severity={s.severity} primary={`${fmtInt(s.count)} ${s.headline}`} secondary={s.detail} onClick={() => router.push(s.href)} />)
              ) : (
                <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }}>
                  No signals for {domain.label} right now.
                </Typography>
              )}
            </Stack>
          </Panel>
          <Panel title="Workflows" subtitle="What you can do here" flush>
            <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
              {domain.leaves.filter(inRail).map((l) => (
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
                  onClick={() => router.push(l.href)}
                />
              ))}
              {domain.leaves.some((l) => !inRail(l)) ? (
                <Typography variant="caption" color="text.disabled" sx={{ px: 1.5, pt: 1 }}>
                  Not in navigation yet: {domain.leaves.filter((l) => !inRail(l)).map((l) => `${l.label} (${leafStatusLabel[l.status ?? 'live'].toLowerCase()})`).join(', ')} — listed in the capability directory.
                </Typography>
              ) : null}
            </Stack>
          </Panel>
          {extra}
        </Stack>
      </Box>
    </Box>
  );
}

const byId = (id: string) => labDomains.find((d) => d.id === id)!;

export function PlanningSurface() {
  const total = planVsShipped.reduce((a, r) => ({ plan: a.plan + r.plan, shipped: a.shipped + r.shipped }), { plan: 0, shipped: 0 });
  return (
    <DomainOverview
      domain={byId('planning')}
      headline={
        <HeadlineStrip columns={5}>
          <HeadlineFigure label="Lineup cases P09–P10" value={lineupSummary.cases} compact caption={`${fmtInt(lineupSummary.lines)} plan lines`} />
          <HeadlineFigure label="Plan units" value={fmtInt(lineupSummary.planUnits)} compact />
          <HeadlineFigure label="Shipped vs plan" value={`${Math.round((total.shipped / total.plan) * 100)}%`} compact caption={`${fmtInt(total.shipped)} of ${fmtInt(total.plan)}`} />
          <HeadlineFigure label="Lines not ready" value={lineupSummary.readinessMissing} compact severity="warn" caption="Missing assumptions / terms" />
          <HeadlineFigure label="Economics flagged" value={lineupSummary.economicsFlagged} compact severity="warn" caption={`${lineupSummary.economicsOk} ok · flags explain why`} />
        </HeadlineStrip>
      }
      analysis={
        <>
          <Panel title="Shipped vs plan by customer, P09" subtitle="Strategic customers first · click a customer to open its lineup case">
            <PairedBars data={planVsShipped} x="customer" a="plan" b="shipped" aLabel="Plan" bLabel="Shipped" height={260} compact />
          </Panel>
          <Panel title="Readiness" subtitle="Before a case can be committed: SKU assumptions, customer terms, distributor attribution, cost basis">
            <Stack spacing={1.25}>
              {[
                ['SKU assumptions present', lineupSummary.readinessOk / lineupSummary.lines],
                ['Customer terms resolved', 0.97],
                ['Distributor attribution', 0.91],
                ['Cost basis (controlled cost)', 0.83],
              ].map(([label, v]) => (
                <Box key={String(label)}>
                  <Typography variant="caption" color="text.secondary">
                    {String(label)}
                  </Typography>
                  <ProportionBar value={Number(v)} tone={Number(v) > 0.95 ? 'success' : Number(v) > 0.85 ? 'primary' : 'warning'} />
                </Box>
              ))}
            </Stack>
          </Panel>
        </>
      }
    />
  );
}

export function SupplySurface() {
  const theme = useTheme();
  return (
    <DomainOverview
      domain={byId('supply')}
      headline={
        <HeadlineStrip columns={5}>
          <HeadlineFigure label="Open shipments" value={fmtInt(388 + 296)} compact caption="Shipped or arrived, not yet received" />
          <HeadlineFigure label="Unreceived past ETA" value={fmtInt(1714)} compact severity="bad" caption="Oldest 41 days" />
          <HeadlineFigure label="Received this week" value={fmtInt(312)} compact severity="good" caption="ASN 2026-09-01 applied" />
          <HeadlineFigure label="PO coverage" value="79%" compact caption="Plan units covered by POs" />
          <HeadlineFigure label="Backlog units" value={fmtInt(poCoverage.reduce((a, r) => a + r.backlogUnits, 0))} compact severity="warn" />
        </HeadlineStrip>
      }
      analysis={
        <>
          <Panel title="Shipment lifecycle" subtitle="Counts by state · unreceived past ETA is the exception queue">
            <CategoryBars data={shipmentLifecycle} x="state" y="count" height={230} horizontal colorBy={(r) => (String(r.state).startsWith('Unreceived') ? theme.palette.error.main : theme.palette.primary.main)} />
          </Panel>
          <Panel title="PO coverage by distributor" subtitle="Share of P09 plan units covered by purchase orders; backlog in units">
            <Stack spacing={1.25}>
              {poCoverage.map((r) => (
                <Box key={r.distributor}>
                  <Stack direction="row" justifyContent="space-between">
                    <Typography variant="caption" color="text.secondary">
                      {r.distributor}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      backlog {fmtInt(r.backlogUnits)}
                    </Typography>
                  </Stack>
                  <ProportionBar value={r.covered} tone={r.covered > 0.85 ? 'success' : r.covered > 0.75 ? 'primary' : 'warning'} />
                </Box>
              ))}
            </Stack>
          </Panel>
        </>
      }
    />
  );
}

export function AdminSurface() {
  return (
    <DomainOverview
      domain={byId('admin')}
      headline={
        <HeadlineStrip columns={4}>
          <HeadlineFigure label="Users" value={14} compact caption="3 admin · 4 steward · 5 planner · 2 viewer" />
          <HeadlineFigure label="Background jobs running" value={2} compact caption="Celery · DSI apply, report schedule" />
          <HeadlineFigure label="Failed jobs (24h)" value={1} compact severity="warn" caption="Retry from Operations" />
          <HeadlineFigure label="Audited SQL queries (7d)" value={38} compact />
        </HeadlineStrip>
      }
      analysis={
        <Panel title="Operations" subtitle="Background tasks register with the activity feed; nothing runs silently" flush>
          <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
            <PanelRow severity="info" primary="DSI apply · job 1276" secondary="running · 62% · 2 981 / 4 812 rows" figure="62%" />
            <PanelRow severity="info" primary="Scheduled report · Weekly cover by distributor" secondary="queued for Mon 07:00" />
            <PanelRow severity="danger" primary="DSI validate · job 1275" secondary="failed 08:52 · parse error row 1 · retry available" figure="retry" />
          </Stack>
        </Panel>
      }
    />
  );
}