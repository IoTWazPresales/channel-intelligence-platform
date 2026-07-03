import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { PoAutoLinkProposalsSection, buildGroupedPoAutoLinkRows } from './PoAutoLinkProposalsSection';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  safeDisplayError: (e: unknown) => String(e),
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({
    rowData,
    columnDefs,
    gridOptions,
  }: {
    rowData: Array<Record<string, unknown>>;
    columnDefs?: Array<Record<string, unknown>>;
    gridOptions?: { onSelectionChanged?: (e: { api: { getSelectedRows: () => unknown[] } }) => void };
  }) => (
    <div data-testid="po-auto-link-grid-mock">
      {rowData.map((row) => {
        const key = String(row.rowType === 'group' ? row.groupKey : row.proposal_key);
        return (
          <div key={key} data-testid={row.rowType === 'group' ? `grid-group-${key}` : `grid-row-${key}`}>
            {columnDefs?.map((c, idx) =>
              c?.cellRenderer ? (
                <div key={`${key}-${idx}`}>
                  {(c.cellRenderer as (p: { data: typeof row }) => React.ReactNode)({ data: row })}
                </div>
              ) : null,
            )}
          </div>
        );
      })}
      <button
        type="button"
        data-testid="mock-select-row"
        onClick={() =>
          gridOptions?.onSelectionChanged?.({
            api: {
              getSelectedRows: () => rowData.filter((r) => r.rowType !== 'group'),
            },
          })
        }
      >
        mock select
      </button>
    </div>
  ),
}));

import { apiGet, apiPost } from '@/lib/api';

const apiGetMock = vi.mocked(apiGet);
const apiPostMock = vi.mocked(apiPost);

const sampleProposal = {
  proposal_key: '10:5:PO99',
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
  matched_products: [
    {
      product_id: 7,
      sku: 'SKU-7',
      sales_model_name: 'Model Seven',
      marketing_name: 'Seven Marketing',
      planned_units: 100,
      shipped_units: 80,
    },
  ],
  total_planned_units: 100,
  total_shipped_units: 80,
};

function renderSection(props: { autoFetch?: boolean } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <PoAutoLinkProposalsSection autoFetch={props.autoFetch ?? false} />
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

  it('does not fetch proposals until expanded', async () => {
    renderSection();
    expect(apiGetMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId('po-auto-link-expand'));
    await waitFor(() => expect(apiGetMock).toHaveBeenCalledWith(expect.stringContaining('/po-auto-link/proposals'), expect.anything()));
  });

  it('renders proposal grid after expand with confidence chip', async () => {
    renderSection();
    await userEvent.click(screen.getByTestId('po-auto-link-expand'));
    expect(await screen.findByTestId('po-auto-link-table')).toBeInTheDocument();
    expect(screen.getByText('high')).toBeInTheDocument();
    expect(screen.getByTestId('grid-row-10:5:PO99')).toBeInTheDocument();
  });

  it('opens confirm dialog with sales_model_name and sku for matched products', async () => {
    const user = userEvent.setup();
    renderSection();
    await user.click(screen.getByTestId('po-auto-link-expand'));
    await screen.findByTestId('po-auto-link-table');
    await user.click(screen.getByTestId('po-auto-link-review-10:5:PO99'));
    expect(await screen.findByTestId('po-auto-link-confirm-dialog')).toBeInTheDocument();
    expect(screen.getByTestId('matched-product-label-7')).toHaveTextContent('Model Seven · SKU-7');
    expect(screen.queryByText(/^7$/)).not.toBeInTheDocument();
  });

  it('applies link from confirm dialog', async () => {
    const user = userEvent.setup();
    renderSection();
    await user.click(screen.getByTestId('po-auto-link-expand'));
    await screen.findByTestId('po-auto-link-table');
    await user.click(screen.getByTestId('po-auto-link-review-10:5:PO99'));
    await user.click(screen.getByTestId('po-auto-link-confirm-submit'));
    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith('/api/v1/commercial-planner/lineup/po-auto-link/apply', {
        items: [{ case_id: 10, purchase_order_id: 99, notes: undefined }],
      });
    });
  });

  it('auto-expands when autoFetch and proposals exist', async () => {
    renderSection({ autoFetch: true });
    expect(await screen.findByTestId('po-auto-link-table')).toBeInTheDocument();
    expect(apiGetMock).toHaveBeenCalledWith(expect.stringContaining('/po-auto-link/proposals'), expect.anything());
  });

  it('bulk apply selected proposals', async () => {
    const user = userEvent.setup();
    renderSection();
    await user.click(screen.getByTestId('po-auto-link-expand'));
    await screen.findByTestId('po-auto-link-table');
    await user.click(screen.getByTestId('mock-select-row'));
    await user.click(screen.getByTestId('po-auto-link-bulk-apply'));
    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith('/api/v1/commercial-planner/lineup/po-auto-link/apply', {
        items: [{ case_id: 10, purchase_order_id: 99 }],
      });
    });
  });

  it('groups three proposals with same period and customer into one header plan figure', () => {
    const proposals = [
      { ...sampleProposal, proposal_key: '10:5:PO99', purchase_order_id: 99, po_number: 'PO-99', total_planned_units: 60 },
      { ...sampleProposal, proposal_key: '10:5:PO100', purchase_order_id: 100, po_number: 'PO-100', total_planned_units: 40 },
      {
        ...sampleProposal,
        proposal_key: '10:5:PO101',
        purchase_order_id: 101,
        po_number: 'PO-101',
        total_planned_units: 100,
        matched_products: [{ ...sampleProposal.matched_products[0], product_id: 8, planned_units: 25 }],
      },
    ];
    const rows = buildGroupedPoAutoLinkRows(proposals);
    const groupRows = rows.filter((r) => r.rowType === 'group');
    const childRows = rows.filter((r) => r.rowType !== 'group');
    expect(groupRows).toHaveLength(1);
    expect(childRows).toHaveLength(3);
    expect(groupRows[0].groupPlanUnits).toBe(125);
  });
});
