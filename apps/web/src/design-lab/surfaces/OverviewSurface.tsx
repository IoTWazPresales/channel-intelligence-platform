'use client';

import AddIcon from '@mui/icons-material/Add';
import CloseIcon from '@mui/icons-material/Close';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import PushPinOutlinedIcon from '@mui/icons-material/PushPinOutlined';
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
  useMediaQuery,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import NextLink from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

import { defaultWidgets, governedMetrics, savedReports, type Widget } from '../fixtures/dashboard';
import { fmtCurrency, fmtInt, tenant } from '../fixtures/entities';
import { ageingBuckets, fundingBook } from '../fixtures/funding';
import { planVsShipped, shipmentLifecycle, signals } from '../fixtures/operations';
import { coverDistribution, coverSummary, sellOutByFamily, weeklySeries } from '../fixtures/stock';
import { CategoryBars, PairedBars, TrendChart } from '../primitives/charts';
import { DomainHeader } from '../primitives/DomainHeader';
import { HeadlineFigure } from '../primitives/HeadlineFigure';
import { Panel, PanelRow } from '../primitives/Panel';
import type { Role } from '../shell/labNav';

function useRole(): Role {
  const [role, setRole] = useState<Role>('planner');
  useEffect(() => {
    const saved = window.localStorage.getItem('cip.design-lab.role') as Role | null;
    if (saved) setRole(saved);
    const onStorage = () => {
      const r = window.localStorage.getItem('cip.design-lab.role') as Role | null;
      if (r) setRole(r);
    };
    window.addEventListener('storage', onStorage);
    const t = window.setInterval(onStorage, 500);
    return () => {
      window.removeEventListener('storage', onStorage);
      window.clearInterval(t);
    };
  }, []);
  return role;
}

/** Widget body = one governed metric. Fixture values are the same figures the domain pages show. */
function WidgetBody({ w, onDrill }: { w: Widget; onDrill: (href: string) => void }) {
  const theme = useTheme();
  const last = weeklySeries[weeklySeries.length - 1];
  const prev = weeklySeries[weeklySeries.length - 2];
  const wow = (last.sellOut - prev.sellOut) / prev.sellOut;
  switch (w.id) {
    case 'w1':
    case 's1':
      return <HeadlineFigure label={w.title} value={fmtInt(coverSummary.soh)} unit="units" caption={`${coverSummary.pairs} distributor × product pairs`} onClick={() => onDrill('/design-lab/stock?lens=cover')} />;
    case 'w2':
      return (
        <HeadlineFigure
          label={w.title}
          value={coverSummary.networkCover.toFixed(1)}
          unit="weeks"
          severity={coverSummary.breach ? 'warn' : 'good'}
          caption={`${coverSummary.breach} pairs under 2w · ${coverSummary.excess} over 8w`}
          onClick={() => onDrill('/design-lab/stock?lens=cover&status=breach')}
        />
      );
    case 'w3':
    case 's3':
      return (
        <HeadlineFigure
          label={w.title}
          value={fmtInt(last.sellOut)}
          unit="units"
          delta={{ text: `${(wow * 100).toFixed(1)}% vs ${prev.week}`, direction: wow >= 0 ? 'up' : 'down' }}
          caption={`${last.week} · all distributors`}
          onClick={() => onDrill('/design-lab/stock?lens=movement')}
        />
      );
    case 'w4':
    case 's4':
      return (
        <HeadlineFigure
          label={w.title}
          value={fmtCurrency(fundingBook.outstanding, { compact: true })}
          severity={fundingBook.blocked ? 'warn' : 'neutral'}
          caption={`${fundingBook.cases} cases · ${fundingBook.blocked} blocked (${fmtCurrency(fundingBook.blockedValue, { compact: true })})`}
          onClick={() => onDrill('/design-lab/funding')}
        />
      );
    case 's2':
      return <HeadlineFigure label={w.title} value={fmtInt(1714)} unit="shipments" severity="warn" caption="Oldest 41 days · Highveld receipts missing" onClick={() => onDrill('/design-lab/supply?lens=receipts')} />;
    case 'w5':
    case 's5':
      return (
        <TrendChart
          data={weeklySeries}
          x="week"
          height={w.h === 2 ? 236 : 120}
          series={[
            { key: 'shipped', label: 'Shipped in', kind: 'bar', tone: 'muted' },
            { key: 'sellOut', label: 'Sell-out', kind: 'line', tone: 'primary' },
          ]}
        />
      );
    case 'w6':
      return (
        <CategoryBars
          data={coverDistribution}
          x="bucket"
          y="pairs"
          height={236}
          compact
          colorBy={(r) => (String(r.bucket).startsWith('<') || String(r.bucket) === '1–2w' ? theme.palette.error.main : String(r.bucket) === '8w+' ? theme.palette.warning.main : theme.palette.primary.main)}
        />
      );
    case 'w7':
      return <PairedBars data={planVsShipped} x="customer" a="plan" b="shipped" aLabel="Plan" bLabel="Shipped" height={236} compact />;
    case 'w8':
      return <CategoryBars data={ageingBuckets} x="bucket" y="value" height={236} format={(v) => fmtCurrency(v, { compact: true })} colorBy={(r) => (String(r.bucket) === '60d+' ? theme.palette.error.main : String(r.bucket) === '31–60d' ? theme.palette.warning.main : theme.palette.primary.main)} />;
    case 's6':
      return <CategoryBars data={shipmentLifecycle} x="state" y="count" height={236} horizontal />;
    case 'w9':
      return (
        <Table size="small" sx={{ '& td, & th': { px: 1, py: 0.6, fontSize: 12.5 } }}>
          <TableHead>
            <TableRow>
              <TableCell>Family</TableCell>
              <TableCell align="right">Units</TableCell>
              <TableCell align="right">WoW</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sellOutByFamily.map((r) => (
              <TableRow key={r.family} hover sx={{ cursor: 'pointer' }} onClick={() => onDrill(`/design-lab/stock?lens=movement&family=${r.family}`)}>
                <TableCell>{r.family}</TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                  {fmtInt(r.units)}
                </TableCell>
                <TableCell align="right" sx={{ color: r.wow >= 0 ? 'success.main' : 'error.main', fontVariantNumeric: 'tabular-nums' }}>
                  {r.wow >= 0 ? '+' : ''}
                  {(r.wow * 100).toFixed(0)}%
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      );
    default:
      if (w.visual === 'kpi') return <HeadlineFigure label={w.title} value="—" caption="Query runs when the dashboard is published (fixture)" />;
      if (w.visual === 'bar') return <CategoryBars data={coverDistribution} x="bucket" y="pairs" height={236} />;
      if (w.visual === 'table')
        return (
          <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
            Table widget bound to {w.metricKey}; rows load on publish (fixture).
          </Typography>
        );
      return <TrendChart data={weeklySeries} x="week" height={236} series={[{ key: 'sellOut', label: w.title, kind: w.visual === 'area' ? 'area' : 'line', tone: 'primary' }]} />;
  }
}

function AddWidgetDialog({ open, onClose, onAdd }: { open: boolean; onClose: () => void; onAdd: (m: (typeof governedMetrics)[number]) => void }) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ pb: 1 }}>Add widget — governed metrics</DialogTitle>
      <DialogContent sx={{ pt: 0 }}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          One widget = one governed metric at a valid grain. Metrics the data layer cannot compute are shown but cannot be added.
        </Typography>
        <List dense disablePadding>
          {governedMetrics.map((m) => (
            <ListItemButton key={m.key} disabled={m.status !== 'implemented'} onClick={() => onAdd(m)} sx={{ borderRadius: 1 }}>
              <ListItemText primary={m.label} secondary={`${m.family} · grains: ${m.grains.join(', ') || '—'}`} primaryTypographyProps={{ variant: 'body2' }} secondaryTypographyProps={{ variant: 'caption' }} />
              <Chip size="small" label={m.status.replace('_', ' ')} color={m.status === 'implemented' ? 'success' : m.status === 'spec_only' ? 'warning' : 'default'} variant="outlined" sx={{ height: 20, fontSize: 11 }} />
            </ListItemButton>
          ))}
        </List>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

export function OverviewSurface() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const router = useRouter();
  const search = useSearchParams();
  const role = useRole();
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const [widgets, setWidgets] = useState<Widget[]>(defaultWidgets.planner);
  useEffect(() => setWidgets(defaultWidgets[role]), [role]);
  const attentionFirst = isMobile && search.get('zone') === 'attention';

  const urgent = useMemo(() => signals.filter((s) => s.severity !== 'info'), []);
  const informational = useMemo(() => signals.filter((s) => s.severity === 'info'), []);

  const dashboard = (
    <Panel
      title={
        <Stack direction="row" spacing={1} alignItems="center">
          <span>Business dashboard</span>
          <Chip size="small" variant="outlined" label={`${role} default · published`} sx={{ height: 20, fontSize: 11 }} />
        </Stack>
      }
      subtitle={`${widgets.length} widgets over governed metrics · ${tenant.period} · refreshed 09:20`}
      actions={
        <Stack direction="row" spacing={0.5}>
          {editing ? (
            <Button size="small" startIcon={<AddIcon />} onClick={() => setAdding(true)}>
              Add widget
            </Button>
          ) : null}
          <Button size="small" variant={editing ? 'contained' : 'outlined'} startIcon={<EditOutlinedIcon />} onClick={() => setEditing((e) => !e)}>
            {editing ? 'Done' : 'Edit'}
          </Button>
        </Stack>
      }
      flush
    >
      <Box
        data-testid="dashboard-canvas"
        sx={{
          display: 'grid',
          gap: 1.5,
          px: 2,
          pb: 2,
          gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', md: 'repeat(12, minmax(0, 1fr))' },
          gridAutoRows: 'minmax(96px, auto)',
        }}
      >
        {widgets.map((w) => (
          <Box
            key={w.id}
            sx={{
              gridColumn: { xs: w.visual === 'kpi' ? 'span 1' : 'span 2', md: `span ${w.w}` },
              gridRow: { md: w.h === 2 ? 'span 3' : 'span 1' },
              position: 'relative',
              minWidth: 0,
              outline: editing ? '1px dashed' : 'none',
              outlineColor: 'primary.main',
              borderRadius: 1.5,
              minHeight: w.visual === 'kpi' ? 96 : 200,
            }}
          >
            {w.visual === 'kpi' ? (
              <WidgetBody w={w} onDrill={(h) => router.push(h)} />
            ) : (
              <Panel title={w.title} subtitle={governedMetrics.find((m) => m.key === w.metricKey)?.label} flush>
                <Box sx={{ px: 1, pb: 1 }}>
                  <WidgetBody w={w} onDrill={(h) => router.push(h)} />
                </Box>
              </Panel>
            )}
            {editing ? (
              <IconButton size="small" aria-label={`Remove ${w.title}`} onClick={() => setWidgets((ws) => ws.filter((x) => x.id !== w.id))} sx={{ position: 'absolute', top: 4, right: 4, bgcolor: 'background.default' }}>
                <CloseIcon fontSize="small" />
              </IconButton>
            ) : null}
          </Box>
        ))}
      </Box>
    </Panel>
  );

  const attention = (
    <Stack spacing={1.5} data-testid="attention-zone">
      <Panel title="Needs attention" subtitle={`${urgent.length} urgent · ${informational.length} informational · live from imports, stock, funding, supply`} flush>
        <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
          {urgent.map((s) => (
            <PanelRow key={s.id} severity={s.severity} primary={`${fmtInt(s.count)} ${s.headline}`} secondary={`${s.area} · ${s.detail}`} onClick={() => router.push(s.href)} />
          ))}
          <Typography variant="caption" color="text.secondary" sx={{ px: 1.5, pt: 1 }}>
            Informational
          </Typography>
          {informational.map((s) => (
            <PanelRow key={s.id} severity="info" primary={`${fmtInt(s.count)} ${s.headline}`} secondary={`${s.area} · ${s.detail}`} onClick={() => router.push(s.href)} />
          ))}
        </Stack>
      </Panel>
      <Panel
        title="Pinned reports"
        subtitle="Saved governed reports; any saved report can be pinned as a widget"
        actions={
          <Button size="small" component={NextLink} href="/design-lab/reports">
            All reports
          </Button>
        }
        flush
      >
        <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
          {savedReports.map((r) => (
            <PanelRow key={r.name} severity="neutral" primary={r.name} secondary={`${r.metric} · ${r.schedule}`} figure={<PushPinOutlinedIcon sx={{ fontSize: 16, color: 'text.disabled' }} />} onClick={() => router.push('/design-lab/reports')} />
          ))}
        </Stack>
      </Panel>
    </Stack>
  );

  return (
    <Box data-testid="overview-surface">
      <DomainHeader
        title={`Good morning — ${tenant.name}`}
        description="Your configurable view of the business, alongside what needs attention right now. Every figure drills into the workflow that owns it."
        meta={`${tenant.period} · data as at 09:20 today · sell-out through W36 for 3 of 4 distributors`}
      />
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'minmax(0, 1fr) 312px' }, alignItems: 'start' }}>
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
      <AddWidgetDialog
        open={adding}
        onClose={() => setAdding(false)}
        onAdd={(m) => {
          setWidgets((ws) => [...ws, { id: `n${Date.now()}`, metricKey: m.key, title: m.label, visual: m.defaultVisual, w: m.defaultVisual === 'kpi' ? 3 : 6, h: m.defaultVisual === 'kpi' ? 1 : 2 }]);
          setAdding(false);
        }}
      />
    </Box>
  );
}
