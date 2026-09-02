'use client';

import {
  Box,
  Button,
  Chip,
  Divider,
  List,
  ListItemButton,
  ListItemText,
  ListSubheader,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import PushPinOutlinedIcon from '@mui/icons-material/PushPinOutlined';
import ScheduleOutlinedIcon from '@mui/icons-material/ScheduleOutlined';
import { useMemo, useState } from 'react';

import { governedMetrics, savedReports, type GovernedMetric } from '../fixtures/dashboard';
import { fmtCurrency, fmtInt, distributors } from '../fixtures/entities';
import { ageingBuckets, fundingCases } from '../fixtures/funding';
import { planVsShipped, shipmentLifecycle } from '../fixtures/operations';
import { coverRows, sellOutByFamily, weeklySeries } from '../fixtures/stock';
import { CategoryBars, PairedBars, TrendChart } from '../primitives/charts';
import { DomainHeader } from '../primitives/DomainHeader';
import { HeadlineFigure, HeadlineStrip } from '../primitives/HeadlineFigure';
import { Panel, PanelRow } from '../primitives/Panel';
import { StatusChip } from '../primitives/controls';

/**
 * Reports = *ask*: a governed question (metric · grain · dimensions) that runs, saves, exports and
 * schedules. It is a sibling of Dashboards (= *keep showing me*): any saved report can be pinned as a
 * widget, but Dashboards is never a saved-report destination. The metric catalogue is the semantic
 * layer's; a metric the layer cannot compute cannot be asked for.
 */

type Row = Record<string, string | number>;

const grainLabel: Record<string, string> = {
  distributor: 'Distributor',
  product: 'Product',
  family: 'Product family',
  week: 'Week',
  customer: 'Customer',
  period: 'Period',
  age_bucket: 'Age bucket',
  state: 'Lifecycle state',
  programme: 'Programme',
};

/** Fixture result sets — every combination maps to a metric × grain the capability audit found derivable. */
function runQuery(metric: GovernedMetric, grain: string): { rows: Row[]; x: string; y: string; format: (v: number) => string; visual: 'bar' | 'line' | 'paired' } {
  const units = (v: number) => fmtInt(v);
  switch (metric.key) {
    case 'channel_ops.weeks_of_cover': {
      const byDist = distributors.map((d) => {
        const rows = coverRows.filter((r) => r.distributor === d.name);
        const soh = rows.reduce((a, r) => a + r.soh, 0);
        const rate = rows.reduce((a, r) => a + r.weeklyRate, 0);
        return { label: d.name, value: Math.round((soh / rate) * 10) / 10 };
      });
      return { rows: byDist, x: 'label', y: 'value', format: (v) => `${v.toFixed(1)}w`, visual: 'bar' };
    }
    case 'channel_ops.network_soh': {
      const byDist = distributors.map((d) => ({ label: d.name, value: coverRows.filter((r) => r.distributor === d.name).reduce((a, r) => a + r.soh, 0) }));
      return { rows: byDist, x: 'label', y: 'value', format: units, visual: 'bar' };
    }
    case 'channel_ops.cover_breaches':
      return {
        rows: distributors.map((d) => ({ label: d.name, value: coverRows.filter((r) => r.distributor === d.name && r.status === 'breach').length })),
        x: 'label',
        y: 'value',
        format: units,
        visual: 'bar',
      };
    case 'channel_ops.sell_out_units':
      if (grain === 'family') return { rows: sellOutByFamily.map((f) => ({ label: f.family, value: f.units })), x: 'label', y: 'value', format: units, visual: 'bar' };
      return { rows: weeklySeries.map((w) => ({ label: w.week, value: w.sellOut })), x: 'label', y: 'value', format: units, visual: 'line' };
    case 'pve.shipped_vs_plan':
    case 'pve.plan_units':
      return { rows: planVsShipped.map((p) => ({ label: p.customer, plan: p.plan, shipped: p.shipped })), x: 'label', y: 'plan', format: units, visual: 'paired' };
    case 'shipping.lifecycle_counts':
      return { rows: shipmentLifecycle.map((s) => ({ label: s.state, value: s.count })), x: 'label', y: 'value', format: units, visual: 'bar' };
    case 'cpor.outstanding':
      if (grain === 'age_bucket') return { rows: ageingBuckets.map((b) => ({ label: b.bucket, value: b.value })), x: 'label', y: 'value', format: (v) => fmtCurrency(v, { compact: true }), visual: 'bar' };
      return {
        rows: Object.entries(
          fundingCases.reduce<Record<string, number>>((acc, c) => {
            acc[c.customer] = (acc[c.customer] ?? 0) + c.outstanding;
            return acc;
          }, {}),
        ).map(([label, value]) => ({ label, value })),
        x: 'label',
        y: 'value',
        format: (v) => fmtCurrency(v, { compact: true }),
        visual: 'bar',
      };
    default:
      return { rows: distributors.map((d, i) => ({ label: d.name, value: 1_000 + i * 640 })), x: 'label', y: 'value', format: units, visual: 'bar' };
  }
}

export function ReportsSurface() {
  const runnable = governedMetrics.filter((m) => m.status === 'implemented');
  const families = Array.from(new Set(runnable.map((m) => m.family)));
  const [metricKey, setMetricKey] = useState('channel_ops.weeks_of_cover');
  const metric = runnable.find((m) => m.key === metricKey) ?? runnable[0];
  const [grain, setGrain] = useState(metric.grains[0]);
  const effectiveGrain = metric.grains.includes(grain) ? grain : metric.grains[0];
  const [pinned, setPinned] = useState<string | null>(null);
  const result = useMemo(() => runQuery(metric, effectiveGrain), [metric, effectiveGrain]);
  const total = result.rows.reduce((a, r) => a + Number(r[result.y]), 0);

  return (
    <Box data-testid="reports-surface">
      <DomainHeader
        crumbs={[{ label: 'Overview', href: '/design-lab' }, { label: 'Reports' }]}
        title="Reports"
        description="Ask a governed question: pick a metric the semantic layer can compute, a valid grain and dimensions; run it, save it, export or schedule it. Pin any saved report to a dashboard as a widget."
        meta={`${runnable.length} runnable metrics · ${governedMetrics.filter((m) => m.status === 'spec_only').length} spec-only (not runnable) · ${savedReports.length} saved reports`}
        actions={
          <>
            <Button size="small" variant="outlined" startIcon={<ScheduleOutlinedIcon />}>
              Schedules
            </Button>
            <Button size="small" variant="contained">
              New report
            </Button>
          </>
        }
      />
      <HeadlineStrip columns={4}>
        <HeadlineFigure label="Saved reports" value={savedReports.length} compact caption="3 pinned to dashboards" />
        <HeadlineFigure label="Scheduled" value={2} compact caption="Mon 07:00 · Fri 16:00" />
        <HeadlineFigure label="Runs this week" value={41} compact caption="12 exports · 0 failures" severity="good" />
        <HeadlineFigure label="Runnable metrics" value={runnable.length} compact caption="Semantic layer · implemented only" />
      </HeadlineStrip>

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: '236px minmax(0, 1fr)', lg: '236px minmax(0, 1fr) 264px' }, mt: 2, alignItems: 'start' }}>
        <Panel title="Metric" subtitle="Grouped by family; only implemented metrics can run" flush>
          <List dense disablePadding sx={{ maxHeight: 520, overflowY: 'auto' }}>
            {families.map((f) => (
              <Box key={f}>
                <ListSubheader disableSticky sx={{ lineHeight: '28px', bgcolor: 'transparent' }}>
                  {f}
                </ListSubheader>
                {runnable
                  .filter((m) => m.family === f)
                  .map((m) => (
                    <ListItemButton
                      key={m.key}
                      selected={m.key === metric.key}
                      onClick={() => {
                        setMetricKey(m.key);
                        setGrain(m.grains[0]);
                      }}
                      sx={{ py: 0.5 }}
                    >
                      <ListItemText primary={m.label} secondary={m.grains.map((g) => grainLabel[g] ?? g).join(' · ')} primaryTypographyProps={{ variant: 'body2' }} secondaryTypographyProps={{ variant: 'caption', noWrap: true }} />
                    </ListItemButton>
                  ))}
              </Box>
            ))}
            <ListSubheader disableSticky sx={{ lineHeight: '28px', bgcolor: 'transparent' }}>
              Not runnable
            </ListSubheader>
            {governedMetrics
              .filter((m) => m.status !== 'implemented')
              .map((m) => (
                <ListItemButton key={m.key} disabled sx={{ py: 0.5 }}>
                  <ListItemText primary={m.label} secondary={m.status === 'spec_only' ? 'Spec only — not yet computable' : 'Do not build'} primaryTypographyProps={{ variant: 'body2' }} secondaryTypographyProps={{ variant: 'caption' }} />
                </ListItemButton>
              ))}
          </List>
        </Panel>

        <Stack spacing={2}>
          <Panel
            title={metric.label}
            subtitle={`by ${grainLabel[effectiveGrain] ?? effectiveGrain} · FY26 P09 · W36 · ${result.rows.length} rows`}
            actions={
              <Stack direction="row" spacing={1} alignItems="center">
                <ToggleButtonGroup size="small" exclusive value={effectiveGrain} onChange={(_, v) => v && setGrain(v)}>
                  {metric.grains.map((g) => (
                    <ToggleButton key={g} value={g} sx={{ px: 1.25, py: 0.25, textTransform: 'none' }}>
                      {grainLabel[g] ?? g}
                    </ToggleButton>
                  ))}
                </ToggleButtonGroup>
                <Button size="small" variant="contained">
                  Run
                </Button>
              </Stack>
            }
          >
            {result.visual === 'paired' ? (
              <PairedBars data={result.rows} x={result.x} a="plan" b="shipped" aLabel="Plan" bLabel="Shipped" height={260} format={result.format} compact />
            ) : result.visual === 'line' ? (
              <TrendChart data={result.rows} x={result.x} height={260} format={result.format} series={[{ key: result.y, label: metric.label, kind: 'line', tone: 'primary' }]} />
            ) : (
              <CategoryBars data={result.rows} x={result.x} y={result.y} height={Math.max(200, 44 * result.rows.length + 40)} format={result.format} horizontal />
            )}
            <Divider sx={{ my: 1.5 }} />
            <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
              <Chip size="small" variant="outlined" label={`Metric · ${metric.key}`} />
              <Chip size="small" variant="outlined" label={`Grain · ${effectiveGrain}`} />
              <Chip size="small" variant="outlined" label="Scope · all distributors" />
              <Box sx={{ flex: 1 }} />
              <Button size="small">Export CSV</Button>
              <Button size="small">Schedule</Button>
              <Button size="small" variant="outlined" startIcon={<PushPinOutlinedIcon />} onClick={() => setPinned(metric.label)}>
                Save &amp; pin to dashboard
              </Button>
            </Stack>
          </Panel>

          <Panel title="Result" subtitle="Governed figures — the same numbers a dashboard widget would show" flush>
            <Table size="small" sx={{ '& td, & th': { py: 0.6 }, '& th': { whiteSpace: 'nowrap' } }}>
              <TableHead>
                <TableRow>
                  <TableCell>{grainLabel[effectiveGrain] ?? effectiveGrain}</TableCell>
                  {result.visual === 'paired' ? (
                    <>
                      <TableCell align="right">Plan</TableCell>
                      <TableCell align="right">Shipped</TableCell>
                      <TableCell align="right">Attainment</TableCell>
                    </>
                  ) : (
                    <>
                      <TableCell align="right">{metric.label}</TableCell>
                      <TableCell align="right">Share</TableCell>
                    </>
                  )}
                </TableRow>
              </TableHead>
              <TableBody>
                {result.rows.map((r) => (
                  <TableRow key={String(r[result.x])} hover>
                    <TableCell>{r[result.x]}</TableCell>
                    {result.visual === 'paired' ? (
                      <>
                        <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>{fmtInt(Number(r.plan))}</TableCell>
                        <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>{fmtInt(Number(r.shipped))}</TableCell>
                        <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>{Math.round((Number(r.shipped) / Number(r.plan)) * 100)}%</TableCell>
                      </>
                    ) : (
                      <>
                        <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>{result.format(Number(r[result.y]))}</TableCell>
                        <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', color: 'text.secondary' }}>
                          {metric.key === 'channel_ops.weeks_of_cover' ? '—' : `${Math.round((Number(r[result.y]) / total) * 100)}%`}
                        </TableCell>
                      </>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Panel>
        </Stack>

        <Stack spacing={2}>
          <Panel title="Saved reports" subtitle="Schedules and last runs" flush>
            <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
              {savedReports.map((r) => (
                <PanelRow key={r.name} severity="neutral" primary={r.name} secondary={`${r.metric} · ${r.schedule}`} figure={<StatusChip label="pinned" tone="info" />} />
              ))}
              {pinned ? <PanelRow severity="info" primary={pinned} secondary={`${metric.label} · ${grainLabel[effectiveGrain]} · just now`} figure={<StatusChip label="pinned" tone="success" />} /> : null}
            </Stack>
          </Panel>
          <Panel title="Recent runs" flush>
            <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
              <PanelRow severity="neutral" primary="Weekly cover by distributor" secondary="Mon 07:00 · 4 rows · exported" />
              <PanelRow severity="neutral" primary="Funding outstanding > 30d" secondary="Fri 16:00 · 5 rows" />
              <PanelRow severity="neutral" primary="P09 shipped vs plan" secondary="Yesterday 14:12 · 6 rows · exported" />
            </Stack>
          </Panel>
          <Typography variant="caption" color="text.secondary">
            Reports and Dashboards are siblings: a report answers a question once; a dashboard keeps showing it. Pinning copies the governed query, not a snapshot.
          </Typography>
        </Stack>
      </Box>
      <Snackbar open={!!pinned} autoHideDuration={3000} onClose={() => setPinned(null)} message={pinned ? `Saved “${pinned}” and pinned to your dashboard` : ''} />
    </Box>
  );
}
