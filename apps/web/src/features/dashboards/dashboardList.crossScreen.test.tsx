import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { OverviewHub } from '@/features/overview/OverviewHub';
import {
  fixtureCatalog,
  fixtureDistributors,
  fixtureInbox,
  fixtureSavedReports,
  fixtureSchedules,
} from '@/features/reports/reportFixtures';
import { ReportBuilderView } from '@/features/reports/ReportBuilderView';
import type { CurrentUser } from '@/features/shell/useCurrentUser';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { dashboardListKey } from './dashboardList';
import { DashboardWorkspace } from './DashboardWorkspace';
import type { Dashboard, DashboardWidget } from './types';

const edge = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(), apiPatch: vi.fn(), apiPut: vi.fn(), apiDelete: vi.fn(), apiDownloadBlob: vi.fn(),
}));
vi.mock('@/lib/api', () => ({
  ...edge,
  safeDisplayError: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}));

// The editor's grid owns geometry only; render each widget through the real renderWidget callback.
vi.mock('next/dynamic', async () => {
  const { createElement: h, Fragment } = await import('react');
  return {
    default: () => (p: { widgets: DashboardWidget[]; renderWidget: (w: DashboardWidget) => import('react').ReactNode }) =>
      h(Fragment, null, ...p.widgets.map((w) => h(Fragment, { key: w.id }, p.renderWidget(w)))),
  };
});
// One card stand-in for both the editor and Overview: its title, and the editor's delete action.
vi.mock('@/features/dashboards/DashboardWidgetCard', async () => {
  const { createElement: h } = await import('react');
  return {
    DashboardWidgetCard: (p: { widget: DashboardWidget; onDelete?: () => void }) =>
      h('section', { 'data-testid': `card-${p.widget.id}` },
        h('span', null, p.widget.title),
        h('button', { type: 'button', onClick: p.onDelete }, `Delete widget ${p.widget.id}`)),
  };
});
vi.mock('@/components/EnterpriseDataGrid', () => ({ EnterpriseDataGrid: () => null }));
vi.mock('@/features/overview/StartWorkPanel', () => ({ StartWorkPanel: () => null }));
vi.mock('@/features/overview/useClientReady', () => ({ useClientReady: () => true }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

const me: CurrentUser = { id: '7', tenant_id: 'test-tenant-a', role: 'planner', job: 'account_manager' };
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));

function widget(id: number, savedReportId: number | null = null): DashboardWidget {
  return {
    id, dashboard_id: 1, title: `Widget ${id}`, visual: 'kpi', metric_key: 'sellout_units', grains: [], filters: {},
    period_grain: null, saved_report_id: savedReportId, sort_order: id, layout_json: { x: 0, y: 0, w: 6, h: 8 },
  };
}

let store: Dashboard[];
let qc: QueryClient;

/** Each screen mounts on its own, as navigation does, against ONE QueryClient retained across screens. */
function show(ui: ReactElement) {
  cleanup();
  return renderWithProviders(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

async function deleteInEditor(widgetId: number) {
  show(<DashboardWorkspace hidePageHeader />);
  fireEvent.click(await screen.findByRole('button', { name: `Delete widget ${widgetId}` }));
  await waitFor(() => expect(edge.apiDelete).toHaveBeenCalledWith(`/api/v1/dashboards/1/widgets/${widgetId}`));
  await waitFor(() => expect(screen.queryByTestId(`card-${widgetId}`)).not.toBeInTheDocument());
}

beforeEach(() => {
  vi.clearAllMocks();
  // The app's own freshness window (providers.tsx): without a shared key, the other screen would not refetch.
  qc = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, retry: false, refetchOnWindowFocus: false } } });
  store = [{
    id: 1, name: 'Test board', description: null, visibility: 'personal', shared_roles: [], filters_json: {},
    owner_user_id: 7, template_key: null, widgets: [widget(11), widget(12, 1)],
  }];
  edge.apiGet.mockImplementation(async (path: string) => {
    if (path === '/api/v1/auth/me') return clone(me);
    if (path === '/api/v1/dashboards') return { items: clone(store) };
    if (path === '/api/v1/dashboards/templates') return { items: [] };
    if (path === '/api/v1/semantics/catalog') return fixtureCatalog;
    if (path === '/api/v1/semantics/v2/catalog') return null;
    if (path === '/api/v1/brief/signals') return { as_of: '2026-11-18', read: 'test', signals: [] };
    if (path === '/api/v1/saved-reports') return fixtureSavedReports();
    if (path === '/api/v1/reports/schedules') return fixtureSchedules();
    if (path.startsWith('/api/v1/reports/inbox')) return fixtureInbox();
    if (path === '/api/v1/sellout/filter-options') return { distributors: fixtureDistributors, customers: [] };
    throw new Error(`Unexpected GET ${path}`);
  });
  edge.apiDelete.mockImplementation(async (path: string) => {
    const m = /^\/api\/v1\/dashboards\/1\/widgets\/(\d+)$/.exec(path);
    if (!m) throw new Error(`Unexpected DELETE ${path}`);
    store[0].widgets = store[0].widgets.filter((w) => w.id !== Number(m[1]));
    return undefined;
  });
  edge.apiPost.mockRejectedValue(new Error('Unexpected POST'));
});

afterEach(() => {
  cleanup();
  qc.clear();
});

describe('one identity-scoped dashboard list across screens (PR #111 B2)', () => {
  it('Overview shows a widget deleted in the editor, within the freshness window', async () => {
    show(<OverviewHub />);
    await screen.findByTestId('card-12');
    expect(screen.getByTestId('card-11')).toBeInTheDocument();

    await deleteInEditor(12);

    show(<OverviewHub />);
    expect(await screen.findByTestId('card-11')).toBeInTheDocument();
    expect(screen.queryByTestId('card-12')).not.toBeInTheDocument();
    // Overview reads the same per-user entry the editor refreshed.
    expect(qc.getQueryData(dashboardListKey(me))).toEqual({ items: store });
    expect(qc.getQueryData(['dashboards'])).toBeUndefined();
  });

  it('Reports pinned counts follow a pinned widget removed in the editor', async () => {
    show(<ReportBuilderView />);
    expect(await screen.findByText('1 pinned to dashboards')).toBeInTheDocument();

    await deleteInEditor(12);

    show(<ReportBuilderView />);
    expect(await screen.findByText('0 pinned to dashboards')).toBeInTheDocument();
    expect(screen.queryByText('1 pinned to dashboards')).not.toBeInTheDocument();
  });
});
