import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { ListingSitesLens } from './ListingSitesLens';

vi.mock('@/features/shell/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: { id: 'u1', role: 'steward' } }),
}));

vi.mock('@/lib/api', () => ({
  apiGet: async (url: string) => {
    if (url.includes('/listing-capture/sites')) {
      return {
        adapter_keys: ['html_page', 'rest_buybox_json'],
        items: [
          {
            id: 3,
            site_key: 'shop-a',
            display_name: 'Shop A',
            adapter_key: 'html_page',
            product_url_pattern: null,
            page_id_pattern: null,
            search_url_pattern: null,
            details_url_pattern: null,
            first_party_seller: 'North Counter',
            rate_limit_seconds: null,
            is_active: true,
            configured: true,
            missing_fields: [],
            sellers: [
              {
                customer_id: 9,
                customer_name: 'North Counter',
                customer_code: 'nc',
                seller_names: ['North Counter'],
                seller_ids: [],
              },
            ],
          },
        ],
      };
    }
    return {};
  },
  apiPatch: vi.fn(),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
}));

describe('ListingSitesLens', () => {
  it('shows the discovered own seller and does not offer a seller field', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <ListingSitesLens />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByTestId('listing-site-shop-a'));
    await waitFor(() => expect(screen.getByTestId('listing-site-editor')).toBeInTheDocument());
    const own = screen.getByTestId('listing-site-own-seller');
    expect(own).toHaveTextContent('Own seller: North Counter');
    expect(own).toHaveTextContent('It is not typed here.');
    expect(screen.getByTestId('listing-site-seller-9')).toHaveTextContent('North Counter');
    expect(screen.queryByLabelText(/seller/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /remove/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /save seller/i })).toBeNull();
  });
});
