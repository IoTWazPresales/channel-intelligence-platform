import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import AdminImportsPage from './page';

let searchString = '';

const mockState = vi.hoisted(() => ({
  templates: [
    {
      id: 10,
      slug: 'customer_master',
      display_name: 'Customer master',
      description: 'Customer account master import',
      requires_provider: true,
      accepted_file_types: ['.csv', '.xlsx'],
      required_fields: ['customer_code', 'customer_name'],
      optional_fields: ['region_code', 'channel_code'],
      pipeline_ready: true,
      destructive_apply_requires_confirm: false,
    },
    {
      id: 11,
      slug: 'customer_channel_mapping',
      display_name: 'Customer/channel mapping',
      description: 'Deferred scaffold',
      requires_provider: true,
      accepted_file_types: ['.csv', '.xlsx'],
      required_fields: ['customer_code', 'channel_code'],
      optional_fields: ['region_code'],
      pipeline_ready: false,
      destructive_apply_requires_confirm: false,
    },
  ] as any[],
  jobDetail: {
    id: 42,
    status: 'completed_with_errors',
    stage: 'validated',
    file_name: 'lineup.xlsx',
    error_summary: null,
    template_slug: 'historical_lineup',
    import_mode: 'validate',
  } as any,
  jobRows: [
    { id: 1, row_number: 2, severity: 'error', code: 'unknown_product', message: 'No product matched for row 2' },
  ] as any[],
  pmJobDetail: {
    id: 99,
    status: 'pm_committed',
    stage: 'pm_committed',
    file_name: 'products.csv',
    error_summary: null,
    template_slug: 'product_master',
    import_mode: 'validate',
  } as any,
}));

const mockRouterReplace = vi.fn();

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(searchString),
  useRouter: () => ({ replace: mockRouterReplace, push: vi.fn() }),
}));

vi.mock('@/components/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <div>{title}</div>,
}));

vi.mock('@/components/ModuleDataSection', () => ({
  ModuleDataSection: ({ children }: any) => <>{children}</>,
}));

vi.mock('@/components/ModuleGridToolbar', () => ({
  ModuleGridToolbar: () => <div>toolbar</div>,
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: () => <div>grid</div>,
}));

vi.mock('./PmImportProgressPanel', () => ({
  PmImportProgressPanel: () => null,
}));

vi.mock('./pmMappingHelpers', () => ({
  PM_GROUP_LABEL: {},
  initPmColumnDrafts: () => [],
  pmDraftsToApiColumns: () => [],
  sortPmFieldDefinitions: (defs: any[]) => defs,
}));

vi.mock('./pmMappingTargetOptions', () => ({
  buildTargetUsageMap: () => ({}),
  enrichPmMappingTargets: () => [],
  filterAndSortPmTargets: (opts: any[]) => opts,
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (url === '/api/v1/imports/templates') return mockState.templates;
    if (url === '/api/v1/imports/jobs') return [];
    if (url.startsWith('/api/v1/imports/sources')) return [];
    if (url === '/api/v1/imports/jobs/42') return mockState.jobDetail;
    if (url === '/api/v1/imports/jobs/42/rows') return mockState.jobRows;
    if (url === '/api/v1/imports/jobs/99') return mockState.pmJobDetail;
    if (url === '/api/v1/imports/jobs/99/rows') return [];
    if (url.match(/\/api\/v1\/imports\/jobs\/\d+\/rows$/)) return [];
    if (url.match(/\/api\/v1\/imports\/jobs\/\d+$/)) return null;
    return [];
  }),
  apiUrl: (path: string) => path,
  readFetchError: async () => 'error',
  safeDisplayError: () => 'error',
}));

vi.mock('@/lib/queryError', () => ({ toQueryError: () => null }));

describe('AdminImportsPage deferred template visibility', () => {
  function renderPage() {
    const qc = new QueryClient();
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <AdminImportsPage />
      </QueryClientProvider>
    );
  }

  beforeEach(() => {
    searchString = '';
    mockRouterReplace.mockReset();
  });

  it('keeps customer_master visible and hides customer_channel_mapping card', async () => {
    renderPage();
    expect(await screen.findByText('Customer master')).toBeInTheDocument();
    expect(screen.queryByText('Customer/channel mapping')).not.toBeInTheDocument();
  });

  it('ignores forced template query when it targets deferred channel mapping', async () => {
    searchString = 'template=customer_channel_mapping';
    renderPage();
    expect(await screen.findByText('Customer master')).toBeInTheDocument();
    expect(screen.queryByText(/Selected type:/)).not.toBeInTheDocument();
  });
});

describe('AdminImportsPage job revisit via ?job= URL param', () => {
  function renderPage() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <AdminImportsPage />
      </QueryClientProvider>
    );
  }

  beforeEach(() => {
    searchString = '';
    mockRouterReplace.mockReset();
  });

  it('renders the revisit banner and diagnostic rows when ?job=42 is in the URL', async () => {
    searchString = 'job=42';
    renderPage();
    // Revisit info banner should appear
    expect(await screen.findByTestId('revisit-banner')).toBeInTheDocument();
    expect(screen.getByTestId('revisit-banner')).toHaveTextContent('Viewing diagnostics for job');
    expect(screen.getByTestId('revisit-banner')).toHaveTextContent('#42');
    // Diagnostic row code from mock job rows should be rendered in the table
    expect(await screen.findByText('unknown_product')).toBeInTheDocument();
  });

  it('shows PM deferred alert and does not crash for a product_master job revisit', async () => {
    searchString = 'job=99';
    renderPage();
    expect(await screen.findByText(/Viewing previous Product Master job/i)).toBeInTheDocument();
    expect(screen.getByText(/Full PM revisit is not yet supported/i)).toBeInTheDocument();
    // Should not throw or show an error
    expect(screen.queryByText('unknown_product')).not.toBeInTheDocument();
  });

  it('does not activate revisit mode when both ?template= and ?job= are in the URL', async () => {
    searchString = 'job=42&template=customer_master';
    renderPage();
    // Page header is always rendered immediately — use it as a stable anchor
    expect(await screen.findByText('Data & imports')).toBeInTheDocument();
    // Template param takes priority over job param; revisit banner must NOT appear
    expect(screen.queryByTestId('revisit-banner')).not.toBeInTheDocument();
  });
});
