import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { PromotionPlannerSurface } from './PromotionPlannerSurface';

const { replaceMock } = vi.hoisted(() => ({ replaceMock: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceMock, push: vi.fn() }),
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
  page_size: 500,
  status_counts: { proposed: 1, draft: 0, approved: 0, active: 0, ended: 0, settled: 0 },
  test_data_count: 7,
  review_queue_count: 1,
};

const apiGetMock = vi.fn(async (url: string) => {
  if (url.includes('/cpor/cases')) return listPayload;
  if (url.includes('/aged-stock')) {
    return {
      lines: [
        { customer_id: 1, product_id: 1, stock_on_hand: 120, suggestion_executed: false, executed_actions: [] },
        { customer_id: 1, product_id: 2, stock_on_hand: 30.5, suggestion_executed: false, executed_actions: [] },
        { customer_id: 2, product_id: 3, stock_on_hand: 999, suggestion_executed: true, executed_actions: ['promote'] },
      ],
      truncated: false,
    };
  }
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
    replaceMock.mockClear();
  });

  const renderPlanner = () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <PromotionPlannerSurface />
      </QueryClientProvider>,
    );
  };

  it('shows the planner cards and no longer repeats the Budget ledger figures', async () => {
    renderPlanner();
    await waitFor(() => expect(screen.getByTestId('planner-card-awaiting')).toHaveTextContent(/Awaiting approval1/i));
    expect(screen.getByTestId('planner-card-starting')).toHaveTextContent(/Starting in 4 weeks/i);
    await waitFor(() => expect(screen.getByTestId('planner-card-aged')).toHaveTextContent('151'));
    expect(screen.getByTestId('planner-card-aged')).toHaveTextContent(/units/);
    expect(screen.getByText('Drafts to finish')).toBeInTheDocument();
    expect(screen.queryByText(/Planned reserve/i)).toBeNull();
    expect(screen.queryByText(/Actual support/i)).toBeNull();
    expect(screen.queryByText(/Settled book/i)).toBeNull();
    expect(screen.queryByText(/Calendar clashes/i)).toBeNull();
    expect(apiGetMock.mock.calls.some(([u]) => String(u).includes('/support-bias'))).toBe(false);
  });

  it('asks the existing case list for windows starting in the next 28 days', async () => {
    renderPlanner();
    await screen.findByTestId('planner-card-starting');
    await waitFor(() => {
      expect(
        apiGetMock.mock.calls.some(([u]) => /window_from=\d{4}-\d{2}-\d{2}&window_to=\d{4}-\d{2}-\d{2}/.test(String(u))),
      ).toBe(true);
    });
  });

  it('awaiting approval filters the planner to Proposed', async () => {
    renderPlanner();
    fireEvent.click(await screen.findByTestId('planner-card-awaiting'));
    expect(replaceMock).toHaveBeenCalledWith('/promotions?stage=proposed', { scroll: false });
  });

  it('selecting a case on the timeline fills the side panel, which opens the plan workspace', async () => {
    renderPlanner();
    expect(await screen.findByTestId('planner-side-panel-empty')).toBeInTheDocument();
    fireEvent.click(await screen.findByTestId('planner-timeline-bar-41'));
    expect(screen.getByTestId('planner-side-panel')).toHaveTextContent('CPR-26-1204');
    fireEvent.click(screen.getByTestId('planner-side-open'));
    expect(replaceMock).toHaveBeenCalledWith('/promotions?plan=41', { scroll: false });
  });

  it('puts a proposed case in the action queue', async () => {
    renderPlanner();
    await waitFor(() =>
      expect(screen.getByTestId('planner-action-queue')).toHaveTextContent('CPR-26-1204 · awaiting approval'),
    );
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
    expect(screen.getByRole('button', { name: /Create promotion plan/i })).toBeInTheDocument();
    expect(screen.getByTestId('planner-new')).toBeInTheDocument();
    expect(screen.getByText(/Test data · 7/)).toBeInTheDocument();
  });
});
