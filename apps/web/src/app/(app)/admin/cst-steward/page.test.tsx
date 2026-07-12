import React, { useEffect } from 'react';
import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import CstStewardPage from './page';

const replaceSpy = vi.fn();
let searchString = 'tab=key-accounts';

const mockState = vi.hoisted(() => ({
  apiGetMock: vi.fn(async () => []),
  apiPatchMock: vi.fn(async () => ({})),
  apiPostMock: vi.fn(async () => ({})),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceSpy, push: vi.fn() }),
  usePathname: () => '/admin/cst-steward',
  useSearchParams: () => new URLSearchParams(searchString),
}));

vi.mock('@/components/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <div>{title}</div>,
}));

vi.mock('@/components/ModuleDataSection', () => ({
  ModuleDataSection: ({ children, isEmpty, empty, isError, error, onRetry, isLoading }: any) => {
    if (isError) {
      return (
        <div role="alert">
          <span>{error?.message ?? 'error'}</span>
          {onRetry ? (
            <button type="button" onClick={onRetry}>
              Retry
            </button>
          ) : null}
        </div>
      );
    }
    if (isLoading) return <div>Loading…</div>;
    if (isEmpty) {
      return (
        <div data-testid="cst-empty">
          <div>{empty?.title}</div>
          <div>{empty?.description}</div>
        </div>
      );
    }
    return <>{children}</>;
  },
}));

vi.mock('@/components/ModuleGridToolbar', () => ({
  ModuleGridToolbar: ({ onRefresh, busy }: { onRefresh?: () => void; busy?: boolean }) => (
    <button type="button" onClick={onRefresh} disabled={busy} data-testid="cst-refresh">
      Refresh
    </button>
  ),
}));

vi.mock('@/components/masterGrid/MasterColumnPickerDialog', () => ({
  MasterColumnPickerDialog: () => null,
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({
    rowData,
    columnDefs,
    gridOptions,
  }: {
    rowData: any[];
    columnDefs: any[];
    gridOptions?: any;
  }) => {
    useEffect(() => {
      gridOptions?.onGridReady?.({
        api: {
          getColumnState: () => [],
          applyColumnState: () => undefined,
          getColumns: () => [],
          setColumnsVisible: () => undefined,
        },
      });
    }, [gridOptions]);
    return (
      <div data-testid="cst-grid">
        {rowData.map((row) => (
          <div key={row.customer_id ?? row.id}>
            <span>{row.customer_code ?? row.article_no_normalized}</span>
            {columnDefs.map((c, idx) =>
              c.cellRenderer ? (
                <div key={idx}>{c.cellRenderer({ data: row })}</div>
              ) : null,
            )}
          </div>
        ))}
      </div>
    );
  },
}));

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => mockState.apiGetMock(...args),
  apiPatch: (...args: unknown[]) => mockState.apiPatchMock(...args),
  apiPost: (...args: unknown[]) => mockState.apiPostMock(...args),
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return renderWithProviders(
    <QueryClientProvider client={client}>
      <CstStewardPage />
    </QueryClientProvider>,
  );
}

describe('CST steward page chrome (BACKLOG-074 Unit 3)', () => {
  beforeEach(() => {
    replaceSpy.mockReset();
    searchString = 'tab=key-accounts';
    mockState.apiGetMock.mockReset();
    mockState.apiPatchMock.mockReset();
    mockState.apiPostMock.mockReset();
    mockState.apiGetMock.mockImplementation(async (url: string) => {
      if (String(url).includes('key-accounts')) {
        return {
          total: 1,
          items: [
            {
              id: 1,
              customer_id: 10,
              customer_code: 'KA-1',
              customer_name: 'Key One',
              is_key_account: true,
              reports_expected: true,
              expected_cadence: 'weekly',
              overdue_threshold_days: 10,
              notes: null,
              feed_profile_json: null,
            },
          ],
        };
      }
      if (String(url).includes('report-slots')) {
        return { counts: { due: 1, late: 0, missing: 0 }, items: [] };
      }
      if (String(url).includes('article-aliases')) {
        return { total: 0, items: [] };
      }
      return { total: 0, items: [] };
    });
  });

  it('deep-links aliases tab from ?tab=aliases', async () => {
    searchString = 'tab=aliases';
    renderPage();
    expect(await screen.findByRole('tab', { name: 'Article aliases', selected: true })).toBeInTheDocument();
    expect(await screen.findByText('No proposed aliases', {}, { timeout: 5000 })).toBeInTheDocument();
  });

  it('wires key_only switch into the URL', async () => {
    renderPage();
    await screen.findByText('KA-1');
    fireEvent.click(screen.getByTestId('cst-key-only'));
    expect(replaceSpy).toHaveBeenCalled();
    const last = replaceSpy.mock.calls.at(-1)?.[0] as string;
    expect(last).toContain('key_only=1');
  });

  it('shows Retry when report-slots query fails', async () => {
    searchString = 'tab=slots';
    mockState.apiGetMock.mockImplementation(async (url: string) => {
      if (String(url).includes('report-slots')) {
        throw new Error('slots down');
      }
      return { total: 0, items: [] };
    });
    renderPage();
    expect(await screen.findByText('slots down')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('exposes Columns control on key-accounts tab', async () => {
    renderPage();
    await screen.findByText('KA-1');
    expect(screen.getByTestId('cst-steward-columns-open')).toBeInTheDocument();
    expect(screen.getByTestId('cst-steward-columns-reset')).toBeInTheDocument();
    expect(screen.getByTestId('cst-refresh')).toBeInTheDocument();
  });

  it('shows server pager total and fetches with offset on Next', async () => {
    mockState.apiGetMock.mockImplementation(async (url: string) => {
      if (String(url).includes('key-accounts')) {
        return {
          total: 250,
          items: [
            {
              id: 1,
              customer_id: 10,
              customer_code: 'KA-1',
              customer_name: 'Key One',
              is_key_account: true,
              reports_expected: true,
              expected_cadence: 'weekly',
              overdue_threshold_days: 10,
              notes: null,
              feed_profile_json: null,
            },
          ],
        };
      }
      return { total: 0, items: [] };
    });
    renderPage();
    expect(await screen.findByText(/250 rows/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    const last = replaceSpy.mock.calls.at(-1)?.[0] as string;
    expect(last).toContain('page=2');
  });

  it('sends offset for page 2 key-accounts fetch', async () => {
    searchString = 'tab=key-accounts&page=2&page_size=100';
    renderPage();
    await screen.findByText('KA-1');
    expect(mockState.apiGetMock).toHaveBeenCalledWith(
      expect.stringMatching(/offset=100/),
      expect.anything(),
    );
  });

  it('shows slots pager total and pages via URL', async () => {
    searchString = 'tab=slots';
    mockState.apiGetMock.mockImplementation(async (url: string) => {
      if (String(url).includes('report-slots')) {
        return {
          counts: { due: 250, late: 0, missing: 0, received: 0 },
          total: 250,
          items: [
            {
              id: 1,
              customer_id: 10,
              customer_code: 'KA-1',
              customer_name: 'Key One',
              week_start_date: '2026-07-06',
              status: 'due',
            },
          ],
        };
      }
      return { total: 0, items: [] };
    });
    renderPage();
    expect(await screen.findByText(/250 rows/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(replaceSpy).toHaveBeenCalled();
    const last = String(replaceSpy.mock.calls.at(-1)?.[0] ?? '');
    expect(last).toContain('page=2');
  });

  it('exposes Columns control on aliases tab', async () => {
    searchString = 'tab=aliases';
    mockState.apiGetMock.mockImplementation(async (url: string) => {
      if (String(url).includes('article-aliases')) {
        return {
          total: 1,
          items: [
            {
              id: 9,
              customer_code: 'KA-1',
              customer_name: 'Key One',
              article_no_normalized: 'ART-1',
              product_sku: 'SKU-1',
              product_name: 'Widget',
              status: 'proposed',
            },
          ],
        };
      }
      return { total: 0, items: [] };
    });
    renderPage();
    await screen.findByText('KA-1');
    expect(screen.getByTestId('cst-aliases-columns-open')).toBeInTheDocument();
  });

  it('shows actionable empty-state copy on aliases and slots tabs (Wave 3)', async () => {
    searchString = 'tab=aliases';
    mockState.apiGetMock.mockResolvedValue({ total: 0, items: [], counts: { due: 0, late: 0, missing: 0 } });
    renderPage();
    expect(await screen.findByText('No proposed aliases')).toBeInTheDocument();
    expect(screen.getByText(/Confirm\/Reject/i)).toBeInTheDocument();
    expect(screen.getByTestId('cst-steward-guide')).toHaveTextContent(/Advance slots now/i);
  });

  it('shows Advance-slots guidance when report-slots worklist is empty', async () => {
    searchString = 'tab=slots';
    mockState.apiGetMock.mockImplementation(async (url: string) => {
      if (String(url).includes('report-slots')) {
        return { total: 0, items: [], counts: { due: 0, late: 0, missing: 0 } };
      }
      return { total: 0, items: [] };
    });
    renderPage();
    expect(await screen.findByText('No open report slots')).toBeInTheDocument();
    expect(screen.getByTestId('cst-empty')).toHaveTextContent(/mint the current period/i);
    expect(screen.getByTestId('cst-slots-advance')).toBeInTheDocument();
  });
});
