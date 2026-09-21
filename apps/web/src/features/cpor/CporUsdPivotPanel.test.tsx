import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';

import { renderWithProviders } from '@/test-utils/renderWithProviders';
import { formatUsdMoney } from '@/features/cpor/fxDisplay';

import { CporUsdPivotPanel, PIVOT_MISSING_ROE_COPY, type CporPivot } from './CporUsdPivotPanel';

const pivotState: { value: CporPivot } = {
  value: {
    cells: { 'B-SKU': { '26Q3': 10 }, 'A-SKU': { '26Q3': 100, '26Q4': 50 } },
    row_totals: { 'A-SKU': 150, 'B-SKU': 10 },
    col_totals: { '26Q3': 110, '26Q4': 50 },
    grand_total_usd: 160,
    missing_roe: false,
  },
};

vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => {
    if (url.includes('/pivot')) return Promise.resolve(pivotState.value);
    return Promise.resolve({});
  },
  apiPost: vi.fn(),
}));

function renderPanel(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('CporUsdPivotPanel', () => {
  it('renders the pivot as a table with row, column and grand totals', async () => {
    renderPanel(<CporUsdPivotPanel caseId={46} roeSnapshot={16.5} />);
    expect(await screen.findByTestId('cpor-usd-pivot')).toBeInTheDocument();
    // rows sorted, columns sorted
    expect(screen.getByTestId('cpor-pivot-row-A-SKU')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-pivot-row-B-SKU')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-pivot-grand-total')).toHaveTextContent(formatUsdMoney(160));
    expect(screen.getByText(/at declared case rate ZAR 16\.50/)).toBeInTheDocument();
    // no raw JSON dump anywhere
    expect(document.querySelector('pre')).toBeNull();
  });

  it('withholds every total and shows the verbatim FX copy when the case rate is missing', async () => {
    pivotState.value = { ...pivotState.value, missing_roe: true };
    renderPanel(<CporUsdPivotPanel caseId={46} roeSnapshot={null} />);
    expect(await screen.findByTestId('cpor-pivot-missing-roe')).toHaveTextContent(PIVOT_MISSING_ROE_COPY);
    expect(screen.queryByTestId('cpor-pivot-grand-total')).toBeNull();
    // cells still visible so the case shape is readable
    expect(screen.getByTestId('cpor-pivot-row-A-SKU')).toBeInTheDocument();
    pivotState.value = { ...pivotState.value, missing_roe: false };
  });

  it('shows the module empty state, not an empty table, when there are no cells', async () => {
    pivotState.value = { cells: {}, row_totals: {}, col_totals: {}, grand_total_usd: 0, missing_roe: false };
    renderPanel(<CporUsdPivotPanel caseId={46} />);
    expect(await screen.findByText('No USD pivot yet')).toBeInTheDocument();
    expect(screen.queryByTestId('cpor-usd-pivot')).toBeNull();
  });
});
