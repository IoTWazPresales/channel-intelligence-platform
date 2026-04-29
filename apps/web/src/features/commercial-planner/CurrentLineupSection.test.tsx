import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { CurrentLineupSection } from './CurrentLineupSection';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
}));

vi.mock('./EntitySearchAutocomplete', () => ({
  EntitySearchAutocomplete: ({
    label,
    onChange,
  }: {
    label: string;
    onChange: (v: unknown) => void;
  }) => (
    <button
      type="button"
      data-testid={`mock-entity-${label.replace(/\s+/g, '-').toLowerCase()}`}
      onClick={() => {
        if (label.includes('Map token to distributor')) {
          onChange({ id: 9, distributor_code: 'DMAP', distributor_name: 'Dist Fixed' });
        } else if (label.includes('Map token to customer')) {
          onChange({ id: 7, customer_code: 'CMAP', customer_name: 'Cust Fixed' });
        } else if (label.toLowerCase().includes('distributor')) {
          onChange({ id: 9, distributor_code: 'DMAP', distributor_name: 'Dist Fixed' });
        } else {
          onChange({ id: 7, customer_code: 'CMAP', customer_name: 'Cust Fixed' });
        }
      }}
    >
      {label}
    </button>
  ),
}));

import { apiGet, apiPost } from '@/lib/api';

const apiGetMock = vi.mocked(apiGet);
const apiPostMock = vi.mocked(apiPost);

function lineupLineOpenChannel() {
  return {
    id: 1,
    case_id: 3,
    source_row_number: 1,
    product_id: 10,
    product_sku: 'SKU',
    product_name: null,
    product_part_number: null,
    product_model_name: null,
    product_sales_model_name: null,
    customer_id: null,
    customer_code: null,
    customer_name: null,
    distributor_id: 3,
    distributor_code: 'D',
    distributor_name: 'Dist',
    customer_token: null,
    distributor_token_raw: null,
    sku_raw: null,
    part_number_raw: null,
    model_raw: null,
    base_unit_raw: null,
    quantity_units: 1,
    msrp_local: 100,
    promo_price_evidence_local: null,
    dap_evidence_local: 12,
    diagnostic_codes: [],
    row_status: 'imported',
    staging_open_channel: true,
    channel_route_uploaded_cell: 'Channel - Rectron',
    catalogue_category: 'Laptops',
    uploaded: { 'Dealer rebate': '5%' },
    product_specs: { cpu: 'M1' },
    sync_eligible: true,
    sync_skip_reason: null,
    sync_skip_detail: null,
    sync_ui_severity: null,
    sync_customer_resolution_note: 'Sync will use Open Channel account (dim_customer code OPEN_CHANNEL).',
  };
}

describe('CurrentLineupSection — lineup workbench semantics', () => {
  beforeEach(() => {
    apiGetMock.mockReset();
    apiPostMock.mockReset();
  });

  it('shows Open Channel customer as Unassigned (not unresolved token)', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const draftCase = {
      id: 3,
      import_job_id: null,
      commercial_plan_id: 5,
      file_name: 'f.csv',
      period_label: 'Q2',
      country_code: 'US',
      currency_code: 'USD',
      commercial_status: 'draft_imported',
      notes: null,
      accepted_at: null,
      accepted_by: null,
      line_count: 1,
      created_at: null,
    };
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/lineup-cases?')) return [draftCase];
      if (url.includes('/workbench-column-metadata')) {
        return {
          case_id: 3,
          raw_columns: ['Dealer rebate'],
          parsed_fields: [{ id: 'parsed:sku_raw', group: 'parsed', label: 'SKU (raw)', field: 'sku_raw' }],
          catalogue_product_fields: [
            { id: 'cat:catalogue_category', group: 'catalogue', label: 'Category (catalogue)', field: 'catalogue_category' },
          ],
          catalogue_spec_keys: ['cpu'],
          sync_fields: [{ id: 'sync:sync_skip_reason', group: 'sync', label: 'r', field: 'sync_skip_reason' }],
        };
      }
      if (url.includes('/lineup-cases/3/lines')) {
        return { lines: [lineupLineOpenChannel()], dap_semantics_note: 'DAP is evidence-only.' };
      }
      return [];
    });

    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CurrentLineupSection activePlanId={5} />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByTestId('current-lineup-section-toggle'));
    await user.click(await screen.findByTestId('lineup-workbench-3'));

    expect(await screen.findByText(/Open Channel · Channel - Rectron \(end customer unassigned\)/)).toBeInTheDocument();
    expect(screen.queryByText(/\(Unresolved\)/)).not.toBeInTheDocument();
  });

  it('shows raw upload column value when enabled in workbench columns', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const draftCase = {
      id: 3,
      import_job_id: null,
      commercial_plan_id: 5,
      file_name: 'f.csv',
      period_label: null,
      country_code: 'US',
      currency_code: 'USD',
      commercial_status: 'draft_imported',
      notes: null,
      accepted_at: null,
      accepted_by: null,
      line_count: 1,
      created_at: null,
    };
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/lineup-cases?')) return [draftCase];
      if (url.includes('/workbench-column-metadata')) {
        return {
          case_id: 3,
          raw_columns: ['Dealer rebate'],
          parsed_fields: [],
          catalogue_product_fields: [
            { id: 'cat:catalogue_category', group: 'catalogue', label: 'Category (catalogue)', field: 'catalogue_category' },
          ],
          catalogue_spec_keys: [],
          sync_fields: [],
        };
      }
      if (url.includes('/lineup-cases/3/lines')) {
        return { lines: [lineupLineOpenChannel()], dap_semantics_note: 'DAP is evidence-only.' };
      }
      return [];
    });

    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CurrentLineupSection activePlanId={5} />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByTestId('current-lineup-section-toggle'));
    await user.click(await screen.findByTestId('lineup-workbench-3'));
    await user.click(await screen.findByTestId('lineup-workbench-columns'));

    const rawToggle = await screen.findByRole('checkbox', { name: /Dealer rebate/i });
    await user.click(rawToggle);

    const catToggle = await screen.findByRole('checkbox', { name: /Category \(catalogue\)/i });
    await user.click(catToggle);

    expect(await screen.findByText('Laptops')).toBeInTheDocument();
  });

  it('auto-shows uploaded CPU column when metadata lists a CPU header', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const draftCase = {
      id: 3,
      import_job_id: null,
      commercial_plan_id: 5,
      file_name: 'f.csv',
      period_label: null,
      country_code: 'US',
      currency_code: 'USD',
      commercial_status: 'draft_imported',
      notes: null,
      accepted_at: null,
      accepted_by: null,
      line_count: 1,
      created_at: null,
    };
    const line = {
      ...lineupLineOpenChannel(),
      uploaded: { CPU: 'Ultra 7 155H', 'Dealer rebate': '5%' },
    };
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/lineup-cases?')) return [draftCase];
      if (url.includes('/workbench-column-metadata')) {
        return {
          case_id: 3,
          raw_columns: ['CPU', 'Dealer rebate'],
          parsed_fields: [],
          catalogue_product_fields: [],
          catalogue_spec_keys: [],
          sync_fields: [],
        };
      }
      if (url.includes('/lineup-cases/3/lines')) {
        return { lines: [line], dap_semantics_note: 'DAP is evidence-only.' };
      }
      return [];
    });

    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CurrentLineupSection activePlanId={5} />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByTestId('current-lineup-section-toggle'));
    await user.click(await screen.findByTestId('lineup-workbench-3'));

    expect(await screen.findByText(/Upload:\s*CPU/i)).toBeInTheDocument();
    expect(await screen.findByText('Ultra 7 155H')).toBeInTheDocument();
  });

  it('shows Distributor unassigned for UNASSIGNED placeholder dim', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const draftCase = {
      id: 4,
      import_job_id: null,
      commercial_plan_id: 5,
      file_name: 'f.csv',
      period_label: null,
      country_code: 'US',
      currency_code: 'USD',
      commercial_status: 'draft_imported',
      notes: null,
      accepted_at: null,
      accepted_by: null,
      line_count: 1,
      created_at: null,
    };
    const line = {
      ...lineupLineOpenChannel(),
      case_id: 4,
      distributor_id: 99,
      distributor_code: 'UNASSIGNED',
      distributor_name: 'Unassigned Distributor',
    };
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/lineup-cases?')) return [draftCase];
      if (url.includes('/workbench-column-metadata')) {
        return {
          case_id: 4,
          raw_columns: [],
          parsed_fields: [],
          catalogue_product_fields: [],
          catalogue_spec_keys: [],
          sync_fields: [],
        };
      }
      if (url.includes('/lineup-cases/4/lines')) {
        return { lines: [line], dap_semantics_note: 'DAP is evidence-only.' };
      }
      return [];
    });

    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CurrentLineupSection activePlanId={5} />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByTestId('current-lineup-section-toggle'));
    await user.click(await screen.findByTestId('lineup-workbench-4'));

    expect(await screen.findByText('Distributor unassigned')).toBeInTheDocument();
  });

  it('auto-shows spec:cpu from processor_spec_key_hints when catalogue has key', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const draftCase = {
      id: 5,
      import_job_id: null,
      commercial_plan_id: 5,
      file_name: 'f.csv',
      period_label: null,
      country_code: 'US',
      currency_code: 'USD',
      commercial_status: 'draft_imported',
      notes: null,
      accepted_at: null,
      accepted_by: null,
      line_count: 1,
      created_at: null,
    };
    const line = {
      ...lineupLineOpenChannel(),
      case_id: 5,
      id: 2,
      product_specs: { cpu: 'Intel i7' },
      // product_specs_flat is the flattened map used by wbCellContent for spec: columns
      product_specs_flat: { cpu: 'Intel i7' },
    };
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/lineup-cases?')) return [draftCase];
      if (url.includes('/workbench-column-metadata')) {
        return {
          case_id: 5,
          raw_columns: [],
          parsed_fields: [],
          catalogue_product_fields: [],
          catalogue_spec_keys: ['cpu'],
          processor_spec_key_hints: ['cpu'],
          sync_fields: [],
        };
      }
      if (url.includes('/lineup-cases/5/lines')) {
        return { lines: [line], dap_semantics_note: 'DAP is evidence-only.' };
      }
      return [];
    });

    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CurrentLineupSection activePlanId={5} />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByTestId('current-lineup-section-toggle'));
    await user.click(await screen.findByTestId('lineup-workbench-5'));

    expect(await screen.findByText('Spec: CPU')).toBeInTheDocument();
    expect(await screen.findByText('Intel i7')).toBeInTheDocument();
  });

  it('entity resolution: apply Open Channel staging sends explicit API action', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const draftCase = {
      id: 8,
      import_job_id: null,
      commercial_plan_id: 5,
      file_name: 'f.csv',
      period_label: null,
      country_code: 'US',
      currency_code: 'USD',
      commercial_status: 'draft_imported',
      notes: null,
      accepted_at: null,
      accepted_by: null,
      line_count: 1,
      created_at: null,
    };
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/lineup-cases?')) return [draftCase];
      if (url.includes('/lineup-cases/8/entity-resolution-candidates')) {
        return {
          case_id: 8,
          customer_tokens: [
            { token_norm: 'ic', token_display: 'IC', line_count: 1, sample_line_ids: [1] },
          ],
          distributor_tokens: [],
        };
      }
      if (url.includes('/workbench-column-metadata')) {
        return {
          case_id: 8,
          raw_columns: [],
          parsed_fields: [],
          catalogue_product_fields: [],
          catalogue_spec_keys: [],
          sync_fields: [],
        };
      }
      if (url.includes('/lineup-cases/8/lines')) {
        return { lines: [], dap_semantics_note: 'DAP is evidence-only.' };
      }
      return [];
    });
    apiPostMock.mockResolvedValue({ case_id: 8, updated_lines: 1, per_resolution: [] });

    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CurrentLineupSection activePlanId={5} />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByTestId('current-lineup-section-toggle'));
    await user.click(await screen.findByTestId('lineup-workbench-8'));
    await user.click(await screen.findByTestId('lineup-entity-resolution-open'));

    const dialog = await screen.findByRole('dialog', { name: /resolve lineup entities/i });
    await user.click(await screen.findByRole('combobox', { name: /resolution/i }));
    await user.click(await screen.findByRole('option', { name: /mark as open channel staging/i }));
    await user.click(await screen.findByTestId('lineup-entity-resolution-apply'));

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/v1/commercial-planner/lineup-cases/8/entity-resolutions/apply',
      expect.objectContaining({
        resolutions: [{ kind: 'customer', token: 'IC', action: 'mark_open_channel_staging' }],
      }),
    );
  });

  it('entity resolution: customer-column token mapped as distributor sends redirect kind', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const draftCase = {
      id: 9,
      import_job_id: null,
      commercial_plan_id: 5,
      file_name: 'f.csv',
      period_label: null,
      country_code: 'US',
      currency_code: 'USD',
      commercial_status: 'draft_imported',
      notes: null,
      accepted_at: null,
      accepted_by: null,
      line_count: 1,
      created_at: null,
    };
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/lineup-cases?')) return [draftCase];
      if (url.includes('/lineup-cases/9/entity-resolution-candidates')) {
        return {
          case_id: 9,
          customer_tokens: [
            { token_norm: 'mitsumi', token_display: 'MITSUMI', line_count: 1, sample_line_ids: [1] },
          ],
          distributor_tokens: [],
        };
      }
      if (url.includes('/workbench-column-metadata')) {
        return {
          case_id: 9,
          raw_columns: [],
          parsed_fields: [],
          catalogue_product_fields: [],
          catalogue_spec_keys: [],
          sync_fields: [],
        };
      }
      if (url.includes('/lineup-cases/9/lines')) {
        return { lines: [], dap_semantics_note: 'DAP is evidence-only.' };
      }
      return [];
    });
    apiPostMock.mockResolvedValue({ case_id: 9, updated_lines: 1, per_resolution: [] });

    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CurrentLineupSection activePlanId={5} />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByTestId('current-lineup-section-toggle'));
    await user.click(await screen.findByTestId('lineup-workbench-9'));
    await user.click(await screen.findByTestId('lineup-entity-resolution-open'));

    await user.click(await screen.findByRole('combobox', { name: /resolution/i }));
    await user.click(await screen.findByRole('option', { name: /token is a distributor/i }));
    await user.click(await screen.findByTestId('mock-entity-map-token-to-distributor'));
    await user.click(await screen.findByTestId('lineup-entity-resolution-apply'));

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/v1/commercial-planner/lineup-cases/9/entity-resolutions/apply',
      expect.objectContaining({
        resolutions: [
          {
            kind: 'customer_token_as_distributor',
            token: 'MITSUMI',
            action: 'map_existing',
            dim_id: 9,
          },
        ],
      }),
    );
  });
});
