import React from 'react';
import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { ImportJobLoadReportView, type ImportLoadReportResponse } from './ImportJobLoadReport';

const base: ImportLoadReportResponse = {
  job_id: 7,
  status: 'completed',
  display_status: 'Completed',
  report: {
    kind: 'customer_sell_through',
    rows_read: 10,
    rows_loaded: 10,
    rows_partly_loaded: 0,
    rows_not_loaded: 0,
    identical_copies_counted_once: 0,
    not_loaded: [],
    files_not_read: [],
    files_excluded: 0,
  },
};

describe('ImportJobLoadReportView (N-0111)', () => {
  it('names rows not loaded and the reason for each category', () => {
    renderWithProviders(
      <ImportJobLoadReportView
        data={{
          ...base,
          display_status: 'Completed with rows not loaded (5)',
          report: {
            ...base.report!,
            rows_read: 15,
            rows_loaded: 10,
            rows_not_loaded: 3,
            rows_partly_loaded: 2,
            not_loaded: [
              { reason: 'no_period', label: 'No sale date or period', rows: 3, partly_loaded: false },
              {
                reason: 'partly_customer_not_matched',
                label: 'Stock loaded; the sale did not (no matched customer)',
                rows: 2,
                partly_loaded: true,
              },
            ],
            files_not_read: [{ filename: 'bad.xlsx', reason: 'parse_error' }],
          },
        }}
      />,
    );
    const panel = screen.getByTestId('import-load-report');
    expect(within(panel).getByText('Completed with rows not loaded (5)')).toBeInTheDocument();
    expect(panel).toHaveTextContent('Rows read 15 · loaded 10 · not loaded 3 · partly loaded 2');
    const list = screen.getByRole('list', { name: 'Rows not loaded, by reason' });
    expect(list).toHaveTextContent('No sale date or period: 3 rows');
    expect(list).toHaveTextContent('Stock loaded; the sale did not (no matched customer): 2 rows (partly loaded)');
    expect(panel).toHaveTextContent('Files not read: bad.xlsx');
  });

  it('reads plain Completed when every row loaded', () => {
    renderWithProviders(<ImportJobLoadReportView data={{ ...base, report: { ...base.report!, identical_copies_counted_once: 1 } }} />);
    const panel = screen.getByTestId('import-load-report');
    expect(within(panel).getByText('Completed')).toBeInTheDocument();
    expect(panel).toHaveTextContent('1 identical copy of a row counted once (loaded).');
    expect(screen.queryByRole('list')).toBeNull();
  });

  it('renders nothing for a job with no report', () => {
    renderWithProviders(<ImportJobLoadReportView data={{ ...base, report: null }} />);
    expect(screen.queryByTestId('import-load-report')).toBeNull();
  });
});
