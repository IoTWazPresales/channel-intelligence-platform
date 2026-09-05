import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { CaseBookSurface } from './CaseBookSurface';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/commercial-planner/cpor-cases',
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ rowData }: { rowData: { case_code: string }[] }) => (
    <div data-testid="case-book-grid">{rowData.map((r) => r.case_code).join(',')}</div>
  ),
}));

const listPayload = {
  items: [
    {
      id: 9,
      case_code: 'C24447247',
      customer_name: 'Credit customer',
      customer_code: 'CR',
      promotion_type: 'Sell out PP',
      window_start: '2024-01-01',
      window_end: '2024-01-31',
      status: 'ended',
      workflow_status: 'ended',
      currency_code: 'ZAR',
      ttl_support_zar: -1050.48,
      owed_amount: -1050.48,
      outstanding_amount: -1050.48,
      estimate_qty_sum: 10,
      settle_readiness: {
        fx_declared: true,
        roe_snapshot: 18.78,
        fx_mode_declared: false,
        fx_settle_allowed: false,
        open_assumption_count: 0,
        claim_evidence_count: 0,
      },
      allowed_next: ['settled'],
    },
    {
      id: 10,
      case_code: 'C26ENDED',
      customer_name: 'Metro',
      customer_code: 'M',
      promotion_type: 'Sell out PP',
      window_start: '2026-01-01',
      window_end: '2026-01-31',
      status: 'ended',
      workflow_status: 'ended',
      currency_code: 'ZAR',
      ttl_support_zar: 5000,
      owed_amount: 5000,
      outstanding_amount: 5000,
      estimate_qty_sum: 20,
      settle_readiness: {
        fx_declared: true,
        roe_snapshot: 18,
        fx_mode_declared: false,
        fx_settle_allowed: false,
        open_assumption_count: 0,
        claim_evidence_count: 0,
      },
      allowed_next: ['settled'],
    },
    {
      id: 11,
      case_code: 'CSETTLED',
      customer_name: 'Settled Co',
      customer_code: 'S',
      promotion_type: 'Sell out PP',
      window_start: '2025-01-01',
      window_end: '2025-01-31',
      status: 'settled',
      workflow_status: 'settled',
      currency_code: 'ZAR',
      ttl_support_zar: 9000,
      owed_amount: 9000,
      outstanding_amount: 9000,
      estimate_qty_sum: 5,
      settle_readiness: {
        fx_declared: true,
        roe_snapshot: 18,
        fx_mode_declared: false,
        fx_settle_allowed: false,
        open_assumption_count: 0,
        claim_evidence_count: 0,
      },
      allowed_next: [],
    },
  ],
  total: 3,
  page: 1,
  page_size: 500,
  status_counts: { ended: 2, proposed: 0, settled: 210, draft: 3 },
};

const bookPayload = {
  open_case_count: 78,
  book_total: 6_021_148.88,
  settled_amount: 0,
  outstanding_amount: 6_021_148.88,
  blocked_amount: 6_022_199.36,
  currency_code: 'ZAR',
};

vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => {
    if (url.includes('/settlement/book')) return Promise.resolve(bookPayload);
    if (url.includes('/cpor/cases')) return Promise.resolve(listPayload);
    return Promise.resolve({});
  },
  apiPost: vi.fn(),
}));

describe('CaseBookSurface', () => {
  it('does not mount the settlement desk and labels open-book vs FX-blocked scopes', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CaseBookSurface />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('funding-case-book')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId('case-book-grid')).toHaveTextContent('C24447247'));
    expect(screen.queryByTestId('settlement-container')).toBeNull();
    expect(screen.queryByTestId('settlement-scope-bar')).toBeNull();
    expect(screen.getByText(/Open book total/i)).toBeInTheDocument();
    expect(screen.getByText(/non-settled, non-cancelled/i)).toBeInTheDocument();
    expect(screen.getByText('Paid on the open book')).toBeInTheDocument();
    expect(screen.getByText(/USD pending-report rows do not pay this ZAR book/i)).toBeInTheDocument();
    expect(screen.getByText(/Negative line ttl_support/i)).toBeInTheDocument();
    expect(screen.getByText(/excludes settled and negative-support/i)).toBeInTheDocument();
    expect(screen.getByText(/FX blocked · 1/)).toBeInTheDocument();
  });
});
