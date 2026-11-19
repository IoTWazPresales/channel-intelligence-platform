import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiGet } from '@/lib/api';

import { PlanVsExecutedView } from './PlanVsExecutedView';

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/plan-vs-executed',
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: () => <div data-testid="enterprise-grid-mock" />,
}));

vi.mock('@/lib/api', () => ({ apiGet: vi.fn() }));

const apiGetMock = vi.mocked(apiGet);

function payload() {
  return {
  data_unavailable: false,
  period_range: { from: '26Q2', to: '26Q2' },
  drill: { customer_id: null, product_id: null, sales_model: null },
  product_group_by: 'description',
  default_period: '26Q2',
  available_periods: [
    { year: 2026, quarter: 3, label: '26Q3' },
    { year: 2026, quarter: 2, label: '26Q2' },
    { year: 2024, quarter: 2, label: '24Q2' },
  ],
  scorecard: {
    fill_rate: 0.46,
    line_hit_rate: 0.35,
    planned_units: 100,
    shipped_units_in_plan: 62,
    shipped_units_total: 70,
    pipeline_units_in_plan: 8,
    short_exposure_units: 38,
    deal_stock_units: 10,
    unplanned_intake_units: 5,
    no_po_blind_spot: { line_count: 2, planned_units: 20, planned_value_plan: 1000 },
    pending_split: {
      inbound_pipeline_lines: 1,
      inbound_pipeline_units: 8,
      cold_lines: 3,
      cold_planned_units: 12,
    },
    value: {
      planned_value_plan: 5000,
      shipped_value_plan: 3000,
      shipped_value_cost: 2500,
      short_exposure_value_plan: 800,
      deal_stock_value_plan: 200,
      unplanned_intake_value_plan: 100,
      fx_partial: true,
    },
    flag_summary: { matched: 10, short: 5, over: 2 },
    buckets: { executed_vs_plan: 17, off_plan: 3, pending: 4 },
  },
  exceptions: {
    customer: {
      short_ships: [{ key: 1, label: 'A', units: 10, value_plan: null, value_cost: null }],
      over_ships: [],
      unplanned_intake: [],
      no_po_blind_spots: [],
    },
    product: { short_ships: [], over_ships: [], unplanned_intake: [], no_po_blind_spots: [] },
    bu: { short_ships: [], over_ships: [], unplanned_intake: [], no_po_blind_spots: [] },
  },
  trend: [{ period_label: '26Q2', fill_rate: 0.46, line_hit_rate: 0.35 }],
  drill_rows: [],
  data_quality: { backlog_066_affected_periods: [], backlog_066_message: null },
  scope_notes: { out_of_scope: ['Sell-through — DSI.'] },
};
}

function pveCalls() {
  return apiGetMock.mock.calls.map((c) => String(c[0])).filter((u) => u.startsWith('/api/v1/plan-vs-executed'));
}

describe('PlanVsExecutedView first load', () => {
  beforeEach(() => {
    apiGetMock.mockReset();
  });

  it('makes ONE request: the default-period response is reused for the explicit default period', async () => {
    apiGetMock.mockImplementation(async (url: string) =>
      url.startsWith('/api/v1/plan-vs-executed') ? payload() : [],
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <PlanVsExecutedView />
      </QueryClientProvider>,
    );

    // Once the default period is adopted, the query key moves to the explicit period...
    await waitFor(() => {
      const keys = qc.getQueryCache().findAll({ queryKey: ['plan-vs-executed'] }).map((q) => q.queryKey);
      expect(keys.some((k) => k[1] === '26Q2' && k[2] === '26Q2')).toBe(true);
    });
    await screen.findAllByText(/26Q2/);
    // ...without a second round trip.
    expect(pveCalls()).toEqual(['/api/v1/plan-vs-executed?rank_by=units&product_group_by=description']);
  });
});
