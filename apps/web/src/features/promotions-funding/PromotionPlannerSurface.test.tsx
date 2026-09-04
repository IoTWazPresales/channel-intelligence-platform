import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { PromotionPlannerSurface } from './PromotionPlannerSurface';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/promotions',
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ rowData }: { rowData: { case_code: string }[] }) => (
    <div data-testid="planner-grid">{rowData.map((r) => r.case_code).join(',')}</div>
  ),
}));

vi.mock('@/app/(app)/promotions/PromoPlanBuilderPanel', () => ({
  PromoPlanBuilderPanel: () => <div data-testid="b4-builder" />,
}));

vi.mock('@/features/commercial-planner/EntitySearchAutocomplete', () => ({
  EntitySearchAutocomplete: () => null,
}));

const listPayload = {
  items: [
    {
      id: 41,
      case_code: 'CPR-26-1204',
      case_name: 'TechMart Sept monitor sell-through',
      customer_name: 'TechMart',
      customer_code: 'TMT',
      promotion_type: 'Sell-Through PP',
      window_start: '2026-09-07',
      window_end: '2026-09-20',
      status: 'proposed',
      workflow_status: 'proposed',
      origin: 'proposed_by_cip',
      currency_code: 'ZAR',
      line_count: 4,
      estimate_qty_sum: 1820,
      ttl_support_zar: 368640,
      ttl_support_usd: null,
    },
  ],
  total: 1,
  page: 1,
  page_size: 200,
  status_counts: { proposed: 1, draft: 0, approved: 0, active: 0, ended: 0, settled: 0 },
  review_queue_count: 1,
};

const apiGetMock = vi.fn(async (url: string) => {
  if (url.includes('/cpor/cases')) return listPayload;
  if (url.includes('/support-bias')) return { totals: { planned_usd: null, actual_usd: 0 } };
  if (url.includes('/promotion-types')) return { promotion_types: ['Sell out PP'] };
  return {};
});

vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => apiGetMock(url),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDownloadBlob: vi.fn(),
}));

describe('PromotionPlannerSurface', () => {
  beforeEach(() => {
    apiGetMock.mockClear();
  });

  it('lists real CPOR cases and shows line-sum support, not a stale plan total', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <PromotionPlannerSurface />
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId('promotion-planner')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Promotions & Funding/i })).toBeInTheDocument();
    expect(screen.getByTestId('lifecycle-rail')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('planner-grid')).toHaveTextContent('CPR-26-1204');
    });
    expect(screen.getByTestId('planner-grid')).not.toHaveTextContent('R486k');
    expect(screen.getByRole('button', { name: /Propose a plan/i })).toBeInTheDocument();
    expect(screen.getByTestId('planner-new')).toBeInTheDocument();
  });
});
