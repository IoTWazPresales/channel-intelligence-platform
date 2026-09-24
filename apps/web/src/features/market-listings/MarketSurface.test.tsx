import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { ListingUrl, listingUrlState, MarketSurface } from './MarketSurface';

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

describe('ListingUrl (N-0039)', () => {
  const url = 'https://www.takealot.com/asus-zenscreen/PLID98174082';

  it('derives state: dead_link wins, then url_verified_at', () => {
    expect(listingUrlState({ status: 'dead_link', url_verified_at: '2026-09-24T00:00:00Z' })).toBe('dead');
    expect(listingUrlState({ status: 'active', url_verified_at: '2026-09-24T00:00:00Z' })).toBe('verified');
    expect(listingUrlState({ status: 'active', url_verified_at: null })).toBe('unverified');
    expect(listingUrlState({ status: 'out_of_stock' })).toBe('unverified');
  });

  it('renders a verified URL as a new-tab anchor', () => {
    renderWithProviders(<ListingUrl listing={{ url, status: 'active', url_verified_at: '2026-09-24T08:00:00Z' }} />);
    const a = screen.getByRole('link', { name: url });
    expect(a).toHaveAttribute('href', url);
    expect(a).toHaveAttribute('target', '_blank');
    expect(a).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.queryByText('Unverified link')).toBeNull();
  });

  it('renders an unverified URL as plain text with an Unverified link marker', () => {
    const sku = 'https://www.takealot.com/PLID222547542';
    renderWithProviders(<ListingUrl listing={{ url: sku, status: 'active', url_verified_at: null }} />);
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText(sku)).toBeInTheDocument();
    expect(screen.getByText('Unverified link')).toBeInTheDocument();
  });

  it('renders a dead link with no anchor and a Dead link marker', () => {
    renderWithProviders(<ListingUrl listing={{ url, status: 'dead_link', url_verified_at: '2026-09-24T08:00:00Z' }} />);
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText(url)).toBeInTheDocument();
    expect(screen.getByText('Dead link')).toBeInTheDocument();
  });

  it('never anchors a non-http URL even when verified', () => {
    renderWithProviders(
      <ListingUrl listing={{ url: 'javascript:alert(1)', status: 'active', url_verified_at: '2026-09-24T08:00:00Z' }} />,
    );
    expect(screen.queryByRole('link')).toBeNull();
  });
});
