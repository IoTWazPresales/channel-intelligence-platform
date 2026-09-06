'use client';

import type { ColDef, RowClickedEvent } from 'ag-grid-community';
import { Box, Button, Card, CardActionArea, CardContent, CircularProgress, Stack, Typography, useMediaQuery } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useQuery } from '@tanstack/react-query';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { CategoryBars, ProportionBar, TrendChart } from '@/features/workbench-ui/charts';
import { ScopeBar, StatusChip } from '@/features/workbench-ui/controls';
import { EntityContextPanel, KeyValueList } from '@/features/workbench-ui/EntityContextPanel';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';
import { apiGet } from '@/lib/api';

import {
  coverPairStatus,
  coverStatusLabel,
  coverStatusTone,
  fmtCoverInt,
  type CoverPairStatus,
} from './coverStatus';

type CoverItem = {
  id: string;
  distributor_id: number;
  distributor_code: string;
  distributor_name: string;
  product_id: number;
  sku: string;
  product_name: string;
  family: string;
  weeks_of_cover: number | null;
  derived_stock: number;
  weekly_velocity: number | null;
  inbound_open: number;
  vintage_days: number;
  status: CoverPairStatus | null;
  lab_bucket: string | null;
  replenishment_flag: boolean;
  cover_as_of_date: string;
};

type CoverDistribution = {
  data_unavailable?: boolean;
  pair_count: number;
  under_4w: number;
  mean_woc: number | null;
  buckets: Record<string, number>;
  lab_buckets?: { bucket: string; pairs: number }[];
  headlines?: {
    soh: number;
    network_cover: number | null;
    pairs: number;
    with_woc: number;
    distributor_count: number;
    breach: number;
    watch: number;
    excess: number;
  };
  items?: CoverItem[];
  cover_as_of_date?: string | null;
  weekly_flow?: {
    points: { week: string; week_start: string; sellOut: number; shipped: number }[];
    sell_out_through: string | null;
    shipped_through: string | null;
  };
  scopes?: {
    distributors: { id: number; code: string; name: string; pairs: number }[];
    families: { family: string; pairs: number }[];
  };
};

function useParam(key: string) {
  const router = useRouter();
  const search = useSearchParams();
  const value = search.get(key);
  const set = useCallback(
    (v: string | null) => {
      const next = new URLSearchParams(search.toString());
      if (v === null) next.delete(key);
      else next.set(key, v);
      const qs = next.toString();
      router.replace(qs ? `/stock?${qs}` : '/stock?lens=cover', { scroll: false });
    },
    [key, router, search],
  );
  return [value, set] as const;
}

export function CoverLensView() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [status, setStatus] = useParam('status');
  const [distributor, setDistributor] = useParam('distributor');
  const [family, setFamily] = useParam('family');
  const [product, setProduct] = useParam('product');
  const [bucket, setBucket] = useParam('bucket');
  const [savedView, setSavedView] = useState('All pairs');
  const [selected, setSelected] = useState<CoverItem | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['channel-ops', 'cover-distribution'],
    queryFn: ({ signal }) => apiGet<CoverDistribution>('/api/v1/channel-ops/cover-distribution', { signal }),
    staleTime: 60_000,
  });

  const items = useMemo(() => data?.items ?? [], [data?.items]);
  const headlines = data?.headlines;
  const rows = useMemo(
    () =>
      items.filter((r) => {
        const st = r.status ?? coverPairStatus(r.weeks_of_cover);
        if (status && st !== status) return false;
        if (distributor && String(r.distributor_id) !== distributor) return false;
        if (family && r.family !== family) return false;
        if (product && String(r.product_id) !== product) return false;
        if (bucket && r.lab_bucket !== bucket) return false;
        return true;
      }),
    [items, status, distributor, family, product, bucket],
  );

  const columnDefs = useMemo<ColDef<CoverItem>[]>(
    () => [
      { field: 'distributor_name', headerName: 'Distributor', minWidth: 190, flex: 1.2, pinned: 'left' },
      {
        field: 'product_name',
        headerName: 'Product',
        minWidth: 240,
        flex: 1.6,
        cellRenderer: (p: { data?: CoverItem }) =>
          p.data ? (
            <Box sx={{ lineHeight: 1.2 }}>
              <Typography variant="body2" noWrap>
                {p.data.product_name}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {p.data.sku} · {p.data.family}
              </Typography>
            </Box>
          ) : null,
      },
      {
        field: 'derived_stock',
        headerName: 'SOH',
        type: 'rightAligned',
        width: 100,
        valueFormatter: (p) => fmtCoverInt(p.value as number),
      },
      {
        field: 'weekly_velocity',
        headerName: 'Sell-out / wk',
        type: 'rightAligned',
        width: 120,
        valueFormatter: (p) => fmtCoverInt(p.value as number | null),
      },
      {
        field: 'weeks_of_cover',
        headerName: 'Weeks of cover',
        width: 170,
        sort: 'asc',
        cellRenderer: (p: { data?: CoverItem }) => {
          if (!p.data || p.data.weeks_of_cover == null) return '—';
          const st = p.data.status ?? coverPairStatus(p.data.weeks_of_cover);
          const tone =
            st === 'breach' ? 'danger' : st === 'watch' ? 'warning' : st === 'excess' ? 'primary' : 'success';
          return (
            <ProportionBar
              value={Math.min(p.data.weeks_of_cover / 10, 1)}
              label={`${p.data.weeks_of_cover.toFixed(1)}w`}
              tone={tone}
            />
          );
        },
      },
      {
        field: 'inbound_open',
        headerName: 'Inbound open',
        type: 'rightAligned',
        width: 130,
        valueFormatter: (p) => (p.value ? fmtCoverInt(p.value as number) : '—'),
      },
      {
        field: 'vintage_days',
        headerName: 'Vintage',
        width: 100,
        valueFormatter: (p) => `${p.value}d`,
        cellStyle: (p) => (Number(p.value) > 10 ? { color: theme.palette.warning.main } : null),
      },
      {
        field: 'status',
        headerName: 'Status',
        width: 120,
        cellRenderer: (p: { data?: CoverItem }) => {
          const st = p.data?.status ?? coverPairStatus(p.data?.weeks_of_cover);
          return <StatusChip label={coverStatusLabel(st)} tone={coverStatusTone(st)} />;
        },
      },
    ],
    [theme],
  );

  const clear = () => {
    setStatus(null);
    setDistributor(null);
    setFamily(null);
    setProduct(null);
    setBucket(null);
    setSavedView('All pairs');
  };

  const chips = [
    {
      key: 'breach',
      label: `Under 2w · ${headlines?.breach ?? 0}`,
      active: status === 'breach',
      onToggle: () => setStatus(status === 'breach' ? null : 'breach'),
      tone: 'danger' as const,
    },
    {
      key: 'watch',
      label: `2–4w · ${headlines?.watch ?? 0}`,
      active: status === 'watch',
      onToggle: () => setStatus(status === 'watch' ? null : 'watch'),
      tone: 'warning' as const,
    },
    {
      key: 'excess',
      label: `Over 8w · ${headlines?.excess ?? 0}`,
      active: status === 'excess',
      onToggle: () => setStatus(status === 'excess' ? null : 'excess'),
    },
    ...(data?.scopes?.distributors ?? []).map((d) => ({
      key: `d${d.id}`,
      label: d.code,
      active: distributor === String(d.id),
      onToggle: () => setDistributor(distributor === String(d.id) ? null : String(d.id)),
    })),
    ...(data?.scopes?.families ?? []).map((f) => ({
      key: f.family,
      label: f.family,
      active: family === f.family,
      onToggle: () => setFamily(family === f.family ? null : f.family),
    })),
  ];

  const selectedProductRows = selected ? items.filter((r) => r.product_id === selected.product_id) : [];
  const flow = data?.weekly_flow;
  const weekCaption =
    flow?.points?.length && flow.points[0] && flow.points[flow.points.length - 1]
      ? `${flow.points[0].week}–${flow.points[flow.points.length - 1].week}`
      : '';

  if (isLoading) {
    return (
      <Box sx={{ display: 'grid', placeItems: 'center', py: 6 }} data-testid="stock-cover-loading">
        <CircularProgress size={28} />
      </Box>
    );
  }

  if (isError || !data || data.data_unavailable) {
    return (
      <Box sx={{ p: 2 }} data-testid="stock-cover-empty">
        <Typography color="text.secondary" sx={{ fontSize: '13px' }}>
          Cover distribution is not available yet — import distributor inventory (DSI) and run cover observations.
        </Typography>
      </Box>
    );
  }

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="stock-cover-lens">
      <HeadlineStrip columns={5}>
        <HeadlineFigure
          label="Network SOH"
          value={fmtCoverInt(headlines?.soh)}
          unit="units"
          caption={`${headlines?.pairs ?? 0} pairs · ${headlines?.distributor_count ?? 0} distributors`}
          compact
        />
        <HeadlineFigure
          label="Network cover"
          value={headlines?.network_cover != null ? headlines.network_cover.toFixed(1) : '—'}
          unit="weeks"
          compact
          caption="SOH ÷ stored weekly velocity (364-day window when mature)"
        />
        <HeadlineFigure
          label="Under 2 weeks"
          value={headlines?.breach ?? 0}
          unit="pairs"
          severity="bad"
          compact
          onClick={() => setStatus(status === 'breach' ? null : 'breach')}
          caption="Risk of stock-out"
        />
        <HeadlineFigure
          label="2–4 weeks"
          value={headlines?.watch ?? 0}
          unit="pairs"
          severity="warn"
          compact
          onClick={() => setStatus(status === 'watch' ? null : 'watch')}
          caption="Watch list"
        />
        <HeadlineFigure
          label="Over 8 weeks"
          value={headlines?.excess ?? 0}
          unit="pairs"
          compact
          onClick={() => setStatus(status === 'excess' ? null : 'excess')}
          caption="Excess / ageing risk"
        />
      </HeadlineStrip>

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '2fr 3fr' } }}>
        <Panel title="Cover distribution" subtitle="Distributor × product pairs by weeks of cover · click a bar to filter">
          <CategoryBars
            data={data.lab_buckets ?? []}
            x="bucket"
            y="pairs"
            height={180}
            onRowClick={(row) => {
              const next = String(row.bucket ?? '');
              setBucket(bucket === next ? null : next);
            }}
            colorBy={(r) =>
              ['<1w', '1–2w'].includes(String(r.bucket))
                ? theme.palette.error.main
                : String(r.bucket) === '2–4w'
                  ? theme.palette.warning.main
                  : String(r.bucket) === '8w+'
                    ? theme.palette.primary.light
                    : theme.palette.success.main
            }
          />
        </Panel>
        <Panel
          title={`Sell-out vs shipped-in${weekCaption ? `, ${weekCaption}` : ''}`}
          subtitle="All distributors · units per week · SOH on right panel of Movement lens"
        >
          <TrendChart
            data={flow?.points ?? []}
            x="week"
            height={180}
            series={[
              { key: 'shipped', label: 'Shipped in', kind: 'bar', tone: 'muted' },
              { key: 'sellOut', label: 'Sell-out', kind: 'line', tone: 'primary' },
            ]}
          />
        </Panel>
      </Box>

      <ScopeBar
        chips={chips}
        savedViews={['All pairs', 'Breaches only']}
        savedView={savedView}
        onSavedView={(v) => {
          setSavedView(v);
          if (v === 'Breaches only') setStatus('breach');
          if (v === 'All pairs') clear();
        }}
        summary={`${rows.length} of ${items.length} pairs`}
        onClear={clear}
      />

      <ModuleDataSection
        isEmpty={rows.length === 0}
        empty={{
          title: 'No pairs match this scope',
          description: 'Clear a chip or pick another saved view. Cover is derived from distributor sell-out and SOH files — nothing is stored.',
          primary: { label: 'Clear scope', onClick: clear },
        }}
      >
        {isMobile ? (
          <Stack spacing={1} data-testid="cover-record-cards">
            {rows.slice(0, 30).map((r) => {
              const st = r.status ?? coverPairStatus(r.weeks_of_cover);
              return (
                <Card key={r.id} variant="outlined" sx={{ boxShadow: 'none' }}>
                  <CardActionArea onClick={() => setSelected(r)}>
                    <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
                      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                        <Box sx={{ minWidth: 0 }}>
                          <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>
                            {r.product_name}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {r.distributor_name}
                          </Typography>
                        </Box>
                        <StatusChip
                          label={r.weeks_of_cover != null ? `${r.weeks_of_cover.toFixed(1)}w` : '—'}
                          tone={coverStatusTone(st)}
                        />
                      </Stack>
                      <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
                        <Typography variant="caption">
                          SOH <b>{fmtCoverInt(r.derived_stock)}</b>
                        </Typography>
                        <Typography variant="caption">
                          /wk <b>{fmtCoverInt(r.weekly_velocity)}</b>
                        </Typography>
                        <Typography variant="caption">
                          Inbound <b>{r.inbound_open ? fmtCoverInt(r.inbound_open) : '—'}</b>
                        </Typography>
                      </Stack>
                    </CardContent>
                  </CardActionArea>
                </Card>
              );
            })}
          </Stack>
        ) : (
          <EnterpriseDataGrid<CoverItem>
            rowData={rows}
            columnDefs={columnDefs}
            height={440}
            gridOptions={{
              onRowClicked: (e: RowClickedEvent<CoverItem>) => e.data && setSelected(e.data),
              rowClass: 'cip-clickable-row',
              getRowId: (p) => p.data.id,
            }}
          />
        )}
      </ModuleDataSection>

      <EntityContextPanel
        open={!!selected}
        onClose={() => setSelected(null)}
        kicker="Product"
        title={selected?.product_name ?? ''}
        subtitle={selected ? `${selected.sku} · ${selected.family}` : undefined}
        figures={
          selected ? (
            <HeadlineStrip columns={3}>
              <HeadlineFigure
                label="SOH (network)"
                value={fmtCoverInt(selectedProductRows.reduce((a, r) => a + r.derived_stock, 0))}
                dense
              />
              <HeadlineFigure
                label="Sell-out / wk"
                value={fmtCoverInt(selectedProductRows.reduce((a, r) => a + (r.weekly_velocity ?? 0), 0))}
                dense
              />
              <HeadlineFigure
                label="Inbound open"
                value={fmtCoverInt(selectedProductRows.reduce((a, r) => a + r.inbound_open, 0))}
                dense
              />
            </HeadlineStrip>
          ) : null
        }
        related={
          selected
            ? [
                { label: 'Plan lines for this product', href: `/lineup?product=${selected.product_id}`, hint: 'Planning › Lineup cases' },
                { label: 'Open inbound shipments', href: `/stock?lens=inbound`, hint: 'Supply & Inbound › Shipments' },
                { label: 'Promotion cases on this SKU', href: '/commercial-planner/cpor-cases', hint: 'Promotions & Funding › Case book' },
                { label: 'Retail listings & shelf price', href: '/listing-capture?tab=registry', hint: 'Market & Listings › Monitored listings' },
                { label: 'Competitor products', href: '/competition?tab=mappings', hint: 'Market & Listings › Competitor mappings' },
                { label: 'Product master record', href: `/admin/products`, hint: 'Data & Stewardship › Products' },
              ]
            : []
        }
        footer={
          <>
            <Button variant="outlined" size="small" onClick={() => selected && setProduct(String(selected.product_id))}>
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
                {selectedProductRows.map((r) => {
                  const st = r.status ?? coverPairStatus(r.weeks_of_cover);
                  return (
                    <PanelRow
                      key={r.id}
                      severity={st === 'breach' ? 'danger' : st === 'watch' ? 'warning' : 'neutral'}
                      primary={r.distributor_name}
                      secondary={`SOH ${fmtCoverInt(r.derived_stock)} · ${fmtCoverInt(r.weekly_velocity)}/wk · vintage ${r.vintage_days}d`}
                      figure={r.weeks_of_cover != null ? `${r.weeks_of_cover.toFixed(1)}w` : '—'}
                    />
                  );
                })}
              </Stack>
            </Box>
            <KeyValueList
              items={[
                { k: 'Selected pair', v: selected.distributor_name },
                {
                  k: 'Weeks of cover',
                  v:
                    selected.weeks_of_cover != null
                      ? `${selected.weeks_of_cover.toFixed(1)} (${coverStatusLabel(selected.status ?? coverPairStatus(selected.weeks_of_cover))})`
                      : '—',
                },
                {
                  k: 'Derivation',
                  v: 'Derived SOH ÷ stored weekly velocity (364-day window when mature). SOH is calculated, never stored.',
                },
                { k: 'Data vintage', v: `${selected.vintage_days} days` },
              ]}
            />
          </Stack>
        ) : null}
      </EntityContextPanel>
    </Stack>
  );
}
