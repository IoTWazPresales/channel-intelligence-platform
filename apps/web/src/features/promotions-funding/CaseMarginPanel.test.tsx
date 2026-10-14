import React from 'react';
import { screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { CaseMarginPanel, type CaseMarginRead } from './CaseMarginPanel';

const margin: CaseMarginRead = {
  case_id: 5,
  cost_basis: 'pm_controlled_cost',
  currency: 'USD',
  definition: 'Margin = DAP - PM controlled cost - support',
  roe: 18,
  margin_total: 1200,
  lines_included: 1,
  lines_total: 2,
  lines: [
    {
      line_id: 1,
      product_id: 10,
      product_sku: 'SKU-A',
      product_name: 'Alpha',
      units: 10,
      units_source: 'estimate_qty',
      margin_per_unit: 120,
      margin_total: 1200,
      margin_pct: 0.4,
      dap_per_unit: 300,
      pm_controlled_cost_per_unit: 160,
      landed_cost_per_unit: 175,
      support_per_unit: 20,
      flags: [],
    },
    {
      line_id: 2,
      product_id: 11,
      product_sku: 'SKU-B',
      product_name: 'Beta',
      units: 4,
      units_source: 'result_qty',
      margin_per_unit: null,
      margin_total: null,
      margin_pct: null,
      dap_per_unit: 250,
      pm_controlled_cost_per_unit: null,
      landed_cost_per_unit: null,
      support_per_unit: 10,
      flags: ['no_sku_economics', 'missing_pm_controlled_cost', 'landed_cost_not_recorded'],
    },
  ],
};

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (url === '/api/v1/cpor/cases/5/margin') return margin;
    return {};
  }),
}));

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <CaseMarginPanel caseId={5} />
    </QueryClientProvider>,
  );
}

describe('CaseMarginPanel (N-0080)', () => {
  it('names the cost basis on the headline and keeps landed cost out of the margin', async () => {
    renderPanel();
    const total = await screen.findByTestId('case-margin-total');
    expect(total).toHaveTextContent('Margin vs PM controlled cost (USD)');
    expect(total).toHaveTextContent('1 of 2 lines have every input');
    expect(screen.getByTestId('case-margin-basis')).toHaveTextContent('PM controlled cost');
    expect(screen.getByTestId('case-margin-landed-count')).toHaveTextContent('1 of 2');
    expect(screen.getByRole('columnheader', { name: 'Landed cost / unit (not in margin)' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'PM controlled cost / unit' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'DAP / unit' })).toBeInTheDocument();
  });

  it('shows missing inputs in words and an unrecorded landed cost as Not recorded', async () => {
    renderPanel();
    const row = await screen.findByTestId('case-margin-line-2');
    expect(within(row).getByText('Not recorded')).toBeInTheDocument();
    expect(row).toHaveTextContent('No SKU economics; No PM controlled cost');
    expect(row).not.toHaveTextContent('landed_cost_not_recorded');
    expect(row).toHaveTextContent('result');
    const first = screen.getByTestId('case-margin-line-1');
    expect(first).toHaveTextContent('40% of DAP');
  });
});
