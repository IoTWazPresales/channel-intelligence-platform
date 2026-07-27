import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import type { DsiCandidateRow } from '@/app/(app)/admin/imports/dsi/dsi-mapping-steward-panel';

import { DsiImportJobResolutionSection } from './DsiImportJobResolutionSection';

const mockApiGet = vi.fn();
const mockApiPost = vi.fn();

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => mockApiGet(...args),
  apiPost: (...args: unknown[]) => mockApiPost(...args),
  safeDisplayError: (e: unknown) => String(e),
}));

const hoisted = vi.hoisted(() => {
  const candidateRow: DsiCandidateRow = {
    id: 101,
    import_job_id: 7,
    source_definition_id: null,
    entity_type: 'customer_dealer_token',
    normalized_key: 'acme_retail',
    dealer_group_token: null,
    row_count: 3,
    total_units: 10,
    total_reported_value: 100,
    sample_raw_values: ['ACME RETAIL'],
    suggested_entity_id: null,
    match_reason: null,
    confidence_score: null,
    status: 'open',
    context: {},
  };
  return { candidateRow, planResult: null as Record<string, unknown> | null };
});

const PLAN_COMPUTE_TASK_ID = 'test-plan-compute-task';

function defaultApiGet(path: string) {
  if (String(path).includes('dsi-steward-bulk-task')) {
    return {
      import_job_id: 7,
      task_id: PLAN_COMPUTE_TASK_ID,
      state: 'SUCCESS',
      result: hoisted.planResult ?? {
        import_job_id: 7,
        rows: [],
        summary: { total: 0, ready: 0, not_ready: 0, hold: 0 },
        defaults_used: { region_id: null, channel_id: null },
      },
    };
  }
  if (String(path).includes('dsi-unresolved-geo-tokens')) {
    return { import_job_id: 7, channels: [], regions: [] };
  }
  if (String(path).includes('/customers?')) {
    return { items: [{ id: 42, customer_code: 'C42', customer_name: 'Test Co' }] };
  }
  return [];
}

/** Wire apiPost/apiGet for async resolution-plan compute + poll. */
function installResolutionPlanMocks(
  planPayload: Record<string, unknown>,
  extraPost?: (url: string, body?: unknown) => Promise<unknown> | unknown
) {
  hoisted.planResult = planPayload;
  mockApiGet.mockImplementation(async (path: string) => defaultApiGet(path));
  mockApiPost.mockImplementation(async (url: string, body?: unknown) => {
    if (extraPost) {
      const hit = await extraPost(url, body);
      if (hit !== undefined) return hit;
    }
    if (String(url).includes('compute-async')) {
      return { import_job_id: 7, task_id: PLAN_COMPUTE_TASK_ID, async_poll: true };
    }
    if (String(url).includes('dsi-resolution-plan/apply')) {
      return {
        import_job_id: 7,
        applied: 1,
        failed: 0,
        skipped_hold: 0,
        skipped_not_ready: 0,
        results: [],
      };
    }
    if (String(url).includes('dsi-resolution-plan/effective')) {
      return planPayload;
    }
    if (String(url).includes('dsi-resolution-plan')) {
      return planPayload;
    }
    return {
      import_job_id: 7,
      action: 'ignore',
      results: [],
      totals: { ok_count: 0, staging_rows_affected: 0 },
    };
  });
}

vi.mock('@/app/(app)/admin/imports/dsi/dsi-mapping-steward-panel', () => ({
  DsiMappingStewardPanel: () => <div data-testid="dsi-steward-panel">steward</div>,
}));

describe('DsiImportJobResolutionSection bulk steward', () => {
  beforeEach(() => {
    mockApiPost.mockReset();
    mockApiGet.mockReset();
    installResolutionPlanMocks({
      import_job_id: 7,
      rows: [],
      summary: { total: 0, ready: 0, not_ready: 0, hold: 0 },
      defaults_used: { region_id: null, channel_id: null },
    });
  });

  function renderSection() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <DsiImportJobResolutionSection importJobId={7} candidates={[hoisted.candidateRow]} onInvalidate={() => {}} />
      </QueryClientProvider>
    );
  }

  it('opens bulk map form without crashing (StewardBulkActionInlineForm)', async () => {
    const user = userEvent.setup();
    renderSection();
    await user.click(screen.getByTestId('dsi-bulk-map-open'));
    expect(await screen.findByTestId('dsi-bulk-action-form')).toBeInTheDocument();
    expect(screen.getByTestId('dsi-bulk-customer-search')).toBeInTheDocument();
  });

  it('disables bulk preview when map_customer is chosen without a customer id', async () => {
    const user = userEvent.setup();
    renderSection();

    await user.click(screen.getByTestId('dsi-bulk-map-open'));
    await screen.findByTestId('dsi-bulk-action-form');

    const previewBtn = screen.getByTestId('dsi-bulk-preview-inline');
    await waitFor(() => expect(previewBtn).toBeDisabled());
  });
});

describe('DsiImportJobResolutionSection resolution plan', () => {
  const defaultPlanRow = {
    candidate_id: 101,
    entity_type: 'customer_dealer_token',
    candidate_status: 'open',
    suggested_action: 'map_customer',
    baseline_suggested_action: 'map_customer',
    suggested_target_id: 55,
    baseline_target_id: 55,
    ready: true,
    confidence: 0.9,
    plan_status: 'ready',
    reason: 'Matched',
    row_count: 3,
    total_units: 10,
    total_reported_value: 100,
    hold_for_manual_review: false,
    resolution_blockers: [] as string[],
  };

  beforeEach(() => {
    mockApiPost.mockReset();
    mockApiGet.mockReset();
    installResolutionPlanMocks({
      import_job_id: 7,
      rows: [defaultPlanRow],
      summary: { total: 1, ready: 1, not_ready: 0, hold: 0 },
      defaults_used: { region_id: null, channel_id: null },
    });
  });

  function renderPlanSection(cands: DsiCandidateRow[] = [hoisted.candidateRow]) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <DsiImportJobResolutionSection importJobId={7} candidates={cands} onInvalidate={() => {}} />
      </QueryClientProvider>
    );
  }

  async function waitForSuggestionsPost() {
    await waitFor(() => {
      const gen = mockApiPost.mock.calls.filter((c) => String(c[0]).includes('compute-async'));
      expect(gen.length).toBeGreaterThanOrEqual(1);
    });
  }

  async function waitForWorkspaceTable() {
    const grid = screen.getByTestId('dsi-resolution-candidate-grid');
    await waitFor(() => {
      expect(within(grid).getByRole('table')).toBeInTheDocument();
    });
    return grid;
  }

  it('auto-loads suggestions when candidates are present (no generate click)', async () => {
    renderPlanSection();
    await waitForSuggestionsPost();
    expect(screen.queryByTestId('dsi-resolution-plan-dialog')).toBeNull();
  });

  it('posts apply with candidate ids after suggestions load + apply all', async () => {
    const user = userEvent.setup();
    renderPlanSection();
    await waitForSuggestionsPost();

    await user.click(screen.getByTestId('dsi-resolution-plan-apply-all'));
    await user.click(await screen.findByTestId('dsi-resolution-plan-apply-all-confirm'));
    await waitFor(() => {
      const applyCalls = mockApiPost.mock.calls.filter((c) => String(c[0]).includes('dsi-resolution-plan/apply'));
      expect(applyCalls.length).toBeGreaterThanOrEqual(1);
      expect(applyCalls[applyCalls.length - 1][1]).toEqual(
        expect.objectContaining({
          candidate_ids: [101],
          confirm_for_suspicious_distributor_token: false,
        })
      );
    });
  });

  it('shows raw sample text in the in-page candidate grid after suggestions load', async () => {
    renderPlanSection();
    await waitForSuggestionsPost();
    const grid = await waitForWorkspaceTable();
    expect(within(grid).getByTitle('ACME RETAIL')).toBeInTheDocument();
  });

  it('Refresh suggestions is clickable again after a failed initial plan request', async () => {
    const user = userEvent.setup();
    mockApiPost.mockReset();
    mockApiGet.mockReset();
    let genN = 0;
    const planPayload = {
      import_job_id: 7,
      rows: [defaultPlanRow],
      summary: { total: 1, ready: 1, not_ready: 0, hold: 0 },
      defaults_used: { region_id: null, channel_id: null },
    };
    installResolutionPlanMocks(planPayload, async (url) => {
      if (String(url).includes('compute-async')) {
        genN += 1;
        if (genN === 1) throw new Error('network');
      }
      return undefined;
    });

    renderPlanSection();
    const btn = screen.getByTestId('dsi-resolution-suggestions-refresh');
    await waitFor(() => expect(btn).not.toBeDisabled());
    await user.click(btn);
    await waitForSuggestionsPost();
  });

  it('calls effective endpoint after global distributor confirm is toggled', async () => {
    const user = userEvent.setup();
    renderPlanSection();
    await waitForSuggestionsPost();
    await screen.findByTestId('dsi-resolution-plan-toolbar');
    const before = mockApiPost.mock.calls.filter((c) => String(c[0]).includes('effective')).length;
    await user.click(screen.getByTestId('dsi-plan-options-open'));
    await user.click(screen.getByTestId('dsi-plan-global-suspicious-confirm'));
    await waitFor(
      () => {
        const after = mockApiPost.mock.calls.filter((c) => String(c[0]).includes('effective'));
        expect(after.length).toBeGreaterThan(before);
        expect(after[after.length - 1][1]).toEqual(
          expect.objectContaining({ confirm_for_suspicious_distributor_token: true })
        );
      },
      { timeout: 5000 }
    );
  });

  it('shows 12 candidates in the workspace when plan has 12 rows', async () => {
    const rows = Array.from({ length: 12 }, (_, i) => ({
      candidate_id: 200 + i,
      entity_type: 'distributor_token',
      candidate_status: 'open',
      suggested_action: 'ignore',
      baseline_suggested_action: 'ignore',
      suggested_target_id: null,
      baseline_target_id: null,
      ready: true,
      confidence: 0.5,
      plan_status: 'ready',
      reason: 'x',
      row_count: 1,
      total_units: 1,
      total_reported_value: 1,
      hold_for_manual_review: false,
      resolution_blockers: [],
      normalized_key: `k${i}`,
    }));
    installResolutionPlanMocks({
      import_job_id: 7,
      rows,
      summary: { total: 12, ready: 12, not_ready: 0, hold: 0 },
      defaults_used: { region_id: null, channel_id: null },
    });

    const candidates: DsiCandidateRow[] = rows.map((r, i) => ({
      id: 200 + i,
      import_job_id: 7,
      source_definition_id: null,
      entity_type: 'distributor_token',
      normalized_key: r.normalized_key as string,
      dealer_group_token: null,
      row_count: 1,
      total_units: 1,
      total_reported_value: 1,
      sample_raw_values: [`T${i}`],
      suggested_entity_id: null,
      match_reason: null,
      confidence_score: null,
      status: 'open',
      context: {},
    }));

    renderPlanSection(candidates);
    await waitForSuggestionsPost();
    expect(screen.getByTestId('dsi-import-job-resolution')).toBeTruthy();
    expect(screen.getByTestId('dsi-resolution-candidate-grid')).toBeTruthy();
    const filters = screen.getByTestId('dsi-steward-candidate-filters');
    expect(within(filters).getByText(/Showing 12 of 12/)).toBeTruthy();
    const grid = await waitForWorkspaceTable();
    for (let i = 0; i < 12; i += 1) {
      expect(within(grid).getByTitle(`T${i}`)).toBeInTheDocument();
    }
  });

  it('shows filter chips and empty table message when there are zero candidates', async () => {
    renderPlanSection([]);
    const filters = await screen.findByTestId('dsi-steward-candidate-filters');
    expect(within(filters).getByTestId('dsi-filter-queue-all')).toBeInTheDocument();
    expect(within(filters).getByText(/No open candidates on this tab/)).toBeInTheDocument();
    const grid = screen.getByTestId('dsi-resolution-candidate-grid');
    expect(
      within(grid).getByText(/No DSI mapping candidates for this import job/i)
    ).toBeInTheDocument();
  });

  it('queue filter chips narrow visible workspace rows', async () => {
    const user = userEvent.setup();
    const planRows = [
      {
        candidate_id: 301,
        entity_type: 'customer_dealer_token',
        candidate_status: 'open',
        suggested_action: 'map_customer',
        baseline_suggested_action: 'map_customer',
        suggested_target_id: 1,
        baseline_target_id: 1,
        ready: true,
        confidence: 0.9,
        plan_status: 'ready',
        reason: 'ok',
        row_count: 1,
        total_units: 1,
        total_reported_value: 1,
        hold_for_manual_review: false,
        resolution_blockers: [],
      },
      {
        candidate_id: 302,
        entity_type: 'customer_dealer_token',
        candidate_status: 'open',
        suggested_action: 'ignore',
        baseline_suggested_action: 'ignore',
        suggested_target_id: null,
        baseline_target_id: null,
        ready: false,
        confidence: 0.2,
        plan_status: 'blocked',
        reason: 'blocked',
        row_count: 1,
        total_units: 1,
        total_reported_value: 1,
        hold_for_manual_review: false,
        resolution_blockers: ['x'],
      },
    ];
    installResolutionPlanMocks({
      import_job_id: 7,
      rows: planRows,
      summary: { total: 2, ready: 1, not_ready: 1, hold: 0 },
      defaults_used: { region_id: null, channel_id: null },
    });

    const two: DsiCandidateRow[] = [301, 302].map((id) => ({
      ...hoisted.candidateRow,
      id,
      sample_raw_values: id === 301 ? ['A'] : ['B'],
    }));

    renderPlanSection(two);
    await waitForSuggestionsPost();
    const filters = screen.getByTestId('dsi-steward-candidate-filters');
    expect(within(filters).getByText(/Showing 2 of 2/)).toBeTruthy();
    const grid = await waitForWorkspaceTable();
    await user.click(screen.getByTestId('dsi-filter-queue-ready_to_map'));
    await waitFor(() => {
      expect(within(filters).getByText(/Showing 1 of 2/)).toBeTruthy();
    });
    expect(within(grid).getByTitle('A')).toBeInTheDocument();
    expect(within(grid).queryByTitle('B')).not.toBeInTheDocument();
  });

  it('entity and action filter chips narrow visible rows', async () => {
    const user = userEvent.setup();
    const planRows = [
      {
        candidate_id: 401,
        entity_type: 'distributor_token',
        candidate_status: 'open',
        suggested_action: 'ignore',
        baseline_suggested_action: 'ignore',
        suggested_target_id: null,
        baseline_target_id: null,
        ready: true,
        confidence: 0.5,
        plan_status: 'ready',
        reason: '',
        row_count: 1,
        total_units: 1,
        total_reported_value: 1,
        hold_for_manual_review: false,
        resolution_blockers: [],
        normalized_key: 'd',
      },
      {
        candidate_id: 402,
        entity_type: 'customer_dealer_token',
        candidate_status: 'open',
        suggested_action: 'map_customer',
        baseline_suggested_action: 'map_customer',
        suggested_target_id: 9,
        baseline_target_id: 9,
        ready: true,
        confidence: 0.5,
        plan_status: 'ready',
        reason: '',
        row_count: 1,
        total_units: 1,
        total_reported_value: 1,
        hold_for_manual_review: false,
        resolution_blockers: [],
      },
    ];
    installResolutionPlanMocks({
      import_job_id: 7,
      rows: planRows,
      summary: { total: 2, ready: 2, not_ready: 0, hold: 0 },
      defaults_used: { region_id: null, channel_id: null },
    });

    const two: DsiCandidateRow[] = [
      { ...hoisted.candidateRow, id: 401, entity_type: 'distributor_token', sample_raw_values: ['D'] },
      { ...hoisted.candidateRow, id: 402, sample_raw_values: ['C'] },
    ];

    renderPlanSection(two);
    await waitForSuggestionsPost();
    const filters = screen.getByTestId('dsi-steward-candidate-filters');
    const grid = await waitForWorkspaceTable();
    await user.click(screen.getByTestId('dsi-filter-entity-distributor'));
    await waitFor(() => {
      expect(within(filters).getByText(/Showing 1 of 2/)).toBeTruthy();
    });
    expect(within(grid).getByTitle('D')).toBeInTheDocument();
    expect(within(grid).queryByTitle('C')).not.toBeInTheDocument();
    await user.click(screen.getByTestId('dsi-filter-entity-all'));
    await user.click(screen.getByTestId('dsi-filter-queue-ready_to_map'));
    await waitFor(() => {
      expect(within(filters).getByText(/Showing 1 of 2/)).toBeTruthy();
    });
    expect(within(grid).getByTitle('C')).toBeInTheDocument();
    expect(within(grid).queryByTitle('D')).not.toBeInTheDocument();
  });

  it('drawer shows full source evidence after Open', async () => {
    const user = userEvent.setup();
    const richCandidate: DsiCandidateRow = {
      ...hoisted.candidateRow,
      context: {
        source_region_raw_samples: ['BC'],
        source_channel_raw_samples: ['Drug'],
      },
    };
    installResolutionPlanMocks({
      import_job_id: 7,
      rows: [
        {
          candidate_id: 101,
          entity_type: 'customer_dealer_token',
          candidate_status: 'open',
          suggested_action: 'create_provisional_customer',
          baseline_suggested_action: 'create_provisional_customer',
          suggested_target_id: null,
          baseline_target_id: null,
          ready: true,
          confidence: 0.9,
          plan_status: 'ready',
          reason: 'Matched',
          row_count: 3,
          total_units: 10,
          total_reported_value: 100,
          hold_for_manual_review: false,
          resolution_blockers: [],
          source_region_resolution_message: 'Region resolved from column A',
          source_channel_resolution_message: 'Channel resolved from column B',
        },
      ],
      summary: { total: 1, ready: 1, not_ready: 0, hold: 0 },
      defaults_used: { region_id: null, channel_id: null },
    });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <DsiImportJobResolutionSection importJobId={7} candidates={[richCandidate]} onInvalidate={() => {}} />
      </QueryClientProvider>
    );

    await waitForSuggestionsPost();
    await waitForWorkspaceTable();
    await user.click(await screen.findByTestId('dsi-plan-cell-101'));
    await waitFor(() => {
      expect(screen.getByTestId('dsi-resolution-suggestion-drawer')).toBeVisible();
    });
    await waitFor(
      () => {
        const drawer = screen.getByTestId('dsi-resolution-suggestion-drawer');
        expect(within(drawer).getByText('BC')).toBeTruthy();
        expect(within(drawer).getByText('Drug')).toBeTruthy();
        expect(within(drawer).getByText(/Region resolved from column A/)).toBeTruthy();
        expect(within(drawer).getByText(/Channel resolved from column B/)).toBeTruthy();
      },
      { timeout: 15000 }
    );
  }, 20000);

  it('shows unassigned geo badge in drawer for ready provisional customer without region/channel', async () => {
    const user = userEvent.setup();
    installResolutionPlanMocks({
      import_job_id: 7,
      rows: [
        {
          candidate_id: 101,
          entity_type: 'customer_dealer_token',
          candidate_status: 'open',
          suggested_action: 'create_provisional_customer',
          baseline_suggested_action: 'create_provisional_customer',
          suggested_target_id: null,
          baseline_target_id: null,
          ready: true,
          confidence: 0.8,
          plan_status: 'ready',
          reason: 'New',
          row_count: 1,
          total_units: 1,
          total_reported_value: 1,
          hold_for_manual_review: false,
          resolution_blockers: [],
          effective_region_id: null,
          effective_channel_id: null,
        },
      ],
      summary: { total: 1, ready: 1, not_ready: 0, hold: 0 },
      defaults_used: { region_id: null, channel_id: null },
    });

    renderPlanSection();
    await waitForSuggestionsPost();
    await waitForWorkspaceTable();
    await user.click(await screen.findByTestId('dsi-plan-cell-101'));
    await waitFor(() => {
      expect(screen.getByTestId('dsi-plan-unassigned-geo-badge')).toBeVisible();
    });
  });

  it('apply selected ready uses main grid selection when row is ready', async () => {
    const user = userEvent.setup();
    renderPlanSection();
    await waitForSuggestionsPost();
    await user.click(screen.getByTestId('dsi-plan-select-visible-ready'));
    const applySel = screen.getByTestId('dsi-resolution-plan-apply-selected');
    await waitFor(() => expect(applySel).not.toBeDisabled());
    await user.click(applySel);
    await waitFor(() => {
      const applyCalls = mockApiPost.mock.calls.filter((c) => String(c[0]).includes('dsi-resolution-plan/apply'));
      expect(applyCalls[applyCalls.length - 1][1]).toEqual(
        expect.objectContaining({
          candidate_ids: [101],
        })
      );
    });
  });

  it('changing an override in the drawer triggers effective refresh', async () => {
    const user = userEvent.setup();
    renderPlanSection();
    await waitForSuggestionsPost();
    await waitForWorkspaceTable();
    const before = mockApiPost.mock.calls.filter((c) => String(c[0]).includes('effective')).length;
    await user.click(await screen.findByTestId('dsi-plan-cell-101'));
    const drawer = await screen.findByTestId('dsi-resolution-suggestion-drawer');
    const holdBox = await within(drawer).findByRole('checkbox', { name: /hold \(skip in apply\)/i });
    expect(holdBox).toBeInTheDocument();
    await user.click(holdBox);
    await waitFor(
      () => {
        const after = mockApiPost.mock.calls.filter((c) => String(c[0]).includes('effective'));
        expect(after.length).toBeGreaterThan(before);
      },
      { timeout: 5000 }
    );
  });

  it('exposes Refresh suggestions separately from server revalidation', () => {
    renderPlanSection();
    expect(screen.getByTestId('dsi-resolution-suggestions-refresh')).toBeTruthy();
    expect(screen.getByTestId('dsi-import-revalidate-server')).toBeTruthy();
  });
});
