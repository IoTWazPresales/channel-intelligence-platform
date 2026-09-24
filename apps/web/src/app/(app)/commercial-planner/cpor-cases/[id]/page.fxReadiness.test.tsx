import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { SettlementDeskLive } from '@/features/settlement/SettlementDeskLive';

// N-0044: CporCaseWorkspace is retired; its FX anchor + readiness now live on the settlement desk.
const case312Payload = {
  id: 312,
  case_code: 'C26C00003',
  customer_code: 'CUST-000012',
  customer_name: 'Takealot',
  promotion_type: 'Sell out PP',
  window_start: '2026-07-30',
  window_end: '2026-08-31',
  status: 'ended',
  currency_code: 'ZAR',
  allowed_next: ['settled', 'cancelled'],
  ttl_support_zar: 1878,
  ttl_support_usd: 100,
  fx_mode: null,
  fx_proposed_rate: 18.5,
  fx_proposed_source: 'sarb',
  fx_declared_by: 'ken',
  fx_declared_at: '2026-08-01T10:00:00Z',
  needs_reapproval: true,
  settle_readiness: {
    fx_declared: true,
    roe_snapshot: 18.78,
    fx_mode: null,
    fx_mode_declared: false,
    fx_settle_allowed: false,
    fx_basis_line: 'FX rate 18.78 · mode not declared',
    open_assumption_count: 2,
    claim_evidence_count: 0,
  },
};

const settlementPayload = {
  case_id: 312,
  status: 'ended',
  window_start: '2026-07-30',
  window_end: '2026-08-31',
  claim_row_count: 0,
  out_of_window_claim_rows: 3,
  unresolved_products: [{ token: 'XYZ-1', units: 4 }],
  cst_reconciliation: { available: false, reason: 'no_cst' },
  lines: [],
  can_settle: true,
};

let detail: Record<string, unknown> = case312Payload;

vi.mock('next/navigation', () => ({
  useParams: () => ({ id: '312' }),
  usePathname: () => '/commercial-planner/cpor-cases/312',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: () => <div data-testid="mock-grid">grid</div>,
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (url === '/api/v1/cpor/cases/312') return detail;
    if (url === '/api/v1/cpor/cases/312/settlement') return settlementPayload;
    if (url.startsWith('/api/v1/cpor/intelligence/comparable-cases')) {
      return {
        case_id: 312,
        total_candidates: 1,
        rank_order: [],
        items: [
          {
            case_id: 46,
            case_code: 'C24446638',
            customer_code: 'CUST-000012',
            customer_name: 'Takealot',
            promotion_type: 'Sell out PP',
            quarter: '2024Q4',
            estimate_qty: 120,
            rank_axes: {
              same_customer: true,
              bu_overlap_ratio: 1,
              same_promotion_type: true,
              quarter_proximity: 0.5,
              volume_similarity: 0.8,
            },
          },
        ],
      };
    }
    if (url.includes('/auth/tenant-commercial-profile')) return { line_identifier_preference: 'sku' };
    if (url.includes('/pivot')) {
      return { cells: {}, row_totals: {}, col_totals: {}, grand_total_usd: 0, missing_roe: false };
    }
    return {};
  }),
  apiPost: vi.fn(async () => ({})),
  apiPostFormData: vi.fn(),
}));

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <SettlementDeskLive caseId={312} />
    </QueryClientProvider>,
  );
}

describe('Settlement desk FX anchor / readiness (case 312 shape, ported from CporCaseWorkspace)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    detail = case312Payload;
  });

  it('shows approved support, readiness chips, reapproval and diagnostics; hides settle when FX blocks', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText(/C26C00003 · Takealot/)).toBeInTheDocument());

    expect(screen.getByTestId('desk-approved')).toHaveTextContent(/R 1[\s,.]?878[.,]00/);
    expect(screen.getByTestId('desk-approved-usd')).toHaveTextContent(/\$ 100[.,]00 · Σ line USD at the booked rate/);
    expect(screen.getByText(/Booked 18\.78 · by ken · 2026-08-01/)).toBeInTheDocument();

    expect(screen.getByTestId('settlement-desk-readiness-fx')).toHaveTextContent(/FX rate 18\.78 · mode not declared/);
    expect(screen.getByTestId('settlement-desk-readiness-assumptions')).toHaveTextContent('2 assumptions open');
    expect(screen.getByTestId('settlement-desk-readiness-evidence')).toHaveTextContent(
      'No claim files · not source-attested',
    );
    expect(screen.getByTestId('settlement-desk-fx-blocked')).toHaveTextContent('FX rate 18.78 · mode not declared');
    expect(screen.getByTestId('settlement-desk-primary')).not.toHaveTextContent(/SETTLED/);

    expect(screen.getByTestId('settlement-desk-needs-reapproval')).toBeInTheDocument();
    expect(screen.getByTestId('settlement-desk-diagnostics')).toHaveTextContent(/Out-of-window rows · 3/);
    expect(screen.getByTestId('settlement-desk-diagnostics')).toHaveTextContent(/Unresolved products · 1/);
    expect(screen.getByTestId('settlement-desk-unresolved-tokens')).toHaveTextContent('XYZ-1 (4)');

    // allowed_next [settled, cancelled]: cancel is on the desk; end is not offered.
    expect(screen.getByTestId('settlement-desk-action-cancel')).toBeInTheDocument();
    expect(screen.queryByTestId('settlement-desk-action-end')).toBeNull();
    expect(screen.getByTestId('settlement-desk-intelligence-exclude')).toBeInTheDocument();
    expect(screen.getByTestId('settlement-desk-rerollup')).toBeInTheDocument();
  });

  it('puts the FX basis line in the header meta when FX is not blocked', async () => {
    detail = {
      ...case312Payload,
      fx_mode: 'booked',
      settle_readiness: {
        ...case312Payload.settle_readiness,
        fx_mode: 'booked',
        fx_mode_declared: true,
        fx_settle_allowed: true,
        fx_basis_line: 'Booked 18.78 ZAR/USD at approval',
      },
    };
    renderPage();
    await waitFor(() => expect(screen.getByText(/C26C00003 · Takealot/)).toBeInTheDocument());
    expect(screen.queryByTestId('settlement-desk-fx-blocked')).toBeNull();
    expect(screen.getByText(/· ZAR · Booked 18\.78 ZAR\/USD at approval/)).toBeInTheDocument();
  });

  it('withholds the approved USD when the case has no booked rate and shows the proposal', async () => {
    detail = {
      ...case312Payload,
      settle_readiness: {
        fx_declared: false,
        roe_snapshot: null,
        open_assumption_count: 2,
        claim_evidence_count: 0,
      },
    };
    renderPage();
    await waitFor(() => expect(screen.getByTestId('desk-approved-usd')).toBeInTheDocument());
    expect(screen.getByTestId('desk-approved-usd')).toHaveTextContent('unbooked — no USD equivalent');
    expect(screen.getByText(/Proposed 18\.50 · sarb · not booked/)).toBeInTheDocument();
    expect(screen.getByTestId('settlement-desk-readiness-fx')).toHaveTextContent('FX undeclared');
  });

  it('confirms before cancelling and posts the existing transition endpoint', async () => {
    const { apiPost } = await import('@/lib/api');
    renderPage();
    fireEvent.click(await screen.findByTestId('settlement-desk-action-cancel'));
    expect(vi.mocked(apiPost)).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByTestId('settlement-lifecycle-confirm'));
    await waitFor(() =>
      expect(vi.mocked(apiPost)).toHaveBeenCalledWith('/api/v1/cpor/cases/312/transition', { action: 'cancel' }),
    );
  });

  it('posts the intelligence-exclude switch and re-rollup to their existing endpoints', async () => {
    const { apiPost } = await import('@/lib/api');
    renderPage();
    fireEvent.click(await screen.findByTestId('settlement-desk-intelligence-exclude'));
    await waitFor(() =>
      expect(vi.mocked(apiPost)).toHaveBeenCalledWith('/api/v1/cpor/cases/312/intelligence-exclude', {
        exclude: true,
        confirm: true,
      }),
    );
    fireEvent.click(screen.getByTestId('settlement-desk-rerollup'));
    await waitFor(() =>
      expect(vi.mocked(apiPost)).toHaveBeenCalledWith('/api/v1/cpor/cases/312/settlement/rollup', {}),
    );
  });

  it('mounts comparable cases lazily in the case tabs', async () => {
    const { apiGet } = await import('@/lib/api');
    renderPage();
    await waitFor(() => expect(screen.getByTestId('settlement-tab-comparables')).toBeInTheDocument());
    const comparableCalls = () =>
      vi.mocked(apiGet).mock.calls.filter(([u]) => String(u).includes('comparable-cases')).length;
    expect(comparableCalls()).toBe(0);
    fireEvent.click(screen.getByTestId('settlement-tab-comparables'));
    expect(await screen.findByTestId('cpor-comparable-46')).toHaveTextContent('C24446638');
    expect(comparableCalls()).toBe(1);
  });
});
