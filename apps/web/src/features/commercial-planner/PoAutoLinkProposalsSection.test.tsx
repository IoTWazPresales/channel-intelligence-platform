import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { PoAutoLinkProposalsSection } from './PoAutoLinkProposalsSection';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  safeDisplayError: (e: unknown) => String(e),
}));

import { apiGet, apiPost } from '@/lib/api';

const apiGetMock = vi.mocked(apiGet);
const apiPostMock = vi.mocked(apiPost);

const sampleProposal = {
  proposal_key: '10:5:21:99',
  case_id: 10,
  case_period_label: '26Q1',
  inferred_period_start: '2026-01-01',
  customer_id: 5,
  customer_label: 'CUST — Acme',
  distributor_id: 21,
  distributor_code: 'DIST',
  distributor_name: 'Mustek',
  purchase_order_id: 99,
  po_number: 'PO-99',
  po_number_norm: 'PO99',
  confidence: 'high' as const,
  reason: 'customer_product_crad_in_period',
  date_source: 'crad',
  dismissed: false,
  matched_products: [{ product_id: 7, planned_units: 100, shipped_units: 80 }],
  total_planned_units: 100,
  total_shipped_units: 80,
};

function renderSection() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <PoAutoLinkProposalsSection />
    </QueryClientProvider>
  );
}

describe('PoAutoLinkProposalsSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiGetMock.mockImplementation((path: string) => {
      if (path.includes('/po-auto-link/proposals')) {
        return Promise.resolve({
          proposals: [sampleProposal],
          total: 1,
          returned: 1,
          dismissed_count: 0,
          data_unavailable: false,
        });
      }
      return Promise.reject(new Error(`unexpected GET ${path}`));
    });
    apiPostMock.mockResolvedValue({ applied_count: 1, applied: [], error_count: 0, errors: [] });
  });

  it('renders proposal table with confidence chip', async () => {
    renderSection();
    expect(await screen.findByTestId('po-auto-link-table')).toBeInTheDocument();
    expect(screen.getByText('high')).toBeInTheDocument();
    expect(screen.getByText('PO-99')).toBeInTheDocument();
    expect(screen.getByText('CUST — Acme')).toBeInTheDocument();
  });

  it('opens customer-grain confirm dialog and applies link', async () => {
    const user = userEvent.setup();
    renderSection();
    await screen.findByTestId('po-auto-link-table');
    await user.click(screen.getByTestId('po-auto-link-review-10:5:21:99'));
    expect(await screen.findByTestId('po-auto-link-confirm-dialog')).toBeInTheDocument();
    expect(screen.getByTestId('confirm-customer-label')).toHaveTextContent('CUST — Acme');
    await user.click(screen.getByTestId('po-auto-link-confirm-submit'));
    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith('/api/v1/commercial-planner/lineup/po-auto-link/apply', {
        items: [{ case_id: 10, purchase_order_id: 99, notes: undefined }],
      });
    });
  });

  it('bulk apply selected proposals', async () => {
    const user = userEvent.setup();
    renderSection();
    await screen.findByTestId('po-auto-link-table');
    const checkbox = screen.getByRole('checkbox', { name: /Select 10:5:21:99/i });
    await user.click(checkbox);
    await user.click(screen.getByTestId('po-auto-link-bulk-apply'));
    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith('/api/v1/commercial-planner/lineup/po-auto-link/apply', {
        items: [{ case_id: 10, purchase_order_id: 99 }],
      });
    });
  });
});
