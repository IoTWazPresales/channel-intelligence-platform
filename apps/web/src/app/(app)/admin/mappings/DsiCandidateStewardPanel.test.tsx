import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { DsiCandidateStewardPanel, type DsiCandidateRow } from './DsiCandidateStewardPanel';

const apiGetMock = vi.fn();
const apiPostMock = vi.fn();

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => apiGetMock(...args),
  apiPost: (...args: unknown[]) => apiPostMock(...args),
}));

const productCandidate: DsiCandidateRow = {
  id: 42,
  import_job_id: 501,
  source_definition_id: 9,
  entity_type: 'product_identifier',
  normalized_key: 'widget-x',
  dealer_group_token: null,
  row_count: 3,
  total_units: 1,
  total_reported_value: null,
  sample_raw_values: ['Widget X'],
  suggested_entity_id: null,
  match_reason: null,
  confidence_score: null,
  status: 'needs_review',
  context: {
    product_match_summary: 'Multiple eligible products matched sales_model_name.',
    product_match_status: 'ambiguous_eligible',
    product_ambiguous_eligible: { product_ids: [10, 20], tier: 'sales_model_name', eligible_products: [] },
  },
};

function renderPanel(candidate: DsiCandidateRow | null = productCandidate) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <DsiCandidateStewardPanel importJobId={501} candidate={candidate} onDone={() => {}} />
    </QueryClientProvider>
  );
}

describe('DsiCandidateStewardPanel product steward', () => {
  beforeEach(() => {
    apiGetMock.mockReset();
    apiPostMock.mockReset();
    apiPostMock.mockResolvedValue({ ok: true });
    apiGetMock.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/v1/catalog/regions')) {
        return [{ id: 1, code: 'NA-W', name: 'NA West' }];
      }
      if (path.startsWith('/api/v1/catalog/channels')) {
        return [{ id: 1, code: 'RET', name: 'Retail' }];
      }
      if (path.startsWith('/api/v1/distributors')) {
        return { items: [] };
      }
      if (path.startsWith('/api/v1/customers')) {
        return { items: [] };
      }
      if (path.startsWith('/api/v1/products')) {
        return {
          items: [
            { id: 10, sku: 'SKU-10', name: 'Product Ten', sales_model_name: 'M10', is_active: true },
            { id: 20, sku: 'SKU-20', name: 'Product Twenty', sales_model_name: 'M20', is_active: true },
          ],
        };
      }
      throw new Error(`unexpected GET ${path}`);
    });
  });

  it('shows product match summary for product_identifier candidates', async () => {
    renderPanel();
    await waitFor(() => expect(screen.getByTestId('dsi-product-match-summary')).toBeInTheDocument());
    expect(screen.getByTestId('dsi-product-match-summary')).toHaveTextContent(/Multiple eligible products/);
    expect(screen.getByTestId('dsi-product-match-summary')).toHaveTextContent(/"product_ids"/);
  });

  it('opens resolve-product dialog, searches products, and posts resolve-product', async () => {
    const user = userEvent.setup();
    renderPanel();

    await waitFor(() => expect(screen.getByTestId('dsi-action-resolve-product')).toBeInTheDocument());
    await user.click(screen.getByTestId('dsi-action-resolve-product'));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Map product token to Product Master/i)).toBeInTheDocument();
    expect(within(dialog).getByTestId('dsi-product-dialog-source-token')).toHaveTextContent('Widget X');

    const search = within(dialog).getByLabelText(/Search products/i);
    expect(search).toHaveValue('Widget X');
    await user.clear(search);
    await user.type(search, 'SKU');

    await waitFor(() => expect(within(dialog).getByRole('combobox', { name: /product/i })).toBeInTheDocument());

    const combo = within(dialog).getByRole('combobox', { name: /product/i });
    await user.click(combo);
    const listbox = await screen.findByRole('listbox');
    await user.click(within(listbox).getByText(/SKU-10/));

    await user.click(within(dialog).getByTestId('dsi-product-resolve-save'));

    await waitFor(() => expect(apiPostMock).toHaveBeenCalled());
    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/v1/mappings/import-candidates/42/resolve-product',
      expect.objectContaining({
        product_id: 10,
        confirm_ineligible_product: false,
      })
    );
  });
});
