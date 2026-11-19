import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { PromotionPlannerSurface } from './PromotionPlannerSurface';
import { todayIso } from './plannerCards';

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

/** Per-test override of a /cpor/cases response, chosen by URL; return undefined to use the default payload. */
let casesOverride: ((url: string) => unknown) | null = null;

const apiGetMock = vi.fn(async (url: string) => {
  if (url.includes('/cpor/cases')) {
    const o = casesOverride?.(url);
    if (o instanceof Error) throw o;
    return o ?? listPayload;
  }
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
    casesOverride = null;
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

  it('moves the starting window to the new local day after midnight', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
    try {
      vi.setSystemTime(new Date(2026, 10, 19, 23, 59, 30));
      renderPlanner();
      await waitFor(() =>
        expect(apiGetMock.mock.calls.some(([u]) => String(u).includes('window_from=2026-11-19&'))).toBe(true),
      );
      vi.setSystemTime(new Date(2026, 10, 20, 0, 0, 40));
      vi.advanceTimersByTime(60_000);
      await waitFor(() =>
        expect(apiGetMock.mock.calls.some(([u]) => String(u).includes('window_from=2026-11-20&'))).toBe(true),
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not report an empty queue as confirmed when a queue source has more than one page', async () => {
    casesOverride = (url) =>
      url.includes('status=proposed') ? { ...listPayload, items: [], total: 700 } : undefined;
    renderPlanner();
    await waitFor(() => expect(screen.getByTestId('planner-card-awaiting')).toHaveTextContent('0+'));
    expect(screen.queryByTestId('planner-action-queue-empty')).toBeNull();
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

  const proposedRow = (id: number, extra: Record<string, unknown> = {}) => ({
    ...listPayload.items[0],
    id,
    case_code: `CPR-${id}`,
    window_start: '2099-01-01',
    window_end: '2099-01-10',
    ...extra,
  });

  it('does not count a replaced proposed case: the replacement pointer, not the status, retires it', async () => {
    casesOverride = (url) =>
      url.includes('status=proposed')
        ? {
            ...listPayload,
            items: [proposedRow(51, { superseded_by_case_id: 52 }), proposedRow(52)],
            total: 2,
          }
        : undefined;
    renderPlanner();
    await waitFor(() => expect(screen.getByTestId('planner-card-awaiting')).toHaveTextContent(/Awaiting approval1cases/i));
    expect(screen.getByTestId('planner-action-queue')).toHaveTextContent('CPR-52 · awaiting approval');
    expect(screen.getByTestId('planner-action-queue')).not.toHaveTextContent('CPR-51');
  });

  it('shows a floor, never a capped number as exact, when the list holds more cases than one page', async () => {
    casesOverride = (url) =>
      url.includes('status=proposed') ? { ...listPayload, items: [proposedRow(61), proposedRow(62)], total: 640 } : undefined;
    renderPlanner();
    await waitFor(() => expect(screen.getByTestId('planner-card-awaiting')).toHaveTextContent('2+'));
    expect(screen.getByTestId('planner-card-awaiting')).toHaveTextContent(/at least/i);
  });

  it('shows a floor on the starting card when the window query returned only part of its matches', async () => {
    casesOverride = (url) =>
      url.includes('window_from=') ? { ...listPayload, items: [proposedRow(71, { window_start: todayIso() })], total: 900 } : undefined;
    renderPlanner();
    await waitFor(() => expect(screen.getByTestId('planner-card-starting')).toHaveTextContent('1+'));
    expect(screen.getByTestId('planner-card-starting')).toHaveTextContent(/at least/i);
  });

  it('shows the awaiting card and the queue as failed, not as zero / nothing waiting, when the proposed request fails', async () => {
    casesOverride = (url) => (url.includes('status=proposed') ? new Error('boom') : undefined);
    renderPlanner();
    await waitFor(() => expect(screen.getByTestId('planner-card-awaiting')).toHaveAttribute('data-state', 'empty'));
    expect(screen.getByTestId('planner-card-awaiting')).toHaveTextContent(/could not be loaded/i);
    expect(screen.getByTestId('planner-card-awaiting')).not.toHaveTextContent(/Awaiting approval0/);
    expect(screen.getByTestId('planner-action-queue-error')).toHaveTextContent('Awaiting approval');
    expect(screen.queryByTestId('planner-action-queue-empty')).toBeNull();
  });

  it('shows the starting card as failed, not zero, when the window request fails', async () => {
    casesOverride = (url) => (url.includes('window_from=') ? new Error('boom') : undefined);
    renderPlanner();
    await waitFor(() => expect(screen.getByTestId('planner-card-starting')).toHaveAttribute('data-state', 'empty'));
    expect(screen.getByTestId('planner-card-starting')).toHaveTextContent(/could not be loaded/i);
  });

  it('shows errors, not empty results, on the cards, timeline and queue when the main case list fails', async () => {
    casesOverride = () => new Error('boom');
    renderPlanner();
    expect(await screen.findByTestId('planner-timeline-error')).toBeInTheDocument();
    expect(screen.queryByTestId('planner-timeline-empty')).toBeNull();
    await waitFor(() => expect(screen.getByTestId('planner-action-queue-error')).toHaveTextContent('Case list'));
    expect(screen.queryByTestId('planner-action-queue-empty')).toBeNull();
    expect(screen.getByText('Drafts to finish').closest('[data-state]')).toHaveAttribute('data-state', 'empty');
  });
});
