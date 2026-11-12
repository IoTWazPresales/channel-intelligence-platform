import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { ListingOffersSupply } from './ListingOffersSupply';

vi.mock('@/lib/api', () => ({
  apiGet: async (url: string) => {
    if (url.includes('/offers')) {
      return {
        shoppers_price: 1299,
        buy_box_label: 'Competition',
        buy_box_seller: 'Harbour Stall',
        items: [
          {
            seller_name: 'Harbour Stall',
            price: 1299,
            availability: 'in_stock',
            is_buy_box: true,
            label: 'Competition',
          },
        ],
      };
    }
    return { status: 'not linked', rows: [] };
  },
}));

describe('ListingOffersSupply', () => {
  it('labels a marketplace seller on the buy box as competition', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <ListingOffersSupply listingId={8} customerId={4} productId={null} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('listing-buy-box')).toHaveTextContent('Competition'));
    expect(screen.getByTestId('listing-buy-box')).toHaveTextContent('Harbour Stall');
    expect(screen.getByText(/Buy box · Competition: Harbour Stall/)).toBeInTheDocument();
  });
});
