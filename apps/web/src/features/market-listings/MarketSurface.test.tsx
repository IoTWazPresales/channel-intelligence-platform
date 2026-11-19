import React from 'react';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { marketLensFromLocation } from './MarketChrome';
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
  /** Real totals over all rows (the page above is only the first rows). */
  listingsTotal: null as number | null,
  statusCounts: null as Record<string, number> | null,
  unlinked: null as number | null,
  /** Intelligence call: held open until released, or failing. */
  intelHold: null as Promise<void> | null,
  intelFail: false,
  intelUnavailable: false,
  intelCalls: 0,
  listingUrls: [] as string[],
  /** When set, the listings endpoint serves these pages (page=1, page=2, ...). */
  listingPages: null as Record<string, unknown>[][] | null,
}));

vi.mock('@/lib/api', () => ({
  apiGet: async (url: string) => {
    if (url.includes('/listing-capture/listings')) {
      apiState.listingUrls.push(url);
      const pageNo = Number(/[?&]page=(\d+)/.exec(url)?.[1] ?? '1');
      return {
        items: apiState.listingPages ? (apiState.listingPages[pageNo - 1] ?? []) : apiState.listings,
        total: apiState.listingsTotal ?? apiState.listings.length,
        ...(apiState.statusCounts ? { status_counts: apiState.statusCounts } : {}),
        ...(apiState.unlinked != null ? { unlinked: apiState.unlinked } : {}),
      };
    }
    if (url.includes('/listing-capture/intelligence')) {
      apiState.intelCalls += 1;
      if (apiState.intelHold) await apiState.intelHold;
      if (apiState.intelFail) throw new Error('intelligence failed');
      if (apiState.intelUnavailable) return { items: [], listings: 0, data_unavailable: true };
      return { items: apiState.intel, listings: apiState.intel.length };
    }
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
        coverage: {
          data_unavailable: false,
          customers: [
            {
              customer_id: 4,
              customer_code: 'c4',
              customer_name: 'Counter Four',
              reported: 6,
              watched: 1,
              awaiting_steward: 2,
              failing: 1,
              not_found: 1,
              not_searched: 1,
            },
          ],
        },
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

function resetState() {
  nav.pathname = '/listing-capture';
  nav.search = '';
  apiState.listings = [];
  apiState.intel = [];
  apiState.listingsTotal = null;
  apiState.statusCounts = null;
  apiState.unlinked = null;
  apiState.intelHold = null;
  apiState.intelFail = false;
  apiState.intelUnavailable = false;
  apiState.intelCalls = 0;
  apiState.listingUrls = [];
  apiState.listingPages = null;
}

describe('MarketSurface', () => {
  beforeEach(resetState);

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
    // Not "not yet" until the read has answered: first loading, then the real answer.
    await waitFor(() =>
      expect(screen.getByTestId('listing-last-check')).toHaveTextContent('Last check: not yet'),
    );
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

  it('opens the coverage tab with reported, watched, awaiting steward, failing, not found and not searched', async () => {
    nav.search = 'tab=coverage';
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <MarketSurface />
      </QueryClientProvider>,
    );
    const row = await screen.findByTestId('listing-coverage-row-4');
    expect(screen.getByTestId('listing-coverage-lens')).toBeInTheDocument();
    expect(within(row).getAllByRole('cell').map((cell) => cell.textContent)).toEqual([
      'Counter Four',
      '6',
      '1',
      '2',
      '1',
      '1',
      '1',
    ]);
    expect(marketLensFromLocation('/listing-capture', new URLSearchParams('tab=coverage'))).toBe('coverage');
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
        product_id: null,
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
    // Click the older worklist row (outside listings page 200); detail panel must resolve it
    // from activationLensRows (not only gridRows / listings page_size=200).
    const caseCell = screen.getByText(/Case 42/i);
    fireEvent.click(caseCell.closest('tr') ?? caseCell);
    await waitFor(() => expect(screen.getByTestId('entity-context-panel')).toBeInTheDocument());
    expect(screen.getByTestId('entity-context-panel')).toHaveTextContent(/listing 1/i);
  });

describe('MarketSurface real counts and the intelligence read (BACKLOG-226)', () => {
  beforeEach(resetState);
  const client = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const meta = () => screen.getByText(/monitored listings/);
  const page = (n: number) =>
    Array.from({ length: n }, (_, i) => ({
      id: 1000 - i,
      customer_id: 1,
      customer_name: 'Cust A',
      product_id: 9,
      url: `https://shop.example.test/${i}`,
      marketplace: 'shop',
      status: 'active',
      source: 'manual',
      external_id: null,
    }));
  const intelRow = (id: number, count: number, last: string | null) => ({
    listing_id: id,
    customer_id: 1,
    product_id: 9,
    marketplace: 'shop',
    url: 'u',
    observation_count: count,
    span_days: 3,
    history_status: 'accumulating',
    first_price: 1,
    last_price: 1,
    price_drift_pct: 0,
    activation_status: null,
    last_fetched: last,
    worklist: false,
  });
  const mount = (qc = client()) =>
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <MarketSurface />
      </QueryClientProvider>,
    );

  it('shows the API total and status counts over every row, not the page', async () => {
    apiState.listings = page(3);
    apiState.listingsTotal = 218;
    apiState.statusCounts = { active: 107, out_of_stock: 69, dead_link: 42 };
    apiState.unlinked = 11;
    mount();
    await waitFor(() => expect(meta()).toHaveTextContent('218 monitored listings'));
    const tile = screen.getByText('Active listings').closest('[data-state]') as HTMLElement;
    expect(tile).toHaveTextContent('107');
    expect(tile).toHaveTextContent('of 218');
    expect(tile).toHaveTextContent('111 out of stock or dead');
    const unlinked = screen.getByText('Unlinked listings').closest('[data-state]') as HTMLElement;
    expect(unlinked).toHaveTextContent('11');
  });

  it('reads on past the 200-row page cap until every row is loaded', async () => {
    const all = page(210).map((l, i) => ({ ...l, id: 5000 - i }));
    apiState.listingPages = [all.slice(0, 200), all.slice(200)];
    apiState.listingsTotal = 210;
    apiState.statusCounts = { active: 210 };
    mount();
    await waitFor(() => expect(meta()).toHaveTextContent('210 monitored listings'));
    await waitFor(() => expect(apiState.listingUrls).toHaveLength(2));
    expect(apiState.listingUrls[0]).toContain('page=1&page_size=200');
    expect(apiState.listingUrls[1]).toContain('page=2&page_size=200');
    const tile = screen.getByText('Active listings').closest('[data-state]') as HTMLElement;
    expect(tile).toHaveTextContent('of 210');
  });

  it('shows loading, not 0 or "not yet", while the intelligence call is open', async () => {
    let release: () => void = () => undefined;
    apiState.intelHold = new Promise<void>((resolve) => {
      release = resolve;
    });
    apiState.listings = page(1);
    apiState.listingsTotal = 1;
    apiState.statusCounts = { active: 1 };
    mount();
    await waitFor(() => expect(meta()).toHaveTextContent('1 monitored listings'));
    expect(meta()).toHaveTextContent('Loading observations…');
    expect(meta()).not.toHaveTextContent(/\b0 observations/);
    expect(screen.getByTestId('listing-last-check')).toHaveTextContent('Last check: loading…');
    expect(screen.getByTestId('listing-last-check')).not.toHaveTextContent('not yet');
    apiState.intel = [intelRow(1000, 40, '2026-11-19T16:06:00+00:00'), intelRow(999, 2, null)];
    release();
    await waitFor(() => expect(meta()).toHaveTextContent('42 observations'));
    expect(screen.getByTestId('listing-last-check')).not.toHaveTextContent('not yet');
    expect(screen.getByTestId('listing-last-check')).not.toHaveTextContent('loading');
  });

  it('says so when the intelligence call fails, instead of showing 0 / not yet', async () => {
    apiState.intelFail = true;
    apiState.listings = page(1);
    mount();
    await waitFor(() => expect(meta()).toHaveTextContent('Observations unavailable'));
    expect(screen.getByTestId('listing-last-check')).toHaveTextContent('Last check: unavailable');
    expect(screen.getByTestId('listing-intelligence-error')).toBeInTheDocument();
    expect(meta()).not.toHaveTextContent(/\b0 observations/);
  });

  it('treats data_unavailable from the API as an error state too', async () => {
    apiState.intelUnavailable = true;
    apiState.listings = page(1);
    mount();
    await waitFor(() => expect(screen.getByTestId('listing-intelligence-error')).toBeInTheDocument());
    expect(screen.getByTestId('listing-last-check')).not.toHaveTextContent('not yet');
  });

  it('reads the intelligence once for the page and the timing tab (one shared query)', async () => {
    nav.search = 'tab=intelligence';
    apiState.listings = page(1);
    const { ActivationTimingAlerts } = await import('./ActivationTimingAlerts');
    renderWithProviders(
      <QueryClientProvider client={client()}>
        <MarketSurface />
        <ActivationTimingAlerts />
      </QueryClientProvider>,
    );
    // The surface already renders the timing panel on this tab; a second one is a second reader.
    await waitFor(() => expect(screen.getAllByTestId('activation-timing-empty')).toHaveLength(2));
    expect(apiState.intelCalls).toBe(1);
  });

  it('does not read the intelligence again when a tab mounts and the data is fresh', async () => {
    apiState.listings = page(1);
    const qc = client();
    const first = mount(qc);
    await waitFor(() => expect(apiState.intelCalls).toBe(1));
    await waitFor(() => expect(screen.getByTestId('listing-last-check')).not.toHaveTextContent('loading'));
    first.unmount();
    nav.search = 'tab=intelligence';
    mount(qc);
    await waitFor(() => expect(screen.getByTestId('market-surface')).toBeInTheDocument());
    expect(apiState.intelCalls).toBe(1);
  });
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
