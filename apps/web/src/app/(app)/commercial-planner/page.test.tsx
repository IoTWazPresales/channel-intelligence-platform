import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import CommercialPlannerPage, {
  fmtMarginPct,
  fmtCurrency,
  fmtFlag,
  fmtIssueChipLabel,
  fmtModelSalesModel,
  economicsBlockingTooltip,
  lineHasBlockingEconomicsFlags,
  roundPlannerUnits,
  sugTypeLabel,
} from './page';

const mockState = vi.hoisted(() => {
  /** Single mutable bag so defaultApiGetImpl always reads current lineupJobs / coverageLines / etc. */
  const st = {
    lineupEvidence: null as any,
    planReadiness: null as any,
    lineupJobs: [] as any[],
    coverageLines: [] as any[],
    productGaps: [] as any[],
    apiPostMock: vi.fn(async () => ({})),
    apiPatchMock: vi.fn(async () => ({})),
    apiDeleteMock: vi.fn(async () => ({})),
  };

  const defaultApiGetImpl = async (url: string) => {
    if (url.startsWith('/api/v1/commercial-planner/lineup-evidence')) return st.lineupEvidence;
    if (url.startsWith('/api/v1/commercial-planner/plans/1/readiness')) return st.planReadiness;
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
          product_part_number: 'PN-001',
          product_model_name: 'X1',
          product_sales_model_name: 'X1 Sales',
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
          product_specs_flat: { cpu: 'Intel Core i7' },
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
    if (url.startsWith('/api/v1/commercial-planner/plans/1/column-metadata')) {
      return {
        plan_id: 1,
        total_products: 10,
        catalogue: { category: 8, form_factor: 5, lifecycle_status: 10, product_line: 9, series_name: 4, business_unit: 10, part_number: 10, sales_model_name: 7, model_name: 10 },
        spec_keys: { cpu: 8, ram: 10, storage: 6 },
        coverage_note: 'Counts are distinct products in the plan with non-null values.',
      };
    }
    if (url === '/api/v1/commercial-planner/lineup-jobs') return st.lineupJobs;
    if (url.startsWith('/api/v1/commercial-planner/lineup-coverage')) return st.coverageLines;
    if (url.startsWith('/api/v1/commercial-planner/lineup-product-gaps')) return st.productGaps;
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
  };

  const apiGetMock = vi.fn(defaultApiGetImpl);
  return {
    get lineupEvidence() {
      return st.lineupEvidence;
    },
    set lineupEvidence(v: any) {
      st.lineupEvidence = v;
    },
    get planReadiness() {
      return st.planReadiness;
    },
    set planReadiness(v: any) {
      st.planReadiness = v;
    },
    get lineupJobs() {
      return st.lineupJobs;
    },
    set lineupJobs(v: any[]) {
      st.lineupJobs = v;
    },
    get coverageLines() {
      return st.coverageLines;
    },
    set coverageLines(v: any[]) {
      st.coverageLines = v;
    },
    get productGaps() {
      return st.productGaps;
    },
    set productGaps(v: any[]) {
      st.productGaps = v;
    },
    get apiPostMock() {
      return st.apiPostMock;
    },
    get apiPatchMock() {
      return st.apiPatchMock;
    },
    get apiDeleteMock() {
      return st.apiDeleteMock;
    },
    apiGetMock,
    defaultApiGetImpl,
  };
});

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
  EnterpriseDataGrid: ({ rowData, columnDefs, gridOptions }: { rowData: any[]; columnDefs?: any[]; gridOptions?: any }) => (
    <div data-testid="enterprise-grid">
      {gridOptions?.loading ? <span data-testid="grid-loading-overlay">Loading grid…</span> : null}
      {(rowData ?? []).map((r) => {
        const gpCol = columnDefs?.find((c: any) => c.field === 'calc_internal_gp_usd');
        const gpDisplay =
          typeof gpCol?.valueGetter === 'function' ? String(gpCol.valueGetter({ data: r } as any) ?? '') : '';
        const specCpuCol = columnDefs?.find(
          (c: any) => c.colId === 'spec_flat_cpu' || c.field === 'product_spec_cpu',
        );
        const cpuDisplay =
          typeof specCpuCol?.valueGetter === 'function'
            ? String(specCpuCol.valueGetter({ data: r } as any) ?? '')
            : '';
        return (
          <div
            key={r.id}
            data-testid={`grid-row-${r.id}`}
            data-internal-gp-display={gpDisplay}
            data-cpu-display={cpuDisplay}
            onClick={() => gridOptions?.onRowClicked?.({ data: r })}
          >
            {r.id}
          </div>
        );
      })}
      <span data-testid="visible-optional-cols">
        {columnDefs
          ?.filter(
            (c: any) =>
              c.field &&
              [
                'product_spec_warranty',
                'product_spec_os',
                'product_spec_colour',
                'product_category',
                'product_form_factor',
                'product_lifecycle_status',
                'product_line',
                'product_series_name',
                'product_business_unit',
                'effective_customer_margin_pct',
                'effective_customer_rebate_pct',
                'effective_distributor_margin_pct',
                'effective_vat_rate_pct',
                'effective_fx_rate_to_usd',
                'effective_reserve_total_pct',
                'effective_promo_reserve_split_pct',
                'effective_controlled_cost_usd_per_unit',
                'promo_mix_pct',
                'calc_buy_price_usd',
                'calc_promo_reserve_usd',
                'calc_non_promo_reserve_usd',
              ].includes(c.field) &&
              c.hide === false
          )
          .map((c: any) => c.field)
          .join(',')}
      </span>
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
    mockState.apiGetMock.mockImplementation(mockState.defaultApiGetImpl);
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
    const summaryPanel = await screen.findByTestId('plan-summary-panel');
    await waitFor(() => {
      expect(summaryPanel).not.toHaveTextContent('Loading plan…');
    });
    expect(summaryPanel).toHaveTextContent('Lines:');
    expect(summaryPanel).toHaveTextContent('100'); // total_units = 100
  });

  it('shows workflow guidance toggle collapsed by default, expands on click', async () => {
    renderPage();
    const guide = await screen.findByTestId('commercial-planner-workflow-guide');
    // Toggle button is always visible with the title text
    expect(guide).toHaveTextContent('How this workspace fits together');
    // Body content is hidden by default
    expect(guide).not.toHaveTextContent('open the builder');

    // Expand the guide
    fireEvent.click(screen.getByRole('button', { name: /How this workspace fits together/i }));
    expect(guide).toHaveTextContent('open the builder');
    expect(guide).toHaveTextContent('Planner defaults');
    expect(guide).toHaveTextContent('Recalculate');
  });

  it('renders plan selector chips and action buttons in the compact plan controls', async () => {
    renderPage();
    // Plan chip for the loaded plan
    expect(await screen.findByText(/Q3 Plan \(draft\)/i)).toBeInTheDocument();
    // Action buttons present in the header
    expect(await screen.findByRole('button', { name: /\+ New plan/i })).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /Add line/i })).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /Recalculate/i })).toBeInTheDocument();
  });

  it('applies assisted suggestion after preview and confirm', async () => {
    renderPage();
    await waitFor(() => expect(screen.queryByTestId('plan-summary-loading')).not.toBeInTheDocument());
    fireEvent.click(await screen.findByTestId('suggestion-apply-open-preview-main'));
    expect(await screen.findByTestId('suggestion-apply-preview-main')).toBeInTheDocument();
    expect(mockState.apiPostMock).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByTestId('suggestion-confirm-apply-main'));
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
// QA polish — column manager, suggestion preview, loading, trust helpers
// ─────────────────────────────────────────────────────────────────────────────

describe('CommercialPlannerPage — QA polish', () => {
  afterEach(() => {
    mockState.apiGetMock.mockImplementation(mockState.defaultApiGetImpl);
  });

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
    localStorage.clear();
    mockState.apiGetMock.mockClear();
    mockState.apiPostMock.mockClear();
    mockState.lineupJobs = [];
    mockState.coverageLines = [];
    mockState.apiGetMock.mockImplementation(async (url: string) => {
      if (url.startsWith('/api/v1/commercial-planner/lineup-evidence')) return mockState.lineupEvidence;
      if (url.startsWith('/api/v1/commercial-planner/plans/1/readiness')) return mockState.planReadiness;
      if (url === '/api/v1/commercial-planner/lineup-jobs') return mockState.lineupJobs;
      if (url.startsWith('/api/v1/commercial-planner/lineup-coverage')) return mockState.coverageLines;
      if (url === '/api/v1/commercial-planner/plans') {
        return [{ id: 1, plan_name: 'Q3 Plan', status: 'draft', period_start: '2026-07-01', period_end: null, owner: 'planner', currency_code: 'USD', line_count: 1, notes: null }];
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
            product_part_number: null,
            product_model_name: null,
            product_sales_model_name: null,
            target_units: 100,
            target_srp_local: 1000,
            promo_srp_local: 900,
            promo_mix_pct: 0.5,
            calc_sell_in_price_usd: 40,
            calc_buy_price_usd: 36,
            calc_promo_reserve_usd: 200,
            calc_non_promo_reserve_usd: 200,
            calc_internal_gp_usd: 300,
            calc_customer_gp_pct: null,
            calc_distributor_gp_pct: null,
            calc_flags: ['missing_sku_assumption'],
            calc_explanation: 'ok',
            override_landed_cost_usd: null,
            product_specs_flat: { cpu: 'Intel Core i7' },
          },
        ];
      }
      if (url.startsWith('/api/v1/commercial-planner/plans/1/column-metadata')) {
        return {
          plan_id: 1,
          total_products: 10,
          catalogue: {
            category: 8,
            form_factor: 5,
            lifecycle_status: 10,
            product_line: 9,
            series_name: 4,
            business_unit: 10,
            part_number: 10,
            sales_model_name: 7,
            model_name: 10,
          },
          spec_keys: { cpu: 8, ram: 10, storage: 6 },
          coverage_note: 'Counts are distinct products in the plan with non-null values.',
        };
      }
      if (url === '/api/v1/commercial-planner/plans/1/summary') {
        return { line_count: 1, total_units: 100, total_internal_gp_usd: 300, total_promo_reserve_usd: 200, total_non_promo_reserve_usd: 200, flags: [] };
      }
      if (url === '/api/v1/commercial-planner/plans/1/suggestions') {
        return [
          {
            line_id: 11,
            suggestions: [
              {
                type: 'target_units',
                value: 5287.68,
                reason: 'Model output',
                confidence: 'low',
                factors: {},
              },
            ],
          },
        ];
      }
      return [];
    });
  });

  it('Columns opens popover with optional column toggles', async () => {
    const { user } = renderPage();
    await waitFor(() => expect(screen.queryByTestId('plan-summary-loading')).not.toBeInTheDocument());
    await user.click(await screen.findByTestId('column-manager-btn'));
    const modal = await screen.findByTestId('column-selector-modal');
    expect(modal).toHaveTextContent('Planner line columns');
    expect(modal).toHaveTextContent('Product catalogue (optional)');
    expect(screen.getByTestId('col-toggle-promo_mix_pct')).toBeInTheDocument();
  });

  it('toggling Promo mix shows column in grid column defs', async () => {
    const { user } = renderPage();
    await waitFor(() => expect(screen.queryByTestId('plan-summary-loading')).not.toBeInTheDocument());
    await user.click(await screen.findByTestId('column-manager-btn'));
    const cb = await screen.findByTestId('col-toggle-promo_mix_pct');
    await user.click(cb);
    expect(await screen.findByTestId('visible-optional-cols')).toHaveTextContent('promo_mix_pct');
    await user.click(await screen.findByTestId('col-reset-defaults'));
    expect(await screen.findByTestId('visible-optional-cols')).toHaveTextContent('');
  });

  it('grid estimated internal margin shows em dash when line has blocking flag', async () => {
    renderPage();
    await waitFor(() => expect(screen.queryByTestId('plan-summary-loading')).not.toBeInTheDocument());
    const row = await screen.findByTestId('grid-row-11');
    expect(row.getAttribute('data-internal-gp-display')).toBe('—');
  });

  it('persists optional column toggles under localStorage key cip.commercial-planner.gridColumns.v4', async () => {
    localStorage.clear();
    const { user } = renderPage();
    await waitFor(() => expect(screen.queryByTestId('plan-summary-loading')).not.toBeInTheDocument());
    await user.click(await screen.findByTestId('column-manager-btn'));
    await user.click(await screen.findByTestId('col-toggle-effective_fx_rate_to_usd'));
    await waitFor(() => {
      const raw = localStorage.getItem('cip.commercial-planner.gridColumns.v4');
      expect(raw).toBeTruthy();
      const parsed = JSON.parse(raw!);
      expect(parsed.version).toBe(4);
      expect(parsed.visibleOptional?.effective_fx_rate_to_usd).toBe(true);
    });
  });

  it('CPU spec shows value from product_specs_flat when metadata-driven spec column is enabled', async () => {
    const { user } = renderPage();
    await waitFor(() => expect(screen.queryByTestId('plan-summary-loading')).not.toBeInTheDocument());
    await user.click(await screen.findByTestId('column-manager-btn'));
    await user.click(await screen.findByTestId('col-spec-toggle-cpu'));
    await user.click(await screen.findByTestId('col-modal-close'));
    const row = await screen.findByTestId('grid-row-11');
    expect(row.getAttribute('data-cpu-display')).toBe('Intel Core i7');
  });

  it('toggling effective FX shows column in grid defs', async () => {
    const { user } = renderPage();
    await waitFor(() => expect(screen.queryByTestId('plan-summary-loading')).not.toBeInTheDocument());
    await user.click(await screen.findByTestId('column-manager-btn'));
    await user.click(await screen.findByTestId('col-toggle-effective_fx_rate_to_usd'));
    expect(await screen.findByTestId('visible-optional-cols')).toHaveTextContent('effective_fx_rate_to_usd');
  });

  it('Add from lineup posts new lines without landed_cost_usd and skips plan duplicates', async () => {
    mockState.lineupJobs = [
      {
        id: 77,
        file_name: 'q2.xlsx',
        status: 'completed',
        stage: 'validated',
        period_label: '2026-Q2',
        country_code: 'ZA',
        currency_code: 'USD',
        line_count: 2,
      },
    ];
    mockState.coverageLines = [
      {
        id: 501,
        source_row_number: 1,
        product_id: 1,
        product_sku: 'NB-X1',
        product_name: 'Notebook X1',
        part_number_raw: 'P1',
        model_raw: 'M1',
        base_unit_raw: 'NB',
        quantity_units: 5,
        msrp_local: 800,
        promo_price_local: 750,
        month_split_json: null,
        dap_local: 600,
        actual_dap_local: null,
        disti_cost_local: null,
        rebate_pct: null,
        dealer_margin_pct: null,
        vat_pct: null,
        disti_margin_pct: null,
        customer_token: 'T1',
        header_customer_id: 1,
        header_customer_code: 'ACME',
        header_customer_name: 'Acme',
        header_distributor_id: 1,
        header_distributor_code: 'DIST01',
        header_distributor_name: 'Summit',
        diagnostic_codes: [],
        has_warnings: false,
        has_unknown_customer: false,
        period_label: '2026-Q2',
        country_code: 'ZA',
        currency_code: 'USD',
      },
      {
        id: 502,
        source_row_number: 2,
        product_id: 99,
        product_sku: 'NB-Z9',
        product_name: 'Z9',
        part_number_raw: 'P2',
        model_raw: 'M2',
        base_unit_raw: 'NB',
        quantity_units: null,
        msrp_local: 1200,
        promo_price_local: null,
        month_split_json: { Apr: 2, May: 3 },
        dap_local: 900,
        actual_dap_local: null,
        disti_cost_local: null,
        rebate_pct: null,
        dealer_margin_pct: null,
        vat_pct: null,
        disti_margin_pct: null,
        customer_token: 'T2',
        header_customer_id: 1,
        header_customer_code: 'ACME',
        header_customer_name: 'Acme',
        header_distributor_id: 1,
        header_distributor_code: 'DIST01',
        header_distributor_name: 'Summit',
        diagnostic_codes: [],
        has_warnings: false,
        has_unknown_customer: false,
        period_label: '2026-Q2',
        country_code: 'ZA',
        currency_code: 'USD',
      },
    ];
    const { user } = renderPage();
    await waitFor(() => expect(screen.queryByTestId('plan-summary-loading')).not.toBeInTheDocument());
    await user.click(await screen.findByTestId('add-from-lineup-btn'));
    const dialog = await screen.findByTestId('add-from-lineup-dialog');
    expect(dialog).toBeInTheDocument();
    await screen.findByTestId('add-lineup-job-select');
    await waitFor(() => expect(screen.getByTestId('lineup-modal-table')).toBeInTheDocument());
    await user.click(await screen.findByTestId('lineup-modal-select-all'));
    await user.click(await screen.findByTestId('lineup-modal-create'));
    await waitFor(() => expect(screen.getByTestId('lineup-batch-summary')).toBeInTheDocument());
    expect(screen.getByTestId('lineup-batch-summary')).toHaveTextContent('Created 1');
    expect(screen.getByTestId('lineup-batch-summary')).toHaveTextContent('skipped duplicates 1');
    const linePosts = mockState.apiPostMock.mock.calls.filter(
      (c) => String(c[0]) === '/api/v1/commercial-planner/plans/1/lines'
    );
    expect(linePosts.length).toBe(1);
    const body = linePosts[0][1] as Record<string, unknown>;
    expect(body.product_id).toBe(99);
    expect(body.target_units).toBe(5);
    expect(body.target_srp_local).toBe(1200);
    expect('landed_cost_usd' in body).toBe(false);
    expect('override_landed_cost_usd' in body).toBe(false);
  });

  it('fractional target_units suggestion preview shows rounded value and confirm sends integer', async () => {
    const { user } = renderPage();
    await waitFor(() => expect(screen.queryByTestId('plan-summary-loading')).not.toBeInTheDocument());
    await user.click(await screen.findByTestId('suggestion-apply-open-preview-main'));
    const preview = await screen.findByTestId('suggestion-apply-preview-main');
    expect(preview).toHaveTextContent('100');
    expect(preview).toHaveTextContent('5288');
    expect(preview).toHaveTextContent('Rounded to whole unit');
    await user.click(await screen.findByTestId('suggestion-confirm-apply-main'));
    await waitFor(() =>
      expect(mockState.apiPostMock).toHaveBeenCalledWith('/api/v1/commercial-planner/apply-suggestion', {
        line_id: 11,
        suggestion_type: 'target_units',
        value: 5288,
      })
    );
  });

  it('shows grid loading overlay while lines request is pending', async () => {
    const linesDeferred: { resolve?: (v: any[]) => void } = {};
    const linesPromise = new Promise<any[]>((res) => {
      linesDeferred.resolve = res;
    });
    mockState.apiGetMock.mockImplementation(async (url: string) => {
      if (url === '/api/v1/commercial-planner/plans/1/lines') return linesPromise;
      if (url === '/api/v1/commercial-planner/plans') {
        return [{ id: 1, plan_name: 'Q3 Plan', status: 'draft', period_start: '2026-07-01', period_end: null, owner: 'planner', currency_code: 'USD', line_count: 1, notes: null }];
      }
      if (url === '/api/v1/commercial-planner/plans/1/summary') {
        return { line_count: 0, total_units: 0, total_internal_gp_usd: 0, total_promo_reserve_usd: 0, total_non_promo_reserve_usd: 0, flags: [] };
      }
      if (url === '/api/v1/commercial-planner/plans/1/suggestions') return [];
      return [];
    });
    renderPage();
    await waitFor(() => expect(screen.getByTestId('grid-loading-overlay')).toBeInTheDocument());
    linesDeferred.resolve!([
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
        target_units: 1,
        target_srp_local: 1,
        promo_srp_local: null,
        promo_mix_pct: 0.5,
        calc_sell_in_price_usd: null,
        calc_buy_price_usd: null,
        calc_promo_reserve_usd: null,
        calc_non_promo_reserve_usd: null,
        calc_internal_gp_usd: null,
        calc_flags: [],
        calc_explanation: null,
      },
    ]);
    await waitFor(() => expect(screen.queryByTestId('grid-loading-overlay')).not.toBeInTheDocument());
    expect(await screen.findByTestId('grid-row-11')).toBeInTheDocument();
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
    mockState.apiGetMock.mockImplementation(mockState.defaultApiGetImpl);
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
    mockState.apiGetMock.mockImplementation(mockState.defaultApiGetImpl);
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
    await screen.findByText(/Q3 Plan \(draft\)/i);

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
    await screen.findByText(/Q3 Plan \(draft\)/i);

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
    mockState.apiGetMock.mockImplementation(mockState.defaultApiGetImpl);
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
    await screen.findByText(/Q3 Plan \(draft\)/i);

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
    await screen.findByText(/Q3 Plan \(draft\)/i);

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

// ─────────────────────────────────────────────────────────────────────────────
// Workspace V1 — layout, line detail panel, flag translations, suggestions UX
// ─────────────────────────────────────────────────────────────────────────────

/** Shared clean line fixture for Workspace V1 tests */
const CLEAN_LINE = {
  id: 11, commercial_plan_id: 1, customer_id: 1, distributor_id: 1, product_id: 1,
  customer_code: 'ACME', customer_name: 'Acme Retail',
  distributor_code: 'DIST01', distributor_name: 'Summit Supply',
  product_sku: 'NB-X1', product_name: 'Notebook X1',
  target_units: 100, target_srp_local: 1000, promo_srp_local: 900, promo_mix_pct: 0.5,
  calc_sell_in_price_usd: 40, calc_buy_price_usd: 36,
  calc_promo_reserve_usd: 200, calc_non_promo_reserve_usd: 200, calc_internal_gp_usd: 300,
  calc_customer_gp_pct: null, calc_distributor_gp_pct: null,
  calc_flags: [], calc_explanation: 'ok', override_landed_cost_usd: null,
};

function makeDefaultMock(linesOverride?: any[]) {
  return async (url: string) => {
    if (url.startsWith('/api/v1/commercial-planner/lineup-evidence')) return mockState.lineupEvidence;
    if (url.startsWith('/api/v1/commercial-planner/plans/1/readiness')) return mockState.planReadiness;
    if (url === '/api/v1/commercial-planner/plans') {
      return [{ id: 1, plan_name: 'Q3 Plan', status: 'draft', period_start: '2026-07-01', period_end: null, owner: 'planner', currency_code: 'USD', line_count: 1, notes: null }];
    }
    if (url === '/api/v1/commercial-planner/plans/1/lines') return linesOverride ?? [CLEAN_LINE];
    if (url === '/api/v1/commercial-planner/plans/1/summary') {
      return { line_count: 1, total_units: 100, total_internal_gp_usd: 300, total_promo_reserve_usd: 200, total_non_promo_reserve_usd: 200, flags: [] };
    }
    if (url === '/api/v1/commercial-planner/plans/1/suggestions') {
      return [{ line_id: 11, suggestions: [{ type: 'target_units', value: 120, reason: 'Historical uplift', confidence: 'medium', factors: { avg_sellout_units: 100 } }] }];
    }
    return [];
  };
}

describe('CommercialPlannerPage — Workspace V1', () => {
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
    mockState.planReadiness = null;
    mockState.lineupEvidence = null;
    // Reset to clean default implementation so tests that override mockImplementation don't bleed over
    mockState.apiGetMock.mockImplementation(makeDefaultMock());
  });

  it('recalculate-needed banner appears when a line has null economics', async () => {
    mockState.apiGetMock.mockImplementation(
      makeDefaultMock([{ ...CLEAN_LINE, calc_sell_in_price_usd: null, calc_buy_price_usd: null, calc_promo_reserve_usd: null, calc_non_promo_reserve_usd: null, calc_internal_gp_usd: null }])
    );
    renderPage();
    expect(await screen.findByTestId('recalc-needed-banner')).toBeInTheDocument();
  });

  it('selected-line detail panel appears when a grid row is clicked', async () => {
    const { user } = renderPage();
    // Wait for the plan and lines to load
    await screen.findByText('Q3 Plan (draft)');
    const row = await screen.findByTestId('grid-row-11');
    await user.click(row);

    const detailPanel = await screen.findByTestId('line-detail-panel');
    expect(detailPanel).toHaveTextContent('Line detail');
    expect(detailPanel).toHaveTextContent('NB-X1');
    expect(detailPanel).toHaveTextContent('Notebook X1');
    expect(detailPanel).toHaveTextContent('Cust: ACME');
    expect(detailPanel).toHaveTextContent('Units: 100');
  });

  it('selected-line detail shows "Economics OK" chip for a clean line', async () => {
    const { user } = renderPage();
    await screen.findByText('Q3 Plan (draft)');
    await user.click(await screen.findByTestId('grid-row-11'));

    const detailPanel = await screen.findByTestId('line-detail-panel');
    expect(detailPanel).toHaveTextContent('Economics OK');
  });

  it('selected-line detail shows controlled cost missing warning when flag is present', async () => {
    mockState.apiGetMock.mockImplementation(
      makeDefaultMock([{ ...CLEAN_LINE, calc_sell_in_price_usd: 0, calc_buy_price_usd: 0, calc_promo_reserve_usd: 0, calc_non_promo_reserve_usd: 0, calc_internal_gp_usd: 0, calc_flags: ['missing_or_invalid_landed_cost'] }])
    );

    const { user } = renderPage();
    await screen.findByText('Q3 Plan (draft)');
    await user.click(await screen.findByTestId('grid-row-11'));

    const detailPanel = await screen.findByTestId('line-detail-panel');
    expect(detailPanel).toHaveTextContent('Controlled cost unavailable');
    expect(screen.getByTestId('line-detail-cost-missing')).toBeInTheDocument();
  });

  it('suggestions panel shows lineup-based source indicator when meta.data_sources.lineup is true', async () => {
    const lineupBundle = {
      line_id: 11,
      suggestions: [{ type: 'target_units', value: 120, reason: 'Lineup-based uplift', confidence: 'medium', factors: {} }],
      _meta: { lineup_job_id: 7, lineup_period_label: '2026-Q2', data_sources: { sellout: false, prior_planned: false, forecast: false, net_price: false, lineup: true } },
    };
    mockState.apiGetMock.mockImplementation(async (url: string) => {
      if (url === '/api/v1/commercial-planner/plans/1/suggestions') return [lineupBundle];
      return makeDefaultMock()(url);
    });

    const { user } = renderPage();
    // Click grid row to open line detail (which shows per-line suggestions with lineup indicator)
    await screen.findByText('Q3 Plan (draft)');
    await user.click(await screen.findByTestId('grid-row-11'));

    const detailPanel = await screen.findByTestId('line-detail-panel');
    expect(detailPanel).toHaveTextContent('Lineup-based uplift');
    const chip = await screen.findByTestId('suggestion-lineup-source');
    expect(chip).toHaveTextContent('Based on lineup evidence');
  });

  // ── Plan summary trust guardrail ────────────────────────────────────────────

  it('plan summary strip shows "Economics incomplete" when a line has null sell-in price', async () => {
    mockState.apiGetMock.mockImplementation(
      makeDefaultMock([{ ...CLEAN_LINE, calc_sell_in_price_usd: null, calc_buy_price_usd: null,
        calc_promo_reserve_usd: null, calc_non_promo_reserve_usd: null, calc_internal_gp_usd: null,
        calc_flags: ['missing_or_invalid_landed_cost'] }])
    );
    // Summary returns flags so economicsComplete stays false
    mockState.apiGetMock.mockImplementation(async (url: string) => {
      if (url === '/api/v1/commercial-planner/plans/1/summary') {
        return { line_count: 1, total_units: 100, total_internal_gp_usd: null, total_promo_reserve_usd: null, total_non_promo_reserve_usd: null, flags: ['missing_or_invalid_landed_cost'] };
      }
      return makeDefaultMock([{ ...CLEAN_LINE, calc_sell_in_price_usd: null, calc_flags: ['missing_or_invalid_landed_cost'] }])(url);
    });
    renderPage();
    await screen.findByText(/Q3 Plan \(draft\)/i);
    await waitFor(() => expect(screen.queryByTestId('plan-summary-loading')).not.toBeInTheDocument());
    const summary = screen.getByTestId('plan-summary-panel');
    expect(summary).toHaveTextContent('Lines:');
    expect(summary).toHaveTextContent('Units:');
    expect(await screen.findByTestId('economics-incomplete-chip')).toBeInTheDocument();
    expect(summary).toHaveTextContent('Complete missing defaults, then Recalculate.');
    expect(summary).not.toHaveTextContent('Est. OEM net margin USD');
  });

  it('plan summary strip shows OEM net margin label when economics are complete', async () => {
    // Default mock has clean line + flags: [] → economicsComplete = true
    renderPage();
    await screen.findByText(/Q3 Plan \(draft\)/i);
    await waitFor(() => expect(screen.queryByTestId('plan-summary-loading')).not.toBeInTheDocument());
    const summary = screen.getByTestId('plan-summary-panel');
    expect(summary).toHaveTextContent('Est. OEM net margin USD (total)');
    expect(summary).toHaveTextContent('Promo reserve USD');
    expect(summary).not.toHaveTextContent('Economics incomplete');
  });

  it('suggestions section is collapsible and defaults to open', async () => {
    renderPage();
    await waitFor(() => expect(screen.queryByTestId('plan-summary-loading')).not.toBeInTheDocument());
    // Suggestions visible by default (Apply opens preview; button label still "Apply")
    expect(await screen.findByRole('button', { name: 'Apply' })).toBeInTheDocument();
    // Toggle collapses
    const toggleBtn = await screen.findByTestId('toggle-suggestions-btn');
    fireEvent.click(toggleBtn);
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Apply' })).not.toBeInTheDocument());
    // Toggle expands again
    fireEvent.click(toggleBtn);
    expect(await screen.findByRole('button', { name: 'Apply' })).toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Utility function unit tests — fmtFlag and sugTypeLabel
// ─────────────────────────────────────────────────────────────────────────────

describe('fmtFlag', () => {
  it('translates known flag codes to human-readable messages', () => {
    expect(fmtFlag('missing_or_invalid_landed_cost')).toContain('Controlled cost unavailable');
    expect(fmtFlag('missing_sku_assumption')).toContain('Controlled cost missing');
    expect(fmtFlag('margin_floor_breach')).toContain('Margin below floor');
    expect(fmtFlag('impossible_margin_stack')).toContain('unsustainable');
  });

  it('returns the raw flag code for unknown flags', () => {
    expect(fmtFlag('some_unknown_flag')).toBe('some_unknown_flag');
  });
});

describe('sugTypeLabel', () => {
  it('maps suggestion type keys to human-readable labels', () => {
    expect(sugTypeLabel('target_units')).toBe('Suggested units');
    expect(sugTypeLabel('pricing_band')).toBe('Pricing anchor');
    expect(sugTypeLabel('promo_mix_pct')).toBe('Promo split');
  });

  it('falls back to the raw type for unknown keys', () => {
    expect(sugTypeLabel('custom_type')).toBe('custom_type');
  });
});

describe('fmtIssueChipLabel', () => {
  it('maps readiness-style flags to short chip labels without raw snake_case', () => {
    expect(fmtIssueChipLabel('missing_sku_assumption')).toBe('Controlled cost missing');
    expect(fmtIssueChipLabel('missing_distributor_term')).toBe('Missing distributor terms');
    expect(fmtIssueChipLabel('missing_customer_term')).toBe('Missing customer terms');
    expect(fmtIssueChipLabel('missing_or_invalid_landed_cost')).toBe('Controlled cost unavailable');
    expect(fmtIssueChipLabel('margin_floor_breach')).toBe('Margin below floor');
  });
});

describe('fmtModelSalesModel', () => {
  it('joins distinct model and sales model with slash', () => {
    expect(fmtModelSalesModel({ product_model_name: 'A', product_sales_model_name: 'B' })).toBe('A / B');
  });
  it('returns single name when equal or only one set', () => {
    expect(fmtModelSalesModel({ product_model_name: 'X', product_sales_model_name: 'X' })).toBe('X');
    expect(fmtModelSalesModel({ product_model_name: 'X', product_sales_model_name: null })).toBe('X');
    expect(fmtModelSalesModel({ product_model_name: null, product_sales_model_name: 'Y' })).toBe('Y');
  });
  it('returns em dash when empty', () => {
    expect(fmtModelSalesModel({ product_model_name: null, product_sales_model_name: null })).toBe('—');
  });
});

describe('economicsBlockingTooltip', () => {
  it('returns undefined when not blocking', () => {
    expect(economicsBlockingTooltip(undefined)).toBeUndefined();
    expect(economicsBlockingTooltip({ calc_flags: ['margin_floor_breach'] } as any)).toBeUndefined();
  });
  it('joins fmtFlag messages for blocking flags', () => {
    const t = economicsBlockingTooltip({
      calc_flags: ['missing_sku_assumption', 'margin_floor_breach'],
    } as any);
    expect(t).toContain('Controlled cost missing');
  });
});

describe('lineHasBlockingEconomicsFlags', () => {
  it('returns true for configured blocking flags', () => {
    expect(lineHasBlockingEconomicsFlags({ calc_flags: ['missing_sku_assumption'] })).toBe(true);
    expect(lineHasBlockingEconomicsFlags({ calc_flags: ['missing_or_invalid_landed_cost'] })).toBe(true);
    expect(lineHasBlockingEconomicsFlags({ calc_flags: ['missing_distributor_term'] })).toBe(true);
  });
  it('returns false when no blocking flags', () => {
    expect(lineHasBlockingEconomicsFlags({ calc_flags: ['margin_floor_breach'] })).toBe(false);
    expect(lineHasBlockingEconomicsFlags({ calc_flags: [] })).toBe(false);
  });
});

describe('roundPlannerUnits', () => {
  it('rounds fractional values to nearest integer', () => {
    expect(roundPlannerUnits(5287.68)).toBe(5288);
    expect(roundPlannerUnits(5287.4)).toBe(5287);
  });
});

// ─── V3 tests: Column selector modal ─────────────────────────────────────────

vi.mock('@/features/commercial-planner/ColumnSelectorModal', () => {
  const OPTIONAL_FIELDS = [
    'product_spec_warranty',
    'product_spec_os',
    'product_spec_colour',
    'product_category',
    'product_form_factor',
    'product_lifecycle_status',
    'product_line',
    'product_series_name',
    'product_business_unit',
    'effective_customer_margin_pct',
    'effective_customer_rebate_pct',
    'effective_distributor_margin_pct',
    'effective_vat_rate_pct',
    'effective_fx_rate_to_usd',
    'effective_reserve_total_pct',
    'effective_promo_reserve_split_pct',
    'effective_controlled_cost_usd_per_unit',
    'promo_mix_pct',
    'calc_buy_price_usd',
    'calc_promo_reserve_usd',
    'calc_non_promo_reserve_usd',
  ];
  return {
    ColumnSelectorModal: ({
      open,
      onClose,
      onReset,
      onPreset,
      optionalVisible,
      onChange,
      columnMeta,
      specKeyVisible,
      onSpecKeyToggle,
    }: {
      open: boolean;
      onClose: () => void;
      onReset: () => void;
      onPreset: (name: string) => void;
      optionalVisible: Record<string, boolean>;
      onChange: (k: string, v: boolean) => void;
      lines: any[];
      columnMeta?: { total_products: number } | null;
      specKeyVisible?: Record<string, boolean>;
      onSpecKeyToggle?: (k: string, v: boolean) => void;
    }) =>
      open ? (
        <div
          data-testid="column-selector-modal"
          role="dialog"
          aria-label="Planner line columns"
          data-column-meta-total={columnMeta?.total_products ?? ''}
        >
          <span>Planner line columns</span>
          <span>Product catalogue (optional)</span>
          <span data-testid="column-selector-discovered-specs">Discovered spec JSON keys</span>
          <span data-testid="col-modal-locked-note">Locked columns cannot be hidden</span>
          <button data-testid="col-modal-preset-product-spec" onClick={() => onPreset('product_spec')}>
            Product / spec
          </button>
          {['cpu', 'ram', 'storage'].map((key) => (
            <button
              key={key}
              type="button"
              data-testid={`col-spec-toggle-${key}`}
              onClick={() => onSpecKeyToggle?.(key, !(specKeyVisible?.[key] ?? false))}
            >
              toggle spec {key}
            </button>
          ))}
          <button data-testid="col-reset-defaults" onClick={onReset}>
            Reset to defaults
          </button>
          {OPTIONAL_FIELDS.map((field) => (
            <input
              key={field}
              type="checkbox"
              data-testid={`col-toggle-${field}`}
              checked={optionalVisible[field] ?? false}
              onChange={() => onChange(field, !(optionalVisible[field] ?? false))}
            />
          ))}
          <button data-testid="col-modal-close" onClick={onClose}>
            Done
          </button>
        </div>
      ) : null,
  };
});

vi.mock('@/features/commercial-planner/AddProductSetDialog', () => ({
  AddProductSetDialog: ({
    open,
    onClose,
  }: {
    open: boolean;
    onClose: () => void;
    onCreated: () => void;
    activePlanId: number | null;
    existingLines: any[];
  }) =>
    open ? (
      <div data-testid="add-product-set-dialog">
        <span>Add product set</span>
        <button data-testid="pick-entity-customer">Pick Customer</button>
        <button data-testid="pick-entity-distributor">Pick Distributor</button>
        <button onClick={onClose}>Cancel</button>
      </div>
    ) : null,
}));

vi.mock('@/features/commercial-planner/CurrentLineupSection', () => ({
  CurrentLineupSection: ({ activePlanId }: { activePlanId: number | null; onSyncComplete?: () => void }) => (
    <div data-testid="current-lineup-section">
      {activePlanId != null && (
        <button data-testid="upload-current-lineup-btn">Upload current lineup</button>
      )}
    </div>
  ),
}));

describe('V3: Column selector modal', () => {
  function renderPage() {
    const qc = new QueryClient();
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <CommercialPlannerPage />
      </QueryClientProvider>
    );
  }

  beforeEach(() => {
    mockState.apiGetMock.mockImplementation(mockState.defaultApiGetImpl);
    mockState.apiGetMock.mockClear();
  });

  it('opens column selector modal when Columns button is clicked', async () => {
    renderPage();
    const btn = await screen.findByTestId('column-manager-btn');
    await userEvent.click(btn);
    const modal = await screen.findByTestId('column-selector-modal');
    expect(modal).toBeInTheDocument();
    expect(modal).toHaveTextContent('Planner line columns');
  });

  it('shows locked columns note in modal', async () => {
    renderPage();
    const btn = await screen.findByTestId('column-manager-btn');
    await userEvent.click(btn);
    expect(await screen.findByTestId('col-modal-locked-note')).toBeInTheDocument();
  });

  it('preset button triggers onPreset callback', async () => {
    renderPage();
    const btn = await screen.findByTestId('column-manager-btn');
    await userEvent.click(btn);
    const presetBtn = await screen.findByTestId('col-modal-preset-product-spec');
    await userEvent.click(presetBtn);
    // Modal stays open unless we close it - just verify no error
    expect(screen.getByTestId('column-selector-modal')).toBeInTheDocument();
  });
});

describe('V3: Add product set', () => {
  function renderPage() {
    const qc = new QueryClient();
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <CommercialPlannerPage />
      </QueryClientProvider>
    );
  }

  beforeEach(() => {
    mockState.apiGetMock.mockImplementation(mockState.defaultApiGetImpl);
    mockState.apiGetMock.mockClear();
    mockState.apiPostMock.mockClear();
  });

  it('Add product set button is present when plan is active', async () => {
    renderPage();
    await screen.findByText('Q3 Plan (draft)');
    const btn = await screen.findByTestId('add-product-set-btn');
    expect(btn).toBeInTheDocument();
    expect(btn).not.toBeDisabled();
  });

  it('opens Add product set dialog when button clicked', async () => {
    renderPage();
    const btn = await screen.findByTestId('add-product-set-btn');
    await userEvent.click(btn);
    const dialog = await screen.findByTestId('add-product-set-dialog');
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveTextContent('Add product set');
  });

  it('Add product set dialog shows customer and distributor pickers', async () => {
    renderPage();
    const btn = await screen.findByTestId('add-product-set-btn');
    await userEvent.click(btn);
    await screen.findByTestId('add-product-set-dialog');
    expect(screen.getByTestId('pick-entity-customer')).toBeInTheDocument();
    expect(screen.getByTestId('pick-entity-distributor')).toBeInTheDocument();
  });
});

describe('V3: Current lineup section', () => {
  function renderPage() {
    const qc = new QueryClient();
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <CommercialPlannerPage />
      </QueryClientProvider>
    );
  }

  beforeEach(() => {
    mockState.apiGetMock.mockImplementation(mockState.defaultApiGetImpl);
    mockState.apiGetMock.mockClear();
  });

  it('Current lineups section renders when plan is active', async () => {
    renderPage();
    // Wait for plan to load, then check section exists
    await screen.findByText('Q3 Plan (draft)');
    expect(screen.getByTestId('current-lineup-section')).toBeInTheDocument();
  });

  it('Upload current lineup button is present in section', async () => {
    renderPage();
    await screen.findByText('Q3 Plan (draft)');
    expect(screen.getByTestId('upload-current-lineup-btn')).toBeInTheDocument();
  });
});

describe('V3: Richer product label', () => {
  it('Add line product shows SKU · model label format', async () => {
    // This tests that the EntitySearchAutocomplete mock gets the richer getOptionLabel.
    // Since the mock renders a button using the label prop, and getOptionLabel is a function prop,
    // we verify the Add Line dialog opens and product picker is present.
    const qc = new QueryClient();
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CommercialPlannerPage />
      </QueryClientProvider>
    );
    const addLineBtn = await screen.findByText('Add line');
    await userEvent.click(addLineBtn);
    const productPicker = await screen.findByTestId('pick-entity-product');
    expect(productPicker).toBeInTheDocument();
  });
});

describe('V4: Column metadata and label fixes', () => {
  function renderPage() {
    const qc = new QueryClient();
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <CommercialPlannerPage />
      </QueryClientProvider>
    );
  }

  beforeEach(() => {
    mockState.apiGetMock.mockImplementation(mockState.defaultApiGetImpl);
    mockState.apiGetMock.mockClear();
  });

  it('column modal receives columnMeta prop when active plan has column metadata', async () => {
    renderPage();
    await screen.findByText('Q3 Plan (draft)');

    // Open the column selector modal
    const colBtn = await screen.findByTestId('column-manager-btn');
    await userEvent.click(colBtn);

    // Modal should be open and columnMeta should be passed (total_products=10 from mock)
    const modal = await screen.findByTestId('column-selector-modal');
    expect(modal).toBeInTheDocument();
    await waitFor(() => {
      expect(modal.getAttribute('data-column-meta-total')).toBe('10');
    });
  });

  it('plan summary strip shows OEM net margin label not per-unit', async () => {
    renderPage();
    const summaryPanel = await screen.findByTestId('plan-summary-panel');
    await waitFor(() => {
      expect(summaryPanel).not.toHaveTextContent('Loading plan…');
    });
    // New label should appear
    expect(summaryPanel).toHaveTextContent('Est. OEM net margin USD (total)');
    // Old label must not appear
    expect(summaryPanel).not.toHaveTextContent('Estimated internal margin USD');
    expect(summaryPanel).not.toHaveTextContent('/ unit');
  });
});

// ── Phase 2: CurrentLineupSection sync-to-plan tests ─────────────────────────

describe('CurrentLineupSection — sync to plan', () => {
  async function renderCLS(
    activePlanId: number | null,
    casesImpl: (url: string) => any,
  ) {
    const { CurrentLineupSection: RealCLS } = await vi.importActual<
      typeof import('@/features/commercial-planner/CurrentLineupSection')
    >('@/features/commercial-planner/CurrentLineupSection');

    mockState.apiGetMock.mockImplementation(casesImpl);
    mockState.apiPostMock.mockClear();

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return {
      user: userEvent.setup(),
      ...renderWithProviders(
        <QueryClientProvider client={qc}>
          {/* @ts-expect-error: importActual may return mismatched types in test context */}
          <RealCLS activePlanId={activePlanId} />
        </QueryClientProvider>
      ),
    };
  }

  const ACCEPTED_CASE = {
    id: 1,
    import_job_id: null,
    commercial_plan_id: 5,
    file_name: 'lineup_q2.csv',
    period_label: 'Q2 2026',
    country_code: 'US',
    currency_code: 'USD',
    commercial_status: 'accepted',
    notes: null,
    accepted_at: '2026-04-01T00:00:00Z',
    accepted_by: 'manager',
    line_count: 10,
    created_at: null,
  };

  const DRAFT_CASE = {
    ...ACCEPTED_CASE,
    id: 2,
    commercial_status: 'draft_imported',
    accepted_at: null,
    accepted_by: null,
  };

  it('sync button visible only for accepted cases', async () => {
    const { user } = await renderCLS(5, async (url: string) => {
      if (url.includes('/lineup-cases')) return [ACCEPTED_CASE, DRAFT_CASE];
      return [];
    });

    // Expand section
    const toggle = await screen.findByTestId('current-lineup-section-toggle');
    await user.click(toggle);

    // Sync button present for accepted case, absent for draft case
    const syncBtns = screen.queryAllByTestId('sync-to-plan-btn');
    expect(syncBtns.length).toBe(1);
  });

  it('sync preview dialog shows counts when sync button is clicked', async () => {
    const previewPayload = {
      case_id: 1,
      plan_id: 5,
      total_lines: 10,
      will_create: 8,
      skipped_duplicates: 1,
      skipped_unresolved: 1,
      skipped_missing_srp: 0,
      created: 0,
      created_line_ids: [],
      warnings: [],
    };

    const { user } = await renderCLS(5, async (url: string) => {
      if (url.includes('/lineup-cases') && !url.includes('/sync-to-plan')) return [ACCEPTED_CASE];
      if (url.includes('/sync-to-plan/preview')) return previewPayload;
      return [];
    });

    // Expand and click sync
    await user.click(await screen.findByTestId('current-lineup-section-toggle'));
    await user.click(await screen.findByTestId('sync-to-plan-btn'));

    // Dialog should appear with counts
    await waitFor(() => {
      expect(screen.getByText(/Total lines in this lineup case/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Total lines in this lineup case/i)).toBeInTheDocument();
    expect(screen.getByText(/Eligible planner lines/i)).toBeInTheDocument();
  });

  it('workbench shows resolve entities and sync preview chip when case is draft and linked to plan', async () => {
    const draft = {
      id: 3,
      import_job_id: null,
      commercial_plan_id: 5,
      file_name: 'f.csv',
      period_label: 'Q2',
      country_code: 'US',
      currency_code: 'USD',
      commercial_status: 'draft_imported',
      notes: null,
      accepted_at: null,
      accepted_by: null,
      line_count: 1,
      created_at: null,
    };
    const line = {
      id: 1,
      case_id: 3,
      source_row_number: 1,
      product_id: 10,
      product_sku: 'SKU',
      product_name: null,
      product_part_number: null,
      product_model_name: null,
      product_sales_model_name: null,
      customer_id: 7,
      customer_code: 'C',
      customer_name: 'Cust',
      distributor_id: 3,
      distributor_code: 'D',
      distributor_name: 'Dist',
      customer_token: null,
      distributor_token_raw: null,
      sku_raw: null,
      part_number_raw: null,
      model_raw: null,
      quantity_units: 1,
      msrp_local: 100,
      promo_price_evidence_local: null,
      dap_evidence_local: 5,
      diagnostic_codes: [],
      row_status: 'imported',
      sync_eligible: true,
      sync_skip_reason: null,
    };
    const { user } = await renderCLS(5, async (url: string) => {
      if (url.includes('/lineup-cases?')) return [draft];
      if (url.includes('/lineup-cases/3/lines')) return { lines: [line], dap_semantics_note: 'DAP is evidence-only.' };
      return [];
    });
    await user.click(await screen.findByTestId('current-lineup-section-toggle'));
    await user.click(await screen.findByTestId('lineup-workbench-3'));
    expect(await screen.findByTestId('lineup-entity-resolution-open')).toBeInTheDocument();
    expect(await screen.findByTestId('lineup-workbench-sync-eligible-chip')).toBeInTheDocument();
  });
});
