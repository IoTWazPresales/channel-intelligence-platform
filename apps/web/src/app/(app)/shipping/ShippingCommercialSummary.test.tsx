import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { ShippingCommercialSummary, type CommercialSummary } from './ShippingCommercialSummary';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (String(url).includes('eta-shifts')) {
      return { slipped_count: 2, improved_count: 1, net_direction: 'slipped', samples: [{ source_key: 'SECRET-KEY', direction: 'slipped', previous_effective: null, current_effective: null, delta_days: 3 }] };
    }
    const body: CommercialSummary = {
      reference_date: '2026-10-10',
      week_start: '2026-10-05',
      week_end: '2026-10-11',
      total_lines: 10,
      pipeline_in_transit: { line_count: 4, quantity: 40, value_by_currency: [{ currency_code: 'USD', amount: 1200 }] },
      arriving_this_week: { total: 3, quantity: 12, line_count: 2, by_distributor: [{ label: 'North', count: 12 }] },
      delivered_this_week: { total: 5, quantity: 8, line_count: 5 },
      overdue: { count: 1, line_count: 1, quantity: 2, pct_of_total_lines: 0.1, pct_of_current_incoming: 0.25 },
      eta_shifts: { slipped_count: 2, improved_count: 1, net_direction: 'slipped' },
    };
    return body;
  }),
}));

function wrap(ui: ReactNode) {
  return renderWithProviders(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
}

describe('ShippingCommercialSummary', () => {
  it('shows the same counts on headline figures and hides definitions until About this figure', async () => {
    wrap(
      <ShippingCommercialSummary
        filterParams={{
          lineState: '',
          cargoStatus: '',
          distributorId: null,
          customerId: null,
          purchaseOrderId: null,
          search: '',
          dateField: 'eta_date',
          dateFrom: '',
          dateTo: '',
          productFamily: '',
          productModel: '',
          currencyCode: '',
          operatingUnit: '',
          podDateFilter: '',
          planQuarter: '',
          planBusinessUnit: '',
          lineupAttribution: '',
          lifecycleBucket: '',
          slipDirection: '',
          cohort: '',
        }}
      />,
    );
    expect(await screen.findByText(/Improved earlier 1/)).toBeTruthy();
    expect(screen.queryByText(/SECRET-KEY/)).toBeNull();
    const about = screen.getByTestId('shipping-about-figure');
    expect(about).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(about);
    await waitFor(() => expect(about).toHaveAttribute('aria-expanded', 'true'));
    expect(screen.getByText(/proof-of-delivery/)).toBeTruthy();
    expect(screen.queryByText(/SECRET-KEY/)).toBeNull();
  });
});
