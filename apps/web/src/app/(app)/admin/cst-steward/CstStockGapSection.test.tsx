import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { CstStockGapSection, flagLabel, formatGap, periodLabel, type StockGapResponse } from './CstStockGapSection';

type GridProps = {
  rowData: Array<Record<string, unknown>>;
  columnDefs: Array<{
    headerName?: string;
    field?: string;
    valueGetter?: (p: { data: unknown }) => unknown;
    valueFormatter?: (p: { value: unknown; data: unknown }) => string;
    cellClassRules?: Record<string, (p: { data: unknown }) => boolean>;
  }>;
};

// Render the grid as a plain table so the formatted cells and flag classes can be read.
vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ rowData, columnDefs }: GridProps) => (
    <table data-testid="grid">
      <thead>
        <tr>
          {columnDefs.map((c) => (
            <th key={c.headerName}>{c.headerName}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rowData.map((row, i) => (
          <tr key={i}>
            {columnDefs.map((c) => {
              const raw = c.valueGetter ? c.valueGetter({ data: row }) : c.field ? row[c.field] : '';
              const text = c.valueFormatter ? c.valueFormatter({ value: raw, data: row }) : String(raw ?? '');
              const cls = Object.entries(c.cellClassRules ?? {})
                .filter(([, fn]) => fn({ data: row }))
                .map(([k]) => k)
                .join(' ');
              return (
                <td key={c.headerName} className={cls} data-col={c.headerName}>
                  {text}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  ),
}));

const payload: StockGapResponse = {
  threshold_units: 2,
  counts: {
    compared: 3,
    highlighted: 2,
    first_report: 1,
    highlighted_by_cause: { unexplained: 1, repeated_report: 1 },
  },
  rows: [
    {
      id: 1,
      customer_id: 7,
      customer_code: 'C007',
      customer_name: 'Retail Co',
      product_id: 3,
      sku: 'SKU-3',
      product_name: 'Laptop 14',
      period_grain: 'week',
      period_start_date: '2026-07-13',
      period_end_date: '2026-07-19',
      period_week: 29,
      period_year: 2026,
      reported_on_hand: 40,
      previous_on_hand: 45,
      previous_period_end_date: '2026-07-12',
      receipts_units: 10,
      units_sold: 12,
      expected_on_hand: 43,
      gap_units: -3,
      in_transit_units: 2,
      on_order_units: 30,
      status: 'compared',
      highlighted: true,
      reason: 'Short: stock not delivered, lost, or sold outside the file. 2 in transit may explain part of it.',
      gap_cause: 'unexplained',
      gap_causes: ['unexplained'],
      gap_cause_label: 'Stock difference: no data gap found',
    },
    {
      id: 2,
      customer_id: 7,
      customer_code: 'C007',
      customer_name: 'Retail Co',
      product_id: 4,
      sku: 'SKU-4',
      product_name: 'Laptop 16',
      period_grain: 'day',
      period_start_date: '2026-07-15',
      period_end_date: '2026-07-15',
      period_week: null,
      period_year: null,
      reported_on_hand: 9,
      previous_on_hand: 8,
      previous_period_end_date: '2026-07-14',
      receipts_units: 0,
      units_sold: 0,
      expected_on_hand: 8,
      gap_units: 1,
      in_transit_units: null,
      on_order_units: null,
      status: 'compared',
      highlighted: false,
      reason: 'Over: a receipt CIP does not have, a return, or overlapping periods.',
      gap_cause: 'unexplained',
      gap_causes: ['unexplained'],
      gap_cause_label: 'Stock difference: no data gap found',
    },
    {
      id: 3,
      customer_id: 7,
      customer_code: 'C007',
      customer_name: 'Retail Co',
      product_id: 5,
      sku: 'SKU-5',
      product_name: 'Monitor 27',
      period_grain: 'week',
      period_start_date: '2026-07-20',
      period_end_date: '2026-07-26',
      period_week: 30,
      period_year: 2026,
      reported_on_hand: 20,
      previous_on_hand: 20,
      previous_period_end_date: '2026-07-19',
      receipts_units: 0,
      units_sold: 6,
      expected_on_hand: 14,
      gap_units: 6,
      in_transit_units: null,
      on_order_units: null,
      status: 'compared',
      highlighted: true,
      reason: "Not read as the customer's stock until this is fixed. Over: a receipt CIP does not have.",
      gap_cause: 'repeated_report',
      gap_causes: ['repeated_report'],
      gap_cause_label: "Data gap: this report repeats the previous report's figures",
    },
  ],
};

const apiGet = vi.fn(async () => payload);
const apiPut = vi.fn(async (_url: string, body: { highlight_units: number }) => ({ threshold_units: body.highlight_units }));
const apiPost = vi.fn(async () => ({ customers: 1, positions: 3 }));

vi.mock('@/lib/api', () => ({
  apiGet: (...a: unknown[]) => apiGet(...(a as [])),
  apiPut: (...a: unknown[]) => apiPut(...(a as [string, { highlight_units: number }])),
  apiPost: (...a: unknown[]) => apiPost(...(a as [])),
}));

function renderSection() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <CstStockGapSection />
    </QueryClientProvider>,
  );
}

describe('CstStockGapSection', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows the unit gap on every compared row and flags only rows over the threshold', async () => {
    renderSection();
    await waitFor(() => expect(screen.getByTestId('cst-stock-gap-counts')).toHaveTextContent('3 compared'));
    expect(screen.getByTestId('cst-stock-gap-counts')).toHaveTextContent('2 at or over 2 units');
    const gaps = screen.getAllByText((_, el) => el?.getAttribute('data-col') === 'Gap (units)');
    expect(gaps.map((g) => g.textContent)).toEqual(['−3', '+1', '+6']);
    expect(gaps[0]).toHaveClass('cip-gap-flag');
    expect(gaps[1]).not.toHaveClass('cip-gap-flag');
    expect(screen.getByText('Stock difference')).toBeInTheDocument();
    expect(screen.getByText('Week 29, 2026')).toBeInTheDocument();
    expect(screen.getByText('2026-07-15')).toBeInTheDocument();
    expect(screen.getByText(/2 in transit may explain part of it/)).toBeInTheDocument();
    // Customer column carries the name; the code sits in its own column.
    const customerCells = screen.getAllByText((_, el) => el?.getAttribute('data-col') === 'Customer');
    expect(customerCells[0].textContent).toBe('Retail Co');
  });

  it('shows a data gap beside its gap and never as a stock difference', async () => {
    renderSection();
    await waitFor(() => expect(screen.getByTestId('cst-stock-gap-cause-counts')).toBeInTheDocument());
    expect(screen.getByTestId('cst-stock-gap-cause-counts')).toHaveTextContent(
      'Of those, 1 are data gaps in CIP and 1 have no data gap found.',
    );
    const gaps = screen.getAllByText((_, el) => el?.getAttribute('data-col') === 'Gap (units)');
    expect(gaps[2]).toHaveClass('cip-gap-data');
    expect(gaps[2]).not.toHaveClass('cip-gap-flag');
    const flags = screen.getAllByText((_, el) => el?.getAttribute('data-col') === 'Flag');
    expect(flags[2].textContent).toBe('Data gap');
    const why = screen.getAllByText((_, el) => el?.getAttribute('data-col') === 'Why it differs');
    expect(why[2].textContent).toBe("Data gap: this report repeats the previous report's figures");
    expect(why[0].textContent).toBe('Stock difference: no data gap found');
    // The cause sits right after the gap.
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent);
    expect(headers[headers.indexOf('Gap (units)') + 1]).toBe('Why it differs');
  });

  it('saves the threshold in absolute units', async () => {
    renderSection();
    const input = await screen.findByTestId('cst-stock-gap-threshold');
    await waitFor(() => expect(input).toHaveValue(2));
    fireEvent.change(input, { target: { value: '5' } });
    fireEvent.click(screen.getByTestId('cst-stock-gap-threshold-save'));
    await waitFor(() =>
      expect(apiPut).toHaveBeenCalledWith('/api/v1/cst-steward/stock-gap/settings', { highlight_units: 5 }),
    );
  });

  it('rejects a zero threshold before sending', async () => {
    renderSection();
    const input = await screen.findByTestId('cst-stock-gap-threshold');
    await waitFor(() => expect(input).toHaveValue(2));
    fireEvent.change(input, { target: { value: '0' } });
    expect(screen.getByText('Enter more than 0 units')).toBeInTheDocument();
    expect(screen.getByTestId('cst-stock-gap-threshold-save')).toBeDisabled();
  });

  it('recomputes on request', async () => {
    renderSection();
    fireEvent.click(await screen.findByTestId('cst-stock-gap-recompute'));
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/v1/cst-steward/stock-gap/recompute', {}));
    expect(await screen.findByText(/Recomputed 3 positions for 1 customer/)).toBeInTheDocument();
  });
});

describe('stock gap labels', () => {
  it('names a week with no on-hand and the report after unreported weeks (N-0111)', () => {
    expect(flagLabel({ status: 'no_on_hand', highlighted: false, gap_cause: null })).toBe('No on-hand reported');
    expect(flagLabel({ status: 'chain_restart', highlighted: false, gap_cause: null })).toBe('Unreported weeks');
  });

  it('formats signed gaps', () => {
    expect(formatGap(null)).toBe('—');
    expect(formatGap(0)).toBe('0');
    expect(formatGap(4)).toBe('+4');
    expect(formatGap(-2.5)).toBe(`−${(2.5).toLocaleString(undefined, { maximumFractionDigits: 2 })}`);
  });

  it('labels each grain', () => {
    expect(periodLabel({ period_grain: 'day', period_start_date: '2026-07-08', period_week: null, period_year: null })).toBe(
      '2026-07-08',
    );
    expect(periodLabel({ period_grain: 'month', period_start_date: '2026-07-01', period_week: null, period_year: null })).toBe(
      '2026-07',
    );
    expect(periodLabel({ period_grain: 'week', period_start_date: '2026-07-05', period_week: null, period_year: null })).toBe(
      'Week from 2026-07-05',
    );
  });
});
