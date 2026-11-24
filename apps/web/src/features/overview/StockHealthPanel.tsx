'use client';

import { Box, Button, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import NextLink from 'next/link';

import { Panel, PanelRow } from '@/features/workbench-ui/Panel';
import { apiGet } from '@/lib/api';

/** One distributor x product cover pair (GET /channel-ops/cover-distribution; the existing lab bands). */
export type CoverPair = {
  id: string;
  distributor_name: string;
  product_name: string;
  sku?: string;
  weeks_of_cover: number | null;
  derived_stock: number | null;
  inbound_open: number;
  status: 'breach' | 'watch' | 'ok' | 'excess' | null;
  cover_as_of_date?: string;
};

type CoverResponse = {
  data_unavailable?: boolean;
  headlines?: { breach?: number; watch?: number; excess?: number; pairs?: number };
  items?: CoverPair[];
  cover_as_of_date?: string | null;
};

/** One aged / no-movement customer x product (GET /channel-intelligence?aged_only=true; the existing CST read model). */
export type AgedItem = {
  customer_id: number;
  product_id: number;
  site_label: string | null;
  customer_name: string | null;
  product_name: string | null;
  product_sku: string | null;
  aged_factors?: { latest_soh?: number | null; latest_soh_date?: string | null; aged_lookback_weeks?: number; interpretation?: string };
};

type AgedResponse = { items: AgedItem[]; total: number; data_unavailable?: boolean; as_of?: string };

const ROWS = 5;

/** Lowest cover first among the pairs in the existing breach band; nothing re-banded here. */
export function replenishmentRows(items: CoverPair[] | undefined, n = ROWS): CoverPair[] {
  return (items ?? [])
    .filter((p) => p.status === 'breach' && p.weeks_of_cover != null)
    .sort((a, b) => (a.weeks_of_cover ?? 0) - (b.weeks_of_cover ?? 0) || a.id.localeCompare(b.id))
    .slice(0, n);
}

const num = (v: number | null | undefined, digits = 0) =>
  v == null ? 'n/a' : v.toLocaleString('en-ZA', { maximumFractionDigits: digits, minimumFractionDigits: digits });

/** Dashboard V2: stock health below the sales charts. Replenishment (distributor stock) and aged stock (retailer stock). */
export function StockHealthPanel() {
  const coverQ = useQuery({
    queryKey: ['channel-ops', 'cover-distribution'],
    queryFn: ({ signal }) => apiGet<CoverResponse>('/api/v1/channel-ops/cover-distribution', { signal }),
    staleTime: 60_000,
    retry: false,
  });
  const agedQ = useQuery({
    queryKey: ['channel-intelligence', 'aged', ROWS],
    queryFn: ({ signal }) => apiGet<AgedResponse>(`/api/v1/channel-intelligence?aged_only=true&page_size=${ROWS}`, { signal }),
    staleTime: 60_000,
    retry: false,
  });
  const h = coverQ.data?.headlines;
  const low = replenishmentRows(coverQ.data?.items);
  const aged = agedQ.data?.items ?? [];

  return (
    <Panel title="Stock health" subtitle="Replenishment at distributors and aged stock at retailers, below the sales view." flush>
      <Box
        data-testid="stock-health"
        sx={{ display: 'grid', gap: 2, px: 2, pb: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'repeat(2, minmax(0, 1fr))' } }}
      >
        <Stack spacing={0.5} data-testid="stock-health-replenishment">
          <Stack direction="row" alignItems="baseline" justifyContent="space-between">
            <Typography variant="subtitle2">Replenishment</Typography>
            <Button size="small" component={NextLink} href="/stock?lens=cover&status=under4w">
              Open Stock · Cover
            </Button>
          </Stack>
          {coverQ.isLoading ? (
            <Typography variant="body2" color="text.secondary">Loading cover.</Typography>
          ) : coverQ.isError || coverQ.data?.data_unavailable ? (
            <Typography variant="body2" color="text.secondary">Cover is not available yet.</Typography>
          ) : (
            <>
              <Typography variant="caption" color="text.secondary" data-testid="stock-health-cover-counts">
                {num(h?.breach)} in breach · {num(h?.watch)} on watch · {num(h?.excess)} in excess
                {coverQ.data?.cover_as_of_date ? ` · cover as of ${coverQ.data.cover_as_of_date}` : ''}
              </Typography>
              {low.length === 0 ? (
                <Typography variant="body2" color="text.secondary">No distributor product is in breach.</Typography>
              ) : (
                low.map((p) => (
                  <PanelRow
                    key={p.id}
                    severity="danger"
                    primary={`${p.product_name}${p.sku ? ` (${p.sku})` : ''}`}
                    secondary={`${p.distributor_name} · ${num(p.derived_stock)} on hand · ${num(p.inbound_open)} inbound`}
                    figure={`${num(p.weeks_of_cover, 1)}w`}
                    href="/stock?lens=cover&status=under4w"
                  />
                ))
              )}
            </>
          )}
        </Stack>
        <Stack spacing={0.5} data-testid="stock-health-aged">
          <Stack direction="row" alignItems="baseline" justifyContent="space-between">
            <Typography variant="subtitle2">Aged stock</Typography>
            <Button size="small" component={NextLink} href="/channel-intelligence">
              Open channel intelligence
            </Button>
          </Stack>
          {agedQ.isLoading ? (
            <Typography variant="body2" color="text.secondary">Loading aged stock.</Typography>
          ) : agedQ.isError || agedQ.data?.data_unavailable ? (
            <Typography variant="body2" color="text.secondary">Aged stock is not available yet.</Typography>
          ) : (
            <>
              <Typography variant="caption" color="text.secondary" data-testid="stock-health-aged-count">
                {num(agedQ.data?.total)} retailer products with stock and no movement
                {aged[0]?.aged_factors?.aged_lookback_weeks ? ` over ${aged[0].aged_factors.aged_lookback_weeks} weeks` : ''}
                {agedQ.data?.as_of ? ` · as of ${agedQ.data.as_of}` : ''}
              </Typography>
              {aged.length === 0 ? (
                <Typography variant="body2" color="text.secondary">No aged stock.</Typography>
              ) : (
                aged.map((a) => (
                  <PanelRow
                    key={`${a.customer_id}-${a.product_id}-${a.site_label ?? ''}`}
                    severity="warning"
                    primary={`${a.product_name ?? `Product ${a.product_id}`}${a.product_sku ? ` (${a.product_sku})` : ''}`}
                    secondary={`${a.customer_name ?? `Customer ${a.customer_id}`}${a.site_label ? ` · ${a.site_label}` : ''} · ${a.aged_factors?.interpretation ?? 'no movement'}`}
                    figure={`${num(a.aged_factors?.latest_soh)} on hand`}
                    href="/channel-intelligence"
                  />
                ))
              )}
            </>
          )}
        </Stack>
      </Box>
    </Panel>
  );
}