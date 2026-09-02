import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import CporCaseDetailPage from './page';

const case312Payload = {
  id: 312,
  case_code: 'C26C00003',
  customer_code: 'CUST-000012',
  customer_name: 'Takealot',
  promotion_type: 'Sell out PP',
  window_start: '2026-07-30',
  window_end: '2026-08-31',
  status: 'draft',
  workflow_status: 'draft',
  export_version: 1,
  currency_code: 'ZAR',
  roe_snapshot: 18.78,
  last_comment: null,
  allowed_next: ['proposed'],
  lines: [
    {
      id: 2980,
      product_id: 1,
      product_sku: 'SKU-A',
      product_name: 'Product A',
      product_line: null,
      distributor_id: 29,
      pod_quarter: null,
      srp: 100,
      vat_rate: 0.15,
      dealer_margin_pct: 0.1,
      margin_source: 'default',
      cost_basis: 50,
      cost_source: 'historical_import',
      estimate_qty: 0,
      dealer_price: null,
      support_unit: null,
      ttl_support: 0,
      support_usd: null,
      flags: ['no_cost_evidence', 'no_soh_evidence'],
    },
    {
      id: 2981,
      product_id: 2,
      product_sku: 'SKU-B',
      product_name: 'Product B',
      product_line: null,
      distributor_id: 29,
      pod_quarter: null,
      srp: 100,
      vat_rate: 0.15,
      dealer_margin_pct: 0.1,
      margin_source: 'default',
      cost_basis: null,
      cost_source: null,
      estimate_qty: 0,
      dealer_price: null,
      support_unit: null,
      ttl_support: 0,
      support_usd: null,
      flags: ['no_cost_basis', 'no_cost_evidence'],
    },
  ],
  flags: ['no_cost_basis', 'no_cost_evidence'],
  missing_roe: false,
  ttl_support_zar: 0,
  ttl_support_usd: null,
  settle_readiness: {
    fx_declared: true,
    roe_snapshot: 18.78,
    open_assumption_count: 2,
    claim_evidence_count: 0,
  },
  needs_reapproval: false,
};

vi.mock('next/navigation', () => ({
  useParams: () => ({ id: '312' }),
}));

vi.mock('@/components/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <div>{title}</div>,
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: () => <div data-testid="mock-grid">grid</div>,
}));

vi.mock('@/app/(app)/commercial-planner/cpor-cases/[id]/CporComparableCasesPanel', () => ({
  CporComparableCasesPanel: () => null,
}));

vi.mock('@/app/(app)/commercial-planner/cpor-cases/[id]/CporPaymentEvidencePanel', () => ({
  CporPaymentEvidencePanel: () => null,
}));

vi.mock('@/app/(app)/commercial-planner/cpor-cases/[id]/CporPromoLoadPanel', () => ({
  CporPromoLoadPanel: () => null,
}));

vi.mock('@/features/commercial-planner/EntitySearchAutocomplete', () => ({
  EntitySearchAutocomplete: () => null,
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (url === '/api/v1/cpor/cases/312') return case312Payload;
    if (url.startsWith('/api/v1/cpor/intelligence/comparable-cases')) {
      return { case_id: 312, total_candidates: 0, rank_order: [], items: [] };
    }
    throw new Error(`Unexpected GET ${url}`);
  }),
  apiPost: vi.fn(),
  apiPostFormData: vi.fn(),
}));

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <CporCaseDetailPage />
    </QueryClientProvider>,
  );
}

describe('CporCaseDetailPage FX/readiness (case 312 shape)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders FX anchor and settle readiness when case has assumption flags', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('C26C00003')).toBeInTheDocument();
    });

    expect(screen.getByTestId('cpor-fx-anchor')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-fx-anchor-local')).toHaveTextContent(/^R 0[.,]00$/);
    expect(screen.getByTestId('cpor-case-readiness-row')).toBeInTheDocument();
    expect(screen.getByTestId('cpor-case-readiness-fx')).toHaveTextContent(/FX declared · 18\.78/);
    expect(screen.getByTestId('cpor-case-readiness-assumptions')).toHaveTextContent(
      '2 assumptions open',
    );
    expect(screen.getByTestId('cpor-case-readiness-evidence')).toHaveTextContent('0 evidence rows');
  });

  it('withholds USD anchor when API marks missing_roe for zero ROE', async () => {
    const zeroRoePayload = {
      ...case312Payload,
      roe_snapshot: 0,
      missing_roe: true,
      settle_readiness: {
        fx_declared: false,
        roe_snapshot: null,
        open_assumption_count: 2,
        claim_evidence_count: 0,
      },
    };
    const { apiGet } = await import('@/lib/api');
    vi.mocked(apiGet).mockImplementation(async (url: string) => {
      if (url === '/api/v1/cpor/cases/312') return zeroRoePayload;
      if (url.startsWith('/api/v1/cpor/intelligence/comparable-cases')) {
        return { case_id: 312, total_candidates: 0, rank_order: [], items: [] };
      }
      throw new Error(`Unexpected GET ${url}`);
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('cpor-fx-undeclared')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('cpor-fx-anchor-usd-basis')).not.toBeInTheDocument();
  });
});
