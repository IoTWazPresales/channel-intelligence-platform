'use client';

import type { ColDef, RowClickedEvent } from 'ag-grid-community';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useMemo, useRef, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { COMPETITION_CAPABILITIES, LISTING_CAPABILITIES } from '@/features/market-listings/capabilities';
import { MarketChrome, marketLensFromLocation, type MarketLens } from '@/features/market-listings/MarketChrome';
import { SubstrateOrPlanned } from '@/features/market-listings/SubstrateOrPlanned';
import { fmtMoney } from '@/features/promotions-funding/format';
import { apiGet, apiPost, apiPostFormData } from '@/lib/api';
import { CapabilityLedger } from '@/features/workbench-ui/CapabilityLedger';
import { TrendChart } from '@/features/workbench-ui/charts';
import { ScopeBar, StatusChip } from '@/features/workbench-ui/controls';
import { EntityContextPanel, KeyValueList } from '@/features/workbench-ui/EntityContextPanel';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';

type Listing = {
  id: number;
  customer_id: number;
  product_id: number | null;
  product_sku?: string | null;
  product_name?: string | null;
  url: string;
  marketplace: string;
  status: string;
  source: string;
  external_id: string | null;
};

type Proposal = {
  id: number;
  customer_id: number;
  marketplace: string;
  external_id: string;
  product_id: number | null;
  product_sku?: string | null;
  product_name?: string | null;
  status: string;
  suggested_url?: string | null;
};

type IntelligenceRow = {
  listing_id: number;
  customer_id: number;
  product_id: number | null;
  marketplace: string;
  url: string;
  observation_count: number;
  span_days: number | null;
  history_status: string;
  first_price: number | null;
  last_price: number | null;
  price_drift_pct: number | null;
  activation_status: string | null;
  activation_message?: string | null;
  case_price?: number | null;
  case_id?: number | null;
  last_availability?: string | null;
  last_promo_badge?: string | null;
  last_fetched?: string | null;
  worklist: boolean;
};

type Observation = {
  id: number;
  listing_id: number;
  fetched_at: string | null;
  extracted_price: number | null;
  extracted_availability: string | null;
  cpor_activation_status: string | null;
  cpor_case_price: number | null;
};

type MapRow = {
  id: number;
  product_id?: number | null;
  internal_sku: string | null;
  product_name?: string | null;
  competitor_sku: string | null;
  competitor_name?: string | null;
  competitor_brand?: string | null;
  score: number;
  explanation: string;
  approval_status: string;
};

type PriceRow = {
  id: number;
  competitor_sku: string | null;
  observed_at: string;
  price: number;
  channel: string | null;
};

type CustomerList = { items?: { id: number; customer_code: string; customer_name: string }[] };
type CustomerPick = { id: number; customer_code: string; customer_name: string };
type ProductPick = { id: number; sku: string; name: string };

const ACTIVATION_LABEL: Record<string, string> = {
  not_activated: 'Not at promo price',
  price_consistent: 'Promo live at price',
  no_case_detected: 'No promotion covering today',
  no_listing: 'No product link',
  not_started: 'Window not started',
};

const LISTING_STATUS_LABEL: Record<string, string> = {
  active: 'Active',
  out_of_stock: 'Out of stock',
  delisted: 'Delisted',
  dead_link: 'Dead link',
};

const SOURCE_LABEL: Record<string, string> = {
  manual: 'Manual',
  csv: 'CSV',
  csv_import: 'CSV',
  feed_proposal: 'Feed proposal',
  auto_finder: 'Auto-finder',
};

function listingTone(s: string): 'success' | 'warning' | 'danger' | 'neutral' {
  if (s === 'active') return 'success';
  if (s === 'out_of_stock') return 'warning';
  if (s === 'dead_link') return 'danger';
  return 'neutral';
}

function activationTone(a: string | null): 'success' | 'danger' | 'warning' | 'neutral' {
  if (a === 'price_consistent') return 'success';
  if (a === 'not_activated') return 'danger';
  if (a === 'no_listing') return 'warning';
  return 'neutral';
}

type GridRow = Listing & {
  intel?: IntelligenceRow;
  customer_name?: string;
};

export function MarketSurface() {
  const pathname = usePathname() || '/listing-capture';
  const search = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const lens = marketLensFromLocation(pathname, search);
  const customerFilter = search.get('customer');
  const productFilter = search.get('product');
  const activationFilter = search.get('activation');
  const listingParam = search.get('listing');
  const [selectedListing, setSelectedListing] = useState<number | null>(
    listingParam && /^\d+$/.test(listingParam) ? Number(listingParam) : null,
  );
  const [selectedMapping, setSelectedMapping] = useState<number | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [customerId, setCustomerId] = useState('1');
  const [url, setUrl] = useState('');
  const [marketplace, setMarketplace] = useState('takealot');
  const [productId, setProductId] = useState('');
  const [confirmUrl, setConfirmUrl] = useState('');
  const [confirmSeed, setConfirmSeed] = useState<Proposal | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const setParams = useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(search.toString());
      Object.entries(patch).forEach(([k, v]) => (v == null || v === '' ? next.delete(k) : next.set(k, v)));
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router, search],
  );

  const { data: listingsPage } = useQuery({
    queryKey: ['listing-capture', 'listings'],
    queryFn: ({ signal }) =>
      apiGet<{ items: Listing[]; total: number; data_unavailable?: boolean }>(
        '/api/v1/listing-capture/listings?page_size=200',
        { signal },
      ),
  });
  const { data: intel } = useQuery({
    queryKey: ['listing-capture', 'intelligence'],
    queryFn: ({ signal }) =>
      apiGet<{ items: IntelligenceRow[]; listings?: number; data_unavailable?: boolean }>(
        '/api/v1/listing-capture/intelligence',
        { signal },
      ),
  });
  const { data: proposals } = useQuery({
    queryKey: ['listing-capture', 'proposals'],
    queryFn: ({ signal }) => apiGet<{ items: Proposal[] }>('/api/v1/listing-capture/proposals', { signal }),
  });
  const { data: observations } = useQuery({
    queryKey: ['listing-capture', 'observations'],
    queryFn: ({ signal }) =>
      apiGet<{ items: Observation[]; data_unavailable?: boolean }>(
        '/api/v1/listing-capture/observations?limit=200',
        { signal },
      ),
  });
  const { data: customersPage } = useQuery({
    queryKey: ['customers', 'market-names'],
    queryFn: ({ signal }) => apiGet<CustomerList>('/api/v1/customers?page=1&page_size=200', { signal }),
    staleTime: 60_000,
  });
  const { data: customerHydrate } = useQuery({
    queryKey: ['customers', 'hydrate', customerFilter],
    queryFn: ({ signal }) =>
      apiGet<CustomerList>(`/api/v1/customers?page=1&page_size=1&customer_id=${customerFilter}`, { signal }),
    enabled: Boolean(customerFilter),
  });
  const { data: productHydrate } = useQuery({
    queryKey: ['products', 'hydrate', productFilter],
    queryFn: ({ signal }) =>
      apiGet<{ items?: ProductPick[] }>(
        `/api/v1/products?page=1&page_size=1&product_id=${productFilter}`,
        { signal },
      ),
    enabled: Boolean(productFilter),
  });
  const { data: mappings } = useQuery({
    queryKey: ['competition-mappings'],
    queryFn: ({ signal }) => apiGet<MapRow[]>('/api/v1/competition/mappings', { signal }),
  });
  const { data: prices } = useQuery({
    queryKey: ['competition-prices'],
    queryFn: ({ signal }) => apiGet<PriceRow[]>('/api/v1/competition/prices', { signal }),
    enabled: lens === 'competitor-prices' || lens === 'competition',
  });

  const listings = listingsPage?.items ?? [];
  const intelById = useMemo(() => {
    const m = new Map<number, IntelligenceRow>();
    for (const row of intel?.items ?? []) m.set(row.listing_id, row);
    return m;
  }, [intel]);
  const customerName = useMemo(() => {
    const m = new Map<number, string>();
    for (const c of customersPage?.items ?? []) m.set(c.id, c.customer_name || c.customer_code);
    return m;
  }, [customersPage]);
  const customerPick = useMemo<CustomerPick | null>(() => {
    if (!customerFilter) return null;
    const id = Number(customerFilter);
    if (!Number.isFinite(id)) return null;
    return (
      customerHydrate?.items?.[0] ??
      customersPage?.items?.find((c) => c.id === id) ?? {
        id,
        customer_code: String(id),
        customer_name: '',
      }
    );
  }, [customerFilter, customerHydrate, customersPage]);
  const productPick = useMemo<ProductPick | null>(() => {
    if (!productFilter) return null;
    const id = Number(productFilter);
    if (!Number.isFinite(id)) return null;
    return (
      productHydrate?.items?.[0] ?? {
        id,
        sku: String(id),
        name: '',
      }
    );
  }, [productFilter, productHydrate]);

  const gridRows: GridRow[] = useMemo(
    () =>
      listings.map((l) => ({
        ...l,
        intel: intelById.get(l.id),
        customer_name: customerName.get(l.customer_id),
      })),
    [listings, intelById, customerName],
  );

  const scoped = useMemo(() => {
    return gridRows.filter((l) => {
      if (customerFilter && String(l.customer_id) !== customerFilter) return false;
      if (productFilter && String(l.product_id ?? '') !== productFilter) return false;
      if (activationFilter && (l.intel?.activation_status ?? '') !== activationFilter) return false;
      return true;
    });
  }, [gridRows, customerFilter, productFilter, activationFilter]);

  const counts = {
    active: listings.filter((l) => l.status === 'active').length,
    problems: listings.filter((l) => l.status === 'dead_link' || l.status === 'out_of_stock').length,
    unlinked: listings.filter((l) => !l.product_id).length,
    notActivated: (intel?.items ?? []).filter((r) => r.activation_status === 'not_activated').length,
    live: (intel?.items ?? []).filter((r) => r.activation_status === 'price_consistent').length,
    drifted: (intel?.items ?? []).filter(
      (r) => r.first_price != null && r.last_price != null && r.first_price !== r.last_price,
    ).length,
    proposals: (proposals?.items ?? []).filter((p) => p.status === 'proposed' || !p.status || p.status === 'pending')
      .length,
    pendingMappings: (mappings ?? []).filter((m) => m.approval_status === 'pending').length,
    approvedMappings: (mappings ?? []).filter((m) => m.approval_status === 'approved').length,
  };

  const selected = gridRows.find((l) => l.id === selectedListing) ?? null;
  const selectedObs = useMemo(() => {
    const id = selected?.id;
    if (!id) return [];
    return (observations?.items ?? [])
      .filter((o) => o.listing_id === id)
      .slice()
      .reverse();
  }, [observations, selected]);

  const chartListing =
    selected ??
    gridRows.find((l) => (l.intel?.observation_count ?? 0) > 1) ??
    gridRows[0] ??
    null;
  const chartObs = useMemo(() => {
    const id = chartListing?.id;
    if (!id) return [];
    return (observations?.items ?? [])
      .filter((o) => o.listing_id === id && o.extracted_price != null)
      .slice()
      .reverse()
      .map((o) => ({
        date: (o.fetched_at || '').slice(0, 10),
        price: o.extracted_price,
        casePrice: o.cpor_case_price,
      }));
  }, [observations, chartListing]);

  const createMut = useMutation({
    mutationFn: () =>
      apiPost('/api/v1/listing-capture/listings', {
        customer_id: Number(customerId),
        url: url.trim(),
        marketplace,
        product_id: productId.trim() ? Number(productId) : null,
      }),
    onSuccess: async () => {
      setAddOpen(false);
      setUrl('');
      await qc.invalidateQueries({ queryKey: ['listing-capture'] });
    },
  });
  const importMut = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      return apiPostFormData<{ created: number; row_flags?: unknown[] }>(
        '/api/v1/listing-capture/listings/import-csv',
        fd,
      );
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['listing-capture'] }),
  });
  const pollMut = useMutation({
    mutationFn: () => apiPost('/api/v1/listing-capture/poll', {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['listing-capture'] }),
  });
  const confirmMut = useMutation({
    mutationFn: () =>
      apiPost(`/api/v1/listing-capture/proposals/${confirmSeed!.id}/confirm`, { url: confirmUrl }),
    onSuccess: async () => {
      setConfirmSeed(null);
      await qc.invalidateQueries({ queryKey: ['listing-capture'] });
    },
  });
  const rejectProposal = useMutation({
    mutationFn: (id: number) => apiPost(`/api/v1/listing-capture/proposals/${id}/reject`, {}),
    onSuccess: () => {
      setToast('Proposal rejected — the feed id is remembered so it is not re-proposed.');
      void qc.invalidateQueries({ queryKey: ['listing-capture'] });
    },
  });
  const approve = useMutation({
    mutationFn: (id: number) => apiPost(`/api/v1/competition/mappings/${id}/approve`, {}),
    onSuccess: () => {
      setToast('Mapping approved — now reusable by the planner, dashboards and reports.');
      setSelectedMapping(null);
      void qc.invalidateQueries({ queryKey: ['competition-mappings'] });
    },
  });
  const rejectMap = useMutation({
    mutationFn: (id: number) => apiPost(`/api/v1/competition/mappings/${id}/reject`, {}),
    onSuccess: () => {
      setToast('Mapping rejected — kept for audit, hidden from consumers.');
      setSelectedMapping(null);
      void qc.invalidateQueries({ queryKey: ['competition-mappings'] });
    },
  });

  const listingCols = useMemo<ColDef<GridRow>[]>(
    () => [
      {
        field: 'customer_name',
        headerName: 'Customer',
        minWidth: 150,
        flex: 1,
        pinned: 'left',
        valueGetter: (p) => p.data?.customer_name ?? p.data?.customer_id,
      },
      {
        headerName: 'Product',
        minWidth: 220,
        flex: 1.5,
        valueGetter: (p) => p.data?.product_sku ?? p.data?.url,
        cellRenderer: (p: { data?: GridRow }) => (
          <Box sx={{ lineHeight: 1.2 }}>
            <Typography variant="body2" noWrap color={p.data?.product_id ? 'text.primary' : 'warning.main'}>
              {p.data?.product_name ??
                (p.data?.product_id ? `product ${p.data.product_id}` : 'No product link — resolve in Data & Stewardship')}
            </Typography>
            <Typography variant="caption" color="text.secondary" noWrap>
              {p.data?.product_sku ?? p.data?.url}
            </Typography>
          </Box>
        ),
      },
      {
        field: 'status',
        headerName: 'Listing',
        width: 130,
        cellRenderer: (p: { data?: GridRow }) =>
          p.data ? (
            <StatusChip label={LISTING_STATUS_LABEL[p.data.status] ?? p.data.status} tone={listingTone(p.data.status)} />
          ) : null,
      },
      {
        headerName: 'Last price',
        type: 'rightAligned',
        width: 115,
        valueGetter: (p) => p.data?.intel?.last_price ?? null,
        valueFormatter: (p) => (p.value == null ? '—' : fmtMoney(Number(p.value))),
      },
      {
        headerName: 'Δ since first',
        type: 'rightAligned',
        width: 115,
        valueGetter: (p) => {
          const a = p.data?.intel?.first_price;
          const b = p.data?.intel?.last_price;
          return a != null && b != null ? b - a : null;
        },
        valueFormatter: (p) =>
          p.value == null ? '—' : Number(p.value) === 0 ? '0' : `${Number(p.value) > 0 ? '+' : '−'}${fmtMoney(Math.abs(Number(p.value)))}`,
      },
      {
        headerName: 'Availability',
        width: 120,
        valueGetter: (p) => p.data?.intel?.last_availability,
        valueFormatter: (p) => (p.value ? String(p.value).replaceAll('_', ' ') : '—'),
      },
      {
        headerName: 'Badge',
        width: 110,
        valueGetter: (p) => p.data?.intel?.last_promo_badge ?? '',
      },
      {
        headerName: 'Promotion on shelf',
        width: 220,
        valueGetter: (p) => p.data?.intel?.activation_status,
        cellRenderer: (p: { data?: GridRow }) => {
          const a = p.data?.intel?.activation_status;
          return a ? <StatusChip label={ACTIVATION_LABEL[a] ?? a} tone={activationTone(a)} /> : '—';
        },
      },
      {
        headerName: 'Obs.',
        type: 'rightAligned',
        width: 80,
        valueGetter: (p) => p.data?.intel?.observation_count ?? 0,
      },
      {
        headerName: 'Span',
        type: 'rightAligned',
        width: 85,
        valueGetter: (p) => p.data?.intel?.span_days,
        valueFormatter: (p) => (p.value == null ? '—' : `${p.value} d`),
      },
      { field: 'source', headerName: 'Source', width: 130 },
      { field: 'marketplace', headerName: 'Marketplace', width: 120 },
    ],
    [],
  );

  const mappingCols = useMemo<ColDef<MapRow>[]>(
    () => [
      { field: 'internal_sku', headerName: 'Our product', minWidth: 160, flex: 1, pinned: 'left' },
      { field: 'competitor_sku', headerName: 'Competing product', minWidth: 180, flex: 1.2 },
      {
        field: 'score',
        headerName: 'Match score',
        width: 150,
        cellRenderer: (p: { data?: MapRow }) =>
          p.data ? (
            <Stack direction="row" spacing={1} alignItems="center" sx={{ width: '100%' }}>
              <LinearProgress
                variant="determinate"
                value={Math.max(0, Math.min(1, p.data.score)) * 100}
                sx={{ flex: 1, height: 6, borderRadius: 3 }}
                color={p.data.score >= 0.8 ? 'success' : p.data.score >= 0.6 ? 'primary' : 'warning'}
              />
              <Typography variant="caption" sx={{ fontVariantNumeric: 'tabular-nums', width: 36 }}>
                {Number(p.data.score).toFixed(3)}
              </Typography>
            </Stack>
          ) : null,
      },
      { field: 'approval_status', headerName: 'Approval', width: 120 },
      { field: 'explanation', headerName: 'Why (stored)', flex: 1.4, minWidth: 240 },
    ],
    [],
  );

  const mapping = (mappings ?? []).find((m) => m.id === selectedMapping) ?? null;
  const obsCount = listings.reduce((n, l) => n + (intelById.get(l.id)?.observation_count ?? 0), 0);

  const lensCounts: Partial<Record<MarketLens, number>> = {
    listings: listings.length,
    proposals: counts.proposals,
    competition: counts.pendingMappings || undefined,
    activation: counts.notActivated || undefined,
  };

  return (
    <Box data-testid="market-surface">
      <MarketChrome
        counts={lensCounts}
        meta={`${listings.length} monitored listings · ${obsCount} observations`}
        actions={
          <>
            <Button variant="outlined" size="small" href="/reports">
              Open in Reports
            </Button>
            <Button variant="outlined" size="small" onClick={() => fileRef.current?.click()}>
              Import CSV
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept=".csv"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = '';
                if (f) importMut.mutate(f);
              }}
            />
            <Button variant="contained" size="small" onClick={() => setAddOpen(true)} data-testid="market-add-listing">
              Add listing
            </Button>
          </>
        }
      >
        {lens === 'listings' || lens === 'history' ? (
          <Stack spacing={2} sx={{ mt: 2 }} data-testid="market-listings-lens">
            <HeadlineStrip columns={5}>
              <HeadlineFigure
                label="Active listings"
                value={counts.active}
                unit={`of ${listings.length}`}
                compact
                caption={`${counts.problems} out of stock or dead`}
                severity={counts.problems ? 'warn' : 'good'}
              />
              <HeadlineFigure
                label="Promo live at price"
                value={counts.live}
                compact
                severity="good"
                caption="Observed price = case SRP in window"
                onClick={() => setParams({ activation: 'price_consistent' })}
              />
              <HeadlineFigure
                label="Promo not at price"
                value={counts.notActivated}
                compact
                severity={counts.notActivated ? 'bad' : 'neutral'}
                caption="Live case, shelf price differs"
                onClick={() => setParams({ activation: 'not_activated' })}
              />
              <HeadlineFigure
                label="Price moved since first seen"
                value={counts.drifted}
                compact
                caption="first ≠ last observation"
              />
              <HeadlineFigure
                label="Unlinked listings"
                value={counts.unlinked}
                compact
                severity={counts.unlinked ? 'warn' : 'neutral'}
                caption="No product — resolve token"
              />
            </HeadlineStrip>

            <Box
              sx={{
                display: 'grid',
                gap: 2,
                gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'minmax(0, 3fr) minmax(300px, 2fr)' },
                alignItems: 'start',
              }}
            >
              <Panel
                title={
                  chartListing
                    ? `Observed price — ${chartListing.customer_name ?? chartListing.customer_id} · listing ${chartListing.id}`
                    : 'Observed price'
                }
                subtitle="Daily observations. Case SRP overlays when the observation carries a covering case. Observed only — no impact computed."
                actions={
                  chartListing ? (
                    <Button size="small" onClick={() => setSelectedListing(chartListing.id)}>
                      Open listing
                    </Button>
                  ) : undefined
                }
              >
                {chartObs.length >= 2 ? (
                  <TrendChart
                    data={chartObs}
                    x="date"
                    height={220}
                    yScale="fit"
                    format={(v) => fmtMoney(v)}
                    series={[
                      { key: 'casePrice', label: 'Case SRP (window)', kind: 'area', tone: 'muted' },
                      { key: 'price', label: 'Observed price', kind: 'line', tone: 'primary' },
                    ]}
                  />
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    Not enough priced observations yet to draw a history. Poll listings, then this chart fills from
                    stored observations — the observations grid is this same lens, not a separate operational page.
                  </Typography>
                )}
                <Box sx={{ mt: 2, borderTop: '1px solid', borderColor: 'divider', pt: 1.5 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                    Price moved since first seen
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    first observation → latest, per listing. A stored comparison; no cause is inferred.
                  </Typography>
                  <Box sx={{ overflowX: 'auto', mt: 1 }}>
                    <Table size="small" sx={{ '& td, & th': { py: 0.5, whiteSpace: 'nowrap' } }}>
                      <TableHead>
                        <TableRow>
                          <TableCell>Listing</TableCell>
                          <TableCell align="right">First</TableCell>
                          <TableCell align="right">Latest</TableCell>
                          <TableCell align="right">Δ</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {gridRows
                          .filter(
                            (l) =>
                              l.intel?.first_price != null &&
                              l.intel?.last_price != null &&
                              l.intel.first_price !== l.intel.last_price,
                          )
                          .map((l) => {
                            const d = (l.intel!.last_price ?? 0) - (l.intel!.first_price ?? 0);
                            return (
                              <TableRow
                                key={l.id}
                                hover
                                sx={{ cursor: 'pointer' }}
                                onClick={() => setSelectedListing(l.id)}
                              >
                                <TableCell>
                                  <Typography variant="body2">
                                    {l.customer_name ?? l.customer_id} · {l.id}
                                  </Typography>
                                  <Typography variant="caption" color="text.secondary">
                                    {l.intel?.observation_count ?? 0} obs · {l.intel?.span_days ?? 0} d
                                  </Typography>
                                </TableCell>
                                <TableCell align="right">{fmtMoney(l.intel!.first_price)}</TableCell>
                                <TableCell align="right">{fmtMoney(l.intel!.last_price)}</TableCell>
                                <TableCell
                                  align="right"
                                  sx={{ color: d < 0 ? 'success.main' : 'warning.main', fontWeight: 600 }}
                                >
                                  {d < 0 ? '−' : '+'}
                                  {fmtMoney(Math.abs(d))}
                                </TableCell>
                              </TableRow>
                            );
                          })}
                      </TableBody>
                    </Table>
                  </Box>
                </Box>
              </Panel>
              <Stack spacing={2} sx={{ minWidth: 0 }}>
                <Panel title="Attention candidates" subtitle="Derived from stored observations; not yet a Brief signal (proposed)" flush>
                  <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
                    {gridRows
                      .filter((l) => l.intel?.activation_status === 'not_activated')
                      .map((l) => (
                        <PanelRow
                          key={l.id}
                          severity="danger"
                          primary={`${l.customer_name ?? l.customer_id} · listing ${l.id} not at promo price`}
                          secondary={`observed ${fmtMoney(l.intel?.last_price)} vs case ${fmtMoney(l.intel?.case_price)}`}
                          onClick={() => setSelectedListing(l.id)}
                        />
                      ))}
                    {listings
                      .filter((l) => l.status === 'dead_link')
                      .map((l) => (
                        <PanelRow
                          key={l.id}
                          severity="warning"
                          primary={`${customerName.get(l.customer_id) ?? l.customer_id} · listing ${l.id} dead link`}
                          secondary="re-find or retire"
                          onClick={() => setSelectedListing(l.id)}
                        />
                      ))}
                    {listings
                      .filter((l) => !l.product_id)
                      .map((l) => (
                        <PanelRow
                          key={`u-${l.id}`}
                          severity="warning"
                          primary={`${customerName.get(l.customer_id) ?? l.customer_id} · listing without product`}
                          secondary={l.url}
                          figure="Resolve"
                          onClick={() => router.push('/admin/imports')}
                        />
                      ))}
                    <PanelRow
                      severity="info"
                      primary={`${counts.proposals} feed proposals waiting`}
                      secondary="Listing ids seen in CST sell-through feeds"
                      onClick={() => router.push('/listing-capture?tab=proposals')}
                    />
                  </Stack>
                </Panel>
                <CapabilityLedger items={LISTING_CAPABILITIES} />
              </Stack>
            </Box>

            <ScopeBar
              chips={[
                {
                  key: 'not_activated',
                  label: `Not at promo price · ${counts.notActivated}`,
                  active: activationFilter === 'not_activated',
                  onToggle: () =>
                    setParams({ activation: activationFilter === 'not_activated' ? null : 'not_activated' }),
                  tone: 'danger',
                },
                {
                  key: 'price_consistent',
                  label: `Promo live · ${counts.live}`,
                  active: activationFilter === 'price_consistent',
                  onToggle: () =>
                    setParams({
                      activation: activationFilter === 'price_consistent' ? null : 'price_consistent',
                    }),
                  tone: 'success',
                },
                {
                  key: 'no_case_detected',
                  label: 'No promotion covering',
                  active: activationFilter === 'no_case_detected',
                  onToggle: () =>
                    setParams({
                      activation: activationFilter === 'no_case_detected' ? null : 'no_case_detected',
                    }),
                },
              ]}
              summary={`${scoped.length} of ${listings.length} listings${customerFilter ? ' · customer scoped' : ''}${productFilter ? ' · product scoped' : ''}`}
              onClear={() => setParams({ activation: null, customer: null, product: null })}
              clearAvailable={Boolean(activationFilter || customerFilter || productFilter)}
              filters={
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ minWidth: 280 }}>
                  <EntitySearchAutocomplete<CustomerPick>
                    label="Customer"
                    value={null}
                    onChange={(v) => setParams({ customer: v ? String(v.id) : null })}
                    fetchOptions={async (q, signal) => {
                      const page = await apiGet<CustomerList>(
                        `/api/v1/customers?page=1&page_size=25${q ? `&q=${encodeURIComponent(q)}` : ''}`,
                        { signal },
                      );
                      return page.items ?? [];
                    }}
                    getOptionLabel={(o) => o.customer_name || o.customer_code}
                  />
                  <EntitySearchAutocomplete<ProductPick>
                    label="Product"
                    value={null}
                    onChange={(v) => setParams({ product: v ? String(v.id) : null })}
                    fetchOptions={async (q, signal) => {
                      const page = await apiGet<{ items?: ProductPick[] }>(
                        `/api/v1/products?page=1&page_size=25${q ? `&q=${encodeURIComponent(q)}` : ''}`,
                        { signal },
                      );
                      return page.items ?? [];
                    }}
                    getOptionLabel={(o) => `${o.sku} ${o.name}`.trim()}
                  />
                </Stack>
              }
              trailing={
                <Button size="small" variant="outlined" disabled={pollMut.isPending} onClick={() => pollMut.mutate()}>
                  Fetch now
                </Button>
              }
            />
            <ModuleDataSection
              isEmpty={scoped.length === 0}
              empty={{
                title: 'No listings in this scope',
                description: 'Clear the scope or add a listing for this customer / product.',
                primary: {
                  label: 'Clear scope',
                  onClick: () => setParams({ activation: null, customer: null, product: null }),
                },
              }}
            >
              <EnterpriseDataGrid<GridRow>
                rowData={scoped}
                columnDefs={listingCols}
                height={380}
                gridOptions={{
                  onRowClicked: (e: RowClickedEvent<GridRow>) => e.data && setSelectedListing(e.data.id),
                  getRowId: (p) => String(p.data.id),
                }}
              />
            </ModuleDataSection>
          </Stack>
        ) : null}

        {lens === 'activation' ? (
          <Stack spacing={2} sx={{ mt: 2 }} data-testid="market-activation-lens">
            <Alert severity="info" variant="outlined">
              Each observation inside a live case window is compared with that case line’s SRP. Three outcomes only:{' '}
              <b>live at price</b>, <b>not at promo price</b>, <b>no promotion covering</b>. Late activation and early
              deactivation are derivable from the same timeline but are not computed yet (data only).
            </Alert>
            <Box
              sx={{
                display: 'grid',
                gap: 2,
                gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'minmax(0, 3fr) minmax(0, 2fr)' },
                alignItems: 'start',
              }}
            >
              <Panel title="Live cases on the shelf" subtitle="Same status the planner and the Case book show" flush>
                <Box sx={{ overflowX: 'auto' }}>
                  <Table size="small" sx={{ '& td, & th': { py: 0.7 } }}>
                    <TableHead>
                      <TableRow>
                        <TableCell>Listing</TableCell>
                        <TableCell align="right">Case SRP</TableCell>
                        <TableCell align="right">Observed</TableCell>
                        <TableCell>Status</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {gridRows
                        .filter((l) => l.intel?.activation_status)
                        .map((l) => (
                          <TableRow
                            key={l.id}
                            hover
                            sx={{ cursor: 'pointer' }}
                            onClick={() => setSelectedListing(l.id)}
                          >
                            <TableCell>
                              <Typography variant="body2">listing {l.id}</Typography>
                              <Typography variant="caption" color="text.secondary">
                                {l.customer_name ?? l.customer_id} · {l.marketplace}
                              </Typography>
                            </TableCell>
                            <TableCell align="right">{fmtMoney(l.intel?.case_price)}</TableCell>
                            <TableCell
                              align="right"
                              sx={{
                                fontWeight: 600,
                                color: l.intel?.activation_status === 'not_activated' ? 'error.main' : 'success.main',
                              }}
                            >
                              {fmtMoney(l.intel?.last_price)}
                            </TableCell>
                            <TableCell>
                              <StatusChip
                                label={ACTIVATION_LABEL[l.intel?.activation_status ?? ''] ?? l.intel?.activation_status ?? '—'}
                                tone={activationTone(l.intel?.activation_status ?? null)}
                              />
                            </TableCell>
                          </TableRow>
                        ))}
                    </TableBody>
                  </Table>
                </Box>
              </Panel>
              <Stack spacing={2}>
                <Panel title="Where this feeds" subtitle="Same fact, four consumers" flush>
                  <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
                    <PanelRow
                      severity="neutral"
                      primary="Promotion planner & Case book"
                      secondary="On-shelf column and the live-case decision list"
                      figure="Promotions & Funding"
                      onClick={() => router.push('/promotions')}
                    />
                    <PanelRow
                      severity="neutral"
                      primary="Attention (Brief)"
                      secondary="Proposed signal promo_not_activated — derivable today, not yet wired"
                      figure="proposed"
                    />
                    <PanelRow
                      severity="neutral"
                      primary="Dashboards"
                      secondary="Activation rate by customer as a widget metric"
                      figure="Overview"
                      onClick={() => router.push('/brief')}
                    />
                    <PanelRow
                      severity="neutral"
                      primary="Claims"
                      secondary="A case whose listing never activated is a settlement risk — evidence, not a rule"
                      figure="Case book"
                      onClick={() => router.push('/commercial-planner/cpor-cases')}
                    />
                  </Stack>
                </Panel>
                <CapabilityLedger items={LISTING_CAPABILITIES.slice(2, 5)} title="Activation jobs" />
              </Stack>
            </Box>
          </Stack>
        ) : null}

        {lens === 'proposals' ? (
          <Stack spacing={2} sx={{ mt: 2 }} data-testid="market-proposals-lens">
            <Alert severity="info" variant="outlined">
              Retailer sell-through feeds carry listing ids. CIP proposes them for the registry; a steward confirms.
              Same governance boundary as every other master-data proposal — nothing is auto-created.
            </Alert>
            <Panel title="Proposed listings" subtitle={`${counts.proposals} waiting`} flush>
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small" sx={{ '& td, & th': { py: 0.7 } }}>
                  <TableHead>
                    <TableRow>
                      <TableCell>Customer</TableCell>
                      <TableCell>Feed id</TableCell>
                      <TableCell>Suggested URL</TableCell>
                      <TableCell>Product</TableCell>
                      <TableCell align="right">Decision</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(proposals?.items ?? []).map((p) => (
                      <TableRow key={p.id} hover>
                        <TableCell>{customerName.get(p.customer_id) ?? p.customer_id}</TableCell>
                        <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>{p.external_id}</TableCell>
                        <TableCell>
                          {p.suggested_url ?? (
                            <Typography variant="caption" color="warning.main">
                              none — paste a URL
                            </Typography>
                          )}
                        </TableCell>
                        <TableCell>
                          {p.product_id ?? (
                            <Typography variant="caption" color="warning.main">
                              unresolved token
                            </Typography>
                          )}
                        </TableCell>
                        <TableCell align="right">
                          <Button
                            size="small"
                            variant="contained"
                            onClick={() => {
                              setConfirmSeed(p);
                              setConfirmUrl(p.suggested_url?.trim() || '');
                            }}
                          >
                            Confirm
                          </Button>
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
          <Stack spacing={2} sx={{ mt: 2 }} data-testid="market-competition-lens">
            <HeadlineStrip columns={4}>
              <HeadlineFigure
                label="Approved mappings"
                value={counts.approvedMappings}
                compact
                caption="stored score on fact_competitor_mapping"
              />
              <HeadlineFigure
                label="Pending review"
                value={counts.pendingMappings}
                compact
                severity={counts.pendingMappings ? 'warn' : 'neutral'}
                caption="Need a decision"
              />
              <HeadlineFigure
                label="Competitor prices observed"
                value={prices?.length ?? 0}
                compact
                caption="fact_competitor_price — nothing inferred"
              />
              <HeadlineFigure
                label="Competitor impact"
                value="—"
                compact
                caption="Not derivable; never shown as a number"
              />
            </HeadlineStrip>
            <Box
              sx={{
                display: 'grid',
                gap: 2,
                gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'minmax(0, 3fr) minmax(300px, 2fr)' },
                alignItems: 'start',
              }}
            >
              <Stack spacing={2} sx={{ minWidth: 0 }}>
                <ScopeBar
                  chips={[
                    {
                      key: 'pending',
                      label: `Pending · ${counts.pendingMappings}`,
                      active: false,
                      onToggle: () => undefined,
                      tone: 'warning',
                    },
                    {
                      key: 'approved',
                      label: `Approved · ${counts.approvedMappings}`,
                      active: false,
                      onToggle: () => undefined,
                      tone: 'success',
                    },
                  ]}
                  summary={`${(mappings ?? []).length} mappings · our SKU ↔ competitor SKU`}
                  trailing={
                    <Tooltip title="Data only: a scorer exists in code but no endpoint runs it against the catalogue yet." arrow>
                      <span>
                        <Button size="small" variant="outlined" disabled>
                          Propose candidates
                        </Button>
                      </span>
                    </Tooltip>
                  }
                />
                <EnterpriseDataGrid<MapRow>
                  rowData={mappings ?? []}
                  columnDefs={mappingCols}
                  height={380}
                  gridOptions={{
                    onRowClicked: (e: RowClickedEvent<MapRow>) => e.data && setSelectedMapping(e.data.id),
                    getRowId: (p) => String(p.data.id),
                  }}
                />
              </Stack>
              <Stack spacing={2}>
                <Panel title="Where this feeds" subtitle="Approved mappings are reusable facts" flush>
                  <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
                    <PanelRow
                      severity="neutral"
                      primary="Promotion planner"
                      secondary="Competitors column per line: mapped counts, not inferences"
                      figure="Promotions & Funding"
                      onClick={() => router.push('/promotions')}
                    />
                    <PanelRow
                      severity="neutral"
                      primary="Planning lineup"
                      secondary="Competing product visible beside each ranked SKU"
                      figure="Planning"
                      onClick={() => router.push('/lineup')}
                    />
                    <PanelRow
                      severity="neutral"
                      primary="Stock & Sell-through"
                      secondary="Product context panel lists mapped competitors"
                      figure="Stock"
                      onClick={() => router.push('/stock')}
                    />
                  </Stack>
                </Panel>
                <CapabilityLedger items={COMPETITION_CAPABILITIES} />
              </Stack>
            </Box>
          </Stack>
        ) : null}

        {lens === 'competitor-prices' ? (
          prices && prices.length > 0 ? (
            <Box sx={{ mt: 2 }}>
              <EnterpriseDataGrid<PriceRow>
                rowData={prices}
                columnDefs={[
                  { field: 'competitor_sku', headerName: 'Comp SKU', pinned: 'left' },
                  { field: 'observed_at', headerName: 'Observed' },
                  { field: 'price', headerName: 'Price', type: 'numericColumn' },
                  { field: 'channel', headerName: 'Channel' },
                ]}
                height={380}
              />
            </Box>
          ) : (
            <SubstrateOrPlanned
              status="substrate"
              title="Competitor prices — data only"
              body="The table (fact_competitor_price) and its list endpoint exist. There is no import template, so this lens shows nothing rather than a placeholder chart. When an import lands, observed competitor prices appear per approved mapping — still as observations, never as inferred impact."
              related={[
                { label: 'Competitor mappings', href: '/competition?tab=mappings' },
                { label: 'Import Center', href: '/admin/imports' },
              ]}
            />
          )
        ) : null}

        {lens === 'competitor-listings' ? (
          <SubstrateOrPlanned
            status="planned"
            title="Competitor listings — planned"
            body="Extend the listing registry so a competitor product can be monitored on the same retailer pages as ours (BACKLOG §9.9). The registry, fetcher and history already exist for our products; the delta is a product-dimension that allows competitor SKUs. Shown so you know where it will live; nothing here works yet."
            related={[{ label: 'Monitored listings', href: '/listing-capture?tab=registry' }]}
          />
        ) : null}

        {lens === 'quality' ? (
          <SubstrateOrPlanned
            status="planned"
            title="Listing quality / SEO — planned"
            body="Content, specification and search-quality checks on monitored listings (roadmap P5). Raw page snapshots are already retained by the fetcher, so this is an extraction and rules layer, not a new capture. Not built; no figures are shown."
            related={[{ label: 'Monitored listings', href: '/listing-capture?tab=registry' }]}
          />
        ) : null}
      </MarketChrome>

      <EntityContextPanel
        open={!!selected}
        onClose={() => setSelectedListing(null)}
        kicker={selected ? `Listing ${selected.id} · ${LISTING_STATUS_LABEL[selected.status] ?? selected.status}` : undefined}
        title={selected ? `${selected.customer_name ?? selected.customer_id} · listing ${selected.id}` : ''}
        subtitle={selected?.url}
        width={520}
        figures={
          selected ? (
            <HeadlineStrip columns={3}>
              <HeadlineFigure
                label="Last price"
                value={selected.intel?.last_price == null ? '—' : fmtMoney(selected.intel.last_price)}
                dense
              />
              <HeadlineFigure
                label="Since first seen"
                value={
                  selected.intel?.first_price != null && selected.intel?.last_price != null
                    ? selected.intel.last_price === selected.intel.first_price
                      ? '0'
                      : `${selected.intel.last_price > selected.intel.first_price ? '+' : '−'}${fmtMoney(Math.abs(selected.intel.last_price - selected.intel.first_price))}`
                    : '—'
                }
                dense
                caption={`${selected.intel?.observation_count ?? 0} obs · ${selected.intel?.span_days ?? 0} d`}
              />
              <HeadlineFigure
                label="Promotion"
                value={ACTIVATION_LABEL[selected.intel?.activation_status ?? ''] ?? selected.intel?.activation_status ?? 'none'}
                dense
                severity={
                  selected.intel?.activation_status === 'not_activated'
                    ? 'bad'
                    : selected.intel?.activation_status === 'price_consistent'
                      ? 'good'
                      : 'neutral'
                }
              />
            </HeadlineStrip>
          ) : null
        }
        related={
          selected
            ? [
                ...(selected.product_id
                  ? [
                      { label: 'Stock cover & sell-through', href: `/stock?product=${selected.product_id}`, hint: 'Stock & Sell-through' },
                      {
                        label: 'Competitor mappings for this SKU',
                        href: `/competition?tab=mappings`,
                        hint: 'Market › Competition',
                      },
                    ]
                  : [{ label: 'Resolve product token', href: '/admin/imports', hint: 'Data & Stewardship' }]),
              ]
            : []
        }
        footer={
          selected ? (
            <>
              <Button size="small" variant="outlined" disabled={pollMut.isPending} onClick={() => pollMut.mutate()}>
                Fetch now
              </Button>
              <Button size="small" variant="outlined" onClick={() => setSelectedListing(null)}>
                Close
              </Button>
            </>
          ) : null
        }
      >
        {selected ? (
          <Stack spacing={2.5}>
            {selectedObs.filter((o) => o.extracted_price != null).length >= 2 ? (
              <TrendChart
                data={selectedObs
                  .filter((o) => o.extracted_price != null)
                  .map((o) => ({
                    date: (o.fetched_at || '').slice(0, 10),
                    price: o.extracted_price,
                    casePrice: o.cpor_case_price,
                  }))}
                x="date"
                height={160}
                yScale="fit"
                format={(v) => fmtMoney(v)}
                series={[
                  { key: 'casePrice', label: 'Case SRP', kind: 'area', tone: 'muted' },
                  { key: 'price', label: 'Observed', kind: 'line', tone: 'primary' },
                ]}
              />
            ) : (
              <Typography variant="caption" color="text.secondary">
                Price history for this listing renders from its {selected.intel?.observation_count ?? 0} observations.
              </Typography>
            )}
            <KeyValueList
              items={[
                { k: 'URL', v: <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>{selected.url}</Typography> },
                { k: 'Marketplace', v: selected.marketplace },
                { k: 'Source', v: selected.source },
                {
                  k: 'Observations',
                  v: `${selected.intel?.observation_count ?? 0} over ${selected.intel?.span_days ?? 0} days${(selected.intel?.span_days ?? 0) < 14 ? ' — below 14-day readiness' : ''}`,
                },
              ]}
            />
            {selected.intel?.activation_status === 'not_activated' ? (
              <Alert severity="error" variant="outlined">
                {selected.intel.activation_message ||
                  `Case SRP ${fmtMoney(selected.intel.case_price)} but the shelf shows ${fmtMoney(selected.intel.last_price)}. This is an observation.`}
              </Alert>
            ) : null}
          </Stack>
        ) : null}
      </EntityContextPanel>

      <EntityContextPanel
        open={!!mapping}
        onClose={() => setSelectedMapping(null)}
        kicker={mapping ? `Mapping ${mapping.id} · ${mapping.approval_status}` : undefined}
        title={mapping ? `${mapping.internal_sku ?? 'SKU'} ↔ ${mapping.competitor_sku ?? 'competitor'}` : ''}
        width={480}
        figures={
          mapping ? (
            <HeadlineStrip columns={2}>
              <HeadlineFigure
                label="Match score"
                value={Number(mapping.score).toFixed(3)}
                dense
                caption="stored on fact_competitor_mapping — not a lab fixture blend"
                severity={mapping.score >= 0.8 ? 'good' : mapping.score >= 0.6 ? 'neutral' : 'warn'}
              />
              <HeadlineFigure label="Approval" value={mapping.approval_status} dense />
            </HeadlineStrip>
          ) : null
        }
        footer={
          mapping && mapping.approval_status === 'pending' ? (
            <>
              <Button size="small" variant="outlined" color="error" onClick={() => rejectMap.mutate(mapping.id)}>
                Reject
              </Button>
              <Button
                size="small"
                variant="contained"
                onClick={() => approve.mutate(mapping.id)}
                data-testid="mapping-approve"
              >
                Approve mapping
              </Button>
            </>
          ) : mapping ? (
            <Button size="small" variant="outlined" onClick={() => setSelectedMapping(null)}>
              Close
            </Button>
          ) : null
        }
      >
        {mapping ? (
          <Stack spacing={2}>
            <Typography variant="body2">{mapping.explanation}</Typography>
            <Alert severity="info" variant="outlined">
              A mapping says “these compete”. Production stores one score and one explanation string — there is no
              factor panel (the lab 0.810 vs 0.781 split is a fixture artefact and is not shown).
            </Alert>
          </Stack>
        ) : null}
      </EntityContextPanel>

      <Dialog open={addOpen} onClose={() => setAddOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Add listing</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ pt: 1 }}>
            <TextField size="small" label="Customer id" value={customerId} onChange={(e) => setCustomerId(e.target.value)} />
            <TextField size="small" label="URL" value={url} onChange={(e) => setUrl(e.target.value)} fullWidth />
            <TextField
              size="small"
              label="Marketplace"
              value={marketplace}
              onChange={(e) => setMarketplace(e.target.value)}
              helperText="takealot | amazon | evetech"
            />
            <TextField
              size="small"
              label="Product id (optional)"
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
            />
            {createMut.isError ? <Alert severity="error">{String((createMut.error as Error)?.message)}</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={!url.trim() || createMut.isPending} onClick={() => createMut.mutate()}>
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!confirmSeed} onClose={() => setConfirmSeed(null)} fullWidth maxWidth="sm">
        <DialogTitle>Confirm feed proposal</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 1 }}>
            {confirmSeed?.marketplace} · {confirmSeed?.external_id}
          </Typography>
          <TextField size="small" label="Listing URL" value={confirmUrl} onChange={(e) => setConfirmUrl(e.target.value)} fullWidth />
          {confirmMut.isError ? <Alert severity="error">{String((confirmMut.error as Error)?.message)}</Alert> : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmSeed(null)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!confirmUrl.trim() || confirmMut.isPending}
            onClick={() => confirmMut.mutate()}
          >
            Confirm → create listing
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
