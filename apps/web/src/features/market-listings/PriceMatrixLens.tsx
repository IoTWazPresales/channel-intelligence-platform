'use client';

import { Box, Link, Stack, Tooltip, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useQuery } from '@tanstack/react-query';
import type { ColDef, GridOptions, ICellRendererParams } from 'ag-grid-community';
import { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { attentionAge } from '@/features/overview/homeDashboard';
import { paginatedGridHeight } from '@/features/plan-vs-executed/gridPagination';
import { OPS_LIST_GRID_PAGINATION, OPS_LIST_PAGE_SIZE } from '@/features/shell/opsListGridPagination';
import { Panel } from '@/features/workbench-ui/Panel';
import { StatusChip } from '@/features/workbench-ui/controls';
import { apiGet } from '@/lib/api';
import { gridRowMetrics } from '@/theme/gridDensity';

import { ListingCustomerScopePicker } from './ListingCustomerScopePicker';
import { useListingCustomerScope } from './listingCustomerScope';

type MatrixCustomer = { id: number; name: string; code?: string | null };
type SrpFields = { srp?: number | null; srp_source?: string | null; srp_reason?: string | null };
type MatrixProduct = SrpFields & {
  id: number;
  sales_model_name?: string | null;
  sku?: string | null;
  name?: string | null;
};
type MatrixCell = SrpFields & {
  product_id: number;
  customer_id: number;
  price: number | null;
  observed_at?: string | null;
  listing_id: number | null;
  listing_url: string | null;
  in_stock: boolean;
  promo?: { name: string; window_start: string | null; window_end: string | null; promotion_type?: string } | null;
};

type MatrixPayload = {
  data_unavailable?: boolean;
  customers: MatrixCustomer[];
  products: MatrixProduct[];
  cells: MatrixCell[];
  summary?: { product_count: number; below_srp_count: number | null };
  srp_source?: string | null;
};

type MatrixRow = { product: MatrixProduct; cells: Record<number, MatrixCell | undefined> };

/** Words for the API's `srp_reason` codes; an unknown code is shown as it came. */
const SRP_REASON_TEXT: Record<string, string> = {
  srp_source_pending: 'SRP source pending Warren',
  no_srp_for_product: 'No SRP',
};

function fmtPrice(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

/** Sales model name first (house rule); SKU, then name, only when the model name is missing. */
export function productLabel(p: MatrixProduct): string {
  return p.sales_model_name || p.sku || p.name || `Product ${p.id}`;
}

function srpText(fields: SrpFields): string {
  if (fields.srp != null) return fmtPrice(fields.srp);
  return SRP_REASON_TEXT[fields.srp_reason ?? ''] ?? fields.srp_reason ?? 'No SRP';
}

function ProductCell({ product }: { product: MatrixProduct }) {
  const secondary = [product.sku, product.name].filter((v) => v && v !== productLabel(product)).join(' · ');
  return (
    <Box sx={{ lineHeight: 1.2, minWidth: 0 }} data-testid={`price-matrix-product-${product.id}`}>
      <Typography variant="body2" noWrap>
        {productLabel(product)}
      </Typography>
      {secondary ? (
        <Typography variant="caption" color="text.secondary" noWrap component="div">
          {secondary}
        </Typography>
      ) : null}
    </Box>
  );
}

function PriceCell({ cell }: { cell: MatrixCell | undefined }) {
  if (!cell || cell.listing_id == null) {
    return (
      <Typography variant="body2" color="text.disabled" title="No monitored listing for this customer">
        —
      </Typography>
    );
  }
  if (cell.price == null) {
    return (
      <Typography variant="caption" color="text.secondary">
        No price yet
      </Typography>
    );
  }
  const belowSrp = cell.in_stock && cell.srp != null && cell.price < cell.srp - 1;
  const promo = cell.promo;
  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0, width: '100%' }}>
      <Box sx={{ lineHeight: 1.2, minWidth: 0 }}>
        <Typography variant="body2" noWrap sx={{ fontVariantNumeric: 'tabular-nums' }}>
          {cell.listing_url ? (
            <Link href={cell.listing_url} target="_blank" rel="noopener noreferrer" underline="hover" color="inherit">
              {fmtPrice(cell.price)}
            </Link>
          ) : (
            fmtPrice(cell.price)
          )}
        </Typography>
        <Typography
          variant="caption"
          color="text.secondary"
          noWrap
          component="div"
          data-testid={`price-matrix-age-${cell.product_id}-${cell.customer_id}`}
        >
          {attentionAge(cell.observed_at, 'observed_at')}
        </Typography>
      </Box>
      <Stack direction="row" spacing={0.5} sx={{ flexShrink: 0 }}>
        {!cell.in_stock ? <StatusChip label="Out of stock" tone="neutral" /> : null}
        {belowSrp ? <StatusChip label="Below SRP" tone="warning" /> : null}
        {promo ? (
          <Tooltip
            title={`${promo.name}${promo.window_start ? ` · ${promo.window_start} – ${promo.window_end ?? ''}` : ''}`}
          >
            <span>
              <StatusChip label={promo.promotion_type ?? 'Promotion'} tone="info" />
            </span>
          </Tooltip>
        ) : null}
      </Stack>
    </Stack>
  );
}

function matrixQueryKey(customerIds: number[]) {
  return ['listing-capture', 'price-matrix', customerIds.join(',')] as const;
}

export function PriceMatrixLens() {
  const theme = useTheme();
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

  /** Every scoped customer keeps a column; customers with more monitored listings come first (stable). */
  const customers = useMemo(() => {
    const listed = new Map<number, number>();
    for (const cell of matrix.data?.cells ?? []) {
      if (cell.listing_id != null) listed.set(cell.customer_id, (listed.get(cell.customer_id) ?? 0) + 1);
    }
    return [...(matrix.data?.customers ?? [])].sort((a, b) => (listed.get(b.id) ?? 0) - (listed.get(a.id) ?? 0));
  }, [matrix.data]);
  const rows = useMemo<MatrixRow[]>(() => {
    const byProduct = new Map<number, Record<number, MatrixCell | undefined>>();
    for (const cell of matrix.data?.cells ?? []) {
      const entry = byProduct.get(cell.product_id) ?? {};
      entry[cell.customer_id] = cell;
      byProduct.set(cell.product_id, entry);
    }
    return (matrix.data?.products ?? []).map((product) => ({ product, cells: byProduct.get(product.id) ?? {} }));
  }, [matrix.data]);

  const columnDefs = useMemo<ColDef<MatrixRow>[]>(
    () => [
      {
        colId: 'product',
        headerName: 'Product',
        pinned: 'left',
        minWidth: 220,
        flex: 1.2,
        valueGetter: (p) => (p.data ? productLabel(p.data.product) : ''),
        tooltipValueGetter: (p) =>
          p.data ? [productLabel(p.data.product), p.data.product.sku, p.data.product.name].filter(Boolean).join(' · ') : undefined,
        cellRenderer: (p: ICellRendererParams<MatrixRow>) => (p.data ? <ProductCell product={p.data.product} /> : null),
      },
      {
        colId: 'srp',
        headerName: 'SRP',
        headerTooltip: 'Suggested Retail Price',
        minWidth: 150,
        type: 'rightAligned',
        valueGetter: (p) => p.data?.product.srp ?? null,
        tooltipValueGetter: (p) => (p.data ? srpText(p.data.product) : undefined),
        cellRenderer: (p: ICellRendererParams<MatrixRow>) =>
          p.data ? (
            <Typography
              variant={p.data.product.srp != null ? 'body2' : 'caption'}
              color={p.data.product.srp != null ? 'text.primary' : 'text.secondary'}
              noWrap
              data-testid={`price-matrix-srp-${p.data.product.id}`}
            >
              {srpText(p.data.product)}
            </Typography>
          ) : null,
      },
      ...customers.map<ColDef<MatrixRow>>((c) => ({
        colId: `customer-${c.id}`,
        headerName: c.name,
        minWidth: 240,
        flex: 1,
        valueGetter: (p) => p.data?.cells[c.id]?.price ?? null,
        tooltipValueGetter: (p) => {
          const cell = p.data?.cells[c.id];
          if (!cell?.observed_at) return undefined;
          return `Read ${new Date(cell.observed_at).toLocaleString()}`;
        },
        cellRenderer: (p: ICellRendererParams<MatrixRow>) => <PriceCell cell={p.data?.cells[c.id]} />,
      })),
    ],
    [customers],
  );

  const { rowHeight, headerHeight } = gridRowMetrics(theme.density);
  const gridOptions = useMemo<GridOptions<MatrixRow>>(
    () => ({
      ...OPS_LIST_GRID_PAGINATION,
      getRowId: (p) => String(p.data.product.id),
    }),
    [],
  );

  const unavailable = matrix.isError || Boolean(matrix.data?.data_unavailable);
  const productCount = matrix.data?.summary?.product_count ?? rows.length;

  return (
    <Box data-testid="price-matrix-lens">
      <Panel
        title="Price comparison"
        subtitle={
          matrix.data
            ? `${productCount} products × ${customers.length} customers · latest observed shelf price per listing, with its age`
            : 'Latest observed shelf price per listing, with its age'
        }
        flush
      >
        <Box sx={{ px: 2, pb: 1.5 }}>
          <ListingCustomerScopePicker testIdPrefix="price-matrix-customers" />
        </Box>
        <ModuleDataSection
          isLoading={enabled && matrix.isLoading}
          isError={unavailable}
          error={unavailable ? new Error('The price comparison could not be loaded. Nothing here is zero because of this; try again.') : null}
          onRetry={() => void matrix.refetch()}
          isEmpty={!unavailable && !matrix.isLoading && rows.length === 0}
          empty={{
            title: enabled ? 'No scoped products with listings' : 'No customers chosen',
            description: enabled
              ? 'Add listings for in-scope products, or widen the customer picker.'
              : 'Choose one or more customers above to compare their shelf prices.',
          }}
        >
          <Box data-testid="price-matrix-table">
            <EnterpriseDataGrid<MatrixRow>
              rowData={rows}
              columnDefs={columnDefs}
              height={paginatedGridHeight(Math.max(1, Math.min(rows.length, OPS_LIST_PAGE_SIZE)), { rowHeight, headerHeight })}
              gridOptions={gridOptions}
            />
          </Box>
        </ModuleDataSection>
      </Panel>
    </Box>
  );
}
