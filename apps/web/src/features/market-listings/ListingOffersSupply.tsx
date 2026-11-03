'use client';

import { Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { fmtMoney } from '@/features/promotions-funding/format';
import { apiGet } from '@/lib/api';

type Offer = {
  seller_name: string | null;
  price: number | null;
  availability: string | null;
  is_buy_box: boolean;
  label: string | null;
};

type SupplyRow = {
  distributor: string;
  units: number;
  price: number | null;
  period: string;
};

export function ListingOffersSupply({
  listingId,
  customerId,
  productId,
}: {
  listingId: number;
  customerId: number;
  productId: number | null;
}) {
  const offers = useQuery({
    queryKey: ['listing-capture', 'offers', listingId],
    queryFn: ({ signal }) =>
      apiGet<{ items: Offer[]; shoppers_price: number | null; buy_box_label: string | null; buy_box_seller: string | null }>(
        `/api/v1/listing-capture/listings/${listingId}/offers`,
        { signal },
      ),
  });
  const supply = useQuery({
    queryKey: ['listing-capture', 'supply', customerId, productId],
    queryFn: ({ signal }) =>
      apiGet<{ status: string; rows: SupplyRow[] }>(
        `/api/v1/listing-capture/supply?customer_id=${customerId}&product_id=${productId}`,
        { signal },
      ),
    enabled: productId != null,
  });
  const buy = offers.data;

  return (
    <Stack spacing={1.5} data-testid="listing-offers-supply">
      <Typography variant="subtitle2">Shopper&apos;s price</Typography>
      <Typography variant="body2" data-testid="listing-buy-box">
        {buy?.shoppers_price == null ? '—' : fmtMoney(buy.shoppers_price)}
        {buy?.buy_box_label ? ` · ${buy.buy_box_label}` : ''}
        {buy?.buy_box_label === 'Competition' && buy.buy_box_seller ? ` · ${buy.buy_box_seller}` : ''}
      </Typography>
      {(buy?.items ?? []).length > 0 ? (
        <Stack spacing={0.25}>
          {buy?.items.map((offer, i) => (
            <Typography key={`${offer.seller_name}-${i}`} variant="caption" color="text.secondary">
              {offer.is_buy_box ? 'Buy box' : 'Offer'}
              {offer.label ? ` · ${offer.label}` : ''}: {offer.seller_name || 'seller not named'}
              {offer.price == null ? '' : ` · ${fmtMoney(offer.price)}`}
              {offer.availability ? ` · ${offer.availability.replaceAll('_', ' ')}` : ''}
            </Typography>
          ))}
        </Stack>
      ) : null}
      <Typography variant="subtitle2">Supplied by</Typography>
      {productId == null || supply.data?.status === 'not linked' || (supply.data && supply.data.rows.length === 0) ? (
        <Typography variant="body2" data-testid="listing-supply-empty">
          not linked
        </Typography>
      ) : (
        <Stack spacing={0.25} data-testid="listing-supply-rows">
          {(supply.data?.rows ?? []).map((row) => (
            <Typography key={`${row.distributor}-${row.period}`} variant="body2">
              {row.distributor} · {row.units} units · {row.price == null ? '—' : fmtMoney(row.price)} · {row.period.slice(0, 7)}
            </Typography>
          ))}
        </Stack>
      )}
    </Stack>
  );
}
