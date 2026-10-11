import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import {
  fixtureCatalog,
  fixtureDashboards,
  fixtureDistributors,
  fixtureInbox,
  fixtureSavedReports,
  fixtureSchedules,
  fixtureSelloutByPeriod,
  fixtureWeeksOfCover,
} from './reportFixtures';
import { ReportBuilderView } from './ReportBuilderView';

const api = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiDownloadBlob: vi.fn(async () => undefined),
}));

vi.mock('@/lib/api', () => ({
  apiGet: api.apiGet,
  apiPost: api.apiPost,
  apiDownloadBlob: api.apiDownloadBlob,
  safeDisplayError: (e: unknown) => String((e as Error)?.message ?? e),
}));

type Col = {
  field: string;
  headerName: string;
  type?: string;
  valueFormatter?: (p: { value: unknown; node?: { rowPinned?: string | null } }) => string;
};

/** Grid stand-in: renders header names and formatted cells, plus the pinned totals row. */
vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({
    rowData,
    columnDefs,
    gridOptions,
  }: {
    rowData: Record<string, unknown>[];
    columnDefs: Col[];
    gridOptions?: { pinnedBottomRowData?: Record<string, unknown>[] };
  }) => {
    const cell = (c: Col, row: Record<string, unknown>, pinned: boolean) =>
      c.valueFormatter ? c.valueFormatter({ value: row[c.field], node: { rowPinned: pinned ? 'bottom' : null } }) : String(row[c.field] ?? '');
    return (
      <table data-testid="grid">
        <thead>
          <tr>
            {columnDefs.map((c) => (
              <th key={c.field} data-align={c.type === 'rightAligned' ? 'right' : 'left'}>
                {c.headerName}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rowData.map((r, i) => (
            <tr key={i} data-testid="grid-row">
              {columnDefs.map((c) => (
                <td key={c.field}>{cell(c, r, false)}</td>
              ))}
            </tr>
          ))}
        </tbody>
        <tfoot>
          {(gridOptions?.pinnedBottomRowData ?? []).map((r, i) => (
            <tr key={i} data-testid="grid-total">
              {columnDefs.map((c) => (
                <td key={c.field}>{cell(c, r, true)}</td>
              ))}
            </tr>
          ))}
        </tfoot>
      </table>
    );
  },
}));

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  api.apiGet.mockReset();
  api.apiPost.mockReset();
  api.apiGet.mockImplementation(async (url: string) => {
    if (url === '/api/v1/semantics/catalog') return fixtureCatalog;
    if (url === '/api/v1/saved-reports') return fixtureSavedReports();
    if (url === '/api/v1/reports/schedules') return fixtureSchedules();
    if (url.startsWith('/api/v1/reports/inbox')) return fixtureInbox();
    if (url === '/api/v1/dashboards') return fixtureDashboards();
    if (url === '/api/v1/sellout/filter-options') return { distributors: fixtureDistributors, customers: [] };
    if (url === '/api/v1/catalog/product-lines') return { product_lines: [], null_product_line_count: 0 };
    throw new Error(`unexpected GET ${url}`);
  });
  api.apiPost.mockImplementation(async (url: string, body: { metric?: string }) => {
    if (url === '/api/v1/query/execute') return body.metric === 'sellout_units' ? fixtureSelloutByPeriod() : fixtureWeeksOfCover();
    throw new Error(`unexpected POST ${url}`);
  });
});

async function run() {
  await screen.findByTestId('report-metric-weeks_of_cover');
  fireEvent.click(screen.getByTestId('report-run'));
  await screen.findByTestId('report-result');
  await waitFor(() => expect(api.apiPost).toHaveBeenCalled());
}

function pickView(name: string) {
  fireEvent.click(within(screen.getByTestId('report-visual-mode')).getByRole('button', { name }));
}

describe('ReportBuilderView', () => {
  it('summary tiles, saved reports and recent runs come from the API', async () => {
    wrap(<ReportBuilderView />);
    expect(await screen.findByText('1 pinned to dashboards')).toBeInTheDocument();
    expect(within(screen.getByTestId('reports-summary-saved')).getByText('2')).toBeInTheDocument();
    expect(within(screen.getByTestId('reports-summary-scheduled')).getByText('Mondays 07:00')).toBeInTheDocument();
    // Two runs of saved reports this week; the shipping digest is not a report run.
    expect(within(screen.getByTestId('reports-summary-runs')).getByText('2')).toBeInTheDocument();
    const saved = screen.getByTestId('saved-reports-panel');
    expect(within(saved).getByText('Weekly cover by distributor')).toBeInTheDocument();
    expect(within(screen.getByTestId('saved-report-1')).getByText('pinned')).toBeInTheDocument();
    expect(within(screen.getByTestId('saved-report-2')).queryByText('pinned')).toBeNull();
    const runs = screen.getByTestId('recent-runs-panel');
    expect(within(runs).getByText('Sell-out trend')).toBeInTheDocument();
    expect(within(runs).queryByText(/sellout_units|\[MISSING DATA\]|digest/i)).toBeNull();
  });

  it('runs the same governed query and shows the KPI tile with unit, target and state counts', async () => {
    wrap(<ReportBuilderView />);
    await run();
    expect(api.apiPost).toHaveBeenCalledWith('/api/v1/query/execute', {
      metric: 'weeks_of_cover',
      grains: ['distributor', 'product'],
      filters: {},
    });
    const lead = await screen.findByTestId('report-kpi-lead');
    expect(within(lead).getByText('4.3')).toBeInTheDocument();
    expect(within(lead).getByText('weeks')).toBeInTheDocument();
    expect(within(lead).getByText('target ≥ 4 weeks')).toBeInTheDocument();
    expect(within(screen.getByTestId('report-kpi-under2')).getByText('3')).toBeInTheDocument();
    expect(within(screen.getByTestId('report-kpi-under4')).getByText('2')).toBeInTheDocument();
    // Result table under the KPI, names first, totals recomputed.
    const grid = screen.getByTestId('grid');
    expect(within(grid).getAllByRole('columnheader').map((h) => h.textContent)).toEqual([
      'Distributor',
      'Distributor code',
      'Product ID',
      'Channel stock (units)',
      'Avg weekly sell-out (units)',
      'Weeks of cover',
      'State',
    ]);
    const firstRow = within(grid).getAllByTestId('grid-row')[0];
    expect(within(firstRow).getAllByRole('cell')[0]).toHaveTextContent('Kwazulu Channel Partners');
    const total = within(grid).getByTestId('grid-total');
    expect(total).toHaveTextContent('Total · 10 rows');
    expect(total).toHaveTextContent('14 028');
    expect(total).toHaveTextContent('3 300');
    expect(total).toHaveTextContent('4.3');
  });

  it('bar view: sorted low to high, direct values, threshold and state key', async () => {
    wrap(<ReportBuilderView />);
    await run();
    pickView('Bar');
    const bar = await screen.findByTestId('report-bar');
    expect(within(bar).getByRole('img', { name: /sorted lowest first, 4-week threshold marked/ })).toBeInTheDocument();
    const rows = within(within(bar).getByRole('table')).getAllByRole('row').slice(1);
    expect(rows[0]).toHaveTextContent('Kwazulu Channel Partners · Product #1040');
    expect(rows[0]).toHaveTextContent('0.4w');
    expect(rows.map((r) => r.textContent)).toHaveLength(9);
    expect(within(bar).getByText(/1 without a value/)).toBeInTheDocument();
    expect(within(bar).getByText('Under 2 weeks')).toBeInTheDocument();
    expect(within(bar).getByText('Under 4 weeks')).toBeInTheDocument();
  });

  it('table view shows the grid only once', async () => {
    wrap(<ReportBuilderView />);
    await run();
    pickView('Table');
    expect(await screen.findByTestId('report-table')).toBeInTheDocument();
    expect(screen.getAllByTestId('grid')).toHaveLength(1);
  });

  it('no engineering vocabulary on screen; formula and scope sit behind "About this figure"', async () => {
    wrap(<ReportBuilderView />);
    await run();
    const text = document.body.textContent ?? '';
    for (const bad of ['weeks_of_cover', 'tenant_scope', 'latest_snapshot', 'Formula', 'Allowed:', 'Distributor id', 'invariant', 'never_sum']) {
      expect(text).not.toContain(bad);
    }
    const toggle = screen.getByRole('button', { name: 'About this figure' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const about = screen.getByTestId('report-about');
    expect(within(about).getByText(/How many weeks the stock/)).toBeInTheDocument();
    expect(within(about).getByText('Stock still in transit is not counted')).toBeInTheDocument();
    expect(within(about).getByText(/All distributors/)).toBeInTheDocument();
  });

  it('distributor is a picker of names; the payload keeps the id filter', async () => {
    wrap(<ReportBuilderView />);
    await screen.findByTestId('report-metric-weeks_of_cover');
    const input = within(screen.getByTestId('report-distributor-picker')).getByRole('combobox');
    fireEvent.mouseDown(input);
    fireEvent.change(input, { target: { value: 'Coastal' } });
    fireEvent.click(await screen.findByRole('option', { name: 'Coastal Tech Supply' }));
    fireEvent.click(screen.getByTestId('report-run'));
    await waitFor(() =>
      expect(api.apiPost).toHaveBeenCalledWith('/api/v1/query/execute', {
        metric: 'weeks_of_cover',
        grains: ['distributor', 'product'],
        filters: { distributor_id: '5' },
      }),
    );
    expect(await screen.findByText('Scope · Coastal Tech Supply')).toBeInTheDocument();
  });

  it('send and schedule explain why they are disabled until the report is saved', async () => {
    wrap(<ReportBuilderView />);
    await screen.findByTestId('report-metric-weeks_of_cover');
    expect(screen.getByTestId('report-deliver-inbox')).toBeDisabled();
    expect(screen.getByTestId('report-schedule')).toBeDisabled();
    expect(screen.getByTestId('report-send-hint')).toHaveTextContent('Save the report to send or schedule it.');
    fireEvent.click(within(screen.getByTestId('saved-report-1')).getByText('Weekly cover by distributor'));
    expect(screen.getByTestId('report-deliver-inbox')).not.toBeDisabled();
    expect(screen.getByTestId('report-loaded-saved')).toHaveTextContent('Weekly cover by distributor');
  });

  it('period breakdown offers a trend with the latest point labelled', async () => {
    wrap(<ReportBuilderView />);
    fireEvent.click(await screen.findByTestId('report-metric-sellout_units'));
    fireEvent.mouseDown(within(screen.getByTestId('report-grain-select')).getByRole('combobox'));
    fireEvent.click(await screen.findByRole('option', { name: 'Period' }));
    fireEvent.click(screen.getByTestId('report-run'));
    await screen.findByTestId('report-kpi-latest');
    expect(within(screen.getByTestId('report-kpi-latest')).getByText('▲ 1 280 vs 2026-W38')).toBeInTheDocument();
    pickView('Trend');
    const trend = await screen.findByTestId('report-trend');
    expect(within(trend).getByRole('img', { name: /latest 15\s560/ })).toBeInTheDocument();
  });
});
