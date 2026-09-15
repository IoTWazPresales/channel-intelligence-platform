import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import AdminMappingsPage from './page';

let searchString = '';

const apiGetMock = vi.fn();

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(searchString),
  usePathname: () => '/admin/mappings',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => apiGetMock(...args),
  apiDelete: vi.fn(),
  apiPost: vi.fn(),
  apiUrl: (p: string) => p,
}));

vi.mock('@/features/data-stewardship/DataChrome', () => ({
  DataChrome: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/features/data-stewardship/StewardFailureQueue', () => ({
  StewardFailureQueue: () => <div data-testid="steward-failure-queue">queue</div>,
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ rowData }: { rowData: any[] }) => (
    <div data-testid="grid">{rowData.length} legacy rows</div>
  ),
}));

vi.mock('@/components/gridDeleteColumn', () => ({
  gridDeleteColumn: () => ({ headerName: 'del' }),
}));

describe('AdminMappingsPage', () => {
  beforeEach(() => {
    searchString = '';
    apiGetMock.mockReset();
  });

  function renderPage() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <AdminMappingsPage />
      </QueryClientProvider>
    );
  }

  it('mounts the failure-type queue and shows empty legacy D-0002 table', async () => {
    apiGetMock.mockImplementation(async (path: string) => {
      if (path === '/api/v1/mappings/queue') return [];
      throw new Error(`unexpected ${path}`);
    });
    renderPage();
    expect(screen.getByTestId('steward-failure-queue')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('legacy-mapping-queue-empty')).toBeInTheDocument());
  });

  it('keeps import_job_id as a deep-link to the existing DSI engine', async () => {
    searchString = 'import_job_id=501';
    apiGetMock.mockImplementation(async (path: string) => {
      if (path === '/api/v1/mappings/queue') return [];
      throw new Error(`unexpected ${path}`);
    });
    renderPage();
    await waitFor(() => expect(screen.getByTestId('dsi-job-filter-banner')).toBeInTheDocument());
    expect(screen.getByTestId('dsi-open-import-resolution')).toHaveAttribute('href', '/admin/imports?job=501');
    expect(screen.getByTestId('steward-failure-queue')).toBeInTheDocument();
  });
});
