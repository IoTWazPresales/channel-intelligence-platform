import { ThemeProvider, createTheme } from '@mui/material/styles';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { OverviewHub } from './OverviewHub';

const theme = createTheme();

const queryByKey = vi.hoisted(() => ({
  brief: { isLoading: false, isError: false, data: null as null | { signals: unknown[]; signal_count?: number } },
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
  DashboardWidgetCard: ({ widget }: { widget: { title: string } }) => <div>{widget.title}</div>,
}));

vi.mock('@tanstack/react-query', () => ({
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

  it('composes dashboard and attention zones from live payloads, not lab fixtures', () => {
    renderHub();
    expect(screen.getByTestId('overview-surface')).toBeInTheDocument();
    expect(screen.getByTestId('dashboard-zone')).toBeInTheDocument();
    expect(screen.getByTestId('attention-zone')).toBeInTheDocument();
    expect(screen.getByText(/No dashboards yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/lab fixture/i)).not.toBeNull();
    expect(screen.getByText('Cover breaches')).toBeInTheDocument();
    expect(screen.getByText('Imports applied')).toBeInTheDocument();
    expect(screen.getByTestId('overview-edit-dashboard')).toHaveAttribute('href', '/dashboards');
    expect(screen.getByTestId('overview-all-reports')).toHaveAttribute('href', '/reports');
  });
});
