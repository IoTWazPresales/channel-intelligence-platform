import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { apiGet } from '@/lib/api';

import { ListingCaptureHealth } from './ListingCaptureHealth';

const healthPayload = {
  data_unavailable: false,
  listings_due: 4,
  skipped_not_configured: { 'shop-b': 2 },
  sites: [
    {
      site_id: 1,
      site_key: 'shop-a',
      configured: true,
      listings_due: 2,
      skipped_not_configured: 0,
      newest_observation: { fetched_at: '2026-11-01T08:00:00Z', status: 'ok', price: 199 },
    },
    {
      site_id: 2,
      site_key: 'shop-b',
      configured: false,
      listings_due: 2,
      skipped_not_configured: 2,
      newest_observation: null,
    },
  ],
  configured: [
    {
      customer_id: 11,
      site_key: 'shop-a',
      outcome: 'configured',
      reason: null,
      reasons: [],
      pattern_status: 'derived',
    },
  ],
  exclusions: [
    {
      customer_id: 12,
      site_key: 'shop-b',
      outcome: 'needs_pattern',
      reason: 'needs_details_pattern',
      reasons: ['needs_details_pattern'],
      pattern_status: 'mixed',
    },
  ],
};

const customerListPayload = {
  items: [
    { id: 11, customer_code: 'C-11', customer_name: 'Northwind Trading' },
    { id: 12, customer_code: 'C-12', customer_name: 'Contoso Supply' },
  ],
};

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (url.includes('/listing-capture/capture-health')) return healthPayload;
    if (url.includes('/customers')) return customerListPayload;
    return {};
  }),
}));

function renderHealth() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={client}>
      <ListingCaptureHealth />
    </QueryClientProvider>,
  );
}

describe('ListingCaptureHealth', () => {
  it('shows site posture and link-pattern status from capture health', async () => {
    vi.mocked(apiGet).mockImplementation(async (url: string) => {
      if (url.includes('/listing-capture/capture-health')) return healthPayload;
      if (url.includes('/customers')) return customerListPayload;
      return {};
    });
    renderHealth();
    await waitFor(() => expect(screen.getByTestId('listing-capture-health-due')).toHaveTextContent('4'));
    expect(screen.getByTestId('listing-capture-health-skipped')).toHaveTextContent('2');
    expect(screen.getByTestId('listing-capture-health-ready')).toHaveTextContent('1');
    expect(screen.getByTestId('listing-capture-health-patterns')).toHaveTextContent('1');
    expect(screen.getByTestId('listing-capture-health-site-shop-a')).toHaveTextContent('Configured');
    expect(screen.getByTestId('listing-capture-health-site-shop-a')).toHaveTextContent('ok');
    expect(screen.getByTestId('listing-capture-health-site-shop-a')).toHaveTextContent('199');
    expect(screen.getByTestId('listing-capture-health-site-shop-b')).toHaveTextContent('Not configured');
    expect(screen.getByTestId('listing-capture-health-site-shop-b')).toHaveTextContent('not yet');
    expect(screen.getByTestId('listing-capture-health-discovery-11-shop-a')).toHaveTextContent('One link pattern');
    expect(screen.getByTestId('listing-capture-health-discovery-12-shop-b')).toHaveTextContent(
      'Links do not share one pattern',
    );
    expect(screen.getByTestId('listing-capture-health-discovery-12-shop-b')).toHaveTextContent(
      'Page reader is not configured',
    );
    expect(screen.getByTestId('listing-capture-health-discovery-11-shop-a')).toHaveTextContent('Northwind Trading');
    expect(screen.getByTestId('listing-capture-health-discovery-12-shop-b')).toHaveTextContent('Contoso Supply');
  });

  it('shows em-dash headline figures and hides empty copy when capture health is unavailable', async () => {
    vi.mocked(apiGet).mockImplementation(async (url: string) => {
      if (url.includes('/listing-capture/capture-health')) return { ...healthPayload, data_unavailable: true };
      if (url.includes('/customers')) return customerListPayload;
      return {};
    });
    renderHealth();
    await waitFor(() => expect(screen.getByTestId('listing-capture-health-unavailable')).toBeInTheDocument());
    expect(screen.getByTestId('listing-capture-health-due')).toHaveTextContent('—');
    expect(screen.getByTestId('listing-capture-health-skipped')).toHaveTextContent('—');
    expect(screen.getByTestId('listing-capture-health-ready')).toHaveTextContent('—');
    expect(screen.getByTestId('listing-capture-health-patterns')).toHaveTextContent('—');
    expect(screen.queryByTestId('listing-capture-health-sites-empty')).toBeNull();
    expect(screen.queryByTestId('listing-capture-health-discovery-empty')).toBeNull();
    expect(screen.getByTestId('listing-capture-health-discovery-11-shop-a')).toHaveTextContent('Northwind Trading');
  });

  it('shows em-dash figures when the capture-health request errors', async () => {
    vi.mocked(apiGet).mockImplementation(async (url: string) => {
      if (url.includes('/listing-capture/capture-health')) throw new Error('network');
      if (url.includes('/customers')) return customerListPayload;
      return {};
    });
    renderHealth();
    await waitFor(() => expect(screen.getByTestId('listing-capture-health-unavailable')).toBeInTheDocument());
    expect(screen.getByTestId('listing-capture-health-due')).toHaveTextContent('—');
    expect(screen.queryByTestId('listing-capture-health-sites-empty')).toBeNull();
  });
});
