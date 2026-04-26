import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import CommercialPlannerPage, { fmtMarginPct, fmtCurrency } from './page';

const mockState = vi.hoisted(() => ({
  apiGetMock: vi.fn(async (url: string) => {
    if (url === '/api/v1/commercial-planner/plans') {
      return [
        {
          id: 1,
          plan_name: 'Q3 Plan',
          status: 'draft',
          period_start: '2026-07-01',
          period_end: null,
          owner: 'planner',
          currency_code: 'USD',
          line_count: 1,
          notes: null,
        },
      ];
    }
    if (url === '/api/v1/commercial-planner/plans/1/lines') {
      return [
        {
          id: 11,
          commercial_plan_id: 1,
          customer_id: 1,
          distributor_id: 1,
          product_id: 1,
          customer_code: 'ACME',
          customer_name: 'Acme Retail',
          distributor_code: 'DIST01',
          distributor_name: 'Summit Supply',
          product_sku: 'NB-X1',
          product_name: 'Notebook X1',
          target_units: 100,
          target_srp_local: 1000,
          promo_srp_local: 900,
          promo_mix_pct: 0.5,
          calc_sell_in_price_usd: 40,
          calc_buy_price_usd: 36,
          calc_promo_reserve_usd: 200,
          calc_non_promo_reserve_usd: 200,
          calc_internal_gp_usd: 300,
          calc_flags: [],
          calc_explanation: 'ok',
        },
      ];
    }
    if (url.startsWith('/api/v1/commercial-planner/customer-terms')) {
      return [];
    }
    if (url.startsWith('/api/v1/commercial-planner/distributor-terms')) {
      return [];
    }
    if (url.startsWith('/api/v1/commercial-planner/sku-assumptions')) {
      return [];
    }
    if (url === '/api/v1/commercial-planner/plans/1/summary') {
      return {
        line_count: 1,
        total_units: 100,
        total_internal_gp_usd: 300,
        total_promo_reserve_usd: 200,
        total_non_promo_reserve_usd: 200,
        flags: [],
      };
    }
    if (url === '/api/v1/commercial-planner/lineup-jobs') return mockState.lineupJobs;
    if (url.startsWith('/api/v1/commercial-planner/lineup-coverage')) return mockState.coverageLines;
    if (url === '/api/v1/commercial-planner/plans/1/suggestions') {
      return [
        {
          line_id: 11,
          suggestions: [
            {
              type: 'target_units',
              value: 120,
              reason: 'Historical uplift',
              confidence: 'medium',
              factors: { avg_sellout_units: 100 },
            },
          ],
        },
      ];
    }
    return [];
  }),
  apiPostMock: vi.fn(async () => ({})),
  apiPatchMock: vi.fn(async () => ({})),
  apiDeleteMock: vi.fn(async () => ({})),
  lineupJobs: [] as any[],
  coverageLines: [] as any[],
}));

vi.mock('@/components/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock('@/components/ModuleDataSection', () => ({
  ModuleDataSection: ({ children }: any) => <>{children}</>,
}));
vi.mock('@/components/ModuleGridToolbar', () => ({
  ModuleGridToolbar: ({ onAdd }: any) => <button onClick={onAdd}>add-plan</button>,
}));
vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ rowData }: { rowData: any[] }) => (
    <div>
      {rowData.map((r) => (
        <div key={r.id}>{r.id}</div>
      ))}
    </div>
  ),
}));
vi.mock('@/lib/queryError', () => ({ toQueryError: () => null }));
vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => mockState.apiGetMock(url),
  apiPost: mockState.apiPostMock,
  apiPatch: mockState.apiPatchMock,
  apiDelete: mockState.apiDeleteMock,
}));

describe('CommercialPlannerPage', () => {
  beforeEach(() => {
    mockState.apiGetMock.mockClear();
    mockState.apiPostMock.mockClear();
    mockState.apiPatchMock.mockClear();
    mockState.apiDeleteMock.mockClear();
  });

  function renderPage() {
    const qc = new QueryClient();
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <CommercialPlannerPage />
      </QueryClientProvider>
    );
  }

  it('loads planner workspace and summary', async () => {
    renderPage();
    expect(await screen.findByText('Commercial planner')).toBeInTheDocument();
    expect(await screen.findByText('Lines: 1')).toBeInTheDocument();
    expect(await screen.findByText('Units: 100')).toBeInTheDocument();
  });

  it('shows workflow guidance for plans, defaults, and suggestions', async () => {
    renderPage();
    const guide = await screen.findByTestId('commercial-planner-workflow-guide');
    expect(guide).toHaveTextContent('How this workspace fits together');
    expect(guide).toHaveTextContent('Add line');
    expect(guide).toHaveTextContent('open the builder');
    expect(guide).toHaveTextContent('Planner defaults');
    expect(guide).toHaveTextContent('Recalculate');
  });

  it('shows inline hint that selectors live inside Add line', async () => {
    renderPage();
    expect(await screen.findByText(/Selectors for customer/i)).toBeInTheDocument();
  });

  it('applies assisted suggestion', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Apply' }));
    await waitFor(() =>
      expect(mockState.apiPostMock).toHaveBeenCalledWith('/api/v1/commercial-planner/apply-suggestion', {
        line_id: 11,
        suggestion_type: 'target_units',
        value: 120,
      })
    );
  });

  it('loads planner defaults tab and fetches maintenance lists', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('tab', { name: /Planner defaults/i }));
    expect(await screen.findByText('Customer commercial terms')).toBeInTheDocument();
    expect(await screen.findByTestId('planner-defaults-guide')).toBeInTheDocument();
    await waitFor(() => {
      const hits = mockState.apiGetMock.mock.calls.filter((c) => String(c[0]).includes('/commercial-planner/customer-terms'));
      expect(hits.length).toBeGreaterThan(0);
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Utility function unit tests (exported from page.tsx)
// ─────────────────────────────────────────────────────────────────────────────

describe('fmtMarginPct', () => {
  it('multiplies decimal fractions by 100 and appends %', () => {
    expect(fmtMarginPct(0.0724)).toBe('7.24%');
    expect(fmtMarginPct(0.15)).toBe('15.00%');
    expect(fmtMarginPct(0.08)).toBe('8.00%');
  });

  it('treats values >= 1.0 as already-percentage-points', () => {
    expect(fmtMarginPct(7.24)).toBe('7.24%');
    expect(fmtMarginPct(15.0)).toBe('15.00%');
  });

  it('returns em-dash for null or undefined', () => {
    expect(fmtMarginPct(null)).toBe('—');
    expect(fmtMarginPct(undefined)).toBe('—');
  });
});

describe('fmtCurrency', () => {
  it('formats with 2 decimal places', () => {
    expect(fmtCurrency(999)).toMatch(/999[.,]00/);
    expect(fmtCurrency(12.5)).toMatch(/12[.,]50/);
  });

  it('returns em-dash for null or undefined', () => {
    expect(fmtCurrency(null)).toBe('—');
    expect(fmtCurrency(undefined)).toBe('—');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Lineup Coverage tab
// ─────────────────────────────────────────────────────────────────────────────

describe('CommercialPlannerPage — Lineup coverage tab', () => {
  const LINEUP_JOB = {
    id: 77,
    file_name: 'Q2_lineup.xlsx',
    status: 'completed',
    stage: 'validated',
    period_label: '2026-Q2',
    country_code: 'ZA',
    currency_code: 'USD',
    line_count: 2,
  };

  const COVERAGE_LINES = [
    {
      id: 1, source_row_number: 5, product_id: 42, product_sku: 'NB-X1', product_name: 'Notebook X1',
      part_number_raw: 'PART-001', model_raw: 'Model X', base_unit_raw: 'NB',
      quantity_units: 12, msrp_local: 999.0, promo_price_local: 899.0, dap_local: 850.0,
      disti_margin_pct: 0.0724,
      customer_token: 'MATCHED-CUST', diagnostic_codes: [], has_warnings: false, has_unknown_customer: false,
      period_label: '2026-Q2', country_code: 'ZA', currency_code: 'USD',
    },
    {
      id: 2, source_row_number: 6, product_id: null, product_sku: null, product_name: null,
      part_number_raw: 'PART-002', model_raw: 'Model Y', base_unit_raw: 'NB',
      quantity_units: 5, msrp_local: 799.0, promo_price_local: null, dap_local: null,
      disti_margin_pct: null,
      customer_token: 'UNKNOWN-ACCT', diagnostic_codes: ['unknown_customer', 'unknown_product'],
      has_warnings: true, has_unknown_customer: true,
      period_label: '2026-Q2', country_code: 'ZA', currency_code: 'USD',
    },
  ];

  function renderPage() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    return {
      user: userEvent.setup(),
      ...renderWithProviders(
        <QueryClientProvider client={qc}>
          <CommercialPlannerPage />
        </QueryClientProvider>
      ),
    };
  }

  beforeEach(() => {
    mockState.apiGetMock.mockClear();
    mockState.lineupJobs = [];
    mockState.coverageLines = [];
  });

  it('Lineup coverage tab renders with empty state when no job selected', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));
    expect(await screen.findByTestId('lineup-coverage-panel')).toBeInTheDocument();
    expect(screen.getByTestId('lineup-empty-state')).toBeInTheDocument();
  });

  it('lineup-jobs endpoint is queried when Lineup coverage tab is active', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));
    await waitFor(() => {
      const calls = mockState.apiGetMock.mock.calls.map((c) => c[0] as string);
      expect(calls.some((u) => u.includes('/lineup-jobs'))).toBe(true);
    });
  });

  async function selectLineupJob(user: ReturnType<typeof userEvent.setup>) {
    // MUI Select requires mouseDown on the trigger to open the listbox, then a click on the option.
    const combobox = screen.getByRole('combobox');
    await user.click(combobox);
    // The MenuItem label is "{period_label} — {line_count} lines"
    const option = await screen.findByRole('option', { name: /2026-Q2/i });
    await user.click(option);
  }

  it('disti_margin_pct 0.0724 displays as 7.24% in coverage table', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    mockState.coverageLines = COVERAGE_LINES;
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));
    await selectLineupJob(user);

    const cell = await screen.findByTestId(`disti-margin-${COVERAGE_LINES[0].id}`);
    expect(cell).toHaveTextContent('7.24%');
  });

  it('unresolved customer chips use has_unknown_customer — not has_warnings', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    mockState.coverageLines = COVERAGE_LINES;
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));
    await selectLineupJob(user);

    // Unresolved token section must appear with the specific token
    const tokenSection = await screen.findByTestId('lineup-coverage-unresolved-tokens');
    expect(tokenSection).toHaveTextContent('UNKNOWN-ACCT (1)');
    // MATCHED-CUST is resolved — must not appear in the unresolved section
    expect(tokenSection).not.toHaveTextContent('MATCHED-CUST');
  });

  it('summary cards show correct resolved-product and unresolved-customer counts', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    mockState.coverageLines = COVERAGE_LINES;
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));
    await selectLineupJob(user);

    const cards = await screen.findByTestId('lineup-summary-cards');
    expect(cards).toHaveTextContent('Total: 2 lines');
    expect(cards).toHaveTextContent('Resolved products: 1 / 2');
    expect(cards).toHaveTextContent('Unresolved customers: 1 tokens');
  });

  it('coverage table renders line data from the endpoint', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    mockState.coverageLines = COVERAGE_LINES;
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));
    await selectLineupJob(user);

    const table = await screen.findByTestId('lineup-coverage-table');
    expect(table).toHaveTextContent('NB-X1');
    expect(table).toHaveTextContent('Model X');
    expect(table).toHaveTextContent('PART-002');
  });

  it('shows no-lines state when coverage returns empty array', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    mockState.coverageLines = [];
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));
    await selectLineupJob(user);

    expect(await screen.findByTestId('lineup-no-lines')).toBeInTheDocument();
  });
});
