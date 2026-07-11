import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import CporCasesListPage from './page';

const replaceSpy = vi.fn();
const pushSpy = vi.fn();
let searchString = '';

const mockState = vi.hoisted(() => ({
  apiGetMock: vi.fn(async () => ({ items: [], total: 0 })),
  apiPostMock: vi.fn(async () => ({ id: 99 })),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceSpy, push: pushSpy }),
  usePathname: () => '/commercial-planner/cpor-cases',
  useSearchParams: () => new URLSearchParams(searchString),
}));

vi.mock('@/components/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <div>{title}</div>,
}));

vi.mock('@/components/ModuleDataSection', () => ({
  ModuleDataSection: ({ children, isEmpty, empty, isLoading }: any) => {
    if (isLoading) return <div>Loading cases…</div>;
    if (isEmpty) return <div>{empty?.title}</div>;
    return <>{children}</>;
  },
}));

vi.mock('@/components/ModuleGridToolbar', () => ({
  ModuleGridToolbar: ({ onRefresh, busy }: { onRefresh?: () => void; busy?: boolean }) => (
    <button type="button" onClick={onRefresh} disabled={busy} data-testid="cpor-refresh">
      Refresh
    </button>
  ),
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ rowData }: { rowData: any[] }) => (
    <div data-testid="cpor-cases-grid">{rowData.length} rows</div>
  ),
}));

vi.mock('@/features/commercial-planner/EntitySearchAutocomplete', () => ({
  EntitySearchAutocomplete: () => null,
}));

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => mockState.apiGetMock(...args),
  apiPost: (...args: unknown[]) => mockState.apiPostMock(...args),
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return renderWithProviders(
    <QueryClientProvider client={client}>
      <CporCasesListPage />
    </QueryClientProvider>,
  );
}

describe('CPOR cases list page pagination (BACKLOG-074 U4d)', () => {
  beforeEach(() => {
    replaceSpy.mockReset();
    pushSpy.mockReset();
    searchString = '';
    mockState.apiGetMock.mockReset();
    mockState.apiGetMock.mockImplementation(async (url: string) => {
      if (String(url).includes('/cpor/meta/promotion-types')) {
        return { promotion_types: ['Sell out PP'] };
      }
      if (String(url).includes('/cpor/cases')) {
        const offset = searchString.includes('page=2') ? 50 : 0;
        return {
          total: 120,
          items: [{ id: offset + 1, case_code: `C26C${String(offset + 1).padStart(5, '0')}`, line_count: 3 }],
        };
      }
      return { items: [], total: 0 };
    });
  });

  it('fetches cases with default limit/offset from URL page 1', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('cpor-cases-grid')).toHaveTextContent('1 rows'));
    const casesCall = mockState.apiGetMock.mock.calls.find((c) => String(c[0]).includes('/cpor/cases'));
    expect(casesCall?.[0]).toContain('limit=50');
    expect(casesCall?.[0]).toContain('offset=0');
  });

  it('advances page via Next and updates URL', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('cpor-cases-pager')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('cpor-cases-next'));
    expect(replaceSpy).toHaveBeenCalledWith(expect.stringContaining('page=2'));
  });

  it('sends offset for page 2 cases fetch', async () => {
    searchString = 'page=2&page_size=50';
    renderPage();
    await waitFor(() => expect(screen.getByTestId('cpor-cases-grid')).toHaveTextContent('1 rows'));
    expect(mockState.apiGetMock).toHaveBeenCalledWith(
      expect.stringMatching(/offset=50/),
      expect.anything(),
    );
  });

  it('exposes toolbar refresh control', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('cpor-refresh')).toBeInTheDocument());
  });
});
