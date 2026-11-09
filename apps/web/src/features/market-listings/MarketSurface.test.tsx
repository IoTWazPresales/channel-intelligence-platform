import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { ListingUrl, listingUrlState, MarketSurface } from './MarketSurface';

const nav = vi.hoisted(() => ({
  pathname: '/listing-capture',
  search: '',
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
  usePathname: () => nav.pathname,
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: () => <div data-testid="market-grid" />,
}));

vi.mock('@/features/commercial-planner/EntitySearchAutocomplete', () => ({
  EntitySearchAutocomplete: () => null,
}));

const apiState = vi.hoisted(() => ({
  listings: [] as Record<string, unknown>[],
  intel: [] as Record<string, unknown>[],
}));

vi.mock('@/lib/api', () => ({
  apiGet: async (url: string) => {
    if (url.includes('/listing-capture/listings')) return { items: apiState.listings, total: apiState.listings.length };
    if (url.includes('/listing-capture/intelligence')) return { items: apiState.intel, listings: apiState.intel.length };
    if (url.includes('/listing-capture/proposals')) return { items: [] };
    if (url.includes('/listing-capture/observations')) return { items: [] };
    if (url.includes('/listing-capture/capture-health')) {
      return {
        data_unavailable: false,
        listings_due: 3,
        skipped_not_configured: {},
        sites: [],
        configured: [],
        exclusions: [],
      };
    }
    if (url.includes('/customers')) return { items: [] };
    if (url.includes('/competition/mappings')) return [];
    if (url.includes('/competition/prices')) return [];
    return {};
  },
  apiPost: vi.fn(),
  apiPostFormData: vi.fn(),
}));

describe('MarketSurface', () => {
  beforeEach(() => {
    nav.pathname = '/listing-capture';
    nav.search = '';
    apiState.listings = [];
    apiState.intel = [];
  });

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
    expect(screen.getByTestId('listing-last-check')).toHaveTextContent(
      'Checks run every 30 minutes while this computer is running',
    );
    expect(screen.getByTestId('listing-last-check')).toHaveTextContent('Last check: not yet');
    expect(screen.getByTestId('market-add-listing')).toBeInTheDocument();
    expect(screen.queryByText(/static JSON stub/i)).toBeNull();
    await waitFor(() => expect(screen.getByTestId('listing-capture-health-due')).toHaveTextContent('3'));
    expect(screen.getByText('No sites in capture health.')).toBeInTheDocument();
    expect(screen.getByText('No link-pattern status yet.')).toBeInTheDocument();
  });

  it('leaves capture health off the competitor lenses', async () => {
    nav.pathname = '/competition';
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <MarketSurface />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('market-surface')).toBeInTheDocument());
    expect(screen.queryByTestId('listing-capture-health')).toBeNull();
  });
});


  it('worklist=1 activation lens shows intel worklist rows beyond listings page_size=200', async () => {
    nav.pathname = '/listing-capture';
    nav.search = 'tab=intelligence&activation=not_activated&worklist=1';
    // Listings page only has the newest id (simulates page_size cap); intel has an older worklist row.
    apiState.listings = [
      {
        id: 200,
        customer_id: 1,
        customer_name: 'Cust A',
        product_id: 9,
        product_name: 'SKU-NEW',
        url: 'https://shop.example.test/new',
        marketplace: 'shop',
        status: 'active',
        source: 'manual',
        external_id: null,
      },
    ];
    apiState.intel = [
      {
        listing_id: 1,
        customer_id: 1,
        product_id: 8,
        marketplace: 'shop',
        url: 'https://shop.example.test/old',
        observation_count: 5,
        span_days: 21,
        history_status: 'ready',
        first_price: 100,
        last_price: 120,
        price_drift_pct: 0.2,
        activation_status: 'not_activated',
        case_price: 99,
        case_id: 42,
        worklist: true,
      },
      {
        listing_id: 200,
        customer_id: 1,
        product_id: 9,
        marketplace: 'shop',
        url: 'https://shop.example.test/new',
        observation_count: 2,
        span_days: 14,
        history_status: 'ready',
        first_price: 50,
        last_price: 50,
        price_drift_pct: 0,
        activation_status: 'price_consistent',
        case_price: 50,
        case_id: 43,
        worklist: false,
      },
    ];
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <MarketSurface />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('market-activation-lens')).toBeInTheDocument());
    // Older worklist listing (id 1) must appear even though it is outside listings page 200.
    await waitFor(() => expect(screen.getByText(/Case 42/i)).toBeInTheDocument());
    expect(screen.queryByText(/Case 43/i)).toBeNull();
  });

describe('ListingUrl (N-0039)', () => {
  const url = 'https://shop-a.example.test/glide/ID98174082';

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
    const sku = 'https://shop-a.example.test/ID222547542';
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
