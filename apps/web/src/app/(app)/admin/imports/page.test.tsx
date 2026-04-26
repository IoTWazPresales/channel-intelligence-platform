import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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
  historicalLineupTemplate: {
    id: 20,
    slug: 'historical_lineup',
    display_name: 'Historical Lineup',
    description: 'Historical lineup workbook import',
    requires_provider: false,
    accepted_file_types: ['.xlsx', '.xlsm', '.csv'],
    required_fields: [],
    optional_fields: [],
    pipeline_ready: true,
    destructive_apply_requires_confirm: false,
  } as any,
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
  // Populated in Apply button tests' beforeEach so the ?source=100 URL param resolves
  hlSources: [] as any[],
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
    if (url.startsWith('/api/v1/imports/sources')) {
      // Return HL source when requested for historical_lineup so sourceId can be set via URL param
      if (url.includes('historical_lineup')) return mockState.hlSources ?? [];
      return [];
    }
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
    vi.restoreAllMocks();
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

describe('AdminImportsPage historical_lineup Apply button post-success behavior', () => {
  const VALIDATE_JOB = { id: 50, status: 'completed_with_errors', stage: 'validated', import_mode: 'validate', template_slug: 'historical_lineup' };
  const APPLY_JOB = { id: 51, status: 'completed', stage: 'loaded', import_mode: 'apply', template_slug: 'historical_lineup' };

  function renderPage() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    return {
      user: userEvent.setup(),
      ...renderWithProviders(
        <QueryClientProvider client={qc}>
          <AdminImportsPage />
        </QueryClientProvider>
      ),
    };
  }

  beforeEach(() => {
    // No ?template= URL param — using that causes the useSearchParams mock to return new objects
    // every render, which re-fires the ?template= effect and resets activeStep back to 1 after
    // every click.  Instead we click the template card directly (step 0 → 1).
    searchString = '';
    mockRouterReplace.mockReset();
    mockState.templates = [mockState.templates[0], mockState.historicalLineupTemplate];
    mockState.hlSources = [];
  });

  afterEach(() => {
    mockState.templates = [
      {
        id: 10, slug: 'customer_master', display_name: 'Customer master',
        description: 'Customer account master import', requires_provider: true,
        accepted_file_types: ['.csv', '.xlsx'], required_fields: ['customer_code', 'customer_name'],
        optional_fields: ['region_code', 'channel_code'], pipeline_ready: true,
        destructive_apply_requires_confirm: false,
      },
      {
        id: 11, slug: 'customer_channel_mapping', display_name: 'Customer/channel mapping',
        description: 'Deferred scaffold', requires_provider: true,
        accepted_file_types: ['.csv', '.xlsx'], required_fields: ['customer_code', 'channel_code'],
        optional_fields: ['region_code'], pipeline_ready: false, destructive_apply_requires_confirm: false,
      },
    ];
    mockState.hlSources = [];
    vi.restoreAllMocks();
  });

  /**
   * Navigate from step 0 through to the upload step (step 4) for historical_lineup.
   * historical_lineup.requires_provider = false, so no source selection is needed.
   */
  async function navigateToUploadStep(user: ReturnType<typeof userEvent.setup>) {
    // Step 0: click the Historical Lineup card
    await user.click(await screen.findByText('Historical Lineup'));
    // Step 1 → 2: no provider required for historical_lineup
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    // Step 2 → 3: template details step
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    // Step 3 → 4: import mode step (locked to validate for historical_lineup)
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    // Confirm we are at the upload step
    await screen.findByRole('button', { name: /Choose file/i });
  }

  const xlsxFile = () =>
    new File(['dummy'], 'lineup.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });

  it('Apply button appears after validate succeeds and a file is present', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => VALIDATE_JOB } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);

    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    expect(await screen.findByRole('button', { name: /Apply validated file/i })).toBeInTheDocument();
  });

  it('Apply button disappears and apply success Alert appears after apply succeeds', async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => VALIDATE_JOB } as any)
      .mockResolvedValueOnce({ ok: true, json: async () => APPLY_JOB } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);

    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    const applyBtn = await screen.findByRole('button', { name: /Apply validated file/i });
    await user.click(applyBtn);

    // Apply button must disappear after apply mutation succeeds
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Apply validated file/i })).not.toBeInTheDocument();
    });

    // Apply success Alert must appear with the apply job ID
    const successAlert = await screen.findByTestId('apply-success-alert');
    expect(successAlert).toHaveTextContent(/Apply job/i);
    expect(successAlert).toHaveTextContent(`#${APPLY_JOB.id}`);
  });

  it('validate success Alert shows generic message and does not show apply Alert', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => VALIDATE_JOB } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);

    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    // Validate mode: generic "Job created" Alert with refresh button appears
    expect(await screen.findByRole('button', { name: /Refresh validation preview/i })).toBeInTheDocument();
    // Apply-specific Alert must NOT appear
    expect(screen.queryByTestId('apply-success-alert')).not.toBeInTheDocument();
  });
});
