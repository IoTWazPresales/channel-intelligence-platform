import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { WidgetEditorDialog } from './WidgetEditorDialog';
import type { SemanticMetric } from './types';

const metrics: SemanticMetric[] = [
  {
    id: 'A3-05',
    key: 'sellout_units',
    label: 'Sell-out units',
    status: 'implemented',
    formula: 'Σ units from fact_sales_sellout, bucketed by period_grain',
    allowed_grains: [['period'], ['customer'], ['product']],
    calendar_period: true,
  },
  {
    id: 'CST-01',
    key: 'cst_sellthrough_units',
    label: 'CST sell-through units',
    status: 'implemented',
    formula: 'Σ units_sold from fact_customer_sellthrough',
    allowed_grains: [['customer'], ['period']],
    calendar_period: true,
  },
];

describe('WidgetEditorDialog', () => {
  it('shows formula and week grain for sell-out line', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <WidgetEditorDialog
        open
        metrics={metrics}
        initial={{ metric_key: 'sellout_units', grains: ['period'], period_grain: 'week', visual: 'line' }}
        onClose={() => undefined}
        onSave={() => undefined}
      />
    );
    expect(screen.getByTestId('widget-editor-formula')).toHaveTextContent('fact_sales_sellout');
    expect(screen.getByTestId('widget-editor-period-week')).toBeInTheDocument();
    await user.click(screen.getByTestId('widget-editor-visual-line'));
    expect(screen.getByTestId('widget-editor-visual-line')).toHaveAttribute('aria-pressed', 'true');
  });

  it('hides calendar chips for CST by customer', () => {
    renderWithProviders(
      <WidgetEditorDialog
        open
        metrics={metrics}
        initial={{
          metric_key: 'cst_sellthrough_units',
          grains: ['customer'],
          period_grain: null,
          visual: 'bar',
        }}
        onClose={() => undefined}
        onSave={() => undefined}
      />
    );
    expect(screen.getByTestId('widget-editor-formula')).toHaveTextContent('fact_customer_sellthrough');
    expect(screen.queryByTestId('widget-editor-period-week')).not.toBeInTheDocument();
    expect(screen.getByTestId('widget-editor-grain-customer')).toBeInTheDocument();
  });

  it('offers week/month/quarter only — never day', async () => {
    renderWithProviders(
      <WidgetEditorDialog
        open
        metrics={metrics}
        initial={{ metric_key: 'sellout_units', grains: ['period'], period_grain: 'quarter', visual: 'line' }}
        onClose={() => undefined}
        onSave={() => undefined}
      />
    );
    expect(screen.getByTestId('widget-editor-period-week')).toBeInTheDocument();
    expect(screen.getByTestId('widget-editor-period-month')).toBeInTheDocument();
    expect(screen.getByTestId('widget-editor-period-quarter')).toBeInTheDocument();
    expect(screen.queryByTestId('widget-editor-period-day')).not.toBeInTheDocument();
  });

  it('hides calendar chips for A1 fill_rate even when grain includes period', () => {
    const fill: SemanticMetric = {
      id: 'A1-01',
      key: 'fill_rate',
      label: 'Fill rate',
      status: 'implemented',
      formula: 'Σ min(shipped, planned) / Σ planned',
      allowed_grains: [['period'], ['period', 'bu']],
    };
    renderWithProviders(
      <WidgetEditorDialog
        open
        metrics={[...metrics, fill]}
        initial={{ metric_key: 'fill_rate', grains: ['period'], period_grain: null, visual: 'kpi' }}
        onClose={() => undefined}
        onSave={() => undefined}
      />
    );
    expect(screen.queryByTestId('widget-editor-period-week')).not.toBeInTheDocument();
  });
});
