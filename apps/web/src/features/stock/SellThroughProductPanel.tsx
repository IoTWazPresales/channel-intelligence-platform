'use client';

import { Box, CircularProgress, Divider, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { Sparkline } from '@/features/workbench-ui/charts';
import { EntityContextPanel, KeyValueList } from '@/features/workbench-ui/EntityContextPanel';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { apiGet, safeDisplayError } from '@/lib/api';

import type { ProblemRow } from './sellThroughTypes';

type ProductDetail = {
  product: {
    id: number;
    label: string;
    sku: string;
    name: string;
    sales_model_name: string | null;
    part_number: string | null;
    ean: string | null;
    upc: string | null;
    business_unit: string | null;
    category: string | null;
    series: string | null;
    product_line: string | null;
    lifecycle: string | null;
    launch_date: string | null;
    retired_date: string | null;
    price_band: string | null;
    specs: Record<string, string>;
  };
  as_of: string;
  vat: 'ex_vat' | 'inc_vat';
  customers: Array<{
    customer_id: number;
    customer_name: string;
    weekly_units: number[];
    units_26w: number;
    rate_4w: number;
    stock_on_hand: number | null;
    stock_date: string | null;
    stock_age_days: number | null;
    on_order: number | null;
    stock_sites: Array<{ site: string; soh: number }>;
    price_history: Array<{ period: string; price: number }>;
    latest_price: number | null;
  }>;
  lowest_price_customer: { customer_name: string; price: number } | null;
};

const n = (v: number | null | undefined, d = 0) =>
  v == null ? '—' : v.toLocaleString(undefined, { maximumFractionDigits: d });

/**
 * Detail panel for one SKU on the Sell-through tab (Warren 2026-10-19): what it is, and at each
 * customer its sales, stock (with report date and stores) and reported price. Opened from a row in
 * "SKUs needing attention" or "Best sellers", like the detail panels on the other stock screens.
 */
export function SellThroughProductPanel({
  productId,
  asOf,
  vat,
  focus,
  onClose,
}: {
  productId: number | null;
  asOf: string;
  vat: 'ex_vat' | 'inc_vat';
  /** The problem row the panel was opened from, if any: shown first. */
  focus?: ProblemRow | null;
  onClose: () => void;
}) {
  const q = useQuery({
    queryKey: ['sell-through', 'product', productId, asOf, vat],
    queryFn: ({ signal }) =>
      apiGet<ProductDetail>(`/api/v1/sell-through/product/${productId}?as_of=${asOf}&vat=${vat}`, { signal }),
    enabled: productId != null,
    staleTime: 60_000,
  });
  const d = q.data;
  const totalStock = d?.customers.reduce((a, c) => a + (c.stock_on_hand ?? 0), 0) ?? 0;
  const totalRate = d?.customers.reduce((a, c) => a + c.rate_4w, 0) ?? 0;

  return (
    <EntityContextPanel
      open={productId != null}
      onClose={onClose}
      kicker="Product"
      title={d?.product.label ?? focus?.product ?? ''}
      subtitle={d ? [d.product.business_unit, d.product.category, d.product.series].filter(Boolean).join(' · ') : undefined}
      width={520}
      figures={
        d ? (
          <HeadlineStrip columns={3}>
            <HeadlineFigure label="Stock at customers" value={n(totalStock)} unit="units" dense />
            <HeadlineFigure label="Selling a week" value={n(totalRate, 1)} unit="units" dense caption="Last 4 weeks" />
            <HeadlineFigure
              label="Lowest price"
              value={d.lowest_price_customer ? n(d.lowest_price_customer.price) : '—'}
              dense
              caption={d.lowest_price_customer ? `${d.lowest_price_customer.customer_name} · ${d.vat === 'inc_vat' ? 'incl.' : 'excl.'} VAT` : 'No prices reported'}
            />
          </HeadlineStrip>
        ) : null
      }
    >
      {q.isLoading ? <CircularProgress size={20} /> : null}
      {q.isError ? <Typography color="error">{safeDisplayError(q.error)}</Typography> : null}
      {focus ? (
        <Box sx={{ mb: 2 }} data-testid="sellthrough-panel-focus">
          <Typography variant="overline" color="text.secondary">
            {focus.reason_label} at {focus.customer_name}
          </Typography>
          <Typography variant="body2">{focus.detail}</Typography>
        </Box>
      ) : null}
      {d ? (
        <Stack spacing={2}>
          <Box>
            <Typography variant="subtitle2" gutterBottom>
              At each customer
            </Typography>
            <Stack spacing={1.5} divider={<Divider flexItem />}>
              {d.customers.map((c) => (
                <Box key={c.customer_id} data-testid="sellthrough-panel-customer">
                  <Stack direction="row" justifyContent="space-between" alignItems="baseline">
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {c.customer_name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {n(c.units_26w)} sold in 26 weeks · {n(c.rate_4w, 1)} a week lately
                    </Typography>
                  </Stack>
                  <Sparkline values={c.weekly_units} height={24} label={`${c.customer_name} weekly units, 26 weeks`} />
                  <Typography variant="caption" display="block">
                    Stock {n(c.stock_on_hand)}
                    {c.stock_date ? ` · reported ${c.stock_date}${c.stock_age_days != null && c.stock_age_days > 35 ? ` (${c.stock_age_days} days old)` : ''}` : ' · this customer does not report stock'}
                    {c.on_order ? ` · ${n(c.on_order)} on order or in transit` : ''}
                  </Typography>
                  {c.stock_sites.length ? (
                    <Typography variant="caption" color="text.secondary" display="block">
                      Stores: {c.stock_sites.map((s) => `${s.site} ${n(s.soh)}`).join(', ')}
                    </Typography>
                  ) : null}
                  <Typography variant="caption" color="text.secondary" display="block">
                    Price {c.latest_price != null ? n(c.latest_price) : 'not reported'}
                    {c.price_history.length > 1
                      ? ` · was ${n(c.price_history[0].price)} on ${c.price_history[0].period}`
                      : ''}
                  </Typography>
                </Box>
              ))}
            </Stack>
          </Box>
          <Box>
            <Typography variant="subtitle2" gutterBottom>
              Product
            </Typography>
            <KeyValueList
              items={[
                { k: 'SKU', v: d.product.sku },
                { k: 'Sales model', v: d.product.sales_model_name ?? '—' },
                { k: 'Part number', v: d.product.part_number ?? '—' },
                { k: 'EAN / UPC', v: [d.product.ean, d.product.upc].filter(Boolean).join(' / ') || '—' },
                { k: 'Lifecycle', v: d.product.lifecycle ?? '—' },
                { k: 'Launched', v: d.product.launch_date ?? '—' },
                { k: 'Price band', v: d.product.price_band ?? '—' },
                ...Object.entries(d.product.specs).map(([k, v]) => ({ k, v })),
              ]}
            />
          </Box>
        </Stack>
      ) : null}
    </EntityContextPanel>
  );
}
