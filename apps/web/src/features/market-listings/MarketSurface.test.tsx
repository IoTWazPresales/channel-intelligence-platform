import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { MarketSurface } from './MarketSurface';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/listing-capture',
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: () => <div data-testid="market-grid" />,
}));

vi.mock('@/features/commercial-planner/EntitySearchAutocomplete', () => ({
  EntitySearchAutocomplete: () => null,
}));

vi.mock('@/lib/api', () => ({
  apiGet: async (url: string) => {
    if (url.includes('/listing-capture/listings')) return { items: [], total: 0 };
    if (url.includes('/listing-capture/intelligence')) return { items: [], listings: 0 };
    if (url.includes('/listing-capture/proposals')) return { items: [] };
    if (url.includes('/listing-capture/observations')) return { items: [] };
    if (url.includes('/customers')) return { items: [] };
    if (url.includes('/competition/mappings')) return [];
    if (url.includes('/competition/prices')) return [];
    return {};
  },
  apiPost: vi.fn(),
  apiPostFormData: vi.fn(),
}));

describe('MarketSurface', () => {
  it('mounts lab chrome and the listings lens, not the /market stub', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <MarketSurface />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('market-surface')).toBeInTheDocument());
    expect(screen.getByRole('heading', { name: /Market & Listings/i })).toBeInTheDocument();
    expect(screen.getByTestId('market-listings-lens')).toBeInTheDocument();
    expect(screen.getByTestId('market-add-listing')).toBeInTheDocument();
    expect(screen.queryByText(/static JSON stub/i)).toBeNull();
  });
});
