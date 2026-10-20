import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders as renderThemed } from '@/test-utils/renderWithProviders';

import { WidgetEditorDialog, autoWidgetTitle } from './WidgetEditorDialog';
import type { SemanticMetric } from './types';

const apiPost = vi.fn();
vi.mock('@/lib/api', () => ({
  apiPost: (...args: unknown[]) => apiPost(...args),
  safeDisplayError: (e: unknown) => String(e),
}));

function renderWithProviders(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderThemed(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  apiPost.mockReset();
  apiPost.mockResolvedValue({
    ok: true,
    status: 'ok',
    metric_key: 'cst_sellthrough_units',
    grains: ['customer'],
    validation: { ok: true, message: '' },
    invariants_applied: [],
    data_vintage: null,
    value: 1234,
    rows: [{ customer_id: 3, customer_name: 'Takealot', value: 1234 }],
    series: null,
    message: null,
    handler: 'volume_series',
  });
});

const metrics: SemanticMetric[] = [
  {
    id: 'A3-05',
    key: 'sellout_units',
    label: 'Sell-out units',
    status: 'implemented',
    formula: 'Sum of distributor sell-out units, bucketed by week, month, or quarter',
    allowed_grains: [['period'], ['customer'], ['product']],
    calendar_period: true,
  },
  {
    id: 'CST-01',
    key: 'cst_sellthrough_units',
    label: 'CST sell-through units',
    status: 'implemented',
    formula: 'Sum of customer sell-through units, bucketed by the stored period',
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
    expect(screen.getByTestId('widget-editor-formula')).toHaveTextContent('distributor sell-out units');
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
    expect(screen.getByTestId('widget-editor-formula')).toHaveTextContent('customer sell-through units');
    expect(screen.queryByTestId('widget-editor-period-week')).not.toBeInTheDocument();
    expect(screen.getByTestId('widget-editor-grain-customer')).toBeInTheDocument();
  });

  it('previews the real query result, by name', async () => {
    renderWithProviders(
      <WidgetEditorDialog
        open
        metrics={metrics}
        initial={{ metric_key: 'cst_sellthrough_units', grains: ['customer'], period_grain: null, visual: 'kpi' }}
        onClose={() => undefined}
        onSave={() => undefined}
      />
    );
    await waitFor(() => expect(screen.getByTestId('dashboard-widget-value-preview')).toBeInTheDocument());
    expect(apiPost).toHaveBeenCalledWith(
      '/api/v1/query/execute',
      { metric: 'cst_sellthrough_units', grains: ['customer'], filters: {}, period_grain: null },
      expect.anything(),
    );
  });

  it('only enables charts that fit the breakdown', () => {
    renderWithProviders(
      <WidgetEditorDialog
        open
        metrics={metrics}
        initial={{ metric_key: 'cst_sellthrough_units', grains: ['customer'], period_grain: null, visual: 'donut' }}
        onClose={() => undefined}
        onSave={() => undefined}
      />
    );
    expect(screen.getByTestId('widget-editor-visual-donut')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('widget-editor-visual-pie')).not.toBeDisabled();
    expect(screen.getByTestId('widget-editor-visual-line')).toBeDisabled();
  });

  it('moves off a chart the new breakdown cannot show', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <WidgetEditorDialog
        open
        metrics={metrics}
        initial={{ metric_key: 'cst_sellthrough_units', grains: ['customer'], period_grain: null, visual: 'pie' }}
        onClose={() => undefined}
        onSave={() => undefined}
      />
    );
    await user.click(screen.getByTestId('widget-editor-grain-period'));
    expect(screen.getByTestId('widget-editor-visual-pie')).toBeDisabled();
    expect(screen.getByTestId('widget-editor-visual-line')).toHaveAttribute('aria-pressed', 'true');
  });

  it('finds metrics by meaning, not only by name', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <WidgetEditorDialog open metrics={metrics} initial={{}} onClose={() => undefined} onSave={() => undefined} />
    );
    await user.type(screen.getByTestId('widget-editor-metric-search'), 'retailers');
    expect(screen.getByTestId('widget-editor-metric-cst_sellthrough_units')).toBeInTheDocument();
    expect(screen.queryByTestId('widget-editor-metric-sellout_units')).not.toBeInTheDocument();
  });

  it('saves with a readable suggested title', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    renderWithProviders(
      <WidgetEditorDialog
        open
        metrics={metrics}
        initial={{ metric_key: 'sellout_units', grains: ['period'], period_grain: 'week', visual: 'line' }}
        onClose={() => undefined}
        onSave={onSave}
      />
    );
    await user.click(screen.getByTestId('widget-editor-save'));
    expect(onSave).toHaveBeenCalledWith({
      title: 'Sell-out units by week',
      metric_key: 'sellout_units',
      grains: ['period'],
      period_grain: 'week',
      visual: 'line',
    });
  });

  it('suggests titles in words', () => {
    expect(autoWidgetTitle('Support spend', ['customer'], null)).toBe('Support spend by customer');
    expect(autoWidgetTitle('Fill rate', ['period', 'bu'], null)).toBe('Fill rate by period and product line');
    expect(autoWidgetTitle('Channel stock', [], null)).toBe('Channel stock');
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
