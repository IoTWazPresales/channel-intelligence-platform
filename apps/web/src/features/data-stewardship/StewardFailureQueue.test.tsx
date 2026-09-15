import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { StewardFailureQueue } from './StewardFailureQueue';

let searchString = '';
const replaceMock = vi.fn();
const pushMock = vi.fn();
const apiGetMock = vi.fn();

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(searchString),
  usePathname: () => '/admin/mappings',
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
}));

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => apiGetMock(...args),
}));

vi.mock('@/components/ModuleDataSection', () => ({
  ModuleDataSection: ({ children, isEmpty, empty, isLoading }: any) => {
    if (isLoading) return <div role="status">loading</div>;
    if (isEmpty) {
      return <div data-testid="empty-title">{empty?.title}</div>;
    }
    return <>{children}</>;
  },
}));

vi.mock('@/components/ModuleGridToolbar', () => ({
  ModuleGridToolbar: () => <div>toolbar</div>,
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ rowData }: { rowData: any[] }) => (
    <div data-testid="steward-failure-grid">
      {rowData.map((row) => (
        <div key={row.id} data-testid={`steward-row-${row.id}`}>
          <span data-field="entity_type">{row.entity_type}</span>
          <span data-field="normalized_key">{row.normalized_key}</span>
          <span data-field="import_job_id">{row.import_job_id}</span>
          {row.steward_href ? (
            <a href={row.steward_href} data-testid={`steward-queue-open-${row.id}`}>
              Steward
            </a>
          ) : (
            <span>UNCOVERED</span>
          )}
        </div>
      ))}
    </div>
  ),
}));

vi.mock('@/features/workbench-ui/controls', () => ({
  ScopeBar: ({ chips }: { chips: { key: string; label: string }[] }) => (
    <div data-testid="steward-failure-chips">
      {chips.map((c) => (
        <span key={c.key} data-chip={c.key}>
          {c.label}
        </span>
      ))}
    </div>
  ),
}));

const payload = {
  database: 'cip',
  tenant_id: 'default',
  open_status: 'needs_review',
  groups: [
    {
      entity_type: 'product_identifier',
      label: 'DSI product identifier',
      candidate_count: 2,
      job_count: 1,
      row_count: 10,
      covered: true,
    },
    {
      entity_type: 'brand_new_token',
      label: 'brand_new_token',
      candidate_count: 1,
      job_count: 1,
      row_count: 3,
      covered: false,
    },
  ],
  items: [
    {
      id: 11,
      entity_type: 'product_identifier',
      label: 'DSI product identifier',
      normalized_key: 'sku-a',
      row_count: 8,
      total_units: 8,
      status: 'needs_review',
      import_job_id: 43,
      template_slug: 'distributor_inventory',
      file_name: 'w35.xlsx',
      job_status: 'completed_with_errors',
      steward_href: '/admin/mappings?workspace=resolve&job=43&entity_type=product_identifier&token=sku-a&candidate=11',
      covered: true,
      memory_state: 'unknown',
    },
    {
      id: 12,
      entity_type: 'brand_new_token',
      label: 'brand_new_token',
      normalized_key: 'x',
      row_count: 3,
      total_units: null,
      status: 'needs_review',
      import_job_id: 99,
      template_slug: 'future_importer',
      file_name: 'x.csv',
      job_status: 'completed',
      steward_href: null,
      covered: false,
    },
  ],
  total_candidates: 3,
  distinct_jobs: 2,
  remembered_count: 0,
  include_remembered: false,
  returned: 2,
  truncated: false,
  entity_type_filter: null,
};

describe('StewardFailureQueue', () => {
  beforeEach(() => {
    searchString = '';
    apiGetMock.mockReset();
    replaceMock.mockReset();
    pushMock.mockReset();
    apiGetMock.mockResolvedValue(payload);
  });

  function renderQueue() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <StewardFailureQueue />
      </QueryClientProvider>
    );
  }

  it('groups from API entity_type, including uncovered future types', async () => {
    renderQueue();
    await waitFor(() =>
      expect(screen.getByTestId('steward-failure-chips').querySelector('[data-chip="product_identifier"]')).toBeTruthy()
    );
    expect(screen.getByTestId('steward-failure-chips').querySelector('[data-chip="brand_new_token"]')).toBeTruthy();
    expect(screen.queryByText('Customer')).not.toBeInTheDocument();
    expect(screen.getByTestId('steward-queue-open-11')).toHaveAttribute(
      'href',
      '/admin/mappings?workspace=resolve&job=43&entity_type=product_identifier&token=sku-a&candidate=11'
    );
    expect(screen.getByTestId('steward-row-12')).toHaveTextContent('UNCOVERED');
    expect(screen.getByTestId('steward-row-11')).toHaveTextContent('43');
  });

  it('shows empty title when the queue has no candidates', async () => {
    apiGetMock.mockResolvedValue({ ...payload, groups: [], items: [], total_candidates: 0, distinct_jobs: 0, returned: 0 });
    renderQueue();
    await waitFor(() => expect(screen.getByTestId('empty-title')).toHaveTextContent('No open steward candidates'));
  });
});
