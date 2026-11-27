import React from 'react';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { PromotionPlannerSurface } from '../PromotionPlannerSurface';

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
vi.mock('@/app/(app)/promotions/PromoPlanBuilderPanel', () => ({ PromoPlanBuilderPanel: () => <div /> }));
// The mock keeps the label so the five filters can be found by name.
vi.mock('@/features/commercial-planner/EntitySearchAutocomplete', () => ({
  EntitySearchAutocomplete: ({ label }: { label: string }) => <input aria-label={label} />,
}));

const row = (id: number, extra: Record<string, unknown> = {}) => ({
  id,
  case_code: `CPR-${id}`,
  case_name: `Plan ${id}`,
  customer_name: id % 2 ? 'Alpha Retail' : 'Beta Retail',
  customer_code: 'X',
  promotion_type: 'Sell-Through PP',
  window_start: '2026-11-02',
  window_end: '2026-11-20',
  status: 'active',
  workflow_status: 'active',
  currency_code: 'ZAR',
  line_count: 3,
  estimate_qty_sum: 1200,
  ttl_support_zar: 50000,
  ttl_support_usd: null,
  ...extra,
});

const listPayload = {
  items: [
    row(1, { status: 'active', evidence_basis: 'claim_evidenced', settle_readiness: { claim_evidence_count: 2 } }),
    row(2, { status: 'approved', window_start: '2026-12-01', window_end: '2026-12-15' }),
    row(3, { status: 'draft', window_start: '2026-12-20', window_end: '2027-01-05' }),
    row(4, { status: 'ended', window_start: '2026-11-01', window_end: '2026-11-08' }),
    row(5, { status: 'active', needs_reapproval: true, flags: ['no_cost'], window_start: '2026-11-10', window_end: '2026-11-30' }),
  ],
  total: 5,
  page: 1,
  page_size: 500,
  status_counts: { active: 2, approved: 1, draft: 1, ended: 1 },
  test_data_count: 0,
};

let failMain = false;
let clash: unknown = { clash_count: 2, promotion_count: 2, customer_count: 1, from: '2026-11-19', to: null };
const apiGetMock = vi.fn(async (url: string) => {
  if (url.includes('/cpor/cases/counts')) return { total_current: 5, status_counts_current: { active: 2, approved: 1, draft: 1, ended: 1 } };
  if (url.includes('/customer-calendar/clashes/summary')) return clash;
  if (url.includes('/cpor/cases')) {
    if (failMain && !url.includes('status=')) throw new Error('boom');
    if (url.includes('status=')) return { ...listPayload, items: [], total: 0 };
    return listPayload;
  }
  if (url.includes('/aged-stock')) return { lines: [], truncated: false, valuation: { unplanned: { lines: 0, units: 0, value: null, lines_with_cost: 0, lines_without_cost: 0, units_without_cost: 0 } } };
  return {};
});
vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => apiGetMock(url),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDownloadBlob: vi.fn(),
}));

const renderPlanner = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <PromotionPlannerSurface />
    </QueryClientProvider>,
  );
};

beforeEach(() => {
  // A fixed local day, so the timeline axis (which always includes today) and its week ticks do not drift.
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 10, 19, 10, 0, 0));
  apiGetMock.mockClear();
  replaceMock.mockClear();
  pushMock.mockClear();
  failMain = false;
  clash = { clash_count: 2, promotion_count: 2, customer_count: 1, from: '2026-11-19', to: null };
});

afterEach(() => {
  vi.useRealTimers();
});

describe('planner layout (mock-up)', () => {
  it('has the page title with a subtitle and the create-promotion-plan action', async () => {
    renderPlanner();
    const head = await screen.findByTestId('planner-header');
    expect(within(head).getByRole('heading', { name: 'Promotion planner' })).toBeInTheDocument();
    expect(within(head).getByTestId('planner-subtitle').textContent?.length).toBeGreaterThan(10);
    expect(within(head).getByRole('button', { name: /Create promotion plan/i })).toBeInTheDocument();
  });

  it('shows exactly five KPI cards in the mock-up order, each with a label, a value and a caption', async () => {
    renderPlanner();
    const strip = await screen.findByTestId('planner-kpi-strip');
    const cards = within(strip).getAllByTestId(/^planner-kpi-/);
    expect(cards.map((c) => c.getAttribute('data-testid'))).toEqual([
      'planner-kpi-planning',
      'planner-kpi-live',
      'planner-kpi-reserve',
      'planner-kpi-support',
      'planner-kpi-at-risk',
    ]);
    const labels = cards.map((c) => within(c).getByTestId('kpi-label').textContent);
    expect(labels).toEqual(['In planning', 'Live promotions', 'Planned reserve', 'Actual support', 'At-risk actions']);
    for (const c of cards) expect(within(c).getByTestId('kpi-caption').textContent?.length).toBeGreaterThan(3);
    await waitFor(() => expect(within(cards[0]).getByTestId('kpi-value')).toHaveTextContent('2'));
  });

  it('shows Planned reserve and Actual support as "Not available yet" with a reason, never as a number', async () => {
    renderPlanner();
    for (const key of ['reserve', 'support']) {
      const card = await screen.findByTestId(`planner-kpi-${key}`);
      expect(card).toHaveAttribute('data-state', 'unavailable');
      expect(within(card).getByTestId('kpi-value')).toHaveTextContent('Not available yet');
      expect(within(card).getByTestId('kpi-caption').textContent).toMatch(/sell-through/i);
      expect(card).not.toHaveTextContent(/R\s?0|\b0\b/);
    }
  });

  it('keeps the extra cards out of the KPI strip, in a secondary row below it', async () => {
    renderPlanner();
    const secondary = await screen.findByTestId('planner-secondary-cards');
    expect(within(screen.getByTestId('planner-kpi-strip')).queryByText('Drafts to finish')).toBeNull();
    expect(within(secondary).getByText('Drafts to finish')).toBeInTheDocument();
    expect(within(secondary).getByText('Calendar clashes')).toBeInTheDocument();
    const strip = screen.getByTestId('planner-kpi-strip');
    expect(strip.compareDocumentPosition(secondary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('has the five filters: Customer, Status, From/To, Distributor and Product', async () => {
    renderPlanner();
    const bar = await screen.findByTestId('planner-filter-bar');
    expect(within(bar).getByLabelText('Customer')).toBeInTheDocument();
    expect(within(bar).getByLabelText('Status')).toBeInTheDocument();
    expect(within(bar).getByLabelText('From')).toBeInTheDocument();
    expect(within(bar).getByLabelText('To')).toBeInTheDocument();
    expect(within(bar).getByLabelText('Distributor')).toBeInTheDocument();
    expect(within(bar).getByLabelText('Product')).toBeInTheDocument();
  });

  it('orders the page: header, KPIs, filters, timeline, then the action queue', async () => {
    renderPlanner();
    const ids = ['planner-header', 'planner-kpi-strip', 'planner-filter-bar', 'planner-timeline', 'planner-queue-section'];
    const nodes = await Promise.all(ids.map((i) => screen.findByTestId(i)));
    for (let i = 1; i < nodes.length; i += 1) {
      const rel = nodes[i - 1].compareDocumentPosition(nodes[i]);
      expect(rel & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
    // The detail column is docked beside the timeline (mock-up) and empty until a promotion is selected.
    expect(screen.getByTestId('planner-detail-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('planner-detail-drawer')).toBeNull();
  });

  it('draws one timeline row per customer, with the bars coloured by status and a legend of the four statuses', async () => {
    renderPlanner();
    await screen.findByTestId('planner-timeline-bar-1');
    const rows = screen.getAllByTestId(/^planner-timeline-row-/);
    expect(rows).toHaveLength(2); // two customers, five promotions
    expect(within(screen.getByTestId('planner-timeline-row-alpha retail')).getAllByTestId(/^planner-timeline-bar-/)).toHaveLength(3);
    expect(screen.getByTestId('planner-timeline-bar-1')).toHaveAttribute('data-lane', 'live');
    expect(screen.getByTestId('planner-timeline-bar-2')).toHaveAttribute('data-lane', 'approved');
    expect(screen.getByTestId('planner-timeline-bar-3')).toHaveAttribute('data-lane', 'planned');
    expect(screen.getByTestId('planner-timeline-bar-4')).toHaveAttribute('data-lane', 'ended');
    const legend = screen.getByTestId('planner-timeline-legend');
    for (const l of ['Live', 'Approved', 'Planned', 'Ended']) expect(within(legend).getByText(l)).toBeInTheDocument();
  });

  it('opens on Week over Nov – Jan, and Month still shows the month labels', async () => {
    // Requirement: Promotion_Planner Mockup.png selects Week, with a month row and "Wnn / d Mon" labels.
    // The earlier assertion that Week hides "Nov 2026" described the unfinished header, not the mock-up.
    renderPlanner();
    await screen.findByTestId('planner-timeline-bar-1');
    const tl = screen.getByTestId('planner-timeline');
    expect(within(tl).getByText('Nov 2026')).toBeInTheDocument();
    expect(within(tl).getByText('W45 / 2 Nov')).toBeInTheDocument();
    expect(screen.getByTestId('planner-period-label')).toHaveTextContent('Nov – Jan 2027');
    fireEvent.click(screen.getByRole('button', { name: 'Month' }));
    expect(within(tl).queryByText('W45 / 2 Nov')).toBeNull();
    expect(within(tl).getByText('Nov 2026')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Week' }));
    expect(within(tl).getByText('W45 / 2 Nov')).toBeInTheDocument();
  });

  it('selecting a promotion fills the docked detail with the seven sections', async () => {
    // Requirement: the mock-up docks the detail on the right of the timeline, rather than a drawer.
    renderPlanner();
    expect(screen.getByTestId('planner-detail-dock')).toBeInTheDocument();
    expect(screen.getByTestId('planner-detail-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('planner-detail-drawer')).toBeNull();
    fireEvent.click(await screen.findByTestId('planner-timeline-bar-1'));
    const detail = screen.getByTestId('planner-detail');
    for (const s of ['support', 'units', 'stock', 'claims', 'evidence', 'risks', 'next-actions']) {
      expect(within(detail).getByTestId(`planner-detail-${s}`)).toBeInTheDocument();
    }
    expect(within(detail).getByTestId('planner-detail-support')).toHaveTextContent(/R\s?50/);
    expect(within(detail).getByTestId('planner-detail-units')).toHaveTextContent(/1\s200/);
    expect(within(detail).getByTestId('planner-detail-claims')).toHaveTextContent(/2/);
    expect(within(detail).getByTestId('planner-detail-evidence')).toHaveTextContent(/claim/i);
  });

  it('shows stock health as "Not available yet" in the detail panel, not as a healthy or zero figure', async () => {
    renderPlanner();
    fireEvent.click(await screen.findByTestId('planner-timeline-bar-1'));
    const stock = screen.getByTestId('planner-detail-stock');
    expect(stock).toHaveAttribute('data-state', 'unavailable');
    expect(stock).toHaveTextContent('Not available yet');
    expect(stock).toHaveTextContent(/sell-through/i);
  });

  it('lists risk signals the case really carries (reapproval, flags) and does not pretend the rest is known', async () => {
    renderPlanner();
    fireEvent.click(await screen.findByTestId('planner-timeline-bar-5'));
    const risks = screen.getByTestId('planner-detail-risks');
    expect(risks).toHaveTextContent(/Reapproval required/i);
    expect(risks).toHaveTextContent('no_cost');
    expect(risks).toHaveTextContent(/stock and funding risks are not available yet/i);
  });

  it('shows linked claims as "Not available yet" when the case carries no claim summary', async () => {
    renderPlanner();
    fireEvent.click(await screen.findByTestId('planner-timeline-bar-2'));
    expect(screen.getByTestId('planner-detail-claims')).toHaveAttribute('data-state', 'unavailable');
  });

  it('shows the five action-queue cards: Overdue approvals, Low stock risk, Funding gaps, Evidence outstanding, Conflicting windows', async () => {
    renderPlanner();
    const section = await screen.findByTestId('planner-queue-section');
    const cards = within(section).getAllByTestId(/^planner-queue-card-/);
    expect(cards.map((c) => c.getAttribute('data-testid'))).toEqual([
      'planner-queue-card-overdue',
      'planner-queue-card-low-stock',
      'planner-queue-card-funding-gaps',
      'planner-queue-card-evidence',
      'planner-queue-card-conflicts',
    ]);
    expect(within(cards[0]).getByTestId('queue-label')).toHaveTextContent('Overdue approvals');
    expect(within(cards[1]).getByTestId('queue-label')).toHaveTextContent('Low stock risk');
    expect(within(cards[2]).getByTestId('queue-label')).toHaveTextContent('Funding gaps');
    await waitFor(() => expect(within(cards[4]).getByTestId('queue-value')).toHaveTextContent('2'));
  });

  it('shows Low stock risk and Funding gaps as "Not available yet" with a reason, never as zero', async () => {
    renderPlanner();
    for (const key of ['low-stock', 'funding-gaps']) {
      const card = await screen.findByTestId(`planner-queue-card-${key}`);
      expect(card).toHaveAttribute('data-state', 'unavailable');
      expect(within(card).getByTestId('queue-value')).toHaveTextContent('Not available yet');
      expect(within(card).getByTestId('queue-note').textContent?.length).toBeGreaterThan(10);
    }
  });

  it('keeps error distinct from empty and from not-available when the case list fails', async () => {
    failMain = true;
    renderPlanner();
    expect(await screen.findByTestId('planner-timeline-error')).toBeInTheDocument();
    const overdue = await screen.findByTestId('planner-queue-card-overdue');
    await waitFor(() => expect(overdue).toHaveAttribute('data-state', 'empty'));
    expect(overdue).toHaveTextContent(/could not be loaded/i);
    expect(screen.getByTestId('planner-queue-card-low-stock')).toHaveAttribute('data-state', 'unavailable');
    expect(screen.getByTestId('planner-kpi-planning')).toHaveAttribute('data-state', 'ready');
    expect(screen.getByTestId('planner-action-queue-error')).toBeInTheDocument();
  });

  it('keeps the timeline page reachable from the conflicting-windows card', async () => {
    renderPlanner();
    const card = await screen.findByTestId('planner-queue-card-conflicts');
    await waitFor(() => expect(card).toHaveAttribute('data-state', 'ready'));
    fireEvent.click(card);
    expect(pushMock).toHaveBeenCalledWith('/promotions/timeline');
  });
});
