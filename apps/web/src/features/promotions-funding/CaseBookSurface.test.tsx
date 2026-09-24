import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { CaseBookSurface } from './CaseBookSurface';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/commercial-planner/cpor-cases',
}));

vi.mock('@/features/commercial-planner/EntitySearchAutocomplete', () => ({
  EntitySearchAutocomplete: () => null,
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
  test_data_count: 7,
};

const bookPayload = {
  open_case_count: 78,
  book_total: 6_021_148.88,
  settled_amount: 0,
  outstanding_amount: 6_021_148.88,
  blocked_amount: 6_022_199.36,
  currency_code: 'ZAR',
};

const portfolioPayload = {
  cases_in_scope: 304,
  lines_included: 621,
  evidence_basis_mix: { claim_evidenced: 0, source_attested: 230, none: 74 },
  totals: {
    support_usd: 1_617_054,
    support_zar: 28_862_698,
    estimate_qty: 48_463,
    result_qty: 29_970,
    delivery_rate: 0.618,
    support_per_unit_sold_usd: 53.96,
    support_per_unit_sold_zar: 963,
  },
  claim_evidenced_only: { cases_in_scope: 0, delivery_rate: null },
  by_bu: [{ bu: 'NB', support_usd: 900_000, support_zar: 16_000_000 }],
  by_promotion_type: [{ promotion_type: 'Sell out PP', support_usd: 1_000_000, support_zar: 18_000_000 }],
  incremental_unit_cost: { cases_ok: 8, cases_flagged: 192, cases_evaluated: 200, avg_cost_per_incremental_unit_usd: 70.62 },
};

const normsPayload = {
  trailing_quarters: 4,
  window_quarters: ['2025Q4', '2026Q1', '2026Q2', '2026Q3'],
  anchor_quarter: '2026Q3',
  by_customer: [
    {
      customer_id: 12,
      customer_code: 'CUST-000012',
      customer_name: 'Takealot',
      quarters_present: 3,
      absolute_support_usd_avg: 1000,
      absolute_support_zar_avg: 18_000,
      support_pct_of_srp_avg: 0.052,
    },
  ],
};

vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => {
    if (url.includes('/intelligence/portfolio')) return Promise.resolve(portfolioPayload);
    if (url.includes('/intelligence/norms')) return Promise.resolve(normsPayload);
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
    expect(screen.getByTestId('fx-declare-mode')).toHaveTextContent(/Declare booked FX mode · 3/);
    expect(screen.getByText(/No cases are missing a rate/i)).toBeInTheDocument();
    expect(screen.queryByTestId('fx-backfill-suggest')).toBeNull();
    expect(screen.getByText(/Test data · 7/)).toBeInTheDocument();
    const grid = screen.getByTestId('case-book-grid');
    const overlay = screen.getByTestId('cpor-payment-overlay');
    expect(grid.compareDocumentPosition(overlay) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByTestId('case-book-lifecycle')).toBeInTheDocument();
  });

  it('mounts the portfolio read collapsed after the ageing grid, money through DualMoney (N-0044)', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CaseBookSurface />
      </QueryClientProvider>,
    );
    const panel = await screen.findByTestId('case-book-portfolio-read');
    expect(panel).toHaveTextContent('Portfolio read — all non-superseded cases');
    const ageing = screen.getByTestId('case-book-ageing');
    expect(ageing.compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    const toggle = screen.getByTestId('case-book-portfolio-toggle');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId('portfolio-support')).toBeNull();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(document.getElementById(toggle.getAttribute('aria-controls') ?? '')).not.toBeNull();
    const support = await screen.findByTestId('portfolio-support');
    expect(support).toHaveTextContent(/^R /);
    expect(screen.getByTestId('portfolio-support-usd')).toHaveTextContent(/\$ 1[\s,.]?617[\s,.]?054[.,]00 · Σ per-line booked USD/);
    expect(screen.getByTestId('portfolio-per-unit-usd')).toHaveTextContent(/\$ 53[.,]96/);
    expect(screen.getByTestId('case-book-portfolio-top')).toHaveTextContent('Top BU · NB');
    expect(await screen.findByTestId('portfolio-norm-12')).toBeInTheDocument();
    expect(screen.getByText('Takealot')).toBeInTheDocument();
    expect(screen.getByText(/5\.2% of SRP · 3Q present/)).toBeInTheDocument();
    // Trimmed: no do-not-build incremental-unit tile, no support-bias block, no empty claim-only line.
    expect(screen.queryByText(/incremental unit/i)).toBeNull();
    expect(screen.queryByText(/Support bias/i)).toBeNull();
    expect(screen.queryByText(/claim-evidenced only/i)).toBeNull();
  });
});
