import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { PlanVsExecutedView } from './PlanVsExecutedView';

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({
    isLoading: false,
    isError: false,
    data: {
      data_unavailable: false,
      available_periods: [{ year: 2026, quarter: 2, label: '26Q2' }],
      scorecard: {
        fill_rate: 0.46,
        line_hit_rate: 0.35,
        planned_units: 100,
        shipped_units_in_plan: 62,
        shipped_units_total: 70,
        short_exposure_units: 38,
        deal_stock_units: 10,
        unplanned_intake_units: 5,
        no_po_blind_spot: { line_count: 2, planned_units: 20, planned_value_plan: 1000 },
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
        customer: { short_ships: [], over_ships: [], unplanned_intake: [], no_po_blind_spots: [] },
        product: { short_ships: [], over_ships: [], unplanned_intake: [], no_po_blind_spots: [] },
        bu: { short_ships: [], over_ships: [], unplanned_intake: [], no_po_blind_spots: [] },
      },
      trend: [{ period_label: '26Q2', fill_rate: 0.46, line_hit_rate: 0.35 }],
      drill_rows: [],
      data_quality: { backlog_066_affected_periods: [], backlog_066_message: null },
      scope_notes: { out_of_scope: ['Sell-through — DSI.'] },
    },
    refetch: vi.fn(),
  }),
}));

describe('PlanVsExecutedView', () => {
  it('renders headline KPIs and scope notes', () => {
    render(<PlanVsExecutedView />);
    expect(screen.getByText('Fill rate (headline)')).toBeTruthy();
    expect(screen.getByText('46.0%')).toBeTruthy();
    expect(screen.getByText(/What this view answers/)).toBeTruthy();
    expect(screen.getByTestId('scope-boundary-notes')).toBeTruthy();
  });
});
