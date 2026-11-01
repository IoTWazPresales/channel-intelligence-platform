import { ThemeProvider, createTheme } from '@mui/material/styles';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { OverviewHub, overviewCardHeight } from './OverviewHub';

const theme = createTheme();

const queryByKey = vi.hoisted(() => ({
  brief: { isLoading: false, isError: false, data: null as null | { signals: unknown[]; signal_count?: number; as_of?: string } },
  dashboards: { isLoading: false, isError: false, data: null as null | { items: unknown[] } },
  catalog: { isLoading: false, isError: false, data: { metrics: [] as unknown[] } },
  reports: { isLoading: false, isError: false, data: null as null | { items: unknown[]; count: number } },
  mobile: false,
  zone: null as string | null,
}));

vi.mock('./useClientReady', () => ({
  useClientReady: () => true,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({ get: (k: string) => (k === 'zone' ? queryByKey.zone : null) }),
}));

vi.mock('@/features/dashboards/DashboardWidgetCard', () => ({
  DashboardWidgetCard: ({ widget, catalog }: { widget: { title: string }; catalog?: unknown }) => (
    <div data-testid="widget-card" data-catalog={catalog === undefined ? 'loading' : catalog === null ? 'none' : 'ready'}>
      {widget.title}
    </div>
  ),
}));

vi.mock('@/features/overview/StartWorkPanel', () => ({
  StartWorkPanel: () => (
    <div data-testid="start-work">
      <a href="/admin/imports?unified=1" data-testid="start-work-create-lineup">
        Import a lineup
      </a>
    </div>
  ),
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useQuery: ({ queryKey }: { queryKey: string[] }) => {
    if (queryKey[0] === 'brief') return queryByKey.brief;
    if (queryKey[0] === 'dashboards') return queryByKey.dashboards;
    if (queryKey[0] === 'semantics-catalog') return queryByKey.catalog;
    if (queryKey[0] === 'saved-reports') return queryByKey.reports;
    return { isLoading: false, isError: false, data: null };
  },
}));

function renderHub() {
  return render(
    <ThemeProvider theme={theme}>
      <OverviewHub />
    </ThemeProvider>,
  );
}

describe('OverviewHub', () => {
  beforeEach(() => {
    queryByKey.mobile = false;
    queryByKey.zone = null;
    queryByKey.brief = {
      isLoading: false,
      isError: false,
      data: {
        signal_count: 2,
        signals: [
          {
            id: 'cover_breach',
            rank: 1,
            severity: 'stop',
            title: 'Cover breaches',
            detail: 'pairs under 2w',
            meta: '12',
            meta_hot: true,
            action_label: 'Open cover',
            action_href: '/stock?lens=cover',
          },
          {
            id: 'import_ok',
            rank: 2,
            severity: 'ok',
            title: 'Imports applied',
            detail: 'DSI job 12',
            meta: '1',
            meta_hot: false,
            action_label: 'Imports',
            action_href: '/admin/imports',
          },
        ],
      },
    };
    queryByKey.dashboards = { isLoading: false, isError: false, data: { items: [] } };
    queryByKey.catalog = { isLoading: false, isError: false, data: { metrics: [] } };
    queryByKey.reports = { isLoading: false, isError: false, data: { items: [], count: 0 } };
  });

  it('composes start work in prime, attention exceptions, and a compact dashboard link', () => {
    renderHub();
    expect(screen.getByTestId('overview-surface')).toBeInTheDocument();
    expect(screen.getByTestId('start-work')).toBeInTheDocument();
    expect(screen.getByTestId('start-work-create-lineup')).toHaveAttribute('href', '/admin/imports?unified=1');
    expect(screen.getByTestId('dashboard-zone')).toBeInTheDocument();
    expect(screen.getByTestId('attention-zone')).toBeInTheDocument();
    expect(screen.getByText(/Open Business dashboard/i)).toBeInTheDocument();
    expect(screen.getByText(/No dashboard yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/lab fixture/i)).toBeNull();
    expect(screen.getByText('Cover breaches')).toBeInTheDocument();
    expect(screen.getByText('Imports applied')).toBeInTheDocument();
    expect(screen.getByTestId('overview-edit-dashboard')).toHaveAttribute('href', '/dashboards');
    expect(screen.getByTestId('overview-all-reports')).toHaveAttribute('href', '/reports');
    expect(screen.getByTestId('overview-body')).toBeInTheDocument();
  });

  it('lists only this user\'s pinned reports and does not print a metric key', () => {
    queryByKey.reports = {
      isLoading: false,
      isError: false,
      data: {
        count: 2,
        items: [
          { id: 1, name: 'Weekly cover', visibility: 'personal', overview_pinned: true },
          { id: 2, name: 'Hidden report', visibility: 'published', overview_pinned: false },
        ],
      },
    };
    renderHub();
    expect(screen.getByText('Weekly cover')).toBeInTheDocument();
    expect(screen.queryByText('Hidden report')).toBeNull();
    expect(screen.getByTestId('unpin-report-1')).toBeInTheDocument();
    expect(screen.queryByText('sellout_units')).toBeNull();
  });

  it('lays dashboard charts out in a grid with a 1/2/3 per-row choice kept in the browser', () => {
    window.localStorage.removeItem('cip.overview.dashboard.columns.v1');
    queryByKey.dashboards = {
      isLoading: false,
      isError: false,
      data: {
        items: [
          {
            id: 1,
            name: 'Main',
            widgets: [
              { id: 1, title: 'Sell-out', metric_key: 'm' },
              { id: 2, title: 'Cover', metric_key: 'm' },
            ],
          },
        ],
      },
    };
    renderHub();
    const grid = screen.getByTestId('dashboard-widget-grid');
    expect(grid).toHaveTextContent('Sell-out');
    expect(screen.getByRole('button', { name: '2 per row' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: '3 per row' }));
    expect(window.localStorage.getItem('cip.overview.dashboard.columns.v1')).toBe('3');
    expect(screen.getByRole('button', { name: '3 per row' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows the dashboard name and the date the data is as of, not the raw timestamp', () => {
    queryByKey.brief = { ...queryByKey.brief, data: { signals: [], as_of: '2026-11-01T12:03:19.558548+00:00' } };
    queryByKey.dashboards = { isLoading: false, isError: false, data: { items: [{ id: 1, name: 'Board', widgets: [] }] } };
    renderHub();
    expect(screen.getByText('Board · data as of 2026-11-01')).toBeInTheDocument();
  });

  it('gives every dashboard card a definite height from its grid rows, within a readable range', () => {
    expect(overviewCardHeight(10)).toBe(10 * 36 + 9 * 8);
    expect(overviewCardHeight(undefined)).toBe(8 * 36 + 7 * 8);
    expect(overviewCardHeight(1)).toBe(220);
    expect(overviewCardHeight(60)).toBe(520);
  });

  it('hands each widget card the v2 catalog state, so a v2 widget is not a skeleton for ever', () => {
    queryByKey.dashboards = { isLoading: false, isError: false, data: { items: [{ id: 1, name: 'Board', widgets: [{ id: 7, title: 'Units', metric_key: 'm' }] }] } };
    renderHub();
    // The query mock answers an unknown key with data null: that is "no v2 catalog", not "loading".
    expect(screen.getByTestId('widget-card')).toHaveAttribute('data-catalog', 'none');
  });
});
