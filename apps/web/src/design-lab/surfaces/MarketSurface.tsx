'use client';

import type { ColDef, RowClickedEvent } from 'ag-grid-community';
import { Alert, Box, Button, Card, CardActionArea, CardContent, Chip, LinearProgress, Snackbar, Stack, Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography, useMediaQuery } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';

import {
  activationLabel,
  commercialCapabilities,
  competitorMappings as seedMappings,
  listingHistory,
  listingProposals as seedProposals,
  listings as seedListings,
  scorerWeights,
  type ActivationStatus,
  type CompetitorMapping,
  type Listing,
  type ListingProposal,
  type ListingStatus,
} from '../fixtures/commercial';
import { fmtCurrency, fmtInt, tenant } from '../fixtures/entities';
import { CapabilityLedger } from '../primitives/CapabilityLedger';
import { CapabilityStatus } from '../primitives/CapabilityStatus';
import { TrendChart } from '../primitives/charts';
import { LensTabs, ScopeBar, StatusChip } from '../primitives/controls';
import { DomainHeader } from '../primitives/DomainHeader';
import { EntityContextPanel, KeyValueList } from '../primitives/EntityContextPanel';
import { HeadlineFigure, HeadlineStrip } from '../primitives/HeadlineFigure';
import { Panel, PanelRow } from '../primitives/Panel';
import { labDomains } from '../shell/labNav';

type Lens = 'listings' | 'history' | 'activation' | 'proposals' | 'competition' | 'competitor-prices' | 'competitor-listings' | 'quality';

const listingTone = (s: ListingStatus) => (s === 'active' ? 'success' : s === 'out_of_stock' ? 'warning' : s === 'dead_link' ? 'danger' : 'neutral');
const listingStatusLabel: Record<ListingStatus, string> = { active: 'Active', out_of_stock: 'Out of stock', delisted: 'Delisted', dead_link: 'Dead link' };
const activationTone = (a: ActivationStatus) => (a === 'price_consistent' ? 'success' : a === 'not_activated' ? 'danger' : a === 'no_listing' ? 'warning' : 'neutral');
const sourceLabel: Record<Listing['source'], string> = { manual: 'Manual', csv: 'CSV', feed_proposal: 'Feed proposal', auto_finder: 'Auto-finder' };

/**
 * Market & Listings — the evidence domain. Retailer listings and observed prices are facts CIP
 * stores and checks; competitor mappings are facts the steward confirms. Everything derived here
 * is a comparison of stored numbers (observed price vs case SRP, first vs last price, score of a
 * deterministic matcher). No uplift, elasticity or impact is shown — none is computed.
 */
export function MarketSurface() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const router = useRouter();
  const search = useSearchParams();
  const lens = (search.get('lens') as Lens) || 'listings';
  const customerFilter = search.get('customer');
  const productFilter = search.get('product');
  const activationFilter = search.get('activation') as ActivationStatus | null;
  const setParam = useCallback(
    (k: string, v: string | null) => {
      const next = new URLSearchParams(search.toString());
      if (v === null) next.delete(k);
      else next.set(k, v);
      router.replace(`/design-lab/market?${next.toString()}`, { scroll: false });
    },
    [router, search]
  );
  const domain = labDomains.find((d) => d.id === 'market')!;

  const [listings] = useState<Listing[]>(seedListings);
  const [proposals, setProposals] = useState<ListingProposal[]>(seedProposals);
  const [mappings, setMappings] = useState<CompetitorMapping[]>(seedMappings);
  const [selectedListing, setSelectedListing] = useState<number | null>(search.get('listing') ? Number(search.get('listing')) : null);
  const [selectedMapping, setSelectedMapping] = useState<number | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const scoped = useMemo(
    () => listings.filter((l) => (!customerFilter || String(l.customerId) === customerFilter) && (!productFilter || String(l.productId) === productFilter) && (!activationFilter || l.activation === activationFilter)),
    [listings, customerFilter, productFilter, activationFilter]
  );
  const listing = listings.find((l) => l.id === selectedListing) ?? null;
  const mapping = mappings.find((m) => m.id === selectedMapping) ?? null;

  const counts = {
    active: listings.filter((l) => l.status === 'active').length,
    problems: listings.filter((l) => l.status === 'dead_link' || l.status === 'out_of_stock').length,
    unlinked: listings.filter((l) => !l.productId).length,
    notActivated: listings.filter((l) => l.activation === 'not_activated').length,
    live: listings.filter((l) => l.activation === 'price_consistent').length,
    drifted: listings.filter((l) => l.firstPrice !== null && l.lastPrice !== null && l.firstPrice !== l.lastPrice).length,
    proposals: proposals.filter((p) => p.status === 'proposed').length,
    pendingMappings: mappings.filter((m) => m.status === 'pending').length,
  };

  const listingCols = useMemo<ColDef<Listing>[]>(
    () => [
      { field: 'customer', headerName: 'Customer', minWidth: 150, flex: 1, pinned: 'left' },
      { field: 'product', headerName: 'Product', minWidth: 220, flex: 1.5, valueGetter: (p) => p.data?.sku ?? '', cellRenderer: (p: { data: Listing }) => (
          <Box sx={{ lineHeight: 1.2 }}>
            <Typography variant="body2" noWrap color={p.data.product ? 'text.primary' : 'warning.main'}>{p.data.product ?? 'No product link — resolve in Data & Stewardship'}</Typography>
            <Typography variant="caption" color="text.secondary" noWrap>{p.data.sku ?? p.data.url}</Typography>
          </Box>
        ) },
      { field: 'status', headerName: 'Listing', width: 130, cellRenderer: (p: { data: Listing }) => <StatusChip label={listingStatusLabel[p.data.status]} tone={listingTone(p.data.status)} /> },
      { field: 'lastPrice', headerName: 'Last price', type: 'rightAligned', width: 115, valueFormatter: (p) => (p.value === null ? '—' : fmtCurrency(p.value)) },
      { headerName: 'Δ since first', type: 'rightAligned', width: 115, valueGetter: (p) => (p.data && p.data.firstPrice !== null && p.data.lastPrice !== null ? p.data.lastPrice - p.data.firstPrice : null), valueFormatter: (p) => (p.value === null ? '—' : p.value === 0 ? '0' : `${p.value > 0 ? '+' : '−'}${fmtCurrency(Math.abs(p.value))}`), cellStyle: (p) => (p.value ? { color: p.value < 0 ? theme.palette.success.main : theme.palette.warning.main } : null) },
      { field: 'availability', headerName: 'Availability', width: 120, valueFormatter: (p) => String(p.value).replace('_', ' ') },
      { field: 'promoBadge', headerName: 'Badge', width: 110, valueFormatter: (p) => p.value ?? '' },
      { field: 'activation', headerName: 'Promotion on shelf', width: 220, cellRenderer: (p: { data: Listing }) => <StatusChip label={activationLabel[p.data.activation]} tone={activationTone(p.data.activation)} /> },
      { field: 'observations', headerName: 'Obs.', type: 'rightAligned', width: 80 },
      { field: 'spanDays', headerName: 'Span', type: 'rightAligned', width: 85, valueFormatter: (p) => `${p.value} d`, cellStyle: (p) => (Number(p.value) < 14 ? { color: theme.palette.text.disabled } : null) },
      { field: 'source', headerName: 'Source', width: 130, valueFormatter: (p) => sourceLabel[p.value as Listing['source']] },
      { field: 'lastFetched', headerName: 'Fetched', width: 130 },
    ],
    [theme]
  );

  const mappingCols = useMemo<ColDef<CompetitorMapping>[]>(
    () => [
      { field: 'sku', headerName: 'Our product', minWidth: 200, flex: 1.3, pinned: 'left', cellRenderer: (p: { data: CompetitorMapping }) => (
          <Box sx={{ lineHeight: 1.2 }}>
            <Typography variant="body2" noWrap>{p.data.product}</Typography>
            <Typography variant="caption" color="text.secondary">{p.data.sku}</Typography>
          </Box>
        ) },
      { field: 'competitorName', headerName: 'Competing product', minWidth: 220, flex: 1.5, cellRenderer: (p: { data: CompetitorMapping }) => (
          <Box sx={{ lineHeight: 1.2 }}>
            <Typography variant="body2" noWrap>{p.data.competitorName}</Typography>
            <Typography variant="caption" color="text.secondary">{p.data.competitorBrand} · {p.data.competitorSku}</Typography>
          </Box>
        ) },
      { field: 'score', headerName: 'Match score', width: 150, cellRenderer: (p: { data: CompetitorMapping }) => (
          <Stack direction="row" spacing={1} alignItems="center" sx={{ width: '100%' }}>
            <LinearProgress variant="determinate" value={p.data.score * 100} sx={{ flex: 1, height: 6, borderRadius: 3 }} color={p.data.score >= 0.8 ? 'success' : p.data.score >= 0.6 ? 'primary' : 'warning'} />
            <Typography variant="caption" sx={{ fontVariantNumeric: 'tabular-nums', width: 32 }}>{p.data.score.toFixed(2)}</Typography>
          </Stack>
        ) },
      { field: 'origin', headerName: 'Origin', width: 120, valueFormatter: (p) => ({ loaded: 'Loaded', confirmed: 'Confirmed', proposed: 'Proposed' })[p.value as CompetitorMapping['origin']] },
      { field: 'status', headerName: 'Approval', width: 120, cellRenderer: (p: { data: CompetitorMapping }) => <StatusChip label={p.data.status === 'approved' ? 'Approved' : p.data.status === 'pending' ? 'Pending' : 'Rejected'} tone={p.data.status === 'approved' ? 'success' : p.data.status === 'pending' ? 'warning' : 'neutral'} /> },
      { field: 'priceObservations', headerName: 'Competitor prices', type: 'rightAligned', width: 150, valueFormatter: (p) => (p.value ? fmtInt(p.value) : 'none observed') },
      { field: 'listingMonitored', headerName: 'Competitor listing', width: 150, valueFormatter: (p) => (p.value ? 'Monitored' : 'Not monitored (planned)') },
    ],
    []
  );

  const decideMapping = (id: number, status: 'approved' | 'rejected') => {
    setMappings((ms) => ms.map((m) => (m.id === id ? { ...m, status, origin: status === 'approved' ? 'confirmed' : m.origin } : m)));
    setToast(status === 'approved' ? 'Mapping approved — now reusable by the planner, dashboards and reports.' : 'Mapping rejected — kept for audit, hidden from consumers.');
    setSelectedMapping(null);
  };
  const decideProposal = (id: number, status: 'confirmed' | 'rejected') => {
    setProposals((ps) => ps.map((p) => (p.id === id ? { ...p, status } : p)));
    setToast(status === 'confirmed' ? 'Listing added to the registry and scheduled for its first fetch.' : 'Proposal rejected — the feed id is remembered so it is not re-proposed.');
  };

  return (
    <Box data-testid="market-surface">
      <DomainHeader
        crumbs={[{ label: domain.label }]}
        title={domain.label}
        description={domain.what}
        meta={`${tenant.period} · ${listings.length} monitored listings · ${listings.reduce((a, l) => a + l.observations, 0)} observations · last fetch today 06:18`}
        actions={
          <>
            <Button variant="outlined" size="small" href="/design-lab/reports">Open in Reports</Button>
            <Button variant="contained" size="small" onClick={() => setToast('Add a listing: paste a URL, pick customer and product (token-resolved). First fetch runs on save.')}>Add listing</Button>
          </>
        }
      />
      <LensTabs
        value={lens}
        onChange={(l) => setParam('lens', l === 'listings' ? null : l)}
        ariaLabel="Market lenses"
        lenses={[
          { value: 'listings', label: 'Monitored listings', count: listings.length },
          { value: 'history', label: 'Price history' },
          { value: 'activation', label: 'Promotion activation', count: counts.notActivated || undefined },
          { value: 'proposals', label: 'Feed proposals', count: counts.proposals },
          { value: 'competition', label: 'Competitor mappings', count: counts.pendingMappings || undefined },
          { value: 'competitor-prices', label: 'Competitor prices' },
          { value: 'competitor-listings', label: 'Competitor listings' },
          { value: 'quality', label: 'Listing quality / SEO' },
        ]}
      />

      {lens === 'listings' || lens === 'history' ? (
        <Stack spacing={2} sx={{ mt: 2 }}>
          <HeadlineStrip columns={5}>
            <HeadlineFigure label="Active listings" value={counts.active} unit={`of ${listings.length}`} compact caption={`${counts.problems} out of stock or dead`} severity={counts.problems ? 'warn' : 'good'} />
            <HeadlineFigure label="Promo live at price" value={counts.live} compact severity="good" caption="Observed price = case SRP in window" onClick={() => setParam('activation', 'price_consistent')} />
            <HeadlineFigure label="Promo not at price" value={counts.notActivated} compact severity={counts.notActivated ? 'bad' : 'neutral'} caption="Live case, shelf price differs" onClick={() => setParam('activation', 'not_activated')} />
            <HeadlineFigure label="Price moved since first seen" value={counts.drifted} compact caption="first ≠ last observation" />
            <HeadlineFigure label="Unlinked listings" value={counts.unlinked} compact severity={counts.unlinked ? 'warn' : 'neutral'} caption="No product — resolve token" />
          </HeadlineStrip>

          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'minmax(0, 3fr) minmax(300px, 2fr)' }, alignItems: 'start' }}>
            <Panel
              title={`Observed price — ${listings[0].customer} · ${listings[0].product}`}
              subtitle="Daily observations (listing 44). Shaded band = covering case window at the planned SRP. Observed only — no impact computed."
              actions={<Button size="small" onClick={() => setSelectedListing(44)}>Open listing</Button>}
            >
              <TrendChart
                data={listingHistory}
                x="date"
                height={220}
                yScale="fit"
                format={(v) => fmtCurrency(v)}
                series={[
                  { key: 'casePrice', label: 'Case SRP (window)', kind: 'area', tone: 'muted' },
                  { key: 'price', label: 'Observed price', kind: 'line', tone: 'primary' },
                ]}
              />
              <Typography variant="caption" color="text.secondary">
                Window 24 Aug – 6 Sep at R16 999 (CPR-26-1203). Observed R18 999 throughout → <b>not activated</b>; the planner and Case book see the same status.
              </Typography>
              <Box sx={{ mt: 2, borderTop: '1px solid', borderColor: 'divider', pt: 1.5 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>Price moved since first seen</Typography>
                <Typography variant="caption" color="text.secondary">first observation → latest, per listing. A stored comparison; no cause is inferred.</Typography>
                <Box sx={{ overflowX: 'auto', mt: 1 }}>
                  <Table size="small" sx={{ '& td, & th': { py: 0.5, whiteSpace: 'nowrap' } }}>
                    <TableHead>
                      <TableRow>
                        <TableCell>Listing</TableCell>
                        <TableCell align="right">First</TableCell>
                        <TableCell align="right">Latest</TableCell>
                        <TableCell align="right">Δ</TableCell>
                        <TableCell>Promotion covering</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {listings.filter((l) => l.firstPrice !== null && l.lastPrice !== null && l.firstPrice !== l.lastPrice).map((l) => (
                        <TableRow key={l.id} hover sx={{ cursor: 'pointer' }} onClick={() => setSelectedListing(l.id)}>
                          <TableCell>
                            <Typography variant="body2">{l.customer} · {l.sku}</Typography>
                            <Typography variant="caption" color="text.secondary">{l.observations} obs · {l.spanDays} d</Typography>
                          </TableCell>
                          <TableCell align="right">{fmtCurrency(l.firstPrice ?? 0)}</TableCell>
                          <TableCell align="right">{fmtCurrency(l.lastPrice ?? 0)}</TableCell>
                          <TableCell align="right" sx={{ color: (l.lastPrice ?? 0) < (l.firstPrice ?? 0) ? 'success.main' : 'warning.main', fontWeight: 600 }}>{(l.lastPrice ?? 0) < (l.firstPrice ?? 0) ? '−' : '+'}{fmtCurrency(Math.abs((l.lastPrice ?? 0) - (l.firstPrice ?? 0)))}</TableCell>
                          <TableCell>{l.caseCode ? `${l.caseCode} · ${activationLabel[l.activation]}` : 'none — a customer price move, not a promotion'}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
              </Box>
            </Panel>
            <Stack spacing={2} sx={{ minWidth: 0 }}>
              <Panel title="Attention candidates" subtitle="Derived from stored observations today; not yet a Brief signal (proposed)" flush>
                <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
                  {listings.filter((l) => l.activation === 'not_activated').map((l) => (
                    <PanelRow key={l.id} severity="danger" primary={`${l.customer} · ${l.sku} not at promo price`} secondary={`observed ${fmtCurrency(l.lastPrice ?? 0)} vs case ${fmtCurrency(l.casePrice ?? 0)} · ${l.caseCode}`} onClick={() => setSelectedListing(l.id)} />
                  ))}
                  {listings.filter((l) => l.status === 'dead_link').map((l) => (
                    <PanelRow key={l.id} severity="warning" primary={`${l.customer} · ${l.sku} dead link`} secondary={`last fetched ${l.lastFetched} · re-find or retire`} onClick={() => setSelectedListing(l.id)} />
                  ))}
                  {listings.filter((l) => !l.productId).map((l) => (
                    <PanelRow key={l.id} severity="warning" primary={`${l.customer} · listing without product`} secondary={l.url} figure="Resolve" onClick={() => router.push('/design-lab/data?tab=steward')} />
                  ))}
                  <PanelRow severity="info" primary={`${counts.proposals} feed proposals waiting`} secondary="Listing ids seen in CST sell-through feeds" onClick={() => setParam('lens', 'proposals')} />
                </Stack>
              </Panel>
              <CapabilityLedger items={commercialCapabilities.listings} />
            </Stack>
          </Box>

          <ScopeBar
            chips={[
              { key: 'not_activated', label: `Not at promo price · ${counts.notActivated}`, active: activationFilter === 'not_activated', onToggle: () => setParam('activation', activationFilter === 'not_activated' ? null : 'not_activated'), tone: 'danger' },
              { key: 'price_consistent', label: `Promo live · ${counts.live}`, active: activationFilter === 'price_consistent', onToggle: () => setParam('activation', activationFilter === 'price_consistent' ? null : 'price_consistent'), tone: 'success' },
              { key: 'no_case_detected', label: 'No promotion covering', active: activationFilter === 'no_case_detected', onToggle: () => setParam('activation', activationFilter === 'no_case_detected' ? null : 'no_case_detected') },
            ]}
            summary={`${scoped.length} of ${listings.length} listings${customerFilter ? ' · customer scoped' : ''}${productFilter ? ' · product scoped' : ''}`}
            onClear={() => { setParam('activation', null); setParam('customer', null); setParam('product', null); }}
          />
          <ModuleDataSection isEmpty={scoped.length === 0} empty={{ title: 'No listings in this scope', description: 'Clear the scope or add a listing for this customer / product.', primary: { label: 'Clear scope', onClick: () => { setParam('activation', null); setParam('customer', null); setParam('product', null); } } }}>
            {isMobile ? (
              <Stack spacing={1} data-testid="listing-record-cards">
                {scoped.map((l) => (
                  <Card key={l.id} variant="outlined" sx={{ boxShadow: 'none' }}>
                    <CardActionArea onClick={() => setSelectedListing(l.id)}>
                      <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
                        <Stack direction="row" justifyContent="space-between" spacing={1} alignItems="flex-start">
                          <Box sx={{ minWidth: 0 }}>
                            <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>{l.customer} · {l.sku ?? 'unlinked'}</Typography>
                            <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>{l.product ?? l.url}</Typography>
                          </Box>
                          <StatusChip label={activationLabel[l.activation]} tone={activationTone(l.activation)} />
                        </Stack>
                        <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
                          <Typography variant="caption">Last <b>{l.lastPrice === null ? '—' : fmtCurrency(l.lastPrice)}</b></Typography>
                          <Typography variant="caption">Obs <b>{l.observations}</b></Typography>
                          <Typography variant="caption">{listingStatusLabel[l.status]}</Typography>
                        </Stack>
                      </CardContent>
                    </CardActionArea>
                  </Card>
                ))}
              </Stack>
            ) : (
              <EnterpriseDataGrid<Listing> rowData={scoped} columnDefs={listingCols} height={380} gridOptions={{ onRowClicked: (e: RowClickedEvent<Listing>) => e.data && setSelectedListing(e.data.id), getRowId: (p) => String(p.data.id) }} />
            )}
          </ModuleDataSection>
        </Stack>
      ) : null}

      {lens === 'activation' ? (
        <Stack spacing={2} sx={{ mt: 2 }}>
          <Alert severity="info" variant="outlined">
            Each observation inside a live case window is compared with that case line’s SRP. Three outcomes only: <b>live at price</b>, <b>not at promo price</b>, <b>no promotion covering</b>. Late activation and early deactivation are derivable from the same timeline but are not computed yet (data only).
          </Alert>
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'minmax(0, 3fr) minmax(0, 2fr)' }, alignItems: 'start' }}>
            <Panel title="Live cases on the shelf" subtitle="Grouped by case — the same status the planner and the Case book show" flush>
              <Box sx={{ overflowX: 'auto' }}>
              <Table size="small" sx={{ '& td, & th': { py: 0.7 } }}>
                <TableHead>
                  <TableRow>
                    <TableCell>Case</TableCell>
                    <TableCell>Listing</TableCell>
                    <TableCell align="right">Case SRP</TableCell>
                    <TableCell align="right">Observed</TableCell>
                    <TableCell>Status</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {listings.filter((l) => l.caseCode).map((l) => (
                    <TableRow key={l.id} hover sx={{ cursor: 'pointer' }} onClick={() => setSelectedListing(l.id)}>
                      <TableCell>
                        <Typography variant="body2">{l.caseCode}</Typography>
                        <Typography variant="caption" color="text.secondary">Metro FNB-Day · 24 Aug – 6 Sep</Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{l.product}</Typography>
                        <Typography variant="caption" color="text.secondary">{l.customer} · {l.promoBadge ? `badge “${l.promoBadge}”` : 'no badge'}</Typography>
                      </TableCell>
                      <TableCell align="right">{fmtCurrency(l.casePrice ?? 0)}</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 600, color: l.activation === 'not_activated' ? 'error.main' : 'success.main' }}>{fmtCurrency(l.lastPrice ?? 0)}</TableCell>
                      <TableCell><StatusChip label={activationLabel[l.activation]} tone={activationTone(l.activation)} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              </Box>
            </Panel>
            <Stack spacing={2} sx={{ minWidth: 0 }}>
              <Panel title="Where this feeds" subtitle="Same fact, four consumers" flush>
                <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
                  <PanelRow severity="neutral" primary="Promotion planner & Case book" secondary="“On shelf” column and the live-case decision list" figure="Promotions & Funding" onClick={() => router.push('/design-lab/funding?lens=planner')} />
                  <PanelRow severity="neutral" primary="Attention (Brief)" secondary="Proposed signal promo_not_activated — derivable today, not yet wired" figure="proposed" />
                  <PanelRow severity="neutral" primary="Dashboards" secondary="Activation rate by customer as a widget metric (read model exists)" figure="Overview" onClick={() => router.push('/design-lab')} />
                  <PanelRow severity="neutral" primary="Claims" secondary="A case whose listing never activated is a settlement risk — evidence, not a rule" figure="Case book" onClick={() => router.push('/design-lab/funding')} />
                </Stack>
              </Panel>
              <CapabilityLedger items={commercialCapabilities.listings.slice(2, 5)} title="Activation jobs" />
            </Stack>
          </Box>
        </Stack>
      ) : null}

      {lens === 'proposals' ? (
        <Stack spacing={2} sx={{ mt: 2 }}>
          <Alert severity="info" variant="outlined">Retailer sell-through feeds carry listing ids (Web ID, PLID). CIP proposes them for the registry; a steward confirms. Same governance boundary as every other master-data proposal — nothing is auto-created.</Alert>
          <Panel title="Proposed listings" subtitle={`${counts.proposals} waiting`} flush>
            <Box sx={{ overflowX: 'auto' }}>
            <Table size="small" sx={{ '& td, & th': { py: 0.7 } }}>
              <TableHead>
                <TableRow>
                  <TableCell>Customer</TableCell>
                  <TableCell>Feed id</TableCell>
                  <TableCell>Suggested URL</TableCell>
                  <TableCell>Product match</TableCell>
                  <TableCell>Source</TableCell>
                  <TableCell align="right">Decision</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {proposals.map((p) => (
                  <TableRow key={p.id} hover sx={{ opacity: p.status === 'proposed' ? 1 : 0.55 }}>
                    <TableCell>{p.customer}</TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>{p.externalId}</TableCell>
                    <TableCell>{p.suggestedUrl ?? <Typography variant="caption" color="warning.main">none — needs URL pattern for {p.marketplace}</Typography>}</TableCell>
                    <TableCell>{p.productMatch ?? <Typography variant="caption" color="warning.main">unresolved token</Typography>}</TableCell>
                    <TableCell><Typography variant="caption" color="text.secondary">{p.source}</Typography></TableCell>
                    <TableCell align="right">
                      {p.status === 'proposed' ? (
                        <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                          <Button size="small" onClick={() => decideProposal(p.id, 'rejected')}>Reject</Button>
                          <Button size="small" variant="contained" disabled={!p.suggestedUrl || !p.productMatch} onClick={() => decideProposal(p.id, 'confirmed')} data-testid={`proposal-confirm-${p.id}`}>Confirm</Button>
                        </Stack>
                      ) : (
                        <StatusChip label={p.status === 'confirmed' ? 'Added' : 'Rejected'} tone={p.status === 'confirmed' ? 'success' : 'neutral'} />
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </Box>
          </Panel>
        </Stack>
      ) : null}

      {lens === 'competition' ? (
        <Stack spacing={2} sx={{ mt: 2 }}>
          <HeadlineStrip columns={4}>
            <HeadlineFigure label="Approved mappings" value={mappings.filter((m) => m.status === 'approved').length} compact caption={`across ${new Set(mappings.filter((m) => m.status === 'approved').map((m) => m.sku)).size} of our SKUs`} />
            <HeadlineFigure label="Pending review" value={counts.pendingMappings} compact severity={counts.pendingMappings ? 'warn' : 'neutral'} caption="System-proposed, need a decision" />
            <HeadlineFigure label="Competitor prices observed" value={0} compact caption="No import yet — nothing inferred from competitors" />
            <HeadlineFigure label="Competitor impact" value="—" compact caption="Not derivable; never shown as a number" />
          </HeadlineStrip>
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'minmax(0, 3fr) minmax(300px, 2fr)' }, alignItems: 'start' }}>
            <Stack spacing={2} sx={{ minWidth: 0 }}>
              <ScopeBar
                chips={[
                  { key: 'pending', label: `Pending · ${counts.pendingMappings}`, active: false, onToggle: () => undefined, tone: 'warning' },
                  { key: 'approved', label: `Approved · ${mappings.filter((m) => m.status === 'approved').length}`, active: false, onToggle: () => undefined, tone: 'success' },
                ]}
                summary={`${mappings.length} mappings · our SKU ↔ competitor SKU`}
                trailing={
                  <Stack direction="row" spacing={1}>
                    <Tooltip title="Data only: the scorer (category, form factor, specs, title tokens, price proximity) exists in code but no endpoint runs it against the catalogue yet." arrow>
                      <span>
                        <Button size="small" variant="outlined" disabled>Propose candidates</Button>
                      </span>
                    </Tooltip>
                    <Button size="small" variant="contained" onClick={() => setToast('Load mappings: CSV of our SKU, competitor brand, competitor SKU/name — rows arrive as pending for review.')}>Load mappings</Button>
                  </Stack>
                }
              />
              <EnterpriseDataGrid<CompetitorMapping> rowData={mappings} columnDefs={mappingCols} height={380} gridOptions={{ onRowClicked: (e: RowClickedEvent<CompetitorMapping>) => e.data && setSelectedMapping(e.data.id), getRowId: (p) => String(p.data.id) }} />
            </Stack>
            <Stack spacing={2}>
              <Panel title="Where this feeds" subtitle="Approved mappings are reusable facts" flush>
                <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
                  <PanelRow severity="neutral" primary="Promotion planner" secondary="“Competitors” column per line: mapped · priced — counts, not inferences" figure="Promotions & Funding" onClick={() => router.push('/design-lab/funding?lens=planner&plan=CPR-26-1204')} />
                  <PanelRow severity="neutral" primary="Planning lineup" secondary="Competing product visible beside each ranked SKU (link only until prices exist)" figure="Planning" onClick={() => router.push('/design-lab/planning')} />
                  <PanelRow severity="neutral" primary="Stock & Sell-through" secondary="Product context panel lists mapped competitors" figure="Stock" onClick={() => router.push('/design-lab/stock?lens=cover&product=61')} />
                  <PanelRow severity="neutral" primary="Reports / dashboards" secondary="Mapping coverage by family — a count the data layer holds" figure="Reports" onClick={() => router.push('/design-lab/reports')} />
                </Stack>
              </Panel>
              <CapabilityLedger items={commercialCapabilities.competition} />
            </Stack>
          </Box>
        </Stack>
      ) : null}

      {lens === 'competitor-prices' ? (
        <Box sx={{ mt: 2 }}>
          <SubstrateOrPlanned
            status="substrate"
            title="Competitor prices — data only"
            body="The table (fact_competitor_price) and its list endpoint exist. There is no import template and no rows, so this lens shows nothing rather than a placeholder chart. When an import lands, observed competitor prices appear per approved mapping and beside our own listing price in the planner — still as observations, never as inferred impact."
            related={[{ label: 'Competitor mappings', href: '/design-lab/market?lens=competition' }, { label: 'Import Center', href: '/design-lab/data?tab=imports' }]}
          />
        </Box>
      ) : null}
      {lens === 'competitor-listings' ? (
        <Box sx={{ mt: 2 }}>
          <SubstrateOrPlanned
            status="planned"
            title="Competitor listings — planned"
            body="Extend the listing registry so a competitor product can be monitored on the same retailer pages as ours (BACKLOG §9.9). The registry, fetcher and history already exist for our products; the delta is a product-dimension that allows competitor SKUs. Shown so you know where it will live; nothing here works yet."
            related={[{ label: 'Monitored listings', href: '/design-lab/market' }]}
          />
        </Box>
      ) : null}
      {lens === 'quality' ? (
        <Box sx={{ mt: 2 }}>
          <SubstrateOrPlanned
            status="planned"
            title="Listing quality / SEO — planned"
            body="Content, specification and search-quality checks on monitored listings (roadmap P5). Raw page snapshots are already retained by the fetcher, so this is an extraction and rules layer, not a new capture. Not built; no figures are shown."
            related={[{ label: 'Monitored listings', href: '/design-lab/market' }]}
          />
        </Box>
      ) : null}

      <EntityContextPanel
        open={!!listing}
        onClose={() => setSelectedListing(null)}
        kicker={listing ? `Listing ${listing.id} · ${listingStatusLabel[listing.status]}` : undefined}
        title={listing ? `${listing.customer} · ${listing.sku ?? 'unlinked'}` : ''}
        subtitle={listing ? listing.product ?? listing.url : undefined}
        width={520}
        figures={
          listing ? (
            <HeadlineStrip columns={3}>
              <HeadlineFigure label="Last price" value={listing.lastPrice === null ? '—' : fmtCurrency(listing.lastPrice)} dense caption={listing.lastFetched} />
              <HeadlineFigure label="Since first seen" value={listing.firstPrice !== null && listing.lastPrice !== null ? (listing.lastPrice === listing.firstPrice ? '0' : `${listing.lastPrice > listing.firstPrice ? '+' : '−'}${fmtCurrency(Math.abs(listing.lastPrice - listing.firstPrice))}`) : '—'} dense caption={`${listing.observations} obs · ${listing.spanDays} d`} />
              <HeadlineFigure label="Promotion" value={listing.caseCode ?? 'none'} dense severity={listing.activation === 'not_activated' ? 'bad' : listing.activation === 'price_consistent' ? 'good' : 'neutral'} caption={activationLabel[listing.activation]} />
            </HeadlineStrip>
          ) : null
        }
        related={
          listing
            ? [
                ...(listing.caseCode ? [{ label: `Open case ${listing.caseCode}`, href: `/design-lab/funding?lens=planner&plan=${listing.caseCode}`, hint: 'Promotions & Funding · same case the planner authored' }] : []),
                ...(listing.productId ? [{ label: 'Stock cover & sell-through', href: `/design-lab/stock?lens=cover&product=${listing.productId}`, hint: 'Stock & Sell-through' }, { label: 'Competitor mappings for this SKU', href: `/design-lab/market?lens=competition&product=${listing.productId}`, hint: 'Market › Competition' }] : [{ label: 'Resolve product token', href: '/design-lab/data?tab=steward', hint: 'Data & Stewardship' }]),
                { label: 'Customer master', href: `/design-lab/data?tab=masters&m=customers&id=${listing.customerId}`, hint: 'Data & Stewardship' },
              ]
            : []
        }
        footer={listing ? (
          <>
            <Button size="small" variant="outlined" onClick={() => setToast('Re-fetch queued — result appears in the activity feed.')}>Fetch now</Button>
            <Button size="small" variant="outlined" onClick={() => setSelectedListing(null)}>Close</Button>
          </>
        ) : null}
      >
        {listing ? (
          <Stack spacing={2.5}>
            {listing.id === 44 ? (
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>Price history</Typography>
                <TrendChart data={listingHistory} x="date" height={160} yScale="fit" format={(v) => fmtCurrency(v)} series={[{ key: 'casePrice', label: 'Case SRP', kind: 'area', tone: 'muted' }, { key: 'price', label: 'Observed', kind: 'line', tone: 'primary' }]} />
              </Box>
            ) : (
              <Typography variant="caption" color="text.secondary">Price history chart for this listing renders from its {listing.observations} observations (fixture only charts listing 44).</Typography>
            )}
            <KeyValueList
              items={[
                { k: 'URL', v: <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>{listing.url}</Typography> },
                { k: 'Marketplace', v: listing.marketplace },
                { k: 'Availability', v: listing.availability.replace('_', ' ') },
                { k: 'Promo badge', v: listing.promoBadge ?? 'none' },
                { k: 'Source', v: sourceLabel[listing.source] },
                { k: 'Observations', v: `${listing.observations} over ${listing.spanDays} days${listing.spanDays < 14 ? ' — below 14-day readiness' : ''}` },
              ]}
            />
            {listing.activation === 'not_activated' ? (
              <Alert severity="error" variant="outlined">
                Case {listing.caseCode} is live at {fmtCurrency(listing.casePrice ?? 0)} but the shelf shows {fmtCurrency(listing.lastPrice ?? 0)}. This is an observation; whether the customer is late or the plan is wrong is a call for the account manager.
              </Alert>
            ) : null}
          </Stack>
        ) : null}
      </EntityContextPanel>

      <EntityContextPanel
        open={!!mapping}
        onClose={() => setSelectedMapping(null)}
        kicker={mapping ? `Mapping ${mapping.id} · ${mapping.status}` : undefined}
        title={mapping ? `${mapping.sku} ↔ ${mapping.competitorSku}` : ''}
        subtitle={mapping ? `${mapping.product} vs ${mapping.competitorName}` : undefined}
        width={480}
        figures={
          mapping ? (
            <HeadlineStrip columns={3}>
              <HeadlineFigure label="Match score" value={mapping.score.toFixed(2)} dense severity={mapping.score >= 0.8 ? 'good' : mapping.score >= 0.6 ? 'neutral' : 'warn'} caption="deterministic scorer" />
              <HeadlineFigure label="Competitor prices" value={mapping.priceObservations || 'none'} dense caption="observed" />
              <HeadlineFigure label="Competitor listing" value={mapping.listingMonitored ? 'yes' : 'no'} dense caption="monitoring planned" />
            </HeadlineStrip>
          ) : null
        }
        related={mapping ? [{ label: 'Our product — stock & sell-through', href: `/design-lab/stock?lens=cover&product=${mapping.productId}`, hint: 'Stock & Sell-through' }, { label: 'Our listings for this SKU', href: `/design-lab/market?product=${mapping.productId}`, hint: 'Market & Listings' }, { label: 'Plans containing this SKU', href: '/design-lab/funding?lens=planner', hint: 'Promotions & Funding' }] : []}
        footer={
          mapping && mapping.status === 'pending' ? (
            <>
              <Button size="small" variant="outlined" color="error" onClick={() => decideMapping(mapping.id, 'rejected')}>Reject</Button>
              <Button size="small" variant="contained" onClick={() => decideMapping(mapping.id, 'approved')} data-testid="mapping-approve">Approve mapping</Button>
            </>
          ) : mapping ? (
            <Button size="small" variant="outlined" onClick={() => setSelectedMapping(null)}>Close</Button>
          ) : null
        }
      >
        {mapping ? (
          <Stack spacing={2.5}>
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>Why this score</Typography>
              <Stack spacing={0.75} sx={{ mt: 1 }}>
                {(Object.keys(mapping.factors) as (keyof CompetitorMapping['factors'])[]).map((k) => (
                  <Stack key={k} direction="row" spacing={1} alignItems="center">
                    <Typography variant="body2" sx={{ width: 120, textTransform: 'capitalize' }}>{k === 'form' ? 'Form factor' : k === 'title' ? 'Title tokens' : k === 'price' ? 'Price proximity' : k}</Typography>
                    <LinearProgress variant="determinate" value={mapping.factors[k] * 100} sx={{ flex: 1, height: 6, borderRadius: 3 }} />
                    <Typography variant="caption" sx={{ width: 36, fontVariantNumeric: 'tabular-nums' }}>{mapping.factors[k].toFixed(2)}</Typography>
                    <Typography variant="caption" color="text.disabled" sx={{ width: 40 }}>× {scorerWeights[k]}</Typography>
                  </Stack>
                ))}
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>{mapping.explanation}</Typography>
            </Box>
            <KeyValueList items={[{ k: 'Origin', v: mapping.origin }, { k: 'Competitor brand', v: mapping.competitorBrand }, { k: 'Competitor SKU', v: mapping.competitorSku }]} />
            <Alert severity="info" variant="outlined">
              A mapping says “these compete”. It does not say how much — CIP holds no competitor price or share data yet and shows no impact.
            </Alert>
          </Stack>
        ) : null}
      </EntityContextPanel>

      <Snackbar open={!!toast} autoHideDuration={4000} onClose={() => setToast(null)} message={toast} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Box>
  );
}

function SubstrateOrPlanned({ status, title, body, related }: { status: 'substrate' | 'planned'; title: string; body: string; related: { label: string; href: string }[] }) {
  return (
    <Box data-testid={`lens-${status}`}>
      <Panel
        title={
          <Stack direction="row" spacing={1} alignItems="center">
            <span>{title}</span>
            <CapabilityStatus status={status} />
          </Stack>
        }
      >
        <Stack spacing={1.5} sx={{ maxWidth: 760 }}>
          <Typography variant="body2" color="text.secondary">{body}</Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {related.map((r) => (
              <Chip key={r.href} component="a" href={r.href} clickable size="small" label={r.label} variant="outlined" />
            ))}
          </Stack>
        </Stack>
      </Panel>
    </Box>
  );
}
