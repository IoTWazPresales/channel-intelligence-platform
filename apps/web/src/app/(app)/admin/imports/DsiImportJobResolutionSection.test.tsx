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
