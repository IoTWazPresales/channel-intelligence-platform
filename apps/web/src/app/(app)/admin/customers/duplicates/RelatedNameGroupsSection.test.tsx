import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { RelatedNameGroupsSection } from './RelatedNameGroupsSection';

const apiGet = vi.fn();
const apiPost = vi.fn();

vi.mock('@/lib/api', () => ({
  apiGet: (...a: unknown[]) => apiGet(...a),
  apiPost: (...a: unknown[]) => apiPost(...a),
}));

const group = {
  similarity_key: 'related:kappa',
  anchor_similarity_key: 'kappa',
  member_count: 3,
  members: [
    { id: 1, customer_code: 'TMP-CUST-1', customer_name: 'Kappa', customer_status: 'unverified', survivor_hint: false, reference_counts: [{ label: 'Sell-out', count: 4 }], match_basis: 'anchor' },
    { id: 2, customer_code: 'CUST-2', customer_name: 'Kappa Commercial Services', customer_status: 'active', survivor_hint: true, reference_counts: [], match_basis: 'contained_prefix' },
    { id: 3, customer_code: 'CUST-3', customer_name: 'Kappa Holdings', customer_status: 'active', survivor_hint: false, reference_counts: [], match_basis: 'contained_prefix' },
  ],
};

function renderSection() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <RelatedNameGroupsSection q="" page={1} pageSize={25} onPageChange={() => undefined} />
    </QueryClientProvider>
  );
}

describe('RelatedNameGroupsSection', () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
    apiGet.mockImplementation(async (url: string) =>
      url.includes('merge-task') ? { state: 'SUCCESS' } : { items: [group], total: 1, customers_scanned: 40, test_fixture_customers_excluded: 5 }
    );
  });

  it('lists the group, says why each name is listed and counts test data apart', async () => {
    renderSection();
    expect(await screen.findByText('Kappa Commercial Services (suggested keeper)')).toBeInTheDocument();
    expect(screen.getAllByText('Starts with that name')).toHaveLength(2);
    expect(screen.getByText(/5 test-data customers are not listed/)).toBeInTheDocument();
  });

  it('merges only the ticked subset into the chosen keeper', async () => {
    apiPost.mockImplementation(async (url: string) =>
      url.endsWith('merge-preview')
        ? { loser_ids: [1], loser_plans: [{ customer_id: 1, fk_breakdown: [{ label: 'x', count: 4 }] }], alias_seal_plan: { alias_seal_minted: [{}], alias_seal_conflicts: [] } }
        : { task_id: 't1' }
    );
    renderSection();
    const mergeButton = await screen.findByRole('button', { name: /Merge ticked/ });
    expect(mergeButton).toBeDisabled();
    fireEvent.click(screen.getByLabelText('Include Kappa'));
    fireEvent.click(screen.getByLabelText('Include Kappa Commercial Services'));
    expect(screen.getByLabelText('Keep Kappa Holdings')).toBeDisabled();
    fireEvent.click(screen.getByLabelText('Keep Kappa Commercial Services'));
    fireEvent.click(screen.getByRole('button', { name: 'Merge ticked (2)' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: 'same business' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Preview' }));
    expect(await within(dialog).findByText(/4 rows move to the keeper/)).toBeInTheDocument();
    expect(apiPost).toHaveBeenCalledWith('/api/v1/customers/duplicate-groups/merge-preview', {
      similarity_key: 'related:kappa',
      customer_ids: [1, 2],
      survivor_id: 2,
      audit_note: 'same business',
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm merge' }));
    await waitFor(() => expect(screen.getByText(/Merged. The merged names now resolve to the keeper/)).toBeInTheDocument());
  });
});
