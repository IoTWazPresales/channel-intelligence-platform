import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { PromotionPlannerSurface } from './PromotionPlannerSurface';

const { replaceMock, pushMock, search } = vi.hoisted(() => ({
  replaceMock: vi.fn(),
  pushMock: vi.fn(),
  /** The page URL's query string; empty unless a test sets it (step 2 History tests). */
  search: { value: '' },
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceMock, push: pushMock }),
  useSearchParams: () => new URLSearchParams(search.value),
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
      window_start: '2026-11-09',
      window_end: '2026-11-20',
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

/** The shared Promotions & Funding header's book read (`cporFundingChromeQueryOptions`); not a planner request. */
const DOMAIN_CHROME_URL = '/api/v1/cpor/cases?page=1&page_size=1';

/** Per-test override of a /cpor/cases response, chosen by URL; return undefined to use the default payload. */
let casesOverride: ((url: string) => unknown) | null = null;
/** Per-test override of a /cpor/cases/counts response (exact counts); return undefined for the default. */
let countsOverride: ((url: string) => unknown) | null = null;
let clashOverride: (() => unknown) | null = null;
/** Per-test override of `GET /cpor/cases/{id}/promo-load-recon`; return undefined for the default (on plan). */
let reconOverride: ((url: string) => unknown) | null = null;

/** Case 41 (window 2026-11-09..20, today 2026-11-19): 11 of 12 days gone, so ~1 668 of 1 820 units expected. */
const defaultRecon = {
  case_id: 41,
  data_unavailable: false,
  reason: null,
  lines: [{ product_id: 1, estimate_qty: 1820, cst_units: 1700 }],
  cst_vintage: { max_period_start_date: '2026-11-16' },
};

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
  if (url.includes('/promo-load-recon')) {
    const o = reconOverride?.(url);
    if (o instanceof Error) throw o;
    return o ?? defaultRecon;
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
  // Step 2 (N-0122): this mock returned ['Sell out PP'] for the planner's create dialog. The planner now asks for the
  // customer sell-through family only. Warren (t454u): "Correct, Sell through, sell out is disti to reseller and is
  // still valuable but not here."
  if (url.includes('/promotion-types?family=customer_sell_through'))
    return { promotion_types: ['Sell-Through PP'], family: 'customer_sell_through' };
  if (url.includes('/promotion-types')) return { promotion_types: ['Sell out PP', 'Sell-Through PP', 'Stock PP (In-Direct)'] };
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
    // The navigator shows the three months around today. Pin the day so a November case stays on the default block.
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(2026, 10, 19, 10, 0, 0));
    apiGetMock.mockClear();
    replaceMock.mockClear();
    pushMock.mockClear();
    casesOverride = null;
    countsOverride = null;
    clashOverride = null;
    reconOverride = null;
    search.value = '';
  });

  afterEach(() => {
    vi.useRealTimers();
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

  // Step 2 (N-0122) changed the two tests below: they asserted official_promotion_types=true, which keeps Sell out PP
  // on the planner. Warren (t454u): "Correct, Sell through, sell out is disti to reseller and is still valuable but not
  // here." Standing rules: "The promotion planner shows customer promotions, never sell-out." and "The planner never
  // shows closed, settled or ended cases (or old years) by default."
  it('loads the timeline case list scoped to reporting customers, customer sell-through and open cases', async () => {
    renderPlanner();
    await waitFor(() =>
      expect(
        apiGetMock.mock.calls.some(
          ([u]) =>
            String(u).includes('/cpor/cases?') &&
            !String(u).includes('status=') &&
            String(u).includes('reporting_only=true') &&
            String(u).includes('promotion_family=customer_sell_through') &&
            String(u).includes('open_only=true'),
        ),
      ).toBe(true),
    );
    expect(apiGetMock.mock.calls.some(([u]) => String(u).includes('official_promotion_types'))).toBe(false);
  });

  it('scopes proposed, ended, and headline count requests to reporting customers and customer sell-through', async () => {
    renderPlanner();
    await waitFor(() =>
      expect(
        apiGetMock.mock.calls.some(
          ([u]) =>
            String(u).includes('status=proposed') &&
            String(u).includes('reporting_only=true') &&
            String(u).includes('promotion_family=customer_sell_through'),
        ),
      ).toBe(true),
    );
    expect(
      apiGetMock.mock.calls.some(
        ([u]) =>
          String(u).includes('status=ended') &&
          String(u).includes('reporting_only=true') &&
          String(u).includes('promotion_family=customer_sell_through'),
      ),
    ).toBe(true);
    // Every planner case and count request carries the family: none reads sell-out. The one exception is the shared
    // Promotions & Funding header (FundingChrome, `page_size=1`), which also serves the case book and settlement desk.
    // Per-case reads (`/cpor/cases/{id}/promo-load-recon`, Warren 27 Nov at-risk rule) name one case of this family.
    const caseCalls = apiGetMock.mock.calls
      .map(([u]) => String(u))
      .filter((u) => u.includes('/cpor/cases') && u !== DOMAIN_CHROME_URL && !/\/cpor\/cases\/\d+\//.test(u));
    expect(caseCalls.length).toBeGreaterThan(0);
    for (const u of caseCalls) expect(u).toContain('promotion_family=customer_sell_through');
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
    // beforeEach already fakes Date. Install the interval fakes on a clean timer so the two do not nest.
    vi.useRealTimers();
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

  it('docks an empty detail column beside the timeline until a case is selected', async () => {
    // Requirement: Promotion_Planner Mockup.png docks the detail on the right. It is not a drawer.
    renderPlanner();
    await screen.findByTestId('planner-timeline-section');
    await screen.findByTestId('planner-timeline');
    expect(screen.getByTestId('planner-detail-dock')).toBeInTheDocument();
    expect(screen.getByTestId('planner-detail-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('planner-detail-drawer')).toBeNull();
  });

  it('selecting a case fills the docked detail and opens the plan workspace from there', async () => {
    renderPlanner();
    fireEvent.click(await screen.findByTestId('planner-timeline-bar-41'));
    expect(screen.getByTestId('planner-detail')).toHaveTextContent('CPR-26-1204');
    expect(screen.queryByTestId('planner-detail-empty')).toBeNull();
    expect(screen.queryByTestId('planner-detail-drawer')).toBeNull();
    fireEvent.click(screen.getByTestId('planner-side-open'));
    expect(replaceMock).toHaveBeenCalledWith('/promotions?plan=41', { scroll: false });
  });

  it('clears the docked detail with the close control, Clear, or Escape', async () => {
    const user = userEvent.setup();
    renderPlanner();
    fireEvent.click(await screen.findByTestId('planner-timeline-bar-41'));
    expect(screen.getByTestId('planner-detail')).toHaveTextContent('CPR-26-1204');
    fireEvent.click(screen.getByTestId('planner-detail-close'));
    expect(screen.getByTestId('planner-detail-empty')).toBeInTheDocument();

    // Warren (27 Nov) asked for the buttons Adjust promotion, Create claim and More: Clear moved under More.
    fireEvent.click(screen.getByTestId('planner-timeline-bar-41'));
    fireEvent.click(screen.getByTestId('planner-side-more'));
    fireEvent.click(await screen.findByTestId('planner-side-clear'));
    expect(screen.getByTestId('planner-detail-empty')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('planner-timeline-bar-41'));
    await user.keyboard('{Escape}');
    expect(screen.getByTestId('planner-detail-empty')).toBeInTheDocument();
  });

  it('the detail has Adjust promotion, Create claim and More, and the sell-through over the window (Warren, 27 Nov)', async () => {
    reconOverride = () => ({ ...defaultRecon, lines: [{ product_id: 1, estimate_qty: 1820, cst_units: 400 }] });
    renderPlanner();
    fireEvent.click(await screen.findByTestId('planner-timeline-bar-41'));
    expect(screen.getByTestId('planner-side-open')).toHaveTextContent('Adjust promotion');
    expect(screen.getByTestId('planner-side-claim')).toHaveTextContent('Create claim');
    expect(screen.getByTestId('planner-side-claim')).toHaveAttribute('href', '/commercial-planner/cpor-cases/41');
    expect(screen.getByTestId('planner-side-more')).toHaveTextContent('More');
    await waitFor(() =>
      expect(screen.getByTestId('planner-detail-sell-through')).toHaveTextContent('400 of 1 820 planned units sold in the window'),
    );
    expect(screen.getByTestId('planner-detail-pace')).toHaveTextContent(/Behind plan: about 1 668 expected with 92% of the window gone/);
    fireEvent.click(screen.getByTestId('planner-side-more'));
    expect(await screen.findByRole('menuitem', { name: 'Open in case book' })).toHaveAttribute(
      'href',
      '/commercial-planner/cpor-cases?status=proposed',
    );
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
    // Requirement: Timeline is the default view (mock-up). The grid is the List view of the same cases.
    expect(screen.queryByTestId('planner-grid')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'List' }));
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

  describe('step 2: open customer sell-through by default, History on request', () => {
    // The at-risk read (Warren, 27 Nov) is always open cases started by today (`window_to=`); it is not the main list.
    const mainListCalls = () =>
      apiGetMock.mock.calls
        .map(([u]) => String(u))
        .filter(
          (u) =>
            u.includes('/cpor/cases?') && !u.includes('status=') && !u.includes('window_to=') && u !== DOMAIN_CHROME_URL,
        );

    it('the Open | History toggle defaults to Open and History sets view=history in the URL', async () => {
      renderPlanner();
      const open = await screen.findByTestId('planner-view-open');
      expect(open).toHaveAttribute('aria-pressed', 'true');
      fireEvent.click(screen.getByTestId('planner-view-history'));
      expect(replaceMock).toHaveBeenCalledWith('/promotions?view=history', { scroll: false });
    });

    it('History drops open_only and keeps the customer sell-through family', async () => {
      search.value = 'view=history';
      renderPlanner();
      await waitFor(() => expect(mainListCalls().length).toBeGreaterThan(0));
      for (const u of mainListCalls()) {
        expect(u).toContain('promotion_family=customer_sell_through');
        expect(u).not.toContain('open_only');
      }
      expect(screen.getByTestId('planner-view-history')).toHaveAttribute('aria-pressed', 'true');
    });

    it('a closed stage in the URL is answered from History, not from the open list', async () => {
      search.value = 'stage=settled';
      renderPlanner();
      await waitFor(() =>
        expect(
          apiGetMock.mock.calls.some(([u]) => String(u).includes('/cpor/cases?') && String(u).includes('status=settled')),
        ).toBe(true),
      );
      const settled = apiGetMock.mock.calls.map(([u]) => String(u)).find((u) => u.includes('status=settled'))!;
      expect(settled).not.toContain('open_only');
      expect(settled).toContain('promotion_family=customer_sell_through');
    });

    it('with no open customer promotion, says so and offers History', async () => {
      casesOverride = (url) => (url.includes('status=') ? undefined : { ...listPayload, items: [], total: 0 });
      renderPlanner();
      expect(await screen.findByTestId('planner-no-open')).toHaveTextContent(
        'No open customer promotions. History shows ended and settled cases.',
      );
      fireEvent.click(screen.getByTestId('planner-show-history'));
      expect(replaceMock).toHaveBeenCalledWith('/promotions?view=history', { scroll: false });
    });

    it('the create dialog offers the customer sell-through family only and defaults to its first type', async () => {
      renderPlanner();
      fireEvent.click(await screen.findByTestId('planner-new'));
      await waitFor(() =>
        expect(screen.getByTestId('create-case-promotion-type')).toHaveValue('Sell-Through PP'),
      );
      expect(
        apiGetMock.mock.calls.some(([u]) =>
          String(u).includes('/cpor/meta/promotion-types?family=customer_sell_through'),
        ),
      ).toBe(true);
      fireEvent.mouseDown(screen.getByRole('combobox', { name: /Promotion type/i }));
      const listbox = await screen.findByRole('listbox');
      expect(listbox).toHaveTextContent('Sell-Through PP');
      expect(listbox).not.toHaveTextContent('Sell out PP');
    });
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
      // Requirement changed (Warren, 27 Nov): "At risk means an open promotion whose sell-through is behind the plan
      // for the time already elapsed." This test counted the overdue approval as at risk. The one open case is
      // selling on plan, so nothing is at risk although it still waits for approval.
      await waitFor(() => expect(screen.getByTestId('planner-kpi-at-risk')).toHaveAttribute('data-state', 'ready'));
      expect(screen.getByTestId('planner-kpi-at-risk')).toHaveTextContent(/At-risk actions0/);
      expect(screen.getByTestId('planner-action-queue')).toHaveTextContent('CPR-26-1204 · awaiting approval · overdue');
    });

    it('counts an open promotion selling behind plan for the time elapsed as at risk and queues it', async () => {
      casesOverride = quietLists;
      reconOverride = () => ({ ...defaultRecon, lines: [{ product_id: 1, estimate_qty: 1820, cst_units: 400 }] });
      renderPlanner();
      await waitFor(() => expect(screen.getByTestId('planner-kpi-at-risk')).toHaveTextContent(/At-risk actions1/));
      expect(screen.getByTestId('planner-action-queue')).toHaveTextContent('CPR-26-1204 · sell-through behind plan');
      expect(apiGetMock.mock.calls.some(([u]) => String(u) === '/api/v1/cpor/cases/41/promo-load-recon')).toBe(true);
      expect(
        apiGetMock.mock.calls.some(
          ([u]) => String(u).includes('window_to=2026-11-19') && String(u).includes('open_only=true'),
        ),
      ).toBe(true);
    });

    it('claims no risk for an open promotion with no sell-through loaded, and says so', async () => {
      casesOverride = quietLists;
      reconOverride = () => ({ case_id: 41, data_unavailable: true, reason: 'no_cst', lines: [] });
      renderPlanner();
      await waitFor(() => expect(screen.getByTestId('planner-kpi-at-risk')).toHaveTextContent(/At-risk actions0/));
      expect(screen.getByTestId('planner-kpi-at-risk')).toHaveTextContent('1 started without sell-through to judge');
    });

    it('never judges an ended case, and does not read its sell-through for the at-risk count', async () => {
      casesOverride = (url) =>
        url.includes('status=ended')
          ? {
              ...listPayload,
              items: [{ ...listPayload.items[0], id: 52, case_code: 'CPR-ENDED', status: 'ended', window_start: '2026-11-01', window_end: '2026-11-10' }],
              total: 1,
            }
          : undefined;
      reconOverride = () => ({ ...defaultRecon, lines: [{ product_id: 1, estimate_qty: 1820, cst_units: 0 }] });
      renderPlanner();
      await waitFor(() => expect(screen.getByTestId('planner-queue-card-evidence')).toHaveTextContent(/Evidence outstanding1/));
      // Case 41 (open) sells nothing, so it is at risk; the ended case is not, and its recon is never asked for.
      await waitFor(() => expect(screen.getByTestId('planner-kpi-at-risk')).toHaveTextContent(/At-risk actions1/));
      expect(screen.getByTestId('planner-action-queue')).not.toHaveTextContent('CPR-ENDED · sell-through behind plan');
      expect(apiGetMock.mock.calls.some(([u]) => String(u).includes('/cpor/cases/52/promo-load-recon'))).toBe(false);
    });

    it('shows In planning / Live promotions as failed, not zero, when the count request fails', async () => {
      countsOverride = (url) =>
        url.includes('window_from=') || url.includes('status=proposed') ? undefined : new Error('boom');
      renderPlanner();
      await waitFor(() => expect(screen.getByTestId('planner-kpi-planning')).toHaveAttribute('data-state', 'empty'));
      expect(screen.getByTestId('planner-kpi-live')).toHaveAttribute('data-state', 'empty');
      expect(screen.getByTestId('planner-kpi-planning')).not.toHaveTextContent(/In planning0/);
    });

    // Requirement changed (Warren, 27 Nov): the at-risk count reads open promotions' sell-through, not the ended list.
    it('shows At-risk actions as failed, not zero, when a sell-through read failed', async () => {
      reconOverride = () => new Error('boom');
      renderPlanner();
      await waitFor(() => expect(screen.getByTestId('planner-kpi-at-risk')).toHaveAttribute('data-state', 'empty'));
      expect(screen.getByTestId('planner-kpi-at-risk')).not.toHaveTextContent(/At-risk actions0/);
    });

    it('a failed ended-case list does not fail the at-risk count', async () => {
      casesOverride = (url) => (url.includes('status=ended') ? new Error('boom') : undefined);
      renderPlanner();
      await waitFor(() => expect(screen.getByTestId('planner-queue-card-evidence')).toHaveAttribute('data-state', 'empty'));
      await waitFor(() => expect(screen.getByTestId('planner-kpi-at-risk')).toHaveAttribute('data-state', 'ready'));
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
