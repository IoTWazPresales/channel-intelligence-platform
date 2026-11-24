import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { PromotionPlannerSurface } from './PromotionPlannerSurface';

const { replaceMock, pushMock } = vi.hoisted(() => ({ replaceMock: vi.fn(), pushMock: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceMock, push: pushMock }),
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
/** Per-test override of a /cpor/cases/counts response (exact counts); return undefined for the default. */
let countsOverride: ((url: string) => unknown) | null = null;
let clashOverride: (() => unknown) | null = null;

const defaultCounts = (url: string) => {
  if (url.includes('window_from=')) return { total_current: 2, status_counts_current: { active: 2 } };
  if (url.includes('status=proposed')) return { total_current: 1, status_counts_current: { proposed: 1 } };
  return { total_current: 8, status_counts_current: { draft: 3, proposed: 1, ended: 4 } };
};

const apiGetMock = vi.fn(async (url: string) => {
  if (url.includes('/cpor/cases/counts')) {
    const o = countsOverride?.(url);
    if (o instanceof Error) throw o;
    return o ?? defaultCounts(url);
  }
  if (url.includes('/customer-calendar/clashes/summary')) {
    const o = clashOverride?.();
    if (o instanceof Error) throw o;
    return o ?? { clash_count: 4, promotion_count: 3, customer_count: 2, from: '2026-11-19', to: null };
  }
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
      // The value is computed on the API; one unplanned line has no cost.
      valuation: {
        cost_basis: 'customer_reported_unit_mac_else_unit_cost_ex_vat',
        unplanned: {
          lines: 2,
          units: 150.5,
          value: 1_234_500,
          lines_with_cost: 1,
          lines_without_cost: 1,
          units_without_cost: 30.5,
        },
      },
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
    pushMock.mockClear();
    casesOverride = null;
    countsOverride = null;
    clashOverride = null;
  });

  const renderPlanner = () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <PromotionPlannerSurface />
      </QueryClientProvider>,
    );
  };

  it('shows the planner cards; Planned reserve and Actual support are "Not available yet", never a repeated Budget ledger figure', async () => {
    renderPlanner();
    await waitFor(() => expect(screen.getByTestId('planner-card-awaiting')).toHaveTextContent(/Awaiting approval1/i));
    await waitFor(() => expect(screen.getByTestId('planner-card-starting')).toHaveTextContent(/Starting in 4 weeks2/i));
    expect(screen.getByText('Drafts to finish')).toBeInTheDocument();
    expect(screen.getByTestId('planner-kpi-reserve')).toHaveAttribute('data-state', 'unavailable');
    expect(screen.getByTestId('planner-kpi-support')).toHaveAttribute('data-state', 'unavailable');
    expect(screen.queryByText(/Settled book/i)).toBeNull();
    expect(apiGetMock.mock.calls.some(([u]) => String(u).includes('/support-bias'))).toBe(false);
  });

  it('loads the timeline case list scoped to reporting customers and official promotion types', async () => {
    renderPlanner();
    await waitFor(() =>
      expect(
        apiGetMock.mock.calls.some(
          ([u]) =>
            String(u).includes('/cpor/cases?') &&
            String(u).includes('reporting_only=true') &&
            String(u).includes('official_promotion_types=true'),
        ),
      ).toBe(true),
    );
  });

  it('scopes proposed, ended, and headline count requests to reporting customers', async () => {
    renderPlanner();
    await waitFor(() =>
      expect(
        apiGetMock.mock.calls.some(
          ([u]) =>
            String(u).includes('status=proposed') &&
            String(u).includes('reporting_only=true') &&
            String(u).includes('official_promotion_types=true'),
        ),
      ).toBe(true),
    );
    expect(
      apiGetMock.mock.calls.some(
        ([u]) =>
          String(u).includes('status=ended') &&
          String(u).includes('reporting_only=true') &&
          String(u).includes('official_promotion_types=true'),
      ),
    ).toBe(true);
    expect(apiGetMock.mock.calls.some(([u]) => String(u).includes('/cpor/cases/counts?reporting_only=true'))).toBe(true);
  });

  it('asks the count endpoint for windows starting in the next 28 days, leaving out cancelled and rejected', async () => {
    renderPlanner();
    await screen.findByTestId('planner-card-starting');
    await waitFor(() => {
      expect(
        apiGetMock.mock.calls.some(([u]) =>
          /\/cpor\/cases\/counts\?reporting_only=true&window_from=\d{4}-\d{2}-\d{2}&window_to=\d{4}-\d{2}-\d{2}&exclude_status=cancelled&exclude_status=rejected/.test(
            String(u),
          ),
        ),
      ).toBe(true);
    });
    expect(
      apiGetMock.mock.calls.some(([u]) => String(u).includes('/cpor/cases/counts?reporting_only=true&status=proposed')),
    ).toBe(true);
  });

  it('shows drafts and ended from the exact counts, not from the capped list', async () => {
    renderPlanner();
    await waitFor(() => expect(screen.getByTestId('planner-card-drafts')).toHaveTextContent('3'));
    expect(screen.getByTestId('planner-card-ended')).toHaveTextContent('4');
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
    await waitFor(() => expect(screen.getByTestId('planner-card-awaiting')).toHaveTextContent(/Awaiting approval1/i));
    expect(screen.queryByTestId('planner-action-queue-empty')).toBeNull();
  });

  it('awaiting approval filters the planner to Proposed', async () => {
    renderPlanner();
    fireEvent.click(await screen.findByTestId('planner-card-awaiting'));
    expect(replaceMock).toHaveBeenCalledWith('/promotions?stage=proposed', { scroll: false });
  });

  it('keeps the timeline full width with no detail column until a case is selected', async () => {
    renderPlanner();
    await screen.findByTestId('planner-timeline-section');
    await screen.findByTestId('planner-timeline');
    expect(screen.queryByTestId('planner-detail-empty')).toBeNull();
    expect(screen.queryByTestId('planner-detail-drawer')).toBeNull();
  });

  it('selecting a case on the timeline opens the detail drawer and opens the plan workspace from there', async () => {
    renderPlanner();
    fireEvent.click(await screen.findByTestId('planner-timeline-bar-41'));
    await waitFor(() => expect(screen.getByTestId('planner-detail-drawer')).toBeVisible());
    expect(screen.getByTestId('planner-detail')).toHaveTextContent('CPR-26-1204');
    fireEvent.click(screen.getByTestId('planner-side-open'));
    expect(replaceMock).toHaveBeenCalledWith('/promotions?plan=41', { scroll: false });
  });

  it('closes the detail drawer with the close control, Clear, or Escape', async () => {
    const user = userEvent.setup();
    renderPlanner();
    fireEvent.click(await screen.findByTestId('planner-timeline-bar-41'));
    await waitFor(() => expect(screen.getByTestId('planner-detail-drawer')).toBeVisible());
    fireEvent.click(screen.getByTestId('planner-detail-close'));
    await waitFor(() => expect(screen.queryByTestId('planner-detail-drawer')).toBeNull());

    fireEvent.click(screen.getByTestId('planner-timeline-bar-41'));
    await waitFor(() => expect(screen.getByTestId('planner-detail-drawer')).toBeVisible());
    fireEvent.click(screen.getByTestId('planner-side-clear'));
    await waitFor(() => expect(screen.queryByTestId('planner-detail-drawer')).toBeNull());

    fireEvent.click(screen.getByTestId('planner-timeline-bar-41'));
    await waitFor(() => expect(screen.getByTestId('planner-detail-drawer')).toBeVisible());
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByTestId('planner-detail-drawer')).toBeNull());
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
    expect(screen.getByRole('heading', { name: 'Promotion planner' })).toBeInTheDocument();
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

  it('shows the exact count above one page of cases, with no "N+" and no "at least"', async () => {
    countsOverride = (url) =>
      url.includes('status=proposed')
        ? { total_current: 640, status_counts_current: { proposed: 640 } }
        : url.includes('window_from=')
          ? { total_current: 900, status_counts_current: { active: 900 } }
          : undefined;
    casesOverride = (url) =>
      url.includes('status=proposed') ? { ...listPayload, items: [proposedRow(61), proposedRow(62)], total: 640 } : undefined;
    renderPlanner();
    await waitFor(() => expect(screen.getByTestId('planner-card-awaiting')).toHaveTextContent(/Awaiting approval640cases/i));
    await waitFor(() => expect(screen.getByTestId('planner-card-starting')).toHaveTextContent(/Starting in 4 weeks900campaigns/i));
    expect(screen.getByTestId('planner-card-awaiting')).not.toHaveTextContent(/\+|at least/i);
    expect(screen.getByTestId('planner-card-starting')).not.toHaveTextContent(/\+|at least/i);
  });

  it('shows the aged-stock card as a rand value from the API, with units and the lines that have no cost', async () => {
    renderPlanner();
    await waitFor(() => expect(screen.getByTestId('planner-card-aged')).toHaveTextContent('R1.2m'));
    const card = screen.getByTestId('planner-card-aged');
    expect(card).toHaveTextContent(/151 units/);
    expect(card).toHaveTextContent(/1 line has no cost/i);
    expect(card).toHaveTextContent(/not valued/i);
  });

  it('shows no value, not R0, when no unplanned aged line has a cost', async () => {
    const base = apiGetMock.getMockImplementation()!;
    apiGetMock.mockImplementation(async (url: string) =>
      url.includes('/aged-stock')
        ? {
            lines: [],
            truncated: false,
            valuation: {
              unplanned: { lines: 3, units: 40, value: null, lines_with_cost: 0, lines_without_cost: 3, units_without_cost: 40 },
            },
          }
        : base(url),
    );
    try {
      renderPlanner();
      await waitFor(() => expect(screen.getByTestId('planner-card-aged')).toHaveTextContent(/3 lines have no cost/i));
      expect(screen.getByTestId('planner-card-aged')).not.toHaveTextContent('R0');
    } finally {
      apiGetMock.mockImplementation(base);
    }
  });

  it('shows the calendar-clash card with an exact count and goes to the timeline', async () => {
    renderPlanner();
    await waitFor(() => expect(screen.getByTestId('planner-card-clashes')).toHaveTextContent(/Calendar clashes4/i));
    expect(screen.getByTestId('planner-card-clashes')).toHaveTextContent(/3 promotions/);
    fireEvent.click(screen.getByTestId('planner-card-clashes'));
    expect(pushMock).toHaveBeenCalledWith('/promotions/timeline');
  });

  it('shows the clash card as failed, not zero, when the clash request fails', async () => {
    clashOverride = () => new Error('boom');
    renderPlanner();
    await waitFor(() => expect(screen.getByTestId('planner-card-clashes')).toHaveAttribute('data-state', 'empty'));
    expect(screen.getByTestId('planner-card-clashes')).toHaveTextContent(/could not be loaded/i);
    expect(screen.getByTestId('planner-card-clashes')).not.toHaveTextContent(/Calendar clashes0/);
  });

  it('says the calendar is not set up, not zero, when the calendar tables are unavailable', async () => {
    clashOverride = () => ({ data_unavailable: true, message: 'Customer calendar tables are unavailable.' });
    renderPlanner();
    await waitFor(() => expect(screen.getByTestId('planner-card-clashes')).toHaveAttribute('data-state', 'empty'));
    expect(screen.getByTestId('planner-card-clashes')).toHaveTextContent(/not set up|unavailable/i);
  });

  it('shows the awaiting card and the queue as failed, not as zero / nothing waiting, when the proposed request fails', async () => {
    casesOverride = (url) => (url.includes('status=proposed') ? new Error('boom') : undefined);
    countsOverride = (url) => (url.includes('status=proposed') ? new Error('boom') : undefined);
    renderPlanner();
    await waitFor(() => expect(screen.getByTestId('planner-card-awaiting')).toHaveAttribute('data-state', 'empty'));
    expect(screen.getByTestId('planner-card-awaiting')).toHaveTextContent(/could not be loaded/i);
    expect(screen.getByTestId('planner-card-awaiting')).not.toHaveTextContent(/Awaiting approval0/);
    expect(screen.getByTestId('planner-action-queue-error')).toHaveTextContent('Awaiting approval');
    expect(screen.queryByTestId('planner-action-queue-empty')).toBeNull();
  });

  it('shows the starting card as failed, not zero, when the window request fails', async () => {
    countsOverride = (url) => (url.includes('window_from=') ? new Error('boom') : undefined);
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
  });

  it('shows the drafts and ended cards as failed, not zero, when the count request fails', async () => {
    countsOverride = (url) =>
      url.includes('/cpor/cases/counts?reporting_only=true') && !url.includes('status=') && !url.includes('window_from=')
        ? new Error('boom')
        : undefined;
    renderPlanner();
    await waitFor(() => expect(screen.getByTestId('planner-card-drafts')).toHaveAttribute('data-state', 'empty'));
    expect(screen.getByTestId('planner-card-ended')).toHaveAttribute('data-state', 'empty');
    expect(screen.getByTestId('planner-card-drafts')).toHaveTextContent(/could not be loaded/i);
  });

  describe('mock-up alignment (fix round 1)', () => {
    const quietLists = (url: string) =>
      url.includes('status=ended') ? { ...listPayload, items: [], total: 0 } : undefined;

    it('shows In planning, Live promotions and At-risk actions cards from the exact counts and the action queue', async () => {
      countsOverride = (url) =>
        url.includes('window_from=') || url.includes('status=proposed')
          ? undefined
          : { total_current: 20, status_counts_current: { draft: 3, proposed: 1, approved: 2, rejected: 1, active: 5, ended: 4 } };
      casesOverride = quietLists;
      renderPlanner();
      await waitFor(() => expect(screen.getByTestId('planner-kpi-planning')).toHaveTextContent(/In planning7/));
      expect(screen.getByTestId('planner-kpi-live')).toHaveTextContent(/Live promotions5/);
      // The one proposed case (window 2026-09-07) is awaiting approval and its window has started.
      await waitFor(() => expect(screen.getByTestId('planner-kpi-at-risk')).toHaveTextContent(/At-risk actions1/));
    });

    it('shows In planning / Live promotions as failed, not zero, when the count request fails', async () => {
      countsOverride = (url) =>
        url.includes('window_from=') || url.includes('status=proposed') ? undefined : new Error('boom');
      renderPlanner();
      await waitFor(() => expect(screen.getByTestId('planner-kpi-planning')).toHaveAttribute('data-state', 'empty'));
      expect(screen.getByTestId('planner-kpi-live')).toHaveAttribute('data-state', 'empty');
      expect(screen.getByTestId('planner-kpi-planning')).not.toHaveTextContent(/In planning0/);
    });

    it('shows At-risk actions as failed, not zero, when a queue source failed', async () => {
      casesOverride = (url) => (url.includes('status=ended') ? new Error('boom') : undefined);
      renderPlanner();
      await waitFor(() => expect(screen.getByTestId('planner-kpi-at-risk')).toHaveAttribute('data-state', 'empty'));
      expect(screen.getByTestId('planner-kpi-at-risk')).not.toHaveTextContent(/At-risk actions0/);
    });

    it('shows Overdue approvals and Evidence outstanding queue cards from the queue', async () => {
      casesOverride = (url) =>
        url.includes('status=ended')
          ? {
              ...listPayload,
              items: [{ ...listPayload.items[0], id: 52, case_code: 'CPR-ENDED', status: 'ended', window_start: '2026-08-01', window_end: '2026-08-10' }],
              total: 1,
            }
          : undefined;
      renderPlanner();
      await waitFor(() => expect(screen.getByTestId('planner-queue-card-overdue')).toHaveTextContent(/Overdue approvals1/));
      expect(screen.getByTestId('planner-queue-card-evidence')).toHaveTextContent(/Evidence outstanding1/);
      expect(screen.getByTestId('planner-action-queue')).toHaveTextContent('CPR-26-1204 · awaiting approval · overdue');
    });

    it('shows a Conflicting windows queue card from the clash summary and opens the timeline', async () => {
      renderPlanner();
      await waitFor(() => expect(screen.getByTestId('planner-queue-card-conflicts')).toHaveTextContent(/Conflicting windows4/));
      fireEvent.click(screen.getByTestId('planner-queue-card-conflicts'));
      expect(pushMock).toHaveBeenCalledWith('/promotions/timeline');
    });

    it('shows the Conflicting windows card as failed, not zero, when the clash request fails', async () => {
      clashOverride = () => new Error('boom');
      renderPlanner();
      await waitFor(() => expect(screen.getByTestId('planner-queue-card-conflicts')).toHaveAttribute('data-state', 'empty'));
      expect(screen.getByTestId('planner-queue-card-conflicts')).not.toHaveTextContent(/Conflicting windows0/);
    });

    it('has a Status filter in the filter row that sets the same stage as the chips', async () => {
      renderPlanner();
      const status = (await screen.findByLabelText('Status')) as HTMLSelectElement;
      expect(status.value).toBe('');
      fireEvent.change(status, { target: { value: 'active' } });
      expect(replaceMock).toHaveBeenCalledWith('/promotions?stage=active', { scroll: false });
    });
  });
});
