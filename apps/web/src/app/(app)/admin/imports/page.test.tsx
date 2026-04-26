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
  // Row results for historical_lineup validate job (job 50) — override per test.
  hlValidateJobRows: [] as any[],
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
    if (url === '/api/v1/imports/jobs/50') return mockState.hlValidateJobDetail;
    if (url === '/api/v1/imports/jobs/50/rows') return mockState.hlValidateJobRows;
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

    // Panel header should appear (job 50 has hlValidateJobDetail with source_columns)
    expect(await screen.findByText(/Column mapping review/i)).toBeInTheDocument();
    // Expand the panel
    await user.click(screen.getByRole('button', { name: /Show \/ edit/i }));

    // Dropdown options should include source_columns from hlValidateJobDetail
    // Opening one Select to see its options
    const selects = screen.getAllByRole('combobox');
    expect(selects.length).toBeGreaterThan(0);
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

    // Expand the panel
    await screen.findByText(/Column mapping review/i);
    await user.click(screen.getByRole('button', { name: /Show \/ edit/i }));

    // Select a column override for "Customer" (customer_token) — pick "Customer" from dropdowns
    // The combobox for customer_token is the first one (HL_MAPPING_DISPLAY_FIELDS order)
    const selects = await screen.findAllByRole('combobox');
    await user.click(selects[0]); // open first Select (Customer field)
    // Pick the first non-empty option in the listbox
    const options = await screen.findAllByRole('option');
    const realOption = options.find((o) => o.textContent && o.textContent !== '— use detected —');
    if (realOption) await user.click(realOption);

    // Re-validate button should appear (edit was made)
    const revalidateBtn = await screen.findByRole('button', { name: /Re-validate with corrections/i });
    await user.click(revalidateBtn);

    // The second fetch call (re-validate) should include mapping_override
    await waitFor(() => {
      expect(capturedBodies.length).toBeGreaterThanOrEqual(2);
    });
    const revalidateBody = capturedBodies[capturedBodies.length - 1];
    expect(revalidateBody.get('mapping_override')).toBeTruthy();
    const override = JSON.parse(revalidateBody.get('mapping_override') as string) as Record<string, unknown>;
    expect(typeof override).toBe('object');
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

    // Expand panel and make an edit
    await screen.findByText(/Column mapping review/i);
    await user.click(screen.getByRole('button', { name: /Show \/ edit/i }));

    const selects = await screen.findAllByRole('combobox');
    await user.click(selects[0]);
    const options = await screen.findAllByRole('option');
    const realOption = options.find((o) => o.textContent && o.textContent !== '— use detected —');
    if (realOption) await user.click(realOption);

    // Click Apply — should include mapping_override
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

    // Open the mapping review panel
    await screen.findByText(/Column mapping review/i);
    await user.click(screen.getByRole('button', { name: /Show \/ edit/i }));

    // New label must be present
    expect(await screen.findByText('Product identity (SKU)')).toBeInTheDocument();
    // Old bare label must NOT exist as a table cell (it was renamed)
    const cells = screen.queryAllByText(/^SKU$/);
    expect(cells).toHaveLength(0);
  });

  it('mapping review shows "Base unit (descriptor)" row', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => VALIDATE_JOB } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    await screen.findByText(/Column mapping review/i);
    await user.click(screen.getByRole('button', { name: /Show \/ edit/i }));

    expect(await screen.findByText('Base unit (descriptor)')).toBeInTheDocument();
  });

  it('regression: Product identity (SKU) shows not-detected when field_mapping has no sku_raw', async () => {
    // This test would have FAILED before the claimed_sources fix: both sku_raw and
    // base_unit_raw would have shown 'Base Unit', replicating the manual test failure.
    // Temporarily override hlValidateJobDetail to use a correct backend mapping
    // (no sku_raw key — only base_unit_raw, part_number_raw, model_raw).
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
    };

    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => VALIDATE_JOB } as any);

    const { user } = renderPage();
    await navigateToUploadStep(user);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, xlsxFile());

    await screen.findByText(/Column mapping review/i);
    await user.click(screen.getByRole('button', { name: /Show \/ edit/i }));

    // "Base unit (descriptor)" row must show "Base Unit"
    expect(await screen.findByText('Base unit (descriptor)')).toBeInTheDocument();

    // "Product identity (SKU)" row must show "— not detected", NOT "Base Unit"
    // The detected-column cell for sku_raw should be the disabled placeholder text.
    const allCells = screen.getAllByText(/— not detected/i);
    expect(allCells.length).toBeGreaterThan(0);

    // Regression guard: no cell in the mapping table should contain both
    // "Product identity" row label AND "Base Unit" as its detected value.
    // We check by finding the label then looking at its sibling detected-column cell.
    const skuLabelCell = screen.getByText('Product identity (SKU)');
    const skuRow = skuLabelCell.closest('tr');
    expect(skuRow).not.toBeNull();
    // The detected-column cell is the second td in the row.
    const detectedCell = skuRow!.querySelectorAll('td')[1];
    expect(detectedCell?.textContent).not.toBe('Base Unit');

    // Restore mock for other tests
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
