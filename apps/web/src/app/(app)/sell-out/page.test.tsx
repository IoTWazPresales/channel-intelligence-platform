import { screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import ChannelOperationsPage from './page';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (url.includes('/channel-ops/summary')) {
      return {
        sell_out_this_quarter: { units: 0, revenue: 0 },
        sell_out_prior_year_quarter: { units: 0, revenue: 0 },
        sell_out_yoy_pct: null,
        total_inventory_units: 0,
        weeks_of_cover: null,
        distributors_reporting: 0,
        distributors_expected: 0,
        active_customers_this_period: 0,
        active_customers_prior_period: 0,
        has_velocity_data: false,
        has_forecast_data: false,
        has_reconciliation_data: false,
      };
    }
    if (url.includes('/channel-ops/weekly-series')) {
      return { weeks: 13, points: [] };
    }
    if (url.includes('/sellout/commercial-summary')) {
      return { total_rows: 0, total_units: 0, total_revenue: 0, latest_period_start: null };
    }
    if (url.includes('/sellout/filter-options')) {
      return { distributors: [], customers: [] };
    }
    if (url.includes('/sellout/commercial-lines')) {
      return { total: 0, skip: 0, limit: 50, items: [] };
    }
    return {};
  }),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={client}>
      <ChannelOperationsPage />
    </QueryClientProvider>
  );
}

describe('ChannelOperationsPage', () => {
  it('renders without crash on empty API responses', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Movement' })).toBeInTheDocument();
    });
    expect(screen.getByText('Overview')).toBeInTheDocument();
    expect(screen.getByText('Sell-out')).toBeInTheDocument();
  });
});
