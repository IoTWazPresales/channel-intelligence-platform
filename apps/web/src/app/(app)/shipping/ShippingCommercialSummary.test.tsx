import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { apiGet } from '@/lib/api';

import type { ShippingFilterParams } from './buildShippingLinesUrl';
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

describe('ShippingCommercialSummary: a vessel click refreshes only the grid', () => {
  const base: ShippingFilterParams = {
    lineState: '', cargoStatus: '', distributorId: null, customerId: null, purchaseOrderId: null, search: '', dateField: 'eta_date', dateFrom: '',
    dateTo: '', productFamily: '', productModel: '', currencyCode: '', operatingUnit: '', podDateFilter: '', planQuarter: '', planBusinessUnit: '',
    lineupAttribution: '', lifecycleBucket: '', slipDirection: '', cohort: '',
  };
  const tileCalls = () => vi.mocked(apiGet).mock.calls.filter(([url]) => /commercial-summary|eta-shifts/.test(String(url))).length;

  it('makes no new tile or ETA-shift request when a vessel is picked while a cohort and a distributor filter are active', async () => {
    vi.mocked(apiGet).mockClear();
    const active: ShippingFilterParams = { ...base, distributorId: 7, cohort: 'overdue', lineState: 'shipped' };
    // What selectVessel leaves behind: the vessel set, the line-picking filters cleared, the distributor untouched.
    const picked: ShippingFilterParams = { ...active, vessel: 'i:2026-09-19|2026-11-05|ZAJNB|asia_durban', cohort: '', lineState: '' };
    const client = new QueryClient();
    const tree = (p: ShippingFilterParams, vessel: string | null) => (
      <QueryClientProvider client={client}>
        <ShippingCommercialSummary filterParams={p} selectedVesselKey={vessel} />
      </QueryClientProvider>
    );
    const view = renderWithProviders(tree(active, null));
    expect(await screen.findByText(/Improved earlier 1/)).toBeTruthy();
    const before = tileCalls();
    expect(before).toBe(2); // the summary and the ETA shifts, once each
    view.rerender(tree(picked, picked.vessel ?? null));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(tileCalls()).toBe(before); // before the fix: 4, the tiles asked again
    expect(screen.getByText(/Improved earlier 1/)).toBeTruthy(); // and they still show their figures
  });
});
