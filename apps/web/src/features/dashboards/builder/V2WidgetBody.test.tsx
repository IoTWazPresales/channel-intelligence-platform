import { fireEvent, screen } from '@testing-library/react';
import { cloneElement, type ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { builderCatalog as catalog } from '@/design-lab/fixtures/builder';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import type { DefinitionV2, V2Response } from './types';
import { V2WidgetBody } from './V2WidgetBody';

vi.mock('recharts', async (original) => ({
  ...await original<typeof import('recharts')>(),
  ResponsiveContainer: ({ children }: { children: ReactElement<{ width?: number; height?: number }> }) =>
    <div>{cloneElement(children, { width: 640, height: 320 })}</div>,
}));
vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ rowData, columnDefs }: { rowData: unknown[]; columnDefs: Array<{ headerName: string }> }) =>
    <div data-testid="grid-boundary">{columnDefs.map((c) => c.headerName).join(' | ')}<output>{JSON.stringify(rowData)}</output></div>,
}));

const measures = ['cpor.support_usd', 'cpor.delivery_rate'];
const def: DefinitionV2 = { v: 1, query: { measures, breakdowns: ['customer'] } };
const result: V2Response = {
  ok: true,
  columns: [{ id: 'customer', kind: 'breakdown', label: 'Customer', fields: ['customer_id', 'customer_name'] }],
  rows: [
    { customer_id: 1, customer_name: 'Kestrel', [measures[0]]: -10, [measures[1]]: 0.25 },
    { customer_id: 2, customer_name: 'Marula', [measures[0]]: 0, [measures[1]]: 0 },
    { customer_id: 3, customer_name: 'Missing', [measures[0]]: null, [measures[1]]: 0.5 },
  ],
  totals: {}, truncated: false, refusals: [],
};

describe('v2 widget rendering', () => {
  it.each(['dual_axis', 'scatter'] as const)('pauses %s safely when catalog metadata is unavailable', (visual) => {
    renderWithProviders(<V2WidgetBody def={def} visual={visual} catalog={null} result={result} loading={false} error={null} testKey="metadata" />);
    expect(screen.getByTestId('dashboard-widget-model-unavailable-metadata')).toHaveTextContent('data model');
  });
  it('draws two real axes and formats each series with its own unit', () => {
    const { container } = renderWithProviders(<V2WidgetBody def={def} visual="dual_axis" catalog={catalog} result={result} loading={false} error={null} testKey="dual" />);
    expect(container.querySelectorAll('.recharts-yAxis')).toHaveLength(2);
    expect(screen.getByTestId('chart-axis-title-top')).toHaveTextContent('Support USD (US$)');
    expect(screen.getByTestId('chart-axis-title-right')).toHaveTextContent('Delivery rate (%)');
    expect(screen.getByRole('table')).toHaveTextContent('25.0%');
    expect(container.querySelectorAll('.recharts-bar-rectangle').length).toBeGreaterThan(0);
    expect(screen.queryByTestId('grid-boundary')).not.toBeInTheDocument();
  });

  it('draws zero and negative scatter points, omits missing coordinates and filters an actual mark', () => {
    const select = vi.fn();
    const { container } = renderWithProviders(<V2WidgetBody def={def} visual="scatter" catalog={catalog} result={result} loading={false} error={null} onSelect={select} testKey="scatter" />);
    const points = container.querySelectorAll('.recharts-scatter-symbol');
    expect(points).toHaveLength(2);
    expect(screen.getByText('1 categories omitted: both measures must be reported.')).toBeInTheDocument();
    fireEvent.click(points[0], { ctrlKey: true });
    expect(select).toHaveBeenCalledWith(expect.objectContaining({ breakdown: 'customer', value: 1, label: 'Kestrel' }), true);
    fireEvent.click(screen.getByRole('button', { name: /Marula:/ }));
    expect(select).toHaveBeenLastCalledWith(expect.objectContaining({ value: 2 }), false);
  });

  it('reshapes a pivot and retains a non-additive server grand total', () => {
    const pivot: DefinitionV2 = { ...def, query: { ...def.query, breakdowns: ['customer', 'status'] } };
    const response = { ...result, totals: { [measures[0]]: 100, [measures[1]]: 0.8 },
      columns: [...result.columns, { id: 'status', kind: 'breakdown' as const, label: 'Status', fields: ['status'] }],
      rows: result.rows.map((r, i) => ({ ...r, status: i === 0 ? 'settled' : 'ended' })) };
    renderWithProviders(<V2WidgetBody def={pivot} visual="pivot" catalog={catalog} result={response} loading={false} error={null} testKey="pivot" />);
    expect(screen.getByTestId('builder-pivot')).toBeInTheDocument();
    expect(screen.getByTestId('grid-boundary')).toHaveTextContent('settled');
    expect(screen.getByTestId('grid-boundary')).toHaveTextContent('Row total: Support USD');
    expect(screen.getByTestId('grid-boundary')).not.toHaveTextContent('Row total: Delivery rate');
    expect(screen.getByTestId('pivot-grand-total')).toHaveTextContent('80.0%');
  });

  it('provides recoverable loading, error, refusal and empty states', () => {
    const retry = vi.fn();
    const clear = vi.fn();
    const props = { def, visual: 'hbar' as const, catalog, testKey: 'state', loading: false, error: null };
    const view = renderWithProviders(<V2WidgetBody {...props} result={undefined} loading />);
    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
    view.rerender(<V2WidgetBody {...props} result={undefined} error={new Error('Failed')} onRetry={retry} />);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(retry).toHaveBeenCalledOnce();
    view.rerender(<V2WidgetBody {...props} result={{ ...result, ok: false, refusals: [{ measure: null, reason: 'Not allowed at this grain' }] }} />);
    expect(screen.getByTestId('dashboard-widget-refused-state')).toHaveTextContent('Not allowed at this grain');
    view.rerender(<V2WidgetBody {...props} result={{ ...result, rows: [] }} onClearFilters={clear} />);
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(clear).toHaveBeenCalledOnce();
  });
});
