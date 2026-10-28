import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { DashboardWidgetCard } from './DashboardWidgetCard';
import type { DashboardWidget, SemanticMetric } from './types';

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({
    isLoading: false,
    isError: false,
    error: null,
    data: {
      ok: true,
      status: 'ok',
      value: 12,
      rows: null,
      series: null,
      message: null,
      data_vintage: { period_grain: 'week', bucket_min: '2026-01-05', bucket_max: '2026-03-29', formula: 'sellout_units' },
    },
  }),
}));

const widget: DashboardWidget = {
  id: 7,
  dashboard_id: 1,
  title: 'Sell-out',
  visual: 'kpi',
  metric_key: 'sellout_units',
  grains: ['period'],
  filters: {},
  period_grain: 'week',
  layout_json: null,
  saved_report_id: null,
  sort_order: 0,
};

const metric: SemanticMetric = {
  id: 'A3-05',
  key: 'sellout_units',
  label: 'Sell-out units',
  status: 'implemented',
  formula: 'Sum of distributor sell-out units, bucketed by week, month, or quarter',
  allowed_grains: [['period']],
};

describe('DashboardWidgetCard', () => {
  it('shows the KPI on a headline figure and keeps the definition behind About this figure', async () => {
    const user = userEvent.setup();
    render(<DashboardWidgetCard widget={widget} metric={metric} onEdit={() => undefined} onDelete={() => undefined} onPromote={() => undefined} />);
    expect(screen.getByTestId('dashboard-widget-value-7')).toHaveTextContent('12');
    expect(screen.getByText('Sell-out units')).toBeTruthy();
    const about = screen.getByRole('button', { name: 'About this figure' });
    expect(screen.queryByTestId('dashboard-widget-formula-7')).toBeNull();
    await user.hover(about);
    expect(await screen.findByTestId('dashboard-widget-formula-7')).toHaveTextContent('Sum of distributor sell-out units');
    expect(document.body.textContent ?? '').not.toContain('sellout_units');
  });
});
