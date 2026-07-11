import React from 'react';
import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { ProductMasterGapWorklistView } from './ProductMasterGapWorklistView';

const replaceSpy = vi.fn();
let searchString = '';

const mockState = vi.hoisted(() => ({
  apiGetMock: vi.fn(async () => ({ total: 0, skip: 0, limit: 100, rows: [], data_unavailable: false })),
  apiPostMock: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceSpy, push: vi.fn() }),
  usePathname: () => '/admin/product-master-gaps',
  useSearchParams: () => new URLSearchParams(searchString),
}));

vi.mock('@/components/ModuleDataSection', () => ({
  ModuleDataSection: ({ children, isEmpty, empty, isLoading }: any) => {
    if (isLoading) return <div>Loading gaps…</div>;
    if (isEmpty) return <div>{empty?.title}</div>;
    return <>{children}</>;
  },
}));

vi.mock('@/components/ModuleGridToolbar', () => ({
  ModuleGridToolbar: ({ onRefresh }: { onRefresh?: () => void }) => (
    <button type="button" data-testid="pmg-toolbar-refresh" onClick={onRefresh}>
      Refresh
    </button>
  ),
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ rowData }: { rowData: any[] }) => (
    <div data-testid="pmg-grid">{rowData.length} rows</div>
  ),
}));

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => mockState.apiGetMock(...args),
  apiPost: (...args: unknown[]) => mockState.apiPostMock(...args),
  safeDisplayError: (err: unknown) => String(err),
}));

function renderView() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return renderWithProviders(
    <QueryClientProvider client={client}>
      <ProductMasterGapWorklistView />
    </QueryClientProvider>,
  );
}

describe('ProductMasterGapWorklistView pagination (BACKLOG-074 U4c)', () => {
  beforeEach(() => {
    replaceSpy.mockReset();
    searchString = '';
    mockState.apiGetMock.mockReset();
    mockState.apiPostMock.mockReset();
    mockState.apiGetMock.mockImplementation(async (url: string) => {
      if (String(url).includes('/product-master-gaps/worklist')) {
        const skip = searchString.includes('skip=100') ? 100 : 0;
        const limit = searchString.includes('limit=50') ? 50 : 100;
        return {
          total: 250,
          skip,
          limit,
          data_unavailable: false,
          rows: [{ token: `TOK-${skip}`, sources: ['shipment'], status: 'unresolved', affected_job_ids: [] }],
        };
      }
      return {};
    });
  });

  it('fetches worklist with skip/limit from URL', async () => {
    searchString = 'skip=100&limit=50';
    renderView();
    await screen.findByTestId('pmg-grid');
    expect(mockState.apiGetMock).toHaveBeenCalledWith(
      expect.stringMatching(/skip=100.*limit=50/),
    );
  });

  it('syncs next page to URL skip param', async () => {
    renderView();
    await screen.findByTestId('pmg-grid');
    fireEvent.click(screen.getByRole('button', { name: 'Go to next page' }));
    expect(replaceSpy).toHaveBeenCalled();
    const last = String(replaceSpy.mock.calls.at(-1)?.[0] ?? '');
    expect(last).toMatch(/skip=100/);
  });

  it('resets skip when source filter changes', async () => {
    searchString = 'skip=100';
    renderView();
    await screen.findByTestId('pmg-grid');
    fireEvent.mouseDown(screen.getByLabelText('Source'));
    fireEvent.click(await screen.findByRole('option', { name: 'Shipment' }));
    expect(replaceSpy).toHaveBeenCalled();
    const last = String(replaceSpy.mock.calls.at(-1)?.[0] ?? '');
    expect(last).toMatch(/source=shipment/);
    expect(last).not.toMatch(/skip=/);
  });

  it('renders ModuleGridToolbar refresh', async () => {
    renderView();
    expect(await screen.findByTestId('pmg-toolbar-refresh')).toBeInTheDocument();
  });
});
