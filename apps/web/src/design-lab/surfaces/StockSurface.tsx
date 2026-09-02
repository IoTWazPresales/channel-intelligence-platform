'use client';

import type { ColDef, RowClickedEvent } from 'ag-grid-community';
import { Box, Button, Card, CardActionArea, CardContent, Stack, Typography, useMediaQuery } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';

import { distributors, fmtInt, products, tenant } from '../fixtures/entities';
import { planVsShipped } from '../fixtures/operations';
import { coverDistribution, coverRows, coverSummary, sellOutByFamily, weeklySeries, type CoverRow } from '../fixtures/stock';
import { CategoryBars, PairedBars, ProportionBar, TrendChart } from '../primitives/charts';
import { LensTabs, ScopeBar, StatusChip } from '../primitives/controls';
import { DomainHeader } from '../primitives/DomainHeader';
import { EntityContextPanel, KeyValueList } from '../primitives/EntityContextPanel';
import { HeadlineFigure, HeadlineStrip } from '../primitives/HeadlineFigure';
import { Panel, PanelRow } from '../primitives/Panel';

type Lens = 'cover' | 'movement' | 'sellthrough' | 'execution' | 'forecast';
const LENSES: { value: Lens; label: string }[] = [
  { value: 'cover', label: 'Cover' },
  { value: 'movement', label: 'Movement' },
  { value: 'sellthrough', label: 'Sell-through' },
  { value: 'execution', label: 'Execution vs plan' },
  { value: 'forecast', label: 'Forecasts' },
];

const statusTone = (s: CoverRow['status']) => (s === 'breach' ? 'danger' : s === 'watch' ? 'warning' : s === 'excess' ? 'info' : 'success');
const statusLabel = (s: CoverRow['status']) => (s === 'breach' ? 'Under 2w' : s === 'watch' ? '2–4w' : s === 'excess' ? 'Over 8w' : 'Healthy');

function useParam(key: string) {
  const router = useRouter();
  const search = useSearchParams();
  const value = search.get(key);
  const set = useCallback(
    (v: string | null) => {
      const next = new URLSearchParams(search.toString());
      if (v === null) next.delete(key);
      else next.set(key, v);
      router.replace(`/design-lab/stock?${next.toString()}`, { scroll: false });
    },
    [key, router, search]
  );
  return [value, set] as const;
}

function CoverLens() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [status, setStatus] = useParam('status');
  const [distributor, setDistributor] = useParam('distributor');
  const [family, setFamily] = useParam('family');
  const [product, setProduct] = useParam('product');
  const [savedView, setSavedView] = useState('All pairs');
  const [selected, setSelected] = useState<CoverRow | null>(null);

  const rows = useMemo(
    () =>
      coverRows.filter(
        (r) =>
          (!status || r.status === status) &&
          (!distributor || String(r.distributorId) === distributor) &&
          (!family || r.family === family) &&
          (!product || String(r.productId) === product)
      ),
    [status, distributor, family, product]
  );

  const columnDefs = useMemo<ColDef<CoverRow>[]>(
    () => [
      { field: 'distributor', headerName: 'Distributor', minWidth: 190, flex: 1.2, pinned: 'left' },
      { field: 'product', headerName: 'Product', minWidth: 240, flex: 1.6, cellRenderer: (p: { data: CoverRow }) => (
          <Box sx={{ lineHeight: 1.2 }}>
            <Typography variant="body2" noWrap>{p.data.product}</Typography>
            <Typography variant="caption" color="text.secondary">{p.data.sku} · {p.data.family}</Typography>
          </Box>
        ) },
      { field: 'soh', headerName: 'SOH', type: 'rightAligned', width: 100, valueFormatter: (p) => fmtInt(p.value) },
      { field: 'weeklyRate', headerName: 'Sell-out / wk', type: 'rightAligned', width: 120, valueFormatter: (p) => fmtInt(p.value) },
      { field: 'weeksOfCover', headerName: 'Weeks of cover', width: 170, sort: 'asc', cellRenderer: (p: { data: CoverRow }) => (
          <ProportionBar value={Math.min(p.data.weeksOfCover / 10, 1)} label={`${p.data.weeksOfCover.toFixed(1)}w`} tone={p.data.status === 'breach' ? 'danger' : p.data.status === 'watch' ? 'warning' : p.data.status === 'excess' ? 'primary' : 'success'} />
        ) },
      { field: 'inboundOpen', headerName: 'Inbound open', type: 'rightAligned', width: 130, valueFormatter: (p) => (p.value ? fmtInt(p.value) : '—') },
      { field: 'vintageDays', headerName: 'Vintage', width: 100, valueFormatter: (p) => `${p.value}d`, cellStyle: (p) => (Number(p.value) > 10 ? { color: theme.palette.warning.main } : null) },
      { field: 'status', headerName: 'Status', width: 120, cellRenderer: (p: { data: CoverRow }) => <StatusChip label={statusLabel(p.data.status)} tone={statusTone(p.data.status)} /> },
    ],
    [theme]
  );

  const chips = [
    { key: 'breach', label: `Under 2w · ${coverSummary.breach}`, active: status === 'breach', onToggle: () => setStatus(status === 'breach' ? null : 'breach'), tone: 'danger' as const },
    { key: 'watch', label: `2–4w · ${coverSummary.watch}`, active: status === 'watch', onToggle: () => setStatus(status === 'watch' ? null : 'watch'), tone: 'warning' as const },
    { key: 'excess', label: `Over 8w · ${coverSummary.excess}`, active: status === 'excess', onToggle: () => setStatus(status === 'excess' ? null : 'excess') },
    ...distributors.map((d) => ({ key: `d${d.id}`, label: d.code, active: distributor === String(d.id), onToggle: () => setDistributor(distributor === String(d.id) ? null : String(d.id)) })),
    ...['Monitors', 'Notebooks', 'Accessories', 'Print'].map((f) => ({ key: f, label: f, active: family === f, onToggle: () => setFamily(family === f ? null : f) })),
  ];

  const clear = () => {
    setStatus(null);
    setDistributor(null);
    setFamily(null);
    setProduct(null);
    setSavedView('All pairs');
  };

  const selectedProductRows = selected ? coverRows.filter((r) => r.productId === selected.productId) : [];

  return (
    <Stack spacing={2} sx={{ mt: 2 }}>
      <HeadlineStrip columns={5}>
        <HeadlineFigure label="Network SOH" value={fmtInt(coverSummary.soh)} unit="units" caption={`${coverSummary.pairs} pairs · ${distributors.length} distributors`} compact />
        <HeadlineFigure label="Network cover" value={coverSummary.networkCover.toFixed(1)} unit="weeks" compact caption="SOH ÷ trailing 4-week sell-out" />
        <HeadlineFigure label="Under 2 weeks" value={coverSummary.breach} unit="pairs" severity="bad" compact onClick={() => setStatus('breach')} caption="Risk of stock-out" />
        <HeadlineFigure label="2–4 weeks" value={coverSummary.watch} unit="pairs" severity="warn" compact onClick={() => setStatus('watch')} caption="Watch list" />
        <HeadlineFigure label="Over 8 weeks" value={coverSummary.excess} unit="pairs" compact onClick={() => setStatus('excess')} caption="Excess / ageing risk" />
      </HeadlineStrip>

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '2fr 3fr' } }}>
        <Panel title="Cover distribution" subtitle="Distributor × product pairs by weeks of cover · click a bar to filter">
          <CategoryBars
            data={coverDistribution}
            x="bucket"
            y="pairs"
            height={180}
            colorBy={(r) => (['<1w', '1–2w'].includes(String(r.bucket)) ? theme.palette.error.main : String(r.bucket) === '2–4w' ? theme.palette.warning.main : String(r.bucket) === '8w+' ? theme.palette.primary.light : theme.palette.success.main)}
          />
        </Panel>
        <Panel title="Sell-out vs shipped-in, W24–W36" subtitle="All distributors · units per week · SOH on right panel of Movement lens">
          <TrendChart data={weeklySeries} x="week" height={180} series={[{ key: 'shipped', label: 'Shipped in', kind: 'bar', tone: 'muted' }, { key: 'sellOut', label: 'Sell-out', kind: 'line', tone: 'primary' }]} />
        </Panel>
      </Box>

      <ScopeBar
        chips={chips}
        savedViews={['All pairs', 'My strategic SKUs', 'Breaches only']}
        savedView={savedView}
        onSavedView={(v) => {
          setSavedView(v);
          if (v === 'Breaches only') setStatus('breach');
          if (v === 'All pairs') clear();
        }}
        summary={`${rows.length} of ${coverRows.length} pairs`}
        onClear={clear}
      />

      <ModuleDataSection
        isEmpty={rows.length === 0}
        empty={{ title: 'No pairs match this scope', description: 'Clear a chip or pick another saved view. Cover is derived from distributor sell-out and SOH files — nothing is stored.', primary: { label: 'Clear scope', onClick: clear } }}
      >
        {isMobile ? (
          <Stack spacing={1} data-testid="cover-record-cards">
            {rows.slice(0, 30).map((r) => (
              <Card key={r.id} variant="outlined" sx={{ boxShadow: 'none' }}>
                <CardActionArea onClick={() => setSelected(r)}>
                  <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                      <Box sx={{ minWidth: 0 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>{r.product}</Typography>
                        <Typography variant="caption" color="text.secondary">{r.distributor}</Typography>
                      </Box>
                      <StatusChip label={`${r.weeksOfCover.toFixed(1)}w`} tone={statusTone(r.status)} />
                    </Stack>
                    <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
                      <Typography variant="caption">SOH <b>{fmtInt(r.soh)}</b></Typography>
                      <Typography variant="caption">/wk <b>{fmtInt(r.weeklyRate)}</b></Typography>
                      <Typography variant="caption">Inbound <b>{r.inboundOpen ? fmtInt(r.inboundOpen) : '—'}</b></Typography>
                    </Stack>
                  </CardContent>
                </CardActionArea>
              </Card>
            ))}
          </Stack>
        ) : (
          <EnterpriseDataGrid<CoverRow>
            rowData={rows}
            columnDefs={columnDefs}
            height={440}
            gridOptions={{ onRowClicked: (e: RowClickedEvent<CoverRow>) => e.data && setSelected(e.data), rowClass: 'cip-clickable-row', getRowId: (p) => p.data.id }}
          />
        )}
      </ModuleDataSection>

      <EntityContextPanel
        open={!!selected}
        onClose={() => setSelected(null)}
        kicker="Product"
        title={selected?.product ?? ''}
        subtitle={selected ? `${selected.sku} · ${selected.family} · ${products.find((p) => p.id === selected.productId)?.active ? 'Active' : 'Inactive'}` : undefined}
        figures={
          selected ? (
            <HeadlineStrip columns={3}>
              <HeadlineFigure label="SOH (network)" value={fmtInt(selectedProductRows.reduce((a, r) => a + r.soh, 0))} dense />
              <HeadlineFigure label="Sell-out / wk" value={fmtInt(selectedProductRows.reduce((a, r) => a + r.weeklyRate, 0))} dense />
              <HeadlineFigure label="Inbound open" value={fmtInt(selectedProductRows.reduce((a, r) => a + r.inboundOpen, 0))} dense />
            </HeadlineStrip>
          ) : null
        }
        related={
          selected
            ? [
                { label: 'Plan lines for this product', href: `/design-lab/planning?lens=cases&product=${selected.productId}`, hint: 'Planning › Lineup cases' },
                { label: 'Open inbound shipments', href: `/design-lab/supply?lens=shipments&product=${selected.productId}`, hint: 'Supply & Inbound › Shipments' },
                { label: 'Promotion cases on this SKU', href: `/design-lab/funding?sku=${selected.sku}`, hint: 'Promotions & Funding › Case book' },
                { label: 'Retail listings & shelf price', href: `/design-lab/market?product=${selected.productId}`, hint: 'Market & Listings › Monitored listings' },
                { label: 'Competitor products', href: `/design-lab/market?lens=competition&product=${selected.productId}`, hint: 'Market & Listings › Competitor mappings' },
                { label: 'Product master record', href: `/design-lab/data?tab=masters&m=products&id=${selected.productId}`, hint: 'Data & Stewardship › Products' },
              ]
            : []
        }
        footer={
          <>
            <Button variant="outlined" size="small" onClick={() => selected && setProduct(String(selected.productId))}>
              Filter grid to this product
            </Button>
            <Button variant="contained" size="small" onClick={() => setSelected(null)}>
              Done
            </Button>
          </>
        }
      >
        {selected ? (
          <Stack spacing={2}>
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Cover by distributor
              </Typography>
              <Stack spacing={0.25} sx={{ mt: 1 }}>
                {selectedProductRows.map((r) => (
                  <PanelRow key={r.id} severity={r.status === 'breach' ? 'danger' : r.status === 'watch' ? 'warning' : 'neutral'} primary={r.distributor} secondary={`SOH ${fmtInt(r.soh)} · ${fmtInt(r.weeklyRate)}/wk · vintage ${r.vintageDays}d`} figure={`${r.weeksOfCover.toFixed(1)}w`} />
                ))}
              </Stack>
            </Box>
            <KeyValueList
              items={[
                { k: 'Selected pair', v: `${selected.distributor}` },
                { k: 'Weeks of cover', v: `${selected.weeksOfCover.toFixed(1)} (${statusLabel(selected.status)})` },
                { k: 'Derivation', v: 'SOH from latest DSI vintage ÷ trailing 4-week sell-out rate' },
                { k: 'Data vintage', v: `${selected.vintageDays} days` },
              ]}
            />
          </Stack>
        ) : null}
      </EntityContextPanel>
    </Stack>
  );
}

function MovementLens() {
  return (
    <Stack spacing={2} sx={{ mt: 2 }}>
      <HeadlineStrip columns={4}>
        <HeadlineFigure label="Sell-out W36" value={fmtInt(weeklySeries[weeklySeries.length - 1].sellOut)} unit="units" compact delta={{ text: '12.8% vs W35', direction: 'down' }} />
        <HeadlineFigure label="Shipped in W36" value={fmtInt(weeklySeries[weeklySeries.length - 1].shipped)} unit="units" compact />
        <HeadlineFigure label="SOH end W36" value={fmtInt(weeklySeries[weeklySeries.length - 1].soh)} unit="units" compact />
        <HeadlineFigure label="Families growing WoW" value={sellOutByFamily.filter((f) => f.wow > 0).length} unit={`of ${sellOutByFamily.length}`} compact />
      </HeadlineStrip>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '3fr 2fr' } }}>
        <Panel title="Stock on hand vs sell-out, W24–W36" subtitle="Derived SOH (area) against weekly sell-out (line)">
          <TrendChart data={weeklySeries} x="week" height={260} series={[{ key: 'soh', label: 'Stock on hand', kind: 'area', tone: 'muted' }, { key: 'sellOut', label: 'Sell-out', kind: 'line', tone: 'primary' }]} />
        </Panel>
        <Panel title="Sell-out by family, W36" subtitle="Units and week-on-week change">
          <CategoryBars data={sellOutByFamily} x="family" y="units" height={260} horizontal />
        </Panel>
      </Box>
    </Stack>
  );
}

function ExecutionLens() {
  const total = planVsShipped.reduce((a, r) => ({ plan: a.plan + r.plan, shipped: a.shipped + r.shipped }), { plan: 0, shipped: 0 });
  return (
    <Stack spacing={2} sx={{ mt: 2 }}>
      <HeadlineStrip columns={3}>
        <HeadlineFigure label="Plan units P09" value={fmtInt(total.plan)} compact />
        <HeadlineFigure label="Shipped to date" value={fmtInt(total.shipped)} compact caption={`${Math.round((total.shipped / total.plan) * 100)}% of plan`} />
        <HeadlineFigure label="Customers under 70% of plan" value={planVsShipped.filter((r) => r.shipped / r.plan < 0.7).length} severity="warn" compact />
      </HeadlineStrip>
      <Panel title="Shipped vs plan by customer, P09" subtitle="Lineup plan lines vs inbound shipments attributed to the customer">
        <PairedBars data={planVsShipped} x="customer" a="plan" b="shipped" aLabel="Plan" bLabel="Shipped" height={280} />
      </Panel>
    </Stack>
  );
}

function ThinLens({ title, body }: { title: string; body: string }) {
  return (
    <Box sx={{ mt: 2 }}>
      <ModuleDataSection isEmpty empty={{ title, description: body, primary: { label: 'Go to Import Center', href: '/design-lab/data?tab=imports' } }}>
        <span />
      </ModuleDataSection>
    </Box>
  );
}

export function StockSurface() {
  const search = useSearchParams();
  const router = useRouter();
  const lens = (search.get('lens') as Lens) || 'cover';
  const setLens = (l: Lens) => router.replace(`/design-lab/stock?lens=${l}`, { scroll: false });

  return (
    <Box data-testid="stock-surface">
      <DomainHeader
        crumbs={[{ label: 'Stock & Sell-through' }]}
        title="Stock & Sell-through"
        description="Distributor and retailer stock, weeks of cover, sell-out velocity and execution against plan — all derived from imported sell-out, SOH and shipment files."
        meta={`${tenant.period} · sell-out through W36 for 3 of 4 distributors · SOH is calculated, never stored`}
        actions={
          <>
            <Button variant="outlined" size="small" href="/design-lab/reports">
              Open in Reports
            </Button>
            <Button variant="contained" size="small" href="/design-lab/data?tab=imports">
              Import sell-out / SOH
            </Button>
          </>
        }
      />
      <LensTabs value={lens} onChange={setLens} ariaLabel="Stock lenses" lenses={LENSES.map((l) => ({ ...l, count: l.value === 'cover' ? coverSummary.breach : undefined }))} />
      {lens === 'cover' ? <CoverLens /> : null}
      {lens === 'movement' ? <MovementLens /> : null}
      {lens === 'execution' ? <ExecutionLens /> : null}
      {lens === 'sellthrough' ? <ThinLens title="Retailer sell-through for W36 not yet imported" body="Sell-through is derived from retailer files (customer_sell_through). TechMart W35 is the latest applied; W36 files are due Wednesday." /> : null}
      {lens === 'forecast' ? <ThinLens title="Forecasts need 8 weeks of applied sell-out" body="Velocity and analogue projections are labelled by method and computed only when the trailing window is complete for the selected scope." /> : null}
    </Box>
  );
}
