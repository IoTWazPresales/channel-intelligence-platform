import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { PastMergesSection, type MergeRecord } from './PastMergesSection';

const apiGet = vi.fn();
const apiPost = vi.fn();

vi.mock('@/lib/api', () => ({
  apiGet: (...a: unknown[]) => apiGet(...a),
  apiPost: (...a: unknown[]) => apiPost(...a),
}));

function record(over: Partial<MergeRecord>): MergeRecord {
  return {
    id: 1,
    customer_code: 'CODE',
    customer_name: 'Name',
    customer_status: 'active',
    created_at: '2026-06-07T18:39:54+02:00',
    origin: null,
    merged_into_customer_id: null,
    merged_at: null,
    reference_rows: 0,
    reference_counts: [],
    sellthrough_rows: 0,
    sellthrough_units: 0,
    cases: 0,
    alias_count: 0,
    aliases: [],
    ...over,
  };
}

const keeper = record({
  id: 299,
  customer_code: 'CUST-000260',
  customer_name: 'AMAZON COMMERCIAL SERVICES (SOUTH AFRICA)',
  origin: 'Provisional customer created from DSI import candidate 2130 (job 43).',
  reference_rows: 9500,
  sellthrough_rows: 31,
  sellthrough_units: 812,
  cases: 15,
  alias_count: 6,
  aliases: ['Amazon', 'Q1 Amazon'],
});
const merged = record({
  id: 26,
  customer_code: 'TMP-CUST-20260603154522-BD28',
  customer_name: 'Amazon',
  customer_status: 'merged',
  merged_into_customer_id: 299,
  merged_at: '2026-07-11T14:36:27+00:00',
  origin: 'Provisional customer created from shipment evidence import candidate 1222 (job 34).',
});

function renderSection() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <PastMergesSection q="amazon" page={1} pageSize={25} onPageChange={() => undefined} />
    </QueryClientProvider>
  );
}

describe('PastMergesSection', () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
    apiGet.mockResolvedValue({
      items: [{ keeper, merged: [merged] }],
      page: 1,
      page_size: 25,
      total: 1,
      test_fixture_merges_excluded: 8,
      note: '',
    });
  });

  it('shows both records with the evidence on each', async () => {
    renderSection();
    const keeperRow = await screen.findByTestId('past-merge-record-299');
    expect(within(keeperRow).getByText('Keeper')).toBeInTheDocument();
    expect(within(keeperRow).getByText('CUST-000260')).toBeInTheDocument();
    expect(within(keeperRow).getByText('15')).toBeInTheDocument();
    expect(within(keeperRow).getByText(/31 rows · 812 units/)).toBeInTheDocument();
    expect(within(keeperRow).getByText(/6: Amazon, Q1 Amazon, …/)).toBeInTheDocument();
    const mergedRow = screen.getByTestId('past-merge-record-26');
    expect(within(mergedRow).getByText(/shipment evidence import candidate 1222/)).toBeInTheDocument();
    expect(within(mergedRow).getByText(/merged/)).toBeInTheDocument();
    expect(screen.getByText(/8 test-data merges are not listed/)).toBeInTheDocument();
    expect(apiGet.mock.calls[0][0]).toContain('q=amazon');
  });

  it('previews then confirms the keeper the steward picked', async () => {
    apiPost.mockImplementation(async (url: string) => {
      if (url.endsWith('change-keeper-preview')) {
        return {
          current_keeper: { id: 299, code: 'CUST-000260', name: 'AMAZON COMMERCIAL SERVICES (SOUTH AFRICA)', status: 'active' },
          new_keeper: { id: 26, code: 'TMP-CUST-20260603154522-BD28', name: 'Amazon', status: 'merged' },
          new_keeper_status_after: 'active',
          rows_to_move: 9500,
          rows_to_move_by_table: {},
          rows_already_on_new_keeper: 0,
          other_merged_records_redirected: [],
          alias_seal_plan: { alias_seal_minted: [{ normalized_token: 'a' }, { normalized_token: 'b' }], alias_seal_conflicts: [] },
          kept: 'TMP-CUST-20260603154522-BD28 — Amazon keeps its code and name.',
        };
      }
      return { rows_moved: 9500 };
    });
    renderSection();
    fireEvent.click(await screen.findByRole('button', { name: 'Make this the keeper' }));
    const dialog = await screen.findByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: 'Confirm keeper change' });
    expect(confirm).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Preview' })).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: 'Warren picked' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Preview' }));
    const moveLine = await within(dialog).findByText(
      (_text, el) => el?.tagName === 'LI' && /rows move from AMAZON/.test(el.textContent ?? '')
    );
    expect(moveLine.textContent).toMatch(/^9\D?500 rows move from AMAZON COMMERCIAL SERVICES \(SOUTH AFRICA\) to Amazon\.$/);
    expect(within(dialog).getByText(/2 aliases added/)).toBeInTheDocument();
    expect(apiPost).toHaveBeenCalledWith('/api/v1/customers/merge-history/change-keeper-preview', {
      current_keeper_id: 299,
      new_keeper_id: 26,
      audit_note: 'Warren picked',
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm keeper change' }));
    await waitFor(() => expect(screen.getByText(/Amazon is now the keeper/)).toBeInTheDocument());
    expect(apiPost).toHaveBeenLastCalledWith('/api/v1/customers/merge-history/change-keeper-confirm', {
      current_keeper_id: 299,
      new_keeper_id: 26,
      audit_note: 'Warren picked',
    });
  });
});
