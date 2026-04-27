import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import CommercialPlannerPage, { fmtMarginPct, fmtCurrency } from './page';

const mockState = vi.hoisted(() => ({
  lineupEvidence: null as any,
  planReadiness: null as any,
  apiGetMock: vi.fn(async (url: string) => {
    if (url.startsWith('/api/v1/commercial-planner/lineup-evidence')) return mockState.lineupEvidence;
    if (url.startsWith('/api/v1/commercial-planner/plans/1/readiness')) return mockState.planReadiness;
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
    if (url.startsWith('/api/v1/commercial-planner/lineup-product-gaps')) return mockState.productGaps;
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
  productGaps: [] as any[],
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
vi.mock('@/features/commercial-planner/EntitySearchAutocomplete', () => ({
  EntitySearchAutocomplete: ({
    label,
    onChange,
  }: {
    label: string;
    onChange: (v: any) => void;
    [k: string]: any;
  }) => (
    <button
      data-testid={`pick-entity-${label.toLowerCase().replace(/\s+/g, '-')}`}
      onClick={() => {
        if (label === 'Product') {
          onChange({ id: 42, sku: 'NB-X1', name: 'Notebook X1' });
        } else if (label === 'Customer') {
          onChange({ id: 1, customer_code: 'ACME', customer_name: 'Acme Retail' });
        } else {
          onChange({ id: 1, distributor_code: 'DIST01', distributor_name: 'Summit Supply' });
        }
      }}
    >
      {`Pick ${label}`}
    </button>
  ),
}));
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
      quantity_units: 12, msrp_local: 999.0, promo_price_local: 899.0,
      month_split_json: { Apr: 4, May: 4, Jun: 4 },
      dap_local: 850.0, actual_dap_local: 830.0, disti_cost_local: 700.0, rebate_pct: 0.03,
      dealer_margin_pct: 0.12, vat_pct: 0.15, disti_margin_pct: 0.0724,
      customer_token: 'MATCHED-CUST', header_customer_id: 7, header_customer_code: 'CUST-A',
      header_customer_name: 'Customer A',
      diagnostic_codes: [], has_warnings: false, has_unknown_customer: false,
      period_label: '2026-Q2', country_code: 'ZA', currency_code: 'USD',
    },
    {
      id: 2, source_row_number: 6, product_id: null, product_sku: null, product_name: null,
      part_number_raw: 'PART-002', model_raw: 'Model Y', base_unit_raw: 'NB',
      quantity_units: 5, msrp_local: null, promo_price_local: null, month_split_json: null,
      dap_local: null, actual_dap_local: null, disti_cost_local: null, rebate_pct: null,
      dealer_margin_pct: null, vat_pct: null, disti_margin_pct: null,
      customer_token: 'UNKNOWN-ACCT', header_customer_id: null, header_customer_code: null,
      header_customer_name: null,
      diagnostic_codes: ['unknown_customer', 'unknown_product'],
      has_warnings: true, has_unknown_customer: true,
      period_label: '2026-Q2', country_code: 'ZA', currency_code: 'USD',
    },
  ];

  const PRODUCT_GAPS = [
    {
      product_id: 42,
      product_sku: 'NB-X1',
      product_name: 'Notebook X1',
      has_sku_assumption: false,
      lineup_evidence: {
        dap_local: 850.0, actual_dap_local: 830.0, disti_cost_local: 700.0,
        vat_pct: 0.15, disti_margin_pct: 0.0724, rebate_pct: 0.03,
        dealer_margin_pct: 0.12, total_quantity_units: 12.0,
        msrp_local: 999.0, promo_price_local: 899.0, period_label: '2026-Q2',
      },
      assumption_gaps: ['missing_sku_assumption'],
      cost_semantics_note:
        'DAP (Distributor Acquisition Price) is the source/import value from the historical lineup. ' +
        'It is not equivalent to landed_cost_usd and must not be used as a cost input to the planner ' +
        'without verification of the cost basis.',
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
    mockState.productGaps = [];
  });

  // ── empty state ──────────────────────────────────────────────────────────────

  it('Lineup coverage panel renders empty state when no jobs are available', async () => {
    // lineupJobs is empty — auto-select cannot fire, lineupJobId stays null.
    mockState.lineupJobs = [];
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));
    expect(await screen.findByTestId('lineup-coverage-panel')).toBeInTheDocument();
    expect(await screen.findByTestId('lineup-empty-state')).toBeInTheDocument();
  });

  // ── lineup-jobs query ────────────────────────────────────────────────────────

  it('lineup-jobs endpoint is queried when Lineup coverage tab is active', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));
    await waitFor(() => {
      const calls = mockState.apiGetMock.mock.calls.map((c) => c[0] as string);
      expect(calls.some((u) => u.includes('/lineup-jobs'))).toBe(true);
    });
  });

  // ── auto-select ──────────────────────────────────────────────────────────────

  it('auto-selects the latest job and loads coverage lines without manual selection', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    mockState.coverageLines = COVERAGE_LINES;
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));
    // Coverage table must appear without any Select interaction — auto-select fires.
    const table = await screen.findByTestId('lineup-coverage-table');
    expect(table).toBeInTheDocument();
    // The lineup-coverage endpoint must be called with the auto-selected job id.
    await waitFor(() => {
      const calls = mockState.apiGetMock.mock.calls.map((c) => c[0] as string);
      expect(calls.some((u) => u.includes(`lineup-coverage?job_id=${LINEUP_JOB.id}`))).toBe(true);
    });
  });

  // ── query gating ─────────────────────────────────────────────────────────────

  it('plan queries (plans/lines/summary/suggestions) are not called after switching to Lineup Coverage', async () => {
    mockState.lineupJobs = [];
    const { user } = renderPage();

    // Wait for ALL tab-0 queries to settle before clearing the call log.
    // React Query fires plans first, then lines/summary/suggestions in the next tick once
    // activePlanId resolves — we must wait for all four to avoid a race against mockClear().
    await waitFor(() => {
      const calls = mockState.apiGetMock.mock.calls.map((c) => String(c[0]));
      expect(calls.some((u) => u === '/api/v1/commercial-planner/plans')).toBe(true);
      expect(calls.some((u) => u.includes('/plans/') && u.includes('/lines'))).toBe(true);
      expect(calls.some((u) => u.includes('/plans/') && u.includes('/summary'))).toBe(true);
      expect(calls.some((u) => u.includes('/plans/') && u.includes('/suggestions'))).toBe(true);
    });

    // Clear and switch to Lineup Coverage.
    mockState.apiGetMock.mockClear();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));

    // Wait for the lineup-jobs query (the only query expected on tab 2).
    await waitFor(() => {
      const calls = mockState.apiGetMock.mock.calls.map((c) => String(c[0]));
      expect(calls.some((u) => u.includes('lineup-jobs'))).toBe(true);
    });

    // Plans-related endpoints must not have been called after the tab switch.
    const allCalls = mockState.apiGetMock.mock.calls.map((c) => String(c[0]));
    expect(allCalls.some((u) => u === '/api/v1/commercial-planner/plans')).toBe(false);
    expect(allCalls.some((u) => u.includes('/plans/') && u.includes('/lines'))).toBe(false);
    expect(allCalls.some((u) => u.includes('/plans/') && u.includes('/summary'))).toBe(false);
    expect(allCalls.some((u) => u.includes('/plans/') && u.includes('/suggestions'))).toBe(false);
  });

  // ── display ──────────────────────────────────────────────────────────────────

  it('disti_margin_pct 0.0724 displays as 7.24% in coverage table', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    mockState.coverageLines = COVERAGE_LINES;
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));

    const cell = await screen.findByTestId(`disti-margin-${COVERAGE_LINES[0].id}`);
    expect(cell).toHaveTextContent('7.24%');
  });

  it('unresolved customer chips use has_unknown_customer — not has_warnings', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    mockState.coverageLines = COVERAGE_LINES;
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));

    const tokenSection = await screen.findByTestId('lineup-coverage-unresolved-tokens');
    expect(tokenSection).toHaveTextContent('UNKNOWN-ACCT (1)');
    // MATCHED-CUST is resolved — must not appear in the unresolved section.
    expect(tokenSection).not.toHaveTextContent('MATCHED-CUST');
  });

  it('summary cards show correct resolved-product and unresolved-customer counts', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    mockState.coverageLines = COVERAGE_LINES;
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));

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

    expect(await screen.findByTestId('lineup-no-lines')).toBeInTheDocument();
  });

  // ── product defaults coverage ─────────────────────────────────────────────

  it('product defaults coverage section renders gap status for each product', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    mockState.coverageLines = COVERAGE_LINES;
    mockState.productGaps = PRODUCT_GAPS;
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));

    const section = await screen.findByTestId('product-defaults-coverage');
    // Product info and chip status.
    expect(section).toHaveTextContent('NB-X1');
    expect(section).toHaveTextContent('Notebook X1');
    expect(section).toHaveTextContent('Missing');
    // Gap flag chip.
    expect(section).toHaveTextContent('missing_sku_assumption');
  });

  it('cost semantics note renders in product defaults section', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    mockState.coverageLines = COVERAGE_LINES;
    mockState.productGaps = PRODUCT_GAPS;
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));

    const section = await screen.findByTestId('product-defaults-coverage');
    expect(section).toHaveTextContent('Cost semantics');
    expect(section).toHaveTextContent('DAP');
    expect(section).toHaveTextContent('not');
  });

  // ── text filter ───────────────────────────────────────────────────────────

  it('text filter reduces visible coverage rows by matching on model_raw', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    mockState.coverageLines = COVERAGE_LINES;
    mockState.productGaps = PRODUCT_GAPS;
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));

    // Both rows visible initially.
    const table = await screen.findByTestId('lineup-coverage-table');
    expect(table).toHaveTextContent('Model X');
    expect(table).toHaveTextContent('Model Y');

    // Type a filter that matches only row 1.
    const filterInput = await screen.findByTestId('coverage-filter');
    await user.type(filterInput, 'Model X');

    // Only row 1 remains; row 2 is filtered out.
    await waitFor(() => {
      expect(screen.getByTestId('lineup-coverage-table')).toHaveTextContent('Model X');
      expect(screen.getByTestId('lineup-coverage-table')).not.toHaveTextContent('Model Y');
    });
  });

  // ── commercial semantics ──────────────────────────────────────────────────

  it('coverage table column headers use MSRP / list and Promo price labels', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    mockState.coverageLines = COVERAGE_LINES;
    mockState.productGaps = PRODUCT_GAPS;
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));

    const table = await screen.findByTestId('lineup-coverage-table');
    expect(table).toHaveTextContent('MSRP / list');
    expect(table).toHaveTextContent('Promo price');
    // The old bare "MSRP" and "Promo" headers must not appear as standalone header labels.
    // Note: MSRP appears inside "MSRP / list" so we test for the full phrase.
    expect(table).not.toHaveTextContent(/^MSRP$/);
  });

  it('commercial completeness summary shows MSRP, Promo, DAP, and month split counts', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    // row1 has msrp=999, promo=899, dap=850, month_split; row2 has all null
    mockState.coverageLines = COVERAGE_LINES;
    mockState.productGaps = [];
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));

    const completeness = await screen.findByTestId('lineup-completeness-summary');
    // Only row 1 has MSRP (999) — row 2 has null.
    expect(completeness).toHaveTextContent('MSRP / list price: 1 / 2');
    // Only row 1 has promo price.
    expect(completeness).toHaveTextContent('Promo price: 1 / 2');
    // Only row 1 has DAP.
    expect(completeness).toHaveTextContent('DAP evidence: 1 / 2');
    // Only row 1 has month split.
    expect(completeness).toHaveTextContent('Month split: 1 / 2');
  });

  it('month split data renders in coverage table row', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    mockState.coverageLines = COVERAGE_LINES;
    mockState.productGaps = PRODUCT_GAPS;
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));

    const table = await screen.findByTestId('lineup-coverage-table');
    // Row 1 has month_split_json: {Apr: 4, May: 4, Jun: 4}
    expect(table).toHaveTextContent('Apr: 4');
    expect(table).toHaveTextContent('May: 4');
  });

  it('product defaults coverage explanation caption is visible', async () => {
    mockState.lineupJobs = [LINEUP_JOB];
    mockState.coverageLines = COVERAGE_LINES;
    mockState.productGaps = PRODUCT_GAPS;
    const { user } = renderPage();
    await user.click(await screen.findByRole('tab', { name: /Lineup coverage/i }));

    const caption = await screen.findByTestId('product-gaps-caption');
    expect(caption).toHaveTextContent('Product defaults coverage shows one row per product');
    expect(caption).toHaveTextContent('DAP is source/local evidence only');
    expect(caption).toHaveTextContent('not landed cost');
  });
});

// ── Planner readiness chips ───────────────────────────────────────────────────
describe('Plan readiness chips', () => {
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
    mockState.planReadiness = null;
    mockState.lineupEvidence = null;
  });

  it('shows missing SKU assumption chip when readiness reports gaps', async () => {
    mockState.planReadiness = {
      plan_id: 1,
      line_count: 1,
      missing_customer_term: 0,
      missing_distributor_term: 0,
      missing_sku_assumption: 1,
      lines_with_calc_flags: 0,
      ready: false,
      readiness_summary: '1 line(s) missing SKU assumptions',
    };
    renderPage();

    const chips = await screen.findByTestId('plan-readiness-chips');
    expect(chips).toHaveTextContent('Missing SKU assumptions: 1');
  });

  it('shows all-defaults-present chip when plan is ready', async () => {
    mockState.planReadiness = {
      plan_id: 1,
      line_count: 1,
      missing_customer_term: 0,
      missing_distributor_term: 0,
      missing_sku_assumption: 0,
      lines_with_calc_flags: 0,
      ready: true,
      readiness_summary: 'All defaults present.',
    };
    renderPage();

    const chips = await screen.findByTestId('plan-readiness-chips');
    expect(chips).toHaveTextContent('All defaults present');
  });
});

// ── Lineup evidence panel in Add line dialog ──────────────────────────────────
describe('Lineup evidence panel in Add line dialog', () => {
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
    mockState.lineupEvidence = null;
    mockState.planReadiness = null;
  });

  it('shows lineup evidence panel when product is selected and evidence is available', async () => {
    mockState.lineupEvidence = {
      product_id: 42,
      lineup_job_id: 10,
      evidence: {
        msrp_local: 999.0,
        promo_price_local: 899.0,
        dap_local: 750.0,
        actual_dap_local: null,
        disti_margin_pct: 0.08,
        vat_pct: 0.15,
        rebate_pct: 0.03,
        total_quantity_units: 216,
        line_count: 2,
        period_label: '2026-Q2',
      },
      cost_semantics_note: 'DAP is not landed_cost_usd.',
    };
    const { user } = renderPage();

    // Open the Add line dialog
    const addBtn = await screen.findByRole('button', { name: /Add line/i });
    await user.click(addBtn);

    // Select a product via the mocked EntitySearchAutocomplete
    const pickProduct = await screen.findByTestId('pick-entity-product');
    await user.click(pickProduct);

    // Evidence panel should appear
    const panel = await screen.findByTestId('lineup-evidence-panel');
    expect(panel).toHaveTextContent('2026-Q2');
    expect(panel).toHaveTextContent('999');
    expect(panel).toHaveTextContent('DAP is not landed cost');
  });

  it('clicking MSRP chip prefills the Target SRP field', async () => {
    mockState.lineupEvidence = {
      product_id: 42,
      lineup_job_id: 10,
      evidence: {
        msrp_local: 1100.0,
        promo_price_local: null,
        dap_local: null,
        actual_dap_local: null,
        disti_margin_pct: null,
        vat_pct: null,
        rebate_pct: null,
        total_quantity_units: null,
        line_count: 1,
        period_label: '2026-Q2',
      },
      cost_semantics_note: 'DAP is not landed_cost_usd.',
    };
    const { user } = renderPage();

    const addBtn = await screen.findByRole('button', { name: /Add line/i });
    await user.click(addBtn);

    const pickProduct = await screen.findByTestId('pick-entity-product');
    await user.click(pickProduct);

    // Click the MSRP chip to prefill target SRP
    const msrpChip = await screen.findByTestId('use-msrp-as-srp');
    await user.click(msrpChip);

    // Target SRP input should now show the MSRP value
    const srpInput = screen.getByLabelText(/Target SRP local/i) as HTMLInputElement;
    expect(srpInput.value).toBe('1100');
  });
});
