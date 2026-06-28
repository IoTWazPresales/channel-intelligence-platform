import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { PoManagementView } from './PoManagementView';

function renderView() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <PoManagementView />
    </QueryClientProvider>
  );
}

const pushMock = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  safeDisplayError: (e: unknown) => String(e),
}));

import { apiGet, apiPost } from '@/lib/api';

const apiGetMock = vi.mocked(apiGet);
const apiPostMock = vi.mocked(apiPost);

function wireApi(opts: { firstRun?: boolean; gapDismissed?: boolean } = {}) {
  apiGetMock.mockImplementation((path: string) => {
    if (path.includes('/po-management/coverage')) {
      return Promise.resolve({
        total_pos_observed: 5,
        total_pos_linked: opts.firstRun ? 0 : 2,
        first_run: !!opts.firstRun,
        data_unavailable: false,
      });
    }
    if (path.includes('/po-management/backlog')) {
      return Promise.resolve({
        groups: [
          {
            year: 2026,
            quarter: 1,
            quarter_label: '26Q1',
            product_line: 'Audio',
            shipped_units: 1200,
            shipped_value_cost: 50000,
            shipped_value_plan: 900000,
            fx_complete: true,
            po_count: 3,
            linked_po_count: opts.firstRun ? 0 : 2,
            status: opts.firstRun ? 'unlinked' : 'linked',
            ...(opts.firstRun
              ? { upload_prompt: { period_label: '26Q1', product_line: 'Audio' } }
              : {
                  reconciliation_summary: { matched: 2, short: 1, unshipped: 0 },
                  linked_case_ids: [10],
                }),
          },
        ],
        data_unavailable: false,
      });
    }
    if (path.includes('/po-gap-worklist')) {
      return Promise.resolve({
        groups: [
          {
            year: 2026,
            quarter: 1,
            quarter_label: '26Q1',
            shipped_units: 300,
            po_count: 1,
            product_count: 1,
            rows: [
              {
                purchase_order_id: 42,
                po_number_raw: 'PO-42',
                product_id: 7,
                product_name: 'Speaker',
                product_line: 'Audio',
                shipped_units: 300,
                period_label: '26Q1',
                dismissed: false,
              },
            ],
          },
        ],
        dismissed: [],
        total_gap_rows: 1,
        data_unavailable: false,
      });
    }
    return Promise.resolve({});
  });
}

describe('PoManagementView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the first-run coverage meter and an upload prompt for unlinked groups', async () => {
    wireApi({ firstRun: true });
    renderView();

    expect(await screen.findByTestId('po-coverage-observed')).toHaveTextContent('5 POs observed');
    expect(screen.getByTestId('po-coverage-linked')).toHaveTextContent('0 linked');

    const uploadBtn = await screen.findByTestId('po-upload-2026-1-Audio');
    await userEvent.click(uploadBtn);
    expect(pushMock).toHaveBeenCalledWith(expect.stringContaining('/admin/imports?unified=1'));
    expect(pushMock).toHaveBeenCalledWith(expect.stringContaining('period=26Q1'));
  });

  it('renders a reconciliation summary for linked groups', async () => {
    wireApi({ firstRun: false });
    renderView();

    expect(await screen.findByText('2 matched')).toBeInTheDocument();
    expect(screen.getByText('1 short')).toBeInTheDocument();
  });

  it('dismisses a gap PO with a reason', async () => {
    wireApi({ firstRun: false });
    apiPostMock.mockResolvedValue({ purchase_order_id: 42, dismiss_reason_code: 'no lineup needed' });
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('no lineup needed');

    renderView();

    const dismissBtn = await screen.findByTestId('gap-dismiss-42');
    await userEvent.click(dismissBtn);

    await waitFor(() =>
      expect(apiPostMock).toHaveBeenCalledWith(
        '/api/v1/commercial-planner/lineup/po-gap-worklist/dismiss',
        { purchase_order_id: 42, reason_code: 'no lineup needed' }
      )
    );
    promptSpy.mockRestore();
  });
});
