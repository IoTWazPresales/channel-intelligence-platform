'use client';

import { Alert, Box, Link, Stack, Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { ModuleDataSection } from '@/components/ModuleDataSection';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { StatusChip } from '@/features/workbench-ui/controls';
import { apiGet } from '@/lib/api';

import { ListingCustomerScopePicker } from './ListingCustomerScopePicker';
import { useListingCustomerScope } from './listingCustomerScope';

type MatrixCustomer = { id: number; name: string; code?: string | null };
type MatrixProduct = { id: number; sku?: string | null; name?: string | null };
type MatrixCell = {
  product_id: number;
  customer_id: number;
  price: number | null;
  listing_id: number | null;
  listing_url: string | null;
  in_stock: boolean;
  tenant_srp?: number | null;
  promo?: { name: string; window_start: string | null; window_end: string | null } | null;
};

type MatrixPayload = {
  data_unavailable?: boolean;
  customers: MatrixCustomer[];
  products: MatrixProduct[];
  cells: MatrixCell[];
  summary: { product_count: number; cheapest_at: Record<string, number>; below_srp_count: number };
};

function fmtMoney(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function matrixQueryKey(customerIds: number[]) {
  const params = new URLSearchParams();
  for (const id of customerIds) params.append('customer_id', String(id));
  const qs = params.toString();
  return ['listing-capture', 'price-matrix', customerIds.join(',')] as const;
}

export function PriceMatrixLens() {
  const scope = useListingCustomerScope();
  const enabled = scope.hydrated && scope.selectedIds.length > 0;
  const matrix = useQuery({
    queryKey: matrixQueryKey(scope.selectedIds),
    queryFn: ({ signal }) => {
      const params = new URLSearchParams();
      for (const id of scope.selectedIds) params.append('customer_id', String(id));
      return apiGet<MatrixPayload>(`/api/v1/listing-capture/price-matrix?${params.toString()}`, { signal });
    },
    enabled,
    staleTime: 30_000,
  });

  const cellMap = useMemo(() => {
    const m = new Map<string, MatrixCell>();
    for (const cell of matrix.data?.cells ?? []) {
      m.set(`${cell.product_id}:${cell.customer_id}`, cell);
    }
    return m;
  }, [matrix.data]);

  const rowLowest = useMemo(() => {
    const out = new Map<number, number | null>();
    for (const product of matrix.data?.products ?? []) {
      let min: number | null = null;
      for (const cid of scope.selectedIds) {
        const cell = cellMap.get(`${product.id}:${cid}`);
        if (cell?.in_stock && cell.price != null) {
          min = min == null ? cell.price : Math.min(min, cell.price);
        }
      }
      out.set(product.id, min);
    }
    return out;
  }, [matrix.data, scope.selectedIds, cellMap]);

  const customers = matrix.data?.customers ?? [];
  const products = matrix.data?.products ?? [];
  const summary = matrix.data?.summary;

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="price-matrix-lens">
      <ListingCustomerScopePicker testIdPrefix="price-matrix-customers" />
      {matrix.isError || matrix.data?.data_unavailable ? (
        <Alert severity="warning" data-testid="price-matrix-unavailable">
          Price matrix could not be loaded.
        </Alert>
      ) : null}
      {summary ? (
        <HeadlineStrip columns={Math.min(4, 1 + customers.length)}>
          <HeadlineFigure
            label="Products monitored"
            value={summary.product_count}
            compact
            testId="price-matrix-product-count"
          />
          {customers.slice(0, 3).map((c) => (
            <HeadlineFigure
              key={c.id}
              label={`Cheapest at · ${c.name}`}
              value={summary.cheapest_at[String(c.id)] ?? 0}
              compact
              testId={`price-matrix-cheapest-${c.id}`}
            />
          ))}
          <HeadlineFigure
            label="Prices below tenant SRP"
            value={summary.below_srp_count}
            compact
            severity={summary.below_srp_count ? 'warn' : 'neutral'}
            testId="price-matrix-below-srp"
          />
        </HeadlineStrip>
      ) : null}
      <ModuleDataSection
        isLoading={matrix.isLoading}
        isEmpty={!matrix.isLoading && products.length === 0}
        empty={{
          title: 'No scoped products with listings',
          description: 'Add listings for in-scope products, or widen the customer picker.',
        }}
      >
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" data-testid="price-matrix-table" sx={{ '& td, & th': { py: 0.75, whiteSpace: 'nowrap' } }}>
            <TableHead>
              <TableRow>
                <TableCell>Product</TableCell>
                <TableCell align="right">Tenant SRP</TableCell>
                {customers.map((c) => (
                  <TableCell key={c.id} align="right">
                    {c.name}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {products.map((p) => {
                const srp =
                  scope.selectedIds
                    .map((cid) => cellMap.get(`${p.id}:${cid}`)?.tenant_srp)
                    .find((v) => v != null) ?? null;
                const rowMin = rowLowest.get(p.id);
                return (
                  <TableRow key={p.id} data-testid={`price-matrix-row-${p.id}`}>
                    <TableCell>
                      <Typography variant="body2">{[p.sku, p.name].filter(Boolean).join(' · ') || `Product ${p.id}`}</Typography>
                    </TableCell>
                    <TableCell align="right">{fmtMoney(srp)}</TableCell>
                    {customers.map((c) => {
                      const cell = cellMap.get(`${p.id}:${c.id}`);
                      const price = cell?.in_stock ? cell.price : null;
                      const isLow =
                        price != null && rowMin != null && Math.abs(price - rowMin) < 0.01;
                      const aboveSrp = srp != null && price != null && price > srp + 1;
                      const hasPromo = Boolean(cell?.promo);
                      const cellSx = {
                        bgcolor: isLow ? 'success.light' : undefined,
                        color: aboveSrp ? 'error.main' : undefined,
                        boxShadow: hasPromo ? 'inset 0 0 0 1px rgba(255, 193, 7, 0.55)' : undefined,
                      };
                      const body =
                        price == null ? (
                          '—'
                        ) : (
                          <Stack spacing={0.25} alignItems="flex-end">
                            {cell?.listing_url ? (
                              <Link href={cell.listing_url} target="_blank" rel="noopener noreferrer" underline="hover">
                                {fmtMoney(price)}
                              </Link>
                            ) : (
                              fmtMoney(price)
                            )}
                            {hasPromo ? (
                              <Tooltip
                                title={`${cell?.promo?.name ?? 'Promotion'}${cell?.promo?.window_start ? ` · ${cell.promo.window_start} – ${cell.promo.window_end ?? ''}` : ''}`}
                              >
                                <span>
                                  <StatusChip label="Promo" tone="warning" />
                                </span>
                              </Tooltip>
                            ) : null}
                          </Stack>
                        );
                      return (
                        <TableCell key={c.id} align="right" sx={cellSx}>
                          {body}
                        </TableCell>
                      );
                    })}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Box>
      </ModuleDataSection>
    </Stack>
  );
}