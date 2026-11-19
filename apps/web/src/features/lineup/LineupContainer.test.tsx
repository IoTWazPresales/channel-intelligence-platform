import { fireEvent, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { LineupContainer } from './LineupContainer';
import type { LineupPlanRow } from './lineupTypes';

const navigation = vi.hoisted(() => ({
  query: '',
  replace: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(navigation.query),
  useRouter: () => ({ replace: navigation.replace }),
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  safeDisplayError: (error: unknown) => String(error),
}));

// Keep the container, workspace, scope bar and grid filtering real.
vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ rowData }: { rowData: LineupPlanRow[] }) => (
    <div data-testid="rendered-plan-ids">{rowData.map((row) => row.id).join(',')}</div>
  ),
}));
vi.mock('@/features/tenant/useLineIdentifierPreference', () => ({
  useLineIdentifierPreference: () => ({ columns: () => [] }),
}));
vi.mock('@/features/lineup/LineupPlanActionBar', () => ({
  LineupPlanActionBar: () => null,
}));

const rows: LineupPlanRow[] = [
  {
    id: 1, customer_id: 3, customer_name: 'Customer A', customer_code: 'A',
    channel_code: null, period_start: '2026-01-01', period_label: '26Q1',
    product_id: 11, sku: 'S1', planned_volume_units: 4, approval_status: 'draft',
  },
  {
    id: 2, customer_id: 3, customer_name: 'Customer A', customer_code: 'A',
    channel_code: null, period_start: '2026-01-01', period_label: '26Q1',
    product_id: 12, sku: 'S2', planned_volume_units: 6, approval_status: 'approved',
  },
  {
    id: 3, customer_id: 4, customer_name: 'Customer B', customer_code: 'B',
    channel_code: null, period_start: '2026-01-01', period_label: '26Q1',
    product_id: 11, sku: 'S1', planned_volume_units: 100, approval_status: 'rejected',
  },
  {
    id: 4, customer_id: 3, customer_name: 'Customer A', customer_code: 'A',
    channel_code: null, period_start: '2026-04-01', period_label: '26Q2',
    product_id: 11, sku: 'S1', planned_volume_units: 200, approval_status: 'submitted',
  },
];

const sliceQuery = 'customer=3&period=2026-01-01';

function renderPage(query = sliceQuery) {
  navigation.query = query;
  navigation.replace.mockImplementation((url: string) => {
    navigation.query = url.split('?')[1] ?? '';
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(['lineup-items'], rows);
  client.setQueryData(['lineup-net-requirement', 'headline'], {
    data_unavailable: false, rows: [{ net_requirement: 90 }],
  });
  client.setQueryData(['plan-vs-executed', 'lineup-read'], {
    data_unavailable: false, scorecard: { fill_rate: 0.75 },
  });
  const view = () => (
    <QueryClientProvider client={client}>
      <LineupContainer />
    </QueryClientProvider>
  );
  const rendered = renderWithProviders(view());
  return () => rendered.rerender(view());
}

function expectSummary(text: string) {
  expect(within(screen.getByTestId('lineup-scope-bar')).getByText(text)).toBeInTheDocument();
}

function expectFigure(testId: string, value: string) {
  expect(within(screen.getByTestId(testId)).getByText(value, { exact: true })).toBeInTheDocument();
}

describe('LineupContainer customer/period scope (PR #115 B1)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('matches the displayed slice and excludes other customers and periods from headlines', () => {
    renderPage();
    expect(screen.getByTestId('rendered-plan-ids')).toHaveTextContent(/^1,2$/);
    expectSummary('2 plan lines');
    expectFigure('lineup-planned-units', '10');
    expect(screen.getByTestId('lineup-planned-units')).toHaveTextContent('2 plan lines (all statuses)');
    expectFigure('lineup-approval', '100%');
    expectFigure('lineup-pending-approval', '1');
    expect(screen.getByText('Master scope; bias included')).toBeInTheDocument();
    expect(screen.getByText('Master scope; shipped against lineup')).toBeInTheDocument();
  });

  it('intersects a slice with the product filter for rows, counts and units', () => {
    renderPage(`${sliceQuery}&product=11`);
    expect(screen.getByTestId('rendered-plan-ids')).toHaveTextContent(/^1$/);
    expectSummary('1 of 2 plan lines');
    expectFigure('lineup-planned-units', '4');
    expectFigure('lineup-pending-approval', '1');
  });

  it('counts visible pending rows while retaining all-status scope headlines', () => {
    const refresh = renderPage();
    fireEvent.click(screen.getByTestId('lineup-pending-approval'));
    expect(navigation.replace).toHaveBeenCalledWith(
      '/lineup/cases?customer=3&period=2026-01-01&approval=pending', { scroll: false },
    );
    refresh();
    expect(screen.getByTestId('rendered-plan-ids')).toHaveTextContent(/^1$/);
    expectSummary('1 of 2 plan lines');
    expectFigure('lineup-planned-units', '10');
    expectFigure('lineup-approval', '100%');
  });

  it('shows an empty intersection instead of falling back to master totals', () => {
    renderPage(`${sliceQuery}&product=12&approval=pending`);
    expect(screen.getByTestId('rendered-plan-ids')).toBeEmptyDOMElement();
    expectSummary('0 of 2 plan lines');
    expectFigure('lineup-planned-units', '6');
    expectFigure('lineup-pending-approval', '0');
  });

  it('shows no scoped headlines when the customer/period has no rows', () => {
    renderPage('customer=4&period=2026-04-01');
    expect(screen.getByTestId('rendered-plan-ids')).toBeEmptyDOMElement();
    expectSummary('0 plan lines');
    expect(screen.getByTestId('lineup-planned-units')).toHaveTextContent('0 plan lines (all statuses)');
    expect(screen.getByTestId('lineup-approval')).not.toHaveTextContent('%');
    expect(screen.getByTestId('lineup-pending-approval')).not.toHaveTextContent(/[0-9]/);
  });

  it('restores master rows and figures when all filters are cleared', () => {
    const refresh = renderPage(`${sliceQuery}&product=11&approval=pending`);
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    expect(navigation.replace).toHaveBeenCalledWith('/lineup/cases', { scroll: false });
    refresh();
    expect(screen.getByTestId('rendered-plan-ids')).toHaveTextContent(/^1,2,3,4$/);
    expectSummary('4 plan lines');
    expectFigure('lineup-planned-units', '310');
    expectFigure('lineup-approval', '50%');
    expectFigure('lineup-pending-approval', '2');
  });
});
