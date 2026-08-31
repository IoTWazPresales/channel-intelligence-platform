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
    {
      id: 30,
      slug: 'distributor_inventory',
      display_name: 'Distributor sales & inventory',
      description: 'Distributor sell-out and inventory snapshots',
      requires_provider: true,
      accepted_file_types: ['.csv', '.xlsx'],
      required_fields: ['distributor_token', 'product_identifier'],
      optional_fields: ['quantity_sold', 'transaction_date'],
      pipeline_ready: true,
      destructive_apply_requires_confirm: true,
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
  dsiSources: [{ id: 5, code: 'distributor_inventory', name: 'Distributor feed', import_template_slug: 'distributor_inventory' }] as any[],
  // Row results for historical_lineup validate job (job 50) — override per test.
  hlValidateJobRows: [] as any[],
  // Lineup lines for apply jobs — override per test.
  lineupLines: [] as any[],
  // Historical lineup validate job detail with source_columns (for mapping review tests)
  hlValidateJobDetail: {
    id: 50,
    status: 'completed_with_errors',
    stage: 'validated',
    file_name: 'lineup.xlsx',
    error_summary: '5 rows require attention',
    template_slug: 'historical_lineup',
    import_mode: 'validate',
    field_mapping: {
      NB: { model_raw: 'Model Name', sku_raw: 'Part Number', quantity_units: 'Qty' },
    },
    inferred_schema: {
      selected_sheet_details: [
        {
          sheet_name: 'NB',
          header_row_number: 4,
          mapped_fields: ['model_raw', 'quantity_units', 'sku_raw'],
          source_columns: ['Product Line', 'Country', 'Customer', 'Model Name', 'Part Number', 'Qty'],
          column_samples: {
            Customer: ['CUST-01', 'CUST-02'],
            'Model Name': ['Widget Pro'],
            'Part Number': ['PN-99'],
            Qty: ['10', '12'],
          },
          row_count: 10,
          mapping_confidence: 0.35,
        },
      ],
    },
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
  initPmColumnDrafts: () => [],
  pmDraftsToApiColumns: () => [],
  sortPmFieldDefinitions: (defs: any[]) => defs,
  pmColumnsToTargetDraft: () => ({}),
  pmColumnsToDispositionDraft: () => ({}),
  applyPmTargetDraft: (prev: any) => prev,
  applyPmDispositionDraft: (prev: any) => prev,
}));

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    apiGet: vi.fn(async (url: string) => {
      if (url === '/api/v1/imports/templates') return mockState.templates;
      if (
        url === '/api/v1/imports/jobs' ||
        url === '/api/v1/imports/jobs?limit=100' ||
        url === '/api/v1/imports/jobs?include_archived=true&limit=100'
      ) {
        return { items: [], total: 0, limit: 100, offset: 0, has_more: false };
      }
      if (url.startsWith('/api/v1/imports/sources')) {
        if (url.includes('historical_lineup')) return mockState.hlSources ?? [];
        if (url.includes('distributor_inventory')) return mockState.dsiSources ?? [];
        return [];
      }
      if (url === '/api/v1/imports/jobs/42') return mockState.jobDetail;
      if (url === '/api/v1/imports/jobs/42/rows') return mockState.jobRows;
      if (url === '/api/v1/imports/jobs/50') return mockState.hlValidateJobDetail;
      if (url === '/api/v1/imports/jobs/50/rows') return mockState.hlValidateJobRows;
      if (url.match(/\/api\/v1\/imports\/jobs\/\d+\/lineup-lines$/)) return mockState.lineupLines;
      if (url === '/api/v1/imports/jobs/99') return mockState.pmJobDetail;
      if (url === '/api/v1/imports/jobs/99/rows') return [];
      if (url.match(/\/api\/v1\/imports\/jobs\/\d+\/rows$/)) return [];
      if (url.match(/\/api\/v1\/imports\/jobs\/\d+$/)) return null;
      return [];
    }),
    apiUrl: (path: string) => path,
    readFetchError: async () => 'error',
    safeDisplayError: () => 'error',
  };
});

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

  it('resumes PM wizard for product_master job revisit (no read-only deferred alert)', async () => {
    searchString = 'job=99';
    renderPage();
    expect(screen.queryByText(/Viewing previous Product Master job/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Full PM revisit is not yet supported/i)).not.toBeInTheDocument();
    expect(await screen.findByText('Commit to catalog')).toBeInTheDocument();
    expect(screen.queryByText('unknown_product')).not.toBeInTheDocument();
  });

  it('does not activate revisit mode when both ?template= and ?job= are in the URL', async () => {
    searchString = 'job=42&template=customer_master';
    renderPage();
    // Page header is always rendered immediately — use it as a stable anchor
    expect(await screen.findByText('Import Center')).toBeInTheDocument();
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

describe('AdminImportsPage historical_lineup mapping review panel', () => {
  // VALIDATE_JOB id=50 matches mockState.hlValidateJobDetail, which has source_columns
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
    mockState.hlValidateJobDetail = {
      id: 50,
      status: 'completed_with_errors',
      stage: 'validated',
      file_name: 'lineup.xlsx',
      error_summary: '5 rows require attention',
      template_slug: 'historical_lineup',
      import_mode: 'validate',
      field_mapping: {
        NB: { model_raw: 'Model Name', sku_raw: 'Part Number', quantity_units: 'Qty' },
      },
      inferred_schema: {
        selected_sheet_details: [
          {
            sheet_name: 'NB',
            header_row_number: 4,
            mapped_fields: ['model_raw', 'quantity_units', 'sku_raw'],
            source_columns: ['Product Line', 'Country', 'Customer', 'Model Name', 'Part Number', 'Qty'],
            column_samples: {
              Customer: ['CUST-01', 'CUST-02'],
              'Model Name': ['Widget Pro'],
              'Part Number': ['PN-99'],
              Qty: ['10', '12'],
            },
            row_count: 10,
            mapping_confidence: 0.35,
          },
        ],
      },
    } as any;
    vi.restoreAllMocks();
  });

  async function navigateToUploadStep(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByText('Historical Lineup'));
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    await screen.findByRole('button', { name: /Choose file/i });
  }

  const xlsxFile = () =>
    new File(['dummy'], 'lineup.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });

  it('mapping review panel is absent before validate completes', async () => {
    // No validate job yet — render page without uploading anything
    const { user } = renderPage();
    await navigateToUploadStep(user);
    // Panel toggle button should not exist yet
    expect(screen.queryByText(/Column mapping review/i)).not.toBeInTheDocument();
  });

  it('mapping review panel appears and shows source columns after validate', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => VALIDATE_JOB } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    expect(await screen.findByText(/Column mapping review/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Show \/ edit/i }));

    expect(await screen.findByTestId('hl-map-Customer')).toBeInTheDocument();
    expect(screen.getByTestId('hl-map-Model Name')).toBeInTheDocument();
  });

  it('mapping review panel renders column samples, required-group chips, and blocking errors', async () => {
    mockState.hlValidateJobDetail = {
      ...mockState.hlValidateJobDetail,
      field_mapping: { NB: { quantity_units: 'Qty' } },
      inferred_schema: {
        selected_sheet_details: [
          {
            sheet_name: 'NB',
            header_row_number: 4,
            mapped_fields: ['quantity_units'],
            source_columns: ['Customer', 'Qty'],
            column_samples: { Customer: ['CUST-01'], Qty: ['10'] },
            row_count: 1,
            mapping_confidence: 0.1,
          },
        ],
      },
    };

    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => VALIDATE_JOB } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    await screen.findByText(/Column mapping review/i);
    await user.click(screen.getByRole('button', { name: /Show \/ edit/i }));

    expect(await screen.findByTestId('hl-samples-Customer')).toHaveTextContent('CUST-01');
    expect(screen.getByTestId('hl-samples-Qty')).toHaveTextContent('10');
    expect(screen.getByText(/Product identity: needs mapping/i)).toBeInTheDocument();
    expect(screen.getByText(/Fix mapping before validating/i)).toBeInTheDocument();
    expect(screen.getByText(/Map at least one column to product identity/i)).toBeInTheDocument();
  });

  it('re-validate with corrections sends mapping_override in FormData', async () => {
    const capturedBodies: FormData[] = [];
    global.fetch = vi.fn().mockImplementation(async (_url: string, opts: RequestInit) => {
      if (opts?.body instanceof FormData) capturedBodies.push(opts.body as FormData);
      return { ok: true, json: async () => VALIDATE_JOB } as Response;
    });

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    await screen.findByText(/Column mapping review/i);
    await user.click(screen.getByRole('button', { name: /Show \/ edit/i }));

    // Map previously-unmapped Customer column → customer_token (creates override delta).
    await user.click(await screen.findByTestId('hl-map-Customer'));
    const option = await screen.findByRole('option', { name: /Customer \(customer_token\)/i });
    await user.click(option);

    const revalidateBtn = await screen.findByRole('button', { name: /Re-validate with corrections/i });
    await user.click(revalidateBtn);

    await waitFor(() => {
      expect(capturedBodies.length).toBeGreaterThanOrEqual(2);
    });
    const revalidateBody = capturedBodies[capturedBodies.length - 1];
    expect(revalidateBody.get('mapping_override')).toBeTruthy();
    const override = JSON.parse(revalidateBody.get('mapping_override') as string) as Record<
      string,
      Record<string, string>
    >;
    expect(override.NB?.customer_token).toBe('Customer');
  });

  it('apply with edits sends mapping_override in FormData', async () => {
    const capturedBodies: FormData[] = [];
    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => VALIDATE_JOB } as any)
      .mockImplementation(async (_url: string, opts: RequestInit) => {
        if (opts?.body instanceof FormData) capturedBodies.push(opts.body as FormData);
        return { ok: true, json: async () => APPLY_JOB } as Response;
      });

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    await screen.findByText(/Column mapping review/i);
    await user.click(screen.getByRole('button', { name: /Show \/ edit/i }));

    await user.click(await screen.findByTestId('hl-map-Customer'));
    const option = await screen.findByRole('option', { name: /Customer \(customer_token\)/i });
    await user.click(option);

    const applyBtn = await screen.findByRole('button', { name: /Apply validated file/i });
    await user.click(applyBtn);

    await waitFor(() => {
      expect(capturedBodies.length).toBeGreaterThan(0);
    });
    const applyBody = capturedBodies[0];
    expect(applyBody.get('mapping_override')).toBeTruthy();
    expect(applyBody.get('import_mode')).toBe('apply');
  });

  it('start over clears the mapping review panel', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => VALIDATE_JOB } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    await screen.findByText(/Column mapping review/i);

    // Click Start over
    await user.click(screen.getByRole('button', { name: /Start over/i }));

    // Panel should be gone
    expect(screen.queryByText(/Column mapping review/i)).not.toBeInTheDocument();
  });
});

describe('AdminImportsPage Phase 3B — mapping review label clarity', () => {
  // Use job 50 so hlValidateJobDetail is returned and the mapping review panel appears.
  const VALIDATE_JOB = { id: 50, status: 'completed_with_errors', stage: 'validated', import_mode: 'validate', template_slug: 'historical_lineup' };

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

  async function navigateToUploadStep(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByText('Historical Lineup'));
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    await screen.findByRole('button', { name: /Choose file/i });
  }

  const xlsxFile = () =>
    new File(['dummy'], 'lineup.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });

  it('mapping review shows "Product identity (SKU)" label not bare "SKU"', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => VALIDATE_JOB } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    await screen.findByText(/Column mapping review/i);
    await user.click(screen.getByRole('button', { name: /Show \/ edit/i }));

    // Header-centric panel: sku_raw target label appears on the mapped Part Number chip.
    expect(await screen.findByText(/Product identity \(SKU\) \(sku_raw\)/)).toBeInTheDocument();
    expect(screen.queryAllByText(/^SKU$/)).toHaveLength(0);
  });

  it('mapping review shows "Base unit (descriptor)" as a target option', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => VALIDATE_JOB } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    await screen.findByText(/Column mapping review/i);
    await user.click(screen.getByRole('button', { name: /Show \/ edit/i }));

    await user.click(await screen.findByTestId('hl-map-Customer'));
    expect(
      await screen.findByRole('option', { name: /Base unit \(descriptor\) \(base_unit_raw\)/i })
    ).toBeInTheDocument();
  });

  it('regression: sku_raw stays unmapped when field_mapping has no sku_raw', async () => {
    // Header-centric: base_unit_raw claims Base Unit; sku_raw must not appear as a mapped chip.
    const savedMapping = mockState.hlValidateJobDetail.field_mapping;
    mockState.hlValidateJobDetail = {
      ...mockState.hlValidateJobDetail,
      field_mapping: {
        NB: {
          customer_token: 'Customer',
          part_number_raw: 'Part Number',
          model_raw: 'Model name',
          base_unit_raw: 'Base Unit',
          quantity_units: 'Qty',
          // sku_raw intentionally absent — no SKU column in this workbook
        },
      },
      inferred_schema: {
        selected_sheet_details: [
          {
            sheet_name: 'NB',
            header_row_number: 4,
            mapped_fields: ['model_raw', 'quantity_units', 'part_number_raw', 'base_unit_raw', 'customer_token'],
            source_columns: [
              'Product Line',
              'Country',
              'Customer',
              'Model name',
              'Part Number',
              'Base Unit',
              'Qty',
            ],
            row_count: 10,
            mapping_confidence: 0.35,
          },
        ],
      },
    };

    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => VALIDATE_JOB } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    await screen.findByText(/Column mapping review/i);
    await user.click(screen.getByRole('button', { name: /Show \/ edit/i }));

    expect(await screen.findByText(/Base unit \(descriptor\) \(base_unit_raw\)/)).toBeInTheDocument();
    expect(screen.queryByText(/Product identity \(SKU\) \(sku_raw\)/)).not.toBeInTheDocument();

    mockState.hlValidateJobDetail.field_mapping = savedMapping;
  });
});

describe('AdminImportsPage Phase 3B — diagnostic summary chips', () => {
  // Use job 42 so previewRows returns mockState.jobRows (has unknown_product code).
  const VALIDATE_JOB_42 = { id: 42, status: 'completed_with_errors', stage: 'validated', import_mode: 'validate', template_slug: 'historical_lineup' };

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

  async function navigateToUploadStep(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByText('Historical Lineup'));
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    await screen.findByRole('button', { name: /Choose file/i });
  }

  const xlsxFile = () =>
    new File(['dummy'], 'lineup.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });

  it('diagnostic summary chips appear with code counts after validate returns rows', async () => {
    // Upload returns job 42; previewRows for job 42 → mockState.jobRows (unknown_product row).
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => VALIDATE_JOB_42 } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    // Summary container should appear
    const summary = await screen.findByTestId('diagnostic-summary');
    expect(summary).toBeInTheDocument();

    // At least one chip should contain the code from mockState.jobRows
    expect(summary).toHaveTextContent('unknown_product');
    expect(summary).toHaveTextContent('(1)');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Phase 3C — Import Quality Review panel
// ─────────────────────────────────────────────────────────────────────────────

describe('AdminImportsPage Phase 3C — quality review panel', () => {
  const VALIDATE_JOB_50 = {
    id: 50,
    status: 'completed_with_errors',
    stage: 'validated',
    import_mode: 'validate',
    template_slug: 'historical_lineup',
  };
  const APPLY_JOB_51 = {
    id: 51,
    status: 'completed',
    stage: 'loaded',
    import_mode: 'apply',
    template_slug: 'historical_lineup',
  };

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
    searchString = '';
    mockRouterReplace.mockReset();
    mockState.templates = [mockState.templates[0], mockState.historicalLineupTemplate];
    mockState.hlSources = [];
    mockState.hlValidateJobRows = [];
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
    mockState.hlValidateJobRows = [];
    vi.restoreAllMocks();
  });

  async function navigateToUploadStep(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByText('Historical Lineup'));
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    await screen.findByRole('button', { name: /Choose file/i });
  }

  const xlsxFile = () =>
    new File(['dummy'], 'lineup.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });

  it('quality review panel shows apply-ready badge when no blocking errors exist', async () => {
    mockState.hlValidateJobRows = [
      { id: 1, row_number: 2, severity: 'info', code: 'historical_lineup_row_ok', message: 'row accepted', raw_payload: {} },
      { id: 2, row_number: 3, severity: 'info', code: 'historical_lineup_row_ok', message: 'row accepted', raw_payload: {} },
      { id: 3, row_number: 4, severity: 'warning', code: 'partial_margin_stack', message: 'partial margin', raw_payload: {} },
    ];

    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => VALIDATE_JOB_50 } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    const badge = await screen.findByTestId('quality-review-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent(/Apply ready/i);
    // Must NOT say "blocking"
    expect(badge.textContent).not.toMatch(/blocking/i);
  });

  it('quality review panel groups unknown customer tokens with row counts', async () => {
    mockState.hlValidateJobRows = [
      {
        id: 1, row_number: 2, severity: 'warning', code: 'unknown_customer',
        message: 'unknown_customer', raw_payload: { customer_token: 'ABC Corp' },
      },
      {
        id: 2, row_number: 3, severity: 'warning', code: 'unknown_customer',
        message: 'unknown_customer', raw_payload: { customer_token: 'ABC Corp' },
      },
      {
        id: 3, row_number: 4, severity: 'warning', code: 'unknown_customer',
        message: 'unknown_customer', raw_payload: { customer_token: 'XYZ Ltd' },
      },
    ];

    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => VALIDATE_JOB_50 } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    const panel = await screen.findByTestId('quality-review-panel');
    expect(panel).toBeInTheDocument();
    // Grouped tokens should appear as chips
    expect(panel).toHaveTextContent('ABC Corp (2)');
    expect(panel).toHaveTextContent('XYZ Ltd (1)');
    // Distinct token count should be mentioned
    expect(panel).toHaveTextContent(/3 rows/i);
  });

  it('apply button shows inline confirmation when unresolved customers exist, then applies on confirm', async () => {
    mockState.hlValidateJobRows = [
      {
        id: 1, row_number: 2, severity: 'warning', code: 'unknown_customer',
        message: 'unknown_customer', raw_payload: { customer_token: 'UNKNOWN CORP' },
      },
    ];

    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => VALIDATE_JOB_50 } as any)
      .mockResolvedValueOnce({ ok: true, json: async () => APPLY_JOB_51 } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    // Apply button should be enabled (unknown_customer is soft warning, not hard block)
    const applyBtn = await screen.findByRole('button', { name: /Apply validated file/i });
    expect(applyBtn).not.toBeDisabled();

    // Click Apply — confirmation alert should appear instead of mutating immediately
    await user.click(applyBtn);
    const confirmAlert = await screen.findByTestId('apply-confirm-alert');
    expect(confirmAlert).toBeInTheDocument();
    expect(confirmAlert).toHaveTextContent(/1 row/i);

    // Click "Apply anyway" — apply mutation should fire and success alert should appear
    await user.click(screen.getByRole('button', { name: /Apply anyway/i }));

    await waitFor(() => {
      expect(screen.queryByTestId('apply-confirm-alert')).not.toBeInTheDocument();
    });
    const successAlert = await screen.findByTestId('apply-success-alert');
    expect(successAlert).toHaveTextContent(`#${APPLY_JOB_51.id}`);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Sub-pass A — Loaded lineup records view
// ─────────────────────────────────────────────────────────────────────────────

describe('AdminImportsPage Sub-pass A — loaded lineup records', () => {
  const VALIDATE_JOB_50 = {
    id: 50, status: 'completed_with_errors', stage: 'validated',
    import_mode: 'validate', template_slug: 'historical_lineup',
  };
  const APPLY_JOB_51 = {
    id: 51, status: 'completed', stage: 'loaded',
    import_mode: 'apply', template_slug: 'historical_lineup',
  };

  const SAMPLE_LINES = [
    {
      id: 1, header_id: 10, source_row_number: 5,
      product_id: 42, sku_raw: null, part_number_raw: 'PART-001',
      model_raw: 'Model X', base_unit_raw: 'NB', quantity_units: 12,
      msrp_local: 999.0, promo_price_local: 899.0, dap_local: 850.0,
      disti_margin_pct: 8.5, period_label: '2026-Q2', header_customer_id: null, sheet_name: 'NB',
      diagnostic_codes: [], customer_token: 'ACME Corp',
    },
  ];

  const LINES_WITH_UNRESOLVED = [
    {
      id: 1, header_id: 10, source_row_number: 5,
      product_id: 42, sku_raw: null, part_number_raw: 'PART-001',
      model_raw: 'Model X', base_unit_raw: 'NB', quantity_units: 12,
      msrp_local: 999.0, promo_price_local: 899.0, dap_local: 850.0,
      disti_margin_pct: 8.5, period_label: '2026-Q2', header_customer_id: null, sheet_name: 'NB',
      diagnostic_codes: ['unknown_customer'], customer_token: 'UNKNOWN-CUST',
    },
    {
      id: 2, header_id: 10, source_row_number: 6,
      product_id: null, sku_raw: null, part_number_raw: 'PART-002',
      model_raw: 'Model Y', base_unit_raw: 'NB', quantity_units: 5,
      msrp_local: 799.0, promo_price_local: null, dap_local: null,
      disti_margin_pct: null, period_label: '2026-Q2', header_customer_id: null, sheet_name: 'NB',
      diagnostic_codes: ['unknown_customer', 'unknown_product'], customer_token: 'UNKNOWN-CUST',
    },
    {
      id: 3, header_id: 10, source_row_number: 7,
      product_id: 10, sku_raw: null, part_number_raw: 'PART-003',
      model_raw: 'Model Z', base_unit_raw: 'NB', quantity_units: 3,
      msrp_local: 599.0, promo_price_local: null, dap_local: null,
      disti_margin_pct: null, period_label: '2026-Q2', header_customer_id: 5, sheet_name: 'NB',
      // Token name deliberately distinct from "UNKNOWN-CUST" to avoid substring collision in assertions.
      diagnostic_codes: [], customer_token: 'MATCHED-ACME',
    },
  ];

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
    searchString = '';
    mockRouterReplace.mockReset();
    mockState.templates = [mockState.templates[0], mockState.historicalLineupTemplate];
    mockState.hlSources = [];
    mockState.hlValidateJobRows = [];
    mockState.lineupLines = [];
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
    mockState.hlValidateJobRows = [];
    mockState.lineupLines = [];
    vi.restoreAllMocks();
  });

  async function navigateToUploadStep(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByText('Historical Lineup'));
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    await screen.findByRole('button', { name: /Choose file/i });
  }

  const xlsxFile = () =>
    new File(['dummy'], 'lineup.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });

  it('loaded lineup section appears after apply and shows line data', async () => {
    mockState.lineupLines = SAMPLE_LINES;

    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => VALIDATE_JOB_50 } as any)
      .mockResolvedValueOnce({ ok: true, json: async () => APPLY_JOB_51 } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    // Validate first
    await screen.findByRole('button', { name: /Apply validated file/i });

    // Click Apply — confirmation not shown (no unknown customers)
    await user.click(screen.getByRole('button', { name: /Apply validated file/i }));

    // Loaded lineup section must appear
    const section = await screen.findByTestId('loaded-lineup-section');
    expect(section).toBeInTheDocument();
    // Should show line data
    expect(section).toHaveTextContent('PART-001');
    expect(section).toHaveTextContent('Model X');
  });

  it('loaded lineup section shows empty state when no lines returned', async () => {
    mockState.lineupLines = [];

    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => VALIDATE_JOB_50 } as any)
      .mockResolvedValueOnce({ ok: true, json: async () => APPLY_JOB_51 } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    await screen.findByRole('button', { name: /Apply validated file/i });
    await user.click(screen.getByRole('button', { name: /Apply validated file/i }));

    // Section still appears but shows empty state text
    const section = await screen.findByTestId('loaded-lineup-section');
    expect(section).toBeInTheDocument();
    expect(section).toHaveTextContent(/No lineup lines loaded/i);
  });

  it('View apply job link appears in success alert with correct job id', async () => {
    mockState.lineupLines = SAMPLE_LINES;

    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => VALIDATE_JOB_50 } as any)
      .mockResolvedValueOnce({ ok: true, json: async () => APPLY_JOB_51 } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    await screen.findByRole('button', { name: /Apply validated file/i });
    await user.click(screen.getByRole('button', { name: /Apply validated file/i }));

    const link = await screen.findByTestId('view-apply-job-link');
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', `/admin/imports?job=${APPLY_JOB_51.id}`);
  });

  // ── Sub-pass B — unresolved customer token audit surface (read-only) ──────

  it('unresolved customer token chips appear in loaded lineup section when lines have unknown_customer', async () => {
    mockState.lineupLines = LINES_WITH_UNRESOLVED;

    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => VALIDATE_JOB_50 } as any)
      .mockResolvedValueOnce({ ok: true, json: async () => APPLY_JOB_51 } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    await screen.findByRole('button', { name: /Apply validated file/i });
    await user.click(screen.getByRole('button', { name: /Apply validated file/i }));

    const tokenSection = await screen.findByTestId('lineup-unresolved-tokens');
    expect(tokenSection).toBeInTheDocument();
    // UNKNOWN-CUST appears on 2 rows — chip must show count
    expect(tokenSection).toHaveTextContent('UNKNOWN-CUST (2)');
    // MATCHED-ACME has no unknown_customer diagnostic — must NOT appear as a chip.
    expect(tokenSection).not.toHaveTextContent('MATCHED-ACME');
    // Summary line should mention distinct count
    expect(tokenSection).toHaveTextContent(/1 distinct/i);
    expect(tokenSection).toHaveTextContent(/2 rows/i);
  });

  it('unresolved customer token section is absent when all customers are resolved', async () => {
    // SAMPLE_LINES has diagnostic_codes: [] — no unknown_customer
    mockState.lineupLines = SAMPLE_LINES;

    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => VALIDATE_JOB_50 } as any)
      .mockResolvedValueOnce({ ok: true, json: async () => APPLY_JOB_51 } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    await screen.findByRole('button', { name: /Apply validated file/i });
    await user.click(screen.getByRole('button', { name: /Apply validated file/i }));

    // Loaded lineup section must be present (lines exist) but no unresolved-token sub-section
    await screen.findByTestId('loaded-lineup-section');
    expect(screen.queryByTestId('lineup-unresolved-tokens')).not.toBeInTheDocument();
  });
});

describe('AdminImportsPage distributor sales & inventory guidance', () => {
  function renderPage() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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
    searchString = '';
    mockRouterReplace.mockReset();
    if (!mockState.templates.some((t: { slug?: string }) => t.slug === 'distributor_inventory')) {
      mockState.templates.push({
        id: 30,
        slug: 'distributor_inventory',
        display_name: 'Distributor sales & inventory',
        description: 'Distributor sell-out and inventory snapshots',
        requires_provider: true,
        accepted_file_types: ['.csv', '.xlsx'],
        required_fields: ['distributor_token', 'product_identifier'],
        optional_fields: ['quantity_sold', 'transaction_date'],
        pipeline_ready: true,
        destructive_apply_requires_confirm: true,
      });
    }
  });

  it('shows DSI contract, unit price ex VAT, shipping preservation, and customer staging copy', async () => {
    const { user } = renderPage();
    await user.click(await screen.findByText('Distributor sales & inventory'));
    const prov = await screen.findByLabelText(/Data provider/i);
    await user.click(prov);
    await user.click(await screen.findByRole('option', { name: /Distributor feed/i }));
    await user.click(await screen.findByRole('button', { name: /^Next$/i }));
    expect(screen.getByTestId('dsi-contract-copy')).toBeInTheDocument();
    expect(screen.getByTestId('dsi-unit-price-copy')).toHaveTextContent(/ex VAT/i);
    expect(screen.getByTestId('dsi-shipping-copy')).toHaveTextContent(/Inbound shipments/i);
    expect(screen.getByTestId('dsi-customer-copy')).toHaveTextContent(/not/i);
    expect(screen.getByTestId('dsi-customer-copy')).toHaveTextContent(/auto-created/i);
  });
});
