import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { ChannelOpsKpiCards } from './ChannelOpsKpiCards';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async () => ({
    sell_out_this_quarter: { units: 0, revenue: 0, has_data: false },
    sell_out_prior_year_quarter: { units: 0, revenue: 0 },
    sell_out_yoy_pct: null,
    sell_out_data_vintage: { max_transaction_date: '2026-06-12', current_quarter_has_data: false, as_of_date: '2026-10-11' },
    total_inventory_units: 64171,
    weeks_of_cover: 28.7,
    replenishment_threshold_weeks: 4,
    replenishment_flag: true,
    replenishment_pairs_below_threshold: 102,
    replenishment_pair_count: 200,
    distributors_reporting: 0,
    distributors_expected: 0,
    active_customers_this_period: 0,
    active_customers_prior_period: 1294,
    has_velocity_data: true,
    has_forecast_data: false,
    has_reconciliation_data: true,
  })),
}));

function wrap(ui: ReactNode) {
  return renderWithProviders(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
}

describe('ChannelOpsKpiCards', () => {
  it('renders the replenish flag as a headline tile, not loose text', async () => {
    wrap(<ChannelOpsKpiCards />);
    const tile = await screen.findByTestId('channel-ops-replenishment');
    expect(tile.tagName).toBe('DIV');
    expect(await screen.findByText('102')).toBeTruthy();
    expect(tile).toHaveTextContent('Replenish flag');
    expect(tile).toHaveTextContent('Below 4 weeks');
    expect(await screen.findByText('Vintage 2026-06-12')).toBeTruthy();
  });
});
