import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { PriceMatrixLens, productLabel } from './PriceMatrixLens';

vi.mock('next/navigation', () => ({
  usePathname: () => '/listing-capture',
}));

vi.mock('./ListingCustomerScopePicker', () => ({
  ListingCustomerScopePicker: () => <div data-testid="mock-customer-picker" />,
}));

vi.mock('./listingCustomerScope', () => ({
  useListingCustomerScope: () => ({
    hydrated: true,
    selectedIds: [1, 2],
    labels: new Map([
      [1, 'Customer A'],
      [2, 'Customer B'],
    ]),
    reportingCustomers: [],
    reportingLoading: false,
    toggleCustomer: vi.fn(),
    setCustomers: vi.fn(),
    resetToReporting: vi.fn(),
  }),
}));

const DAY = 86_400_000;
const payload = vi.hoisted(() => ({ value: null as unknown }));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async () => payload.value),
}));

function matrixPayload() {
  const now = Date.now();
  return {
    customers: [
      { id: 1, name: 'Customer A' },
      { id: 2, name: 'Customer B' },
    ],
    products: [
      {
        id: 10,
        sales_model_name: 'MODEL-X1',
        sku: 'SKU1',
        name: 'Phone',
        srp: null,
        srp_source: null,
        srp_reason: 'srp_source_pending',
      },
    ],
    cells: [
      {
        product_id: 10,
        customer_id: 1,
        price: 100,
        observed_at: new Date(now - 3 * DAY).toISOString(),
        listing_id: 5,
        listing_url: 'https://shop.example.test/p',
        in_stock: true,
        srp: null,
        srp_reason: 'srp_source_pending',
        promo: { name: 'Spring deal', window_start: '2026-11-01', window_end: '2026-11-30', promotion_type: 'Sell-Through PP' },
      },
      {
        product_id: 10,
        customer_id: 2,
        price: 90,
        observed_at: new Date(now - 20 * DAY).toISOString(),
        listing_id: 6,
        listing_url: null,
        in_stock: false,
        srp: null,
        srp_reason: 'srp_source_pending',
        promo: null,
      },
    ],
    summary: { product_count: 1, below_srp_count: null },
    srp_source: null,
  };
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={client}>
      <PriceMatrixLens />
    </QueryClientProvider>,
  );
}

describe('PriceMatrixLens', () => {
  beforeEach(() => {
    payload.value = matrixPayload();
  });

  it('renders the matrix on the shared AG Grid with sales model names and price ages', async () => {
    mount();
    const table = await screen.findByTestId('price-matrix-table');
    expect(table.querySelector('.ag-root-wrapper')).not.toBeNull();
    await waitFor(() => expect(screen.getByTestId('price-matrix-product-10')).toBeInTheDocument());
    expect(within(screen.getByTestId('price-matrix-product-10')).getByText('MODEL-X1')).toBeInTheDocument();
    expect(screen.getByText('Customer A')).toBeInTheDocument();
    expect(screen.getByTestId('price-matrix-age-10-1')).toHaveTextContent('3 days ago');
    expect(screen.getByTestId('price-matrix-age-10-2')).toHaveTextContent('20 days ago');
    expect(screen.getByText('Out of stock')).toBeInTheDocument();
    expect(screen.getByText('Sell-Through PP')).toBeInTheDocument();
  });

  it('shows SRP as pending, never a number, while no SRP source is chosen', async () => {
    mount();
    await waitFor(() => expect(screen.getByTestId('price-matrix-srp-10')).toBeInTheDocument());
    expect(screen.getByTestId('price-matrix-srp-10')).toHaveTextContent('SRP source not yet chosen');
    expect(screen.queryByText('Below SRP')).toBeNull();
  });

  it('shows the Below SRP chip only on cells the API flags below_srp', async () => {
    const base = matrixPayload();
    payload.value = {
      ...base,
      cells: [
        { ...base.cells[0], srp: 120, srp_reason: null, below_srp: true },
        { ...base.cells[1], srp: 120, srp_reason: null, below_srp: false },
      ],
    };
    mount();
    await waitFor(() => expect(screen.getByTestId('price-matrix-age-10-1')).toBeInTheDocument());
    expect(screen.getAllByText('Below SRP')).toHaveLength(1);
  });

  it('shows no per-cell SRP line while no cell has an SRP from any source', async () => {
    mount();
    await waitFor(() => expect(screen.getByTestId('price-matrix-age-10-1')).toBeInTheDocument());
    expect(screen.queryByTestId('price-matrix-cell-srp-10-1')).toBeNull();
    expect(screen.queryByTestId('price-matrix-cell-srp-10-2')).toBeNull();
  });

  it('shows each cell SRP with the label of the source it came from', async () => {
    const base = matrixPayload();
    payload.value = {
      ...base,
      customers: [...base.customers, { id: 3, name: 'Customer C' }],
      products: [{ ...base.products[0], srp: null, srp_source: null, srp_reason: 'srp_varies_by_customer' }],
      cells: [
        { ...base.cells[0], srp: 120, srp_source: 'sell_out_price', srp_period: '2026-07-06', srp_reason: null, below_srp: true },
        { ...base.cells[1], srp: 1234.5, srp_source: 'lineup_price', srp_period: '2026-10-01', srp_reason: null },
        {
          ...base.cells[0],
          customer_id: 3,
          listing_id: 7,
          srp: 99,
          srp_source: 'website_off_promo_price',
          srp_reason: null,
          promo: null,
        },
      ],
      srp_source_order: ['sell_out_price', 'lineup_price', 'website_off_promo_price'],
    };
    mount();
    await waitFor(() => expect(screen.getByTestId('price-matrix-cell-srp-10-1')).toBeInTheDocument());
    // The sell-out and line-up labels carry the period the figure came from, formatted by the UI.
    expect(screen.getByTestId('price-matrix-cell-srp-10-1')).toHaveTextContent('SRP 120 · Sell-out · Jul 2026');
    expect(screen.getByTestId('price-matrix-cell-srp-10-2')).toHaveTextContent('SRP 1,234.5 · Line-up · Oct 2026');
    // The website tier has no period: just its label.
    expect(screen.getByTestId('price-matrix-cell-srp-10-3').textContent).toBe('SRP 99 · Website off-promo price');
    // The product-level column states that the customers' figures differ; the old pending text is gone.
    expect(screen.getByTestId('price-matrix-srp-10')).toHaveTextContent('Varies by customer');
    expect(screen.queryByText('SRP source not yet chosen')).toBeNull();
  });

  it('shows the source without a period when the API gives none or an unreadable one', async () => {
    const base = matrixPayload();
    payload.value = {
      ...base,
      cells: [
        { ...base.cells[0], srp: 120, srp_source: 'sell_out_price', srp_period: null, srp_reason: null },
        { ...base.cells[1], srp: 121, srp_source: 'lineup_price', srp_period: 'not-a-date', srp_reason: null },
      ],
    };
    mount();
    await waitFor(() => expect(screen.getByTestId('price-matrix-cell-srp-10-1')).toBeInTheDocument());
    expect(screen.getByTestId('price-matrix-cell-srp-10-1').textContent).toBe('SRP 120 · Sell-out');
    expect(screen.getByTestId('price-matrix-cell-srp-10-2').textContent).toBe('SRP 121 · Line-up');
  });

  it('shows the product SRP once when every customer agrees, and "No SRP" for a gap beside cells that have one', async () => {
    const base = matrixPayload();
    payload.value = {
      ...base,
      products: [{ ...base.products[0], srp: 120, srp_source: 'sell_out_price', srp_reason: null }],
      cells: [
        { ...base.cells[0], srp: 120, srp_source: 'sell_out_price', srp_reason: null },
        { ...base.cells[1], srp: null, srp_source: null, srp_reason: 'no_srp_for_product' },
      ],
    };
    mount();
    await waitFor(() => expect(screen.getByTestId('price-matrix-srp-10')).toBeInTheDocument());
    expect(screen.getByTestId('price-matrix-srp-10')).toHaveTextContent('120');
    expect(screen.getByTestId('price-matrix-cell-srp-10-2')).toHaveTextContent('No SRP');
  });

  it('has no "Cheapest at" figures', async () => {
    mount();
    await screen.findByTestId('price-matrix-table');
    expect(screen.queryByText(/cheapest at/i)).toBeNull();
  });

  it('shows an error state, not an empty matrix, when the API reports data_unavailable', async () => {
    payload.value = { ...matrixPayload(), data_unavailable: true };
    mount();
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('could not be loaded'));
    expect(screen.queryByTestId('price-matrix-table')).toBeNull();
  });

  it('keeps every customer column and puts customers with listings first', async () => {
    const base = matrixPayload();
    payload.value = { ...base, customers: [{ id: 3, name: 'Customer C' }, ...base.customers] };
    mount();
    await waitFor(() => expect(screen.getByText('Customer C')).toBeInTheDocument());
    const headers = Array.from(document.querySelectorAll('.ag-header-cell-text')).map((e) => e.textContent);
    expect(headers).toEqual(['Product', 'SRP', 'Customer A', 'Customer B', 'Customer C']);
  });

  it('labels a product by sales model name first', () => {
    expect(productLabel({ id: 1, sales_model_name: 'M', sku: 'S', name: 'N' })).toBe('M');
    expect(productLabel({ id: 1, sales_model_name: null, sku: 'S', name: 'N' })).toBe('S');
    expect(productLabel({ id: 7 })).toBe('Product 7');
  });

  it('has no hex or rgba colour literals in the component source', () => {
    const source = readFileSync(join(__dirname, 'PriceMatrixLens.tsx'), 'utf8');
    expect(source).not.toMatch(/rgba?\(/);
    expect(source).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});
