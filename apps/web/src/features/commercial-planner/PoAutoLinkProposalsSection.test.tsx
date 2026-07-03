import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import {
  PoAutoLinkProposalsSection,
  buildProposalGroups,
  dedupeGroupPlanUnits,
  formatCoverageLineParts,
} from './PoAutoLinkProposalsSection';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  safeDisplayError: (e: unknown) => String(e),
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
  customer_label: 'CUST — Acme Retail Group',
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
  total_open_order_units: 0,
};

function renderSection(props: { autoFetch?: boolean } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <PoAutoLinkProposalsSection autoFetch={props.autoFetch ?? false} />
    </QueryClientProvider>
  );
}

async function expandSection() {
  await userEvent.click(screen.getByTestId('po-auto-link-expand'));
  await screen.findByTestId('po-auto-link-cards');
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
          group_coverage: [],
          group_coverage_by_key: {},
        });
      }
      return Promise.reject(new Error(`unexpected GET ${path}`));
    });
    apiPostMock.mockResolvedValue({ applied_count: 1, applied: [], error_count: 0, errors: [] });
  });

  it('does not fetch proposals until expanded', async () => {
    renderSection();
    expect(apiGetMock).not.toHaveBeenCalled();
    await expandSection();
    expect(apiGetMock).toHaveBeenCalledWith(expect.stringContaining('/po-auto-link/proposals'), expect.anything());
  });

  it('renders proposal card rows after expand with confidence chip', async () => {
    renderSection();
    await expandSection();
    expect(screen.getByText('high')).toBeInTheDocument();
    expect(screen.getByTestId('po-auto-link-row-10:5:PO99')).toBeInTheDocument();
    expect(screen.queryByTestId('po-auto-link-grid-mock')).not.toBeInTheDocument();
  });

  it('opens confirm dialog with sales_model_name and sku for matched products', async () => {
    const user = userEvent.setup();
    renderSection();
    await expandSection();
    await user.click(screen.getByTestId('po-auto-link-review-10:5:PO99'));
    expect(await screen.findByTestId('po-auto-link-confirm-dialog')).toBeInTheDocument();
    expect(screen.getByTestId('matched-product-label-7')).toHaveTextContent('Model Seven · SKU-7');
    expect(screen.queryByText(/^7$/)).not.toBeInTheDocument();
  });

  it('applies link from confirm dialog', async () => {
    const user = userEvent.setup();
    renderSection();
    await expandSection();
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
    expect(await screen.findByTestId('po-auto-link-cards')).toBeInTheDocument();
    expect(apiGetMock).toHaveBeenCalledWith(expect.stringContaining('/po-auto-link/proposals'), expect.anything());
  });

  it('bulk apply selected proposals after confirm dialog', async () => {
    const user = userEvent.setup();
    renderSection();
    await expandSection();
    await user.click(screen.getByTestId('po-auto-link-select-10:5:PO99'));
    await user.click(screen.getByTestId('po-auto-link-bulk-apply'));
    expect(await screen.findByTestId('po-auto-link-bulk-confirm-dialog')).toBeInTheDocument();
    await user.click(screen.getByTestId('po-auto-link-bulk-confirm-submit'));
    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith('/api/v1/commercial-planner/lineup/po-auto-link/apply', {
        items: [{ case_id: 10, purchase_order_id: 99 }],
      });
    });
  });

  it('groups three proposals with same period and customer into one card with deduped plan', () => {
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
    const groups = buildProposalGroups(proposals);
    expect(groups).toHaveLength(1);
    expect(groups[0].proposals).toHaveLength(3);
    expect(groups[0].groupPlanUnits).toBe(125);
    expect(dedupeGroupPlanUnits(proposals)).toBe(125);
  });

  it('renders two cards with full distinct customer labels for near-identical tokens', async () => {
    apiGetMock.mockResolvedValue({
      proposals: [
        { ...sampleProposal, proposal_key: 'a', customer_id: 1, customer_label: 'PROV — Makro South Africa' },
        { ...sampleProposal, proposal_key: 'b', customer_id: 2, customer_label: 'PROV — Makro Wholesale' },
      ],
      total: 2,
      returned: 2,
      dismissed_count: 0,
      data_unavailable: false,
    });
    renderSection();
    await expandSection();
    expect(screen.getByText('PROV — Makro South Africa')).toBeInTheDocument();
    expect(screen.getByText('PROV — Makro Wholesale')).toBeInTheDocument();
    expect(screen.getAllByTestId(/^po-auto-link-group-card-/)).toHaveLength(2);
  });

  it('shows per-card selection counts when global select-all-high runs on collapsed cards', async () => {
    const user = userEvent.setup();
    apiGetMock.mockResolvedValue({
      proposals: [
        { ...sampleProposal, proposal_key: 'a', customer_id: 1, customer_label: 'Makro', confidence: 'high' as const },
        { ...sampleProposal, proposal_key: 'b', customer_id: 2, customer_label: 'Game', confidence: 'high' as const },
        { ...sampleProposal, proposal_key: 'c', customer_id: 3, customer_label: 'Pepkor', confidence: 'medium' as const },
        { ...sampleProposal, proposal_key: 'd', customer_id: 4, customer_label: 'Shoprite', confidence: 'high' as const },
      ],
      total: 4,
      returned: 4,
      dismissed_count: 0,
      data_unavailable: false,
    });
    renderSection();
    await expandSection();
    // 4 cards → default collapsed
    for (const key of ['26Q1|1', '26Q1|2', '26Q1|3', '26Q1|4']) {
      expect(screen.getByTestId(`po-auto-link-group-selection-${key}`)).toHaveTextContent('0 of 1 selected');
    }
    await user.click(screen.getByRole('button', { name: /select all high/i }));
    expect(screen.getByTestId('po-auto-link-group-selection-26Q1|1')).toHaveTextContent('1 of 1 selected');
    expect(screen.getByTestId('po-auto-link-group-selection-26Q1|2')).toHaveTextContent('1 of 1 selected');
    expect(screen.getByTestId('po-auto-link-group-selection-26Q1|3')).toHaveTextContent('0 of 1 selected');
    expect(screen.getByTestId('po-auto-link-group-selection-26Q1|4')).toHaveTextContent('1 of 1 selected');
  });

  it('global link confirm lists per-customer totals', async () => {
    const user = userEvent.setup();
    apiGetMock.mockResolvedValue({
      proposals: [
        { ...sampleProposal, proposal_key: 'a', customer_id: 1, customer_label: 'Makro', purchase_order_id: 1, po_number: 'PO-1' },
        { ...sampleProposal, proposal_key: 'b', customer_id: 1, customer_label: 'Makro', purchase_order_id: 2, po_number: 'PO-2' },
        { ...sampleProposal, proposal_key: 'c', customer_id: 2, customer_label: 'Game', purchase_order_id: 3, po_number: 'PO-3' },
      ],
      total: 3,
      returned: 3,
      dismissed_count: 0,
      data_unavailable: false,
    });
    renderSection();
    await expandSection();
    await user.click(screen.getByRole('button', { name: /select all high/i }));
    await user.click(screen.getByTestId('po-auto-link-bulk-apply'));
    const summary = await screen.findByTestId('po-auto-link-bulk-confirm-summary');
    expect(summary).toHaveTextContent('Linking 3 proposals');
    expect(summary).toHaveTextContent('Game 1');
    expect(summary).toHaveTextContent('Makro 2');
  });

  it('per-card link selected posts only that card proposal keys', async () => {
    const user = userEvent.setup();
    apiGetMock.mockResolvedValue({
      proposals: [
        { ...sampleProposal, proposal_key: 'a', customer_id: 1, customer_label: 'Makro', purchase_order_id: 1, po_number: 'PO-1' },
        { ...sampleProposal, proposal_key: 'b', customer_id: 1, customer_label: 'Makro', purchase_order_id: 2, po_number: 'PO-2' },
        { ...sampleProposal, proposal_key: 'c', customer_id: 2, customer_label: 'Game', purchase_order_id: 3, po_number: 'PO-3' },
      ],
      total: 3,
      returned: 3,
      dismissed_count: 0,
      data_unavailable: false,
    });
    renderSection();
    await expandSection();
    const makroCard = screen.getByTestId('po-auto-link-group-card-26Q1|1');
    await user.click(within(makroCard).getByTestId('po-auto-link-card-select-all-26Q1|1'));
    await user.click(within(makroCard).getByTestId('po-auto-link-card-link-26Q1|1'));
    await user.click(screen.getByTestId('po-auto-link-bulk-confirm-submit'));
    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith('/api/v1/commercial-planner/lineup/po-auto-link/apply', {
        items: [
          { case_id: 10, purchase_order_id: 1 },
          { case_id: 10, purchase_order_id: 2 },
        ],
      });
    });
  });

  it('shows Restore on dismissed row when Show dismissed is on', async () => {
    const user = userEvent.setup();
    apiGetMock.mockImplementation((path: string) => {
      if (!path.includes('/po-auto-link/proposals')) return Promise.reject(new Error(path));
      const includeDismissed = path.includes('include_dismissed=true');
      return Promise.resolve({
        proposals: includeDismissed
          ? [
              { ...sampleProposal, proposal_key: 'active', dismissed: false },
              { ...sampleProposal, proposal_key: '10:5:PO99', dismissed: true },
            ]
          : [{ ...sampleProposal, proposal_key: 'active', dismissed: false }],
        total: 1,
        returned: includeDismissed ? 2 : 1,
        dismissed_count: 1,
        data_unavailable: false,
      });
    });
    renderSection();
    await expandSection();
    expect(screen.queryByTestId('po-auto-link-restore-10:5:PO99')).not.toBeInTheDocument();
    await user.click(screen.getByTestId('po-auto-link-toggle-dismissed'));
    await waitFor(() => expect(screen.getByTestId('po-auto-link-restore-10:5:PO99')).toBeInTheDocument());
  });

  it('formatCoverageLineParts omits zero pipeline and linked terms', () => {
    expect(
      formatCoverageLineParts({
        planUnits: 500,
        proposedShipUnits: 120,
        proposedPipelineUnits: 0,
        linkedShipUnits: 0,
      }),
    ).toBe('Plan 500 · shipped 120 proposed');
    expect(
      formatCoverageLineParts({
        planUnits: 503,
        proposedShipUnits: 200,
        proposedPipelineUnits: 360,
        linkedShipUnits: 863,
      }),
    ).toContain('pipeline 360 proposed');
    expect(
      formatCoverageLineParts({
        planUnits: 503,
        proposedShipUnits: 200,
        proposedPipelineUnits: 360,
        linkedShipUnits: 863,
      }),
    ).toContain('863 already linked');
  });

  it('renders coverage line with plan, proposed shipped+pipeline, and already linked', async () => {
    apiGetMock.mockResolvedValue({
      proposals: [
        {
          ...sampleProposal,
          total_shipped_units: 140,
          total_open_order_units: 60,
        },
      ],
      total: 1,
      returned: 1,
      dismissed_count: 0,
      data_unavailable: false,
      group_coverage_by_key: {
        '26Q1|5': { group_key: '26Q1|5', linked_shipped_units: 250 },
      },
    });
    renderSection();
    await expandSection();
    const line = screen.getByTestId('po-auto-link-coverage-line');
    expect(line).toHaveTextContent('Plan 100');
    expect(line).toHaveTextContent('shipped 140');
    expect(line).toHaveTextContent('pipeline 60 proposed');
    expect(line).toHaveTextContent('250 already linked');
    expect(screen.getByTestId('po-auto-link-pipeline-chip')).toBeInTheDocument();
  });

  it('proposal row annotates pipeline separately from shipped', async () => {
    apiGetMock.mockResolvedValue({
      proposals: [{ ...sampleProposal, total_shipped_units: 50, total_open_order_units: 30 }],
      total: 1,
      returned: 1,
      dismissed_count: 0,
      data_unavailable: false,
      group_coverage_by_key: {},
    });
    renderSection();
    await expandSection();
    const row = screen.getByTestId('po-auto-link-row-10:5:PO99');
    expect(row).toHaveTextContent('Shipped 50');
    expect(row).toHaveTextContent('+30 pipeline');
  });

  it('buildProposalGroups merges linked coverage from API map', () => {
    const groups = buildProposalGroups([sampleProposal], {
      '26Q1|5': { group_key: '26Q1|5', linked_shipped_units: 400 },
    });
    expect(groups[0].linkedShipUnits).toBe(400);
    expect(groups[0].proposedPipelineUnits).toBe(0);
  });

  it('after link apply refetch moves units into already-linked header', async () => {
    const user = userEvent.setup();
    let linked = 0;
    apiGetMock.mockImplementation(() =>
      Promise.resolve({
        proposals: [{ ...sampleProposal, total_shipped_units: 80 }],
        total: 1,
        returned: 1,
        dismissed_count: 0,
        data_unavailable: false,
        group_coverage_by_key: {
          '26Q1|5': { group_key: '26Q1|5', linked_shipped_units: linked },
        },
      }),
    );
    apiPostMock.mockImplementation(async () => {
      linked = 80;
      return { applied_count: 1, applied: [], error_count: 0, errors: [] };
    });
    renderSection();
    await expandSection();
    expect(screen.getByTestId('po-auto-link-coverage-line')).not.toHaveTextContent('80 already linked');
    await user.click(screen.getByTestId('po-auto-link-select-10:5:PO99'));
    await user.click(screen.getByTestId('po-auto-link-bulk-apply'));
    await user.click(screen.getByTestId('po-auto-link-bulk-confirm-submit'));
    await waitFor(() => {
      expect(screen.getByTestId('po-auto-link-coverage-line')).toHaveTextContent('80 already linked');
    });
  });
});
