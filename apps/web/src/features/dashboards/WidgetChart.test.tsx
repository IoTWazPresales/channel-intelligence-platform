import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { formatChartValue } from '@/features/workbench-ui/charts';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { WidgetChart } from './WidgetChart';

// Twenty customers: more than any starting top N, so the old chart would have folded a tail into "Other (n)".
const rows = Array.from({ length: 20 }, (_, i) => ({ customer_id: i + 1, customer_name: `Customer ${i + 1}`, value: (i + 1) * 100 }));
const total = rows.reduce((s, r) => s + r.value, 0);

describe('WidgetChart (N-0114)', () => {
  it('columns by customer: the viewer top N with a caption, no "Other (n)" bar, names and values as given', () => {
    renderWithProviders(<WidgetChart visual="bar" grains={['customer']} series={null} rows={rows} unit="units" metricLabel="Sell-out" />);
    const chart = screen.getByTestId('dashboard-widget-chart');
    expect(chart.textContent).not.toMatch(/Other \(/);
    expect(within(chart).getByText('Top 10 of 20')).toBeInTheDocument();
    // Ten bars run horizontal: the category title sits above the names, the value title under the axis.
    expect(within(chart).getByTestId('chart-axis-title-top')).toHaveTextContent('Customer');
    expect(within(chart).getByTestId('chart-axis-title-bottom')).toHaveTextContent('Sell-out (units)');
    const body = within(within(chart).getByRole('table')).getAllByRole('row').slice(1);
    expect(body).toHaveLength(10);
    expect(body[0]).toHaveTextContent('Customer 20');
    expect(within(body[0]).getByRole('cell').textContent).toBe(formatChartValue(2000, 'units', 'full'));
  });

  it('pie by customer: legend of full names, shares of the full total, no "Other (n)" slice', () => {
    renderWithProviders(<WidgetChart visual="pie" grains={['customer']} series={null} rows={rows} unit="usd" metricLabel="Support spend" />);
    const chart = screen.getByTestId('dashboard-widget-chart');
    expect(chart.textContent).not.toMatch(/Other \(/);
    expect(within(chart).getByText('Top 5 of 20 shown · shares are of the full total')).toBeInTheDocument();
    const legend = within(chart).getByTestId('share-chart-legend');
    expect(within(legend).getAllByRole('listitem')).toHaveLength(5);
    // 2 000 of 21 000 = 9.5%, against every customer, not only the five drawn.
    expect(legend.textContent).toContain(`${((2000 / total) * 100).toFixed(1)}%`);
  });

  it('ranked bars by customer start at the dashboard top N of 15', () => {
    renderWithProviders(<WidgetChart visual="hbar" grains={['customer']} series={null} rows={rows} unit="units" metricLabel="Sell-out" />);
    const chart = screen.getByTestId('dashboard-widget-chart');
    expect(chart.textContent).not.toMatch(/Other \(/);
    expect(within(chart).getByText('Top 15 of 20')).toBeInTheDocument();
  });

  it('a single series over time has titles and no legend', () => {
    const series = [
      { bucket_key: '2026-W40', value: 10 },
      { bucket_key: '2026-W41', value: 12 },
    ];
    renderWithProviders(<WidgetChart visual="line" grains={['period']} series={series} rows={null} unit="units" metricLabel="Sell-out" />);
    const chart = screen.getByTestId('dashboard-widget-chart');
    expect(within(chart).getByTestId('chart-axis-title-bottom')).toHaveTextContent('Period');
    expect(within(chart).getByTestId('chart-axis-title-top')).toHaveTextContent('Sell-out (units)');
    expect(within(chart).queryByTestId('chart-legend')).toBeNull();
  });
});
