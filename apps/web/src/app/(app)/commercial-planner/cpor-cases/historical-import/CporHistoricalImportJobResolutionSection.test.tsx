import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';

import { CporHistoricalImportJobResolutionSection } from './CporHistoricalImportJobResolutionSection';
import type { CporHistoricalCandidate, CporPlanClass } from './cporHistoricalSteward.config';
import { CPOR_HISTORICAL_ENGINE_CONFIG } from './cporHistoricalSteward.engineConfig';

const PRODUCT_CANDIDATES: CporHistoricalCandidate[] = [
  {
    id: 101,
    entity: 'product',
    token: 'MODEL-A',
    row_count: 4,
    status: 'unresolved',
    confidence: 0.92,
    plan_class: 'ready_to_map',
    match_reason: 'prefix_match',
    suggestions: [{ dim_id: 11, label: 'Model A Pro', score: 0.92, reason: 'prefix_match' }],
    sample_raw_values: ['MODEL-A', 'Model A'],
    case_codes: ['CASE-1'],
    total_units: 12,
    total_reported_value: 3400,
  },
  {
    id: 102,
    entity: 'product',
    token: 'MODEL-B',
    row_count: 1,
    status: 'unresolved',
    confidence: 1.0,
    plan_class: 'ambiguous_eligible',
    match_reason: 'exact_key_collision:sales_model_name',
    suggestions: [
      { dim_id: 21, label: 'Model B One', score: 1.0, reason: 'exact_key_collision:sales_model_name' },
      { dim_id: 22, label: 'Model B Two', score: 1.0, reason: 'exact_key_collision:sales_model_name' },
    ],
    sample_raw_values: ['MODEL-B'],
    case_codes: ['CASE-2'],
    total_units: 3,
    total_reported_value: null,
  },
];

vi.mock('./cporHistoricalImportApi', async () => {
  const actual = await vi.importActual<typeof import('./cporHistoricalImportApi')>(
    './cporHistoricalImportApi'
  );
  return {
    ...actual,
    fetchCporHistoricalSummary: vi.fn(async () => ({
      id: 42,
      stage: 'validated',
      status: 'completed',
      file_name: 'test.xlsx',
      staging_count: 10,
      unresolved_counts: { product: 2, customer: 1, distributor: 0 },
      plan_class_counts: {
        product: {
          ready_to_map: 1,
          ambiguous_eligible: 1,
          no_match: 0,
          needs_review: 0,
        },
      },
      cases_ready: 3,
      cases_blocked: 1,
    })),
    fetchCporHistoricalCandidates: vi.fn(
      async (
        _jobId: number,
        _entity: string,
        opts: { skip: number; limit: number; planClass?: CporPlanClass | null }
      ) => {
        const filtered = opts.planClass
          ? PRODUCT_CANDIDATES.filter((c) => c.plan_class === opts.planClass)
          : PRODUCT_CANDIDATES;
        return {
          entity: 'product',
          candidates: filtered,
          items: filtered,
          total: filtered.length,
          skip: opts.skip,
          limit: opts.limit,
          counts: { product: 2, customer: 1, distributor: 0 },
          plan_class_counts: {
            product: {
              ready_to_map: 1,
              ambiguous_eligible: 1,
              no_match: 0,
              needs_review: 0,
            },
          },
        };
      }
    ),
  };
});

vi.mock('@/features/import-steward/useStewardResolutionPlan', () => ({
  useStewardResolutionPlan: () => ({
    resolutionPlan: {
      summary: { total: 2, ready: 1, not_ready: 1 },
      rows: [{ candidate_id: 101, ready: true }],
    },
    planByCandidateId: new Map([[101, { candidate_id: 101, ready: true }]]),
    readyPlanCandidateIds: [101],
    suggestionsQuery: { isFetching: false, isError: false, error: null, refetch: vi.fn() },
    applyResolutionPlan: { isPending: false, mutate: vi.fn(), mutateAsync: vi.fn() },
    applyAllConfirmOpen: false,
    setApplyAllConfirmOpen: vi.fn(),
    refreshSuggestions: vi.fn(),
    evictResolvedCandidates: vi.fn(),
    shrinkPlanScope: vi.fn(),
    revalidateFromServer: { isPending: false },
    planOverrideMap: {},
    planLoadToken: 0,
    replaceResolutionPlan: vi.fn(),
  }),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('CporHistoricalImportJobResolutionSection', () => {
  it('renders entity tabs when jobId is set', async () => {
    wrap(<CporHistoricalImportJobResolutionSection importJobId={42} />);
    expect(await screen.findByTestId('cpor-historical-entity-tabs')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-tab-product')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-tab-customer')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-tab-distributor')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-steward-workspace-viewport-shell')).toBeInTheDocument();
    expect(screen.getByTestId('dsi-steward-candidate-filters')).toBeInTheDocument();
  });

  it('shows confidence bands, units/value, and plan toolbar from Unit C payload', async () => {
    wrap(<CporHistoricalImportJobResolutionSection importJobId={42} />);
    expect(await screen.findByText('Model A Pro')).toBeInTheDocument();
    expect(screen.getAllByTestId('cpor-historical-confidence-band').length).toBeGreaterThan(0);
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('3400')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-resolution-plan-toolbar')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-resolution-plan-apply-all')).toBeInTheDocument();
    expect(screen.getByTestId('dsi-candidates-pagination')).toBeInTheDocument();
    expect(screen.getByTestId('dsi-filter-queue-ambiguous_eligible')).toBeInTheDocument();
    expect(screen.queryByTestId('dsi-filter-queue-provisional')).not.toBeInTheDocument();
  });

  it('opens suggestion-first drawer (not autocomplete-only)', async () => {
    const user = userEvent.setup();
    wrap(<CporHistoricalImportJobResolutionSection importJobId={42} />);
    await screen.findByText('Model A Pro');
    const mapButtons = await screen.findAllByRole('button', { name: 'Map…' });
    await user.click(mapButtons[0]!);
    expect(await screen.findByTestId('cpor-historical-drawer-intelligence')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-drawer-suggestions')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-suggestion-map-11')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-drawer-override-search')).toBeInTheDocument();
  });

  it('filters by plan_class ready_to_map via server plan_class param', async () => {
    const user = userEvent.setup();
    wrap(<CporHistoricalImportJobResolutionSection importJobId={42} />);
    await screen.findByText('MODEL-A');
    expect(screen.getByText('MODEL-B')).toBeInTheDocument();
    await user.click(screen.getByTestId('dsi-filter-queue-ready_to_map'));
    expect(await screen.findByText('MODEL-A')).toBeInTheDocument();
    expect(screen.queryByText('MODEL-B')).not.toBeInTheDocument();
  });

  it('uses persisted surrogate ids for row map test ids (not string-hash)', async () => {
    wrap(<CporHistoricalImportJobResolutionSection importJobId={42} />);
    expect(await screen.findByTestId('cpor-historical-row-map-101')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-historical-row-map-102')).toBeInTheDocument();
  });

  it('shows prompt when jobId is null', () => {
    wrap(<CporHistoricalImportJobResolutionSection importJobId={null} />);
    expect(screen.getByTestId('cpor-historical-import-job-resolution-section')).toHaveTextContent(
      /Upload and validate/
    );
  });
});

describe('CPOR_HISTORICAL_ENGINE_CONFIG', () => {
  it('points plan compute/apply at CPOR resolution-plan routes (not case-apply)', () => {
    expect(CPOR_HISTORICAL_ENGINE_CONFIG.computePlanAsyncPath(7)).toBe(
      '/api/v1/cpor/historical-import/jobs/7/resolution-plan/compute-async'
    );
    expect(CPOR_HISTORICAL_ENGINE_CONFIG.applyPlanAsyncPath(7)).toBe(
      '/api/v1/cpor/historical-import/jobs/7/resolution-plan/apply-async'
    );
    expect(CPOR_HISTORICAL_ENGINE_CONFIG.computeBackgroundKind).toBe('cpor_resolution_plan');
    expect(CPOR_HISTORICAL_ENGINE_CONFIG.applyBackgroundKind).toBe('cpor_resolution_plan');
  });
});
