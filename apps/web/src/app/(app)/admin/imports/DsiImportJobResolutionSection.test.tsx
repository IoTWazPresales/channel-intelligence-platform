import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import type { DsiCandidateRow } from '../mappings/DsiCandidateStewardPanel';

import { DsiImportJobResolutionSection } from './DsiImportJobResolutionSection';

const mockApiPost = vi.fn();

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async () => []),
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
  return { candidateRow };
});

vi.mock('@/components/EnterpriseDataGrid', () => {
  const React = require('react');
  return {
    EnterpriseDataGrid: React.forwardRef((props: { gridOptions?: { onSelectionChanged?: (e: unknown) => void } }, _ref: unknown) => {
      React.useEffect(() => {
        props.gridOptions?.onSelectionChanged?.({
          api: { getSelectedRows: () => [hoisted.candidateRow] },
        });
      }, [props.gridOptions]);
      return React.createElement('div', { 'data-testid': 'mock-grid' });
    }),
  };
});

vi.mock('../mappings/DsiCandidateStewardPanel', () => ({
  DsiCandidateStewardPanel: () => <div data-testid="dsi-steward-panel">steward</div>,
}));

describe('DsiImportJobResolutionSection bulk steward', () => {
  beforeEach(() => {
    mockApiPost.mockReset();
    mockApiPost.mockResolvedValue({
      import_job_id: 7,
      action: 'ignore',
      results: [],
      totals: { ok_count: 0, staging_rows_affected: 0 },
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

  it('disables bulk preview when map_customer is chosen without a customer id', async () => {
    const user = userEvent.setup();
    renderSection();

    await user.click(screen.getByRole('button', { name: /bulk actions/i }));

    await waitFor(() => {
      expect(screen.getByTestId('bulk-selection-count')).toHaveTextContent('1 selected');
    });

    const previewBtn = screen.getByTestId('bulk-preview-danger');
    await waitFor(() => expect(previewBtn).not.toBeDisabled());

    await user.click(screen.getByLabelText(/bulk action/i));
    await user.click(await screen.findByRole('option', { name: /map to existing customer/i }));

    await waitFor(() => expect(previewBtn).toBeDisabled());

    const customerField = await screen.findByRole('spinbutton', { name: /customer id/i });
    await user.clear(customerField);
    await user.type(customerField, '42');
    await waitFor(() => expect(previewBtn).not.toBeDisabled());
  });
});

describe('DsiImportJobResolutionSection resolution plan', () => {
  beforeEach(() => {
    mockApiPost.mockReset();
    mockApiPost.mockImplementation(async (url: string) => {
      if (url.includes('dsi-resolution-plan/apply')) {
        return {
          import_job_id: 7,
          applied: 1,
          failed: 0,
          skipped_hold: 0,
          skipped_not_ready: 0,
          results: [],
        };
      }
      if (url.includes('dsi-resolution-plan/effective')) {
        return {
          import_job_id: 7,
          rows: [
            {
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
              resolution_blockers: [],
            },
          ],
          summary: { total: 1, ready: 1, not_ready: 0, hold: 0 },
          defaults_used: { region_id: null, channel_id: null },
        };
      }
      if (url.includes('dsi-resolution-plan')) {
        return {
          import_job_id: 7,
          rows: [
            {
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
              resolution_blockers: [],
            },
          ],
          summary: { total: 1, ready: 1, not_ready: 0, hold: 0 },
          defaults_used: { region_id: null, channel_id: null },
        };
      }
      return { import_job_id: 7, action: 'ignore', results: [], totals: {} };
    });
  });

  function renderPlanSection() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <DsiImportJobResolutionSection importJobId={7} candidates={[hoisted.candidateRow]} onInvalidate={() => {}} />
      </QueryClientProvider>
    );
  }

  it('posts apply with candidate ids and override keys after generate + apply all', async () => {
    const user = userEvent.setup();
    renderPlanSection();

    await user.click(screen.getByTestId('dsi-resolution-plan-generate'));
    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith(
        '/api/v1/mappings/import-jobs/7/dsi-resolution-plan',
        expect.any(Object)
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId('dsi-resolution-plan-dialog')).toBeVisible();
    });

    await user.click(screen.getByTestId('dsi-resolution-plan-apply-all'));
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

  it('shows raw sample text from candidates in the plan dialog', async () => {
    const user = userEvent.setup();
    renderPlanSection();
    await user.click(screen.getByTestId('dsi-resolution-plan-generate'));
    await waitFor(() => {
      expect(screen.getByTestId('dsi-resolution-plan-dialog')).toBeVisible();
    });
    expect(screen.getByText('ACME RETAIL')).toBeTruthy();
  });

  it('generate button is clickable again after a failed plan request', async () => {
    const user = userEvent.setup();
    mockApiPost.mockReset();
    let genN = 0;
    const planRow = {
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
      resolution_blockers: [],
    };
    mockApiPost.mockImplementation(async (url: string) => {
      if (url.includes('dsi-resolution-plan/apply')) {
        return {
          import_job_id: 7,
          applied: 0,
          failed: 0,
          skipped_hold: 0,
          skipped_not_ready: 0,
          results: [],
        };
      }
      if (url.includes('dsi-resolution-plan/effective')) {
        return {
          import_job_id: 7,
          rows: [planRow],
          summary: { total: 1, ready: 1, not_ready: 0, hold: 0 },
          defaults_used: { region_id: null, channel_id: null },
        };
      }
      if (url.includes('dsi-resolution-plan')) {
        genN += 1;
        if (genN === 1) throw new Error('network');
        return {
          import_job_id: 7,
          rows: [planRow],
          summary: { total: 1, ready: 1, not_ready: 0, hold: 0 },
          defaults_used: { region_id: null, channel_id: null },
        };
      }
      return { import_job_id: 7, action: 'ignore', results: [], totals: {} };
    });

    renderPlanSection();
    const btn = screen.getByTestId('dsi-resolution-plan-generate');
    await user.click(btn);
    await waitFor(() => expect(btn).not.toBeDisabled());
    await user.click(btn);
    await waitFor(() => {
      expect(screen.getByTestId('dsi-resolution-plan-dialog')).toBeVisible();
    });
  });

  it('calls effective endpoint after global distributor confirm is toggled', async () => {
    const user = userEvent.setup();
    renderPlanSection();
    await user.click(screen.getByTestId('dsi-resolution-plan-generate'));
    await waitFor(() => {
      expect(screen.getByTestId('dsi-resolution-plan-dialog')).toBeVisible();
    });
    const before = mockApiPost.mock.calls.filter((c) => String(c[0]).includes('effective')).length;
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
});
