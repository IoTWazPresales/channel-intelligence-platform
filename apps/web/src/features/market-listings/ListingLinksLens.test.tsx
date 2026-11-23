import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiPost } from '@/lib/api';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { ListingLinksLens } from './ListingLinksLens';

const state = vi.hoisted(() => ({ productId: null as number | null, unavailable: false }));
vi.mock('@/features/shell/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: { id: 'fixture-user', role: 'steward' } }),
}));
vi.mock('@/lib/api', () => ({
  safeDisplayError: (error: unknown) => error instanceof Error ? error.message : 'Request failed',
  apiPut: vi.fn(),
  apiGet: vi.fn(async (url: string) => {
    if (url.includes('/products')) return { items: [{ id: 39, sku: 'SYNTHETIC-39', name: 'Searched fixture product' }] };
    if (state.unavailable) return { items: [], data_unavailable: true };
    return { items: [{
      id: 28, site_id: 4, product_id: state.productId, product_label: 'Known fixture product',
      listing_id: 6, listing_url: 'https://fixture-shop.test/item', customer_name: 'Fixture customer',
      reason: 'ambiguous_identity', status: 'open',
      candidates: [{ product_id: 38, label: 'Suggested fixture product', url: 'https://fixture-shop.test/item' }],
      evidence: { facts: { barcodes: ['000123'], models: ['MODEL-TEST'] } },
    }] };
  }),
  apiPost: vi.fn(async () => ({})),
}));

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  renderWithProviders(<QueryClientProvider client={client}><ListingLinksLens /></QueryClientProvider>);
}

describe('ListingLinksLens discovery rows', () => {
  beforeEach(() => {
    state.productId = null;
    state.unavailable = false;
    vi.clearAllMocks();
  });

  it('renders a no-product listing and links an explicit suggested product', async () => {
    mount();
    await screen.findByText(/Listing has no product/);
    expect(screen.getAllByRole('link', { name: 'https://fixture-shop.test/item' }).length).toBeGreaterThan(0);
    expect(screen.getByText('Barcodes: 000123')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Link to Suggested fixture product' }));
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/v1/listing-capture/link-queue/28', { action: 'link_product', product_id: 38 },
    ));
  });

  it('uses the existing product search and sends the selected product id', async () => {
    mount();
    fireEvent.change(await screen.findByLabelText('Find a product'), { target: { value: 'Searched' } });
    fireEvent.click(await screen.findByRole('option', { name: 'SYNTHETIC-39 Searched fixture product' }));
    fireEvent.click(screen.getByRole('button', { name: 'Link selected product' }));
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/v1/listing-capture/link-queue/28', { action: 'link_product', product_id: 39 },
    ));
  });

  it('allows a no-product listing to be marked not on the site', async () => {
    mount();
    fireEvent.click(await screen.findByRole('button', { name: 'Not on this site' }));
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/v1/listing-capture/link-queue/28', { action: 'not_on_site', url: null },
    ));
  });

  it('keeps the existing product-page confirmation path', async () => {
    state.productId = 17;
    mount();
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/v1/listing-capture/link-queue/28', { action: 'confirm', url: 'https://fixture-shop.test/item' },
    ));
  });

  it('does not report an unavailable queue as empty', async () => {
    state.unavailable = true;
    mount();
    await screen.findByText('The link queue could not be loaded.');
    expect(screen.queryByText('Nothing waiting.')).not.toBeInTheDocument();
  });
});
