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
}));

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => apiGetMock(...args),
  apiDelete: vi.fn(),
  apiPost: vi.fn(),
  apiUrl: (p: string) => p,
}));

vi.mock('@/components/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <div>{title}</div>,
}));

vi.mock('@/components/ModuleDataSection', () => ({
  ModuleDataSection: ({ children, isEmpty, empty, isLoading }: any) => {
    if (isLoading) return <div role="status">loading</div>;
    if (isEmpty) {
      return (
        <div>
          <div data-testid="empty-title">{empty?.title}</div>
        </div>
      );
    }
    return <>{children}</>;
  },
}));

vi.mock('@/components/ModuleGridToolbar', () => ({
  ModuleGridToolbar: () => <div>toolbar</div>,
}));

vi.mock('@/components/gridDeleteColumn', () => ({
  gridDeleteColumn: () => ({ headerName: 'del' }),
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ rowData, columnDefs }: { rowData: any[]; columnDefs: any[] }) => (
    <div data-testid="grid">
      {rowData.map((row) => (
        <div key={row.id} data-row-kind={row.entity_type != null ? 'dsi' : 'legacy'}>
          {columnDefs
            .filter((c) => c.field)
            .map((c) => (
              <span key={String(c.field)} data-field={c.field}>
                {String((row as Record<string, unknown>)[c.field as string] ?? '')}
              </span>
            ))}
        </div>
      ))}
    </div>
  ),
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

  it('shows empty title when legacy queue and no job filter', async () => {
    apiGetMock.mockImplementation(async (path: string) => {
      if (path === '/api/v1/mappings/queue') return [];
      throw new Error(`unexpected ${path}`);
    });
    renderPage();
    await waitFor(() => expect(screen.getByTestId('empty-title')).toHaveTextContent('Mapping queue is empty'));
  });

  it('loads DSI grouped candidates when import_job_id is present and legacy queue is empty', async () => {
    searchString = 'import_job_id=501';
    apiGetMock.mockImplementation(async (path: string) => {
      if (path === '/api/v1/mappings/queue') return [];
      if (path.startsWith('/api/v1/mappings/import-jobs/501/distributor-si-candidates')) {
        return {
          items: [
            {
              id: 1,
              import_job_id: 501,
              source_definition_id: 9,
              entity_type: 'customer_dealer_token',
              normalized_key: 'mystery dealer zed',
              dealer_group_token: '__blank__',
              row_count: 104,
              total_units: 10,
              total_reported_value: null,
              sample_raw_values: ['Mystery Dealer Zed'],
              suggested_entity_id: null,
              match_reason: null,
              confidence_score: null,
              status: 'needs_review',
              context: {},
              created_at: '2026-01-01T00:00:00+00:00',
              updated_at: '2026-01-01T00:00:00+00:00',
            },
          ],
          total: 1,
          skip: 0,
          limit: 100,
        };
      }
      throw new Error(`unexpected ${path}`);
    });
    renderPage();
    await waitFor(() => expect(screen.getByTestId('dsi-job-filter-banner')).toBeInTheDocument());
    await waitFor(() =>
      expect(screen.getByTestId('dsi-candidate-count')).toHaveTextContent(/1 grouped mapping candidate/)
    );
    expect(screen.getByTestId('dsi-open-import-resolution')).toHaveAttribute('href', '/admin/imports?job=501');
    expect(screen.queryByTestId('empty-title')).not.toBeInTheDocument();
  });
});
