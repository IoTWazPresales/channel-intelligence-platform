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
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/admin/po-management',
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  safeDisplayError: (e: unknown) => String(e),
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({
    rowData,
    columnDefs,
  }: {
    rowData: Array<Record<string, unknown>>;
    columnDefs?: Array<Record<string, unknown>>;
  }) => (
    <div data-testid="po-gap-grid-mock">
      {rowData.map((row) => (
        <div key={String(row.row_key ?? row.purchase_order_id)}>
          {columnDefs?.map((c, idx) =>
            c?.cellRenderer ? (
              <div key={idx}>{(c.cellRenderer as (p: { data: typeof row }) => React.ReactNode)({ data: row })}</div>
            ) : null
          )}
        </div>
      ))}
    </div>
  ),
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
    if (path.includes('/po-auto-link/proposals')) {
      return Promise.resolve({
        proposals: [],
        total: 0,
        returned: 0,
        dismissed_count: 0,
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

  it('shows lineup on file when case exists without upload prompt', async () => {
    apiGetMock.mockImplementation((path: string) => {
      if (path.includes('/po-management/coverage')) {
        return Promise.resolve({
          total_pos_observed: 5,
          total_pos_linked: 0,
          first_run: true,
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
              product_line: 'NB',
              shipped_units: 1200,
              shipped_value_cost: 50000,
              shipped_value_plan: 900000,
              fx_complete: true,
              po_count: 3,
              linked_po_count: 0,
              status: 'unlinked',
              lineup_case_exists: true,
            },
          ],
          data_unavailable: false,
        });
      }
      if (path.includes('/po-gap-worklist')) {
        return Promise.resolve({ groups: [], dismissed: [], total_gap_rows: 0, data_unavailable: false });
      }
      if (path.includes('/po-auto-link/proposals')) {
        return Promise.resolve({
          proposals: [],
          total: 0,
          returned: 0,
          dismissed_count: 0,
          data_unavailable: false,
        });
      }
      return Promise.resolve({});
    });
    renderView();
    expect(await screen.findByText('Lineup on file')).toBeInTheDocument();
    expect(screen.queryByTestId('po-upload-2026-1-NB')).not.toBeInTheDocument();
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

  it('renders Execution vs plan button for linked groups instead of reconciliation dump', async () => {
    wireApi({ firstRun: false });
    renderView();

    const status = await screen.findByTestId('po-linked-status-2026-1-Audio');
    expect(status).toHaveTextContent('Linked 2/3 POs');
    const pveBtn = screen.getByTestId('po-pve-link-2026-1-Audio');
    expect(pveBtn).toHaveTextContent('Execution vs plan outcomes');
    expect(pveBtn).toHaveAttribute(
      'href',
      '/stock?lens=execution&period_from=26Q1&period_to=26Q1&product_line=Audio',
    );
    expect(screen.queryByText('2 matched')).not.toBeInTheDocument();
    expect(screen.queryByText('1 short')).not.toBeInTheDocument();
  });

  it('renders operational worklist summary chips', async () => {
    wireApi({ firstRun: false });
    renderView();

    expect(await screen.findByTestId('po-worklist-summary')).toBeInTheDocument();
    expect(screen.getByTestId('po-worklist-unlinked')).toHaveTextContent('3 POs unlinked');
    expect(screen.getByTestId('po-worklist-upload-needed')).toHaveTextContent('0 period×BU need lineup upload');
    expect(screen.getByTestId('po-worklist-gaps')).toHaveTextContent('1 gap line');
  });

  it('shows pending link chip in coverage when proposals exist', async () => {
    apiGetMock.mockImplementation((path: string) => {
      if (path.includes('/po-management/coverage')) {
        return Promise.resolve({
          total_pos_observed: 10,
          total_pos_linked: 2,
          first_run: false,
          data_unavailable: false,
        });
      }
      if (path.includes('/po-management/backlog')) {
        return Promise.resolve({ groups: [], data_unavailable: false });
      }
      if (path.includes('/po-gap-worklist')) {
        return Promise.resolve({ groups: [], dismissed: [], total_gap_rows: 0, data_unavailable: false });
      }
      if (path.includes('/po-auto-link/proposals')) {
        return Promise.resolve({
          proposals: [
            {
              proposal_key: '1:2:PO1',
              case_id: 1,
              purchase_order_id: 2,
              confidence: 'high',
              reason: 'customer_product_crad_in_period',
              matched_products: [],
              total_planned_units: 10,
              total_shipped_units: 8,
            },
          ],
          total: 3,
          returned: 1,
          dismissed_count: 0,
          data_unavailable: false,
        });
      }
      return Promise.resolve({});
    });
    renderView();
    expect(await screen.findByTestId('po-coverage-pending-links')).toHaveTextContent('3 CRAD link suggestions');
    expect(await screen.findByTestId('po-auto-link-cards')).toBeInTheDocument();
  });

  it('dismisses a gap PO via reason dialog', async () => {
    wireApi({ firstRun: false });
    apiPostMock.mockResolvedValue({ purchase_order_id: 42, dismiss_reason_code: 'no lineup needed' });
    const user = userEvent.setup();

    renderView();

    const dismissBtn = await screen.findByTestId('gap-dismiss-42');
    await user.click(dismissBtn);
    expect(await screen.findByTestId('po-dismiss-reason-dialog')).toBeInTheDocument();
    await user.click(screen.getByTestId('po-dismiss-reason-submit'));

    await waitFor(() =>
      expect(apiPostMock).toHaveBeenCalledWith(
        '/api/v1/commercial-planner/lineup/po-gap-worklist/dismiss',
        { purchase_order_id: 42, reason_code: 'no lineup needed' }
      )
    );
  });
});
