import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { PriceMatrixLens } from './PriceMatrixLens';

vi.mock('./ListingCustomerScopePicker', () => ({
  ListingCustomerScopePicker: () => <div data-testid="mock-customer-picker" />,
}));

vi.mock('./listingCustomerScope', () => ({
  useListingCustomerScope: () => ({
    hydrated: true,
    selectedIds: [1],
    labels: new Map([[1, 'Customer A']]),
    reportingCustomers: [],
    reportingLoading: false,
    toggleCustomer: vi.fn(),
    setCustomers: vi.fn(),
    resetToReporting: vi.fn(),
  }),
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async () => ({
    customers: [{ id: 1, name: 'Customer A' }],
    products: [{ id: 10, sku: 'SKU1', name: 'Phone' }],
    cells: [{ product_id: 10, customer_id: 1, price: 100, listing_id: 5, listing_url: 'https://x', in_stock: true, tenant_srp: 120 }],
    summary: { product_count: 1, cheapest_at: { '1': 1 }, below_srp_count: 1 },
  })),
}));

describe('PriceMatrixLens', () => {
  it('renders the matrix table', async () => {
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <PriceMatrixLens />
      </QueryClientProvider>,
    );
    expect(await screen.findByTestId('price-matrix-table')).toBeTruthy();
    expect(screen.getByText('Customer A')).toBeTruthy();
  });
});