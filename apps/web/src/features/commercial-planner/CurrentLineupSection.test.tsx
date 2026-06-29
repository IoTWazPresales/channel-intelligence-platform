import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { CurrentLineupSection } from './CurrentLineupSection';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
}));

// Mirror the repo pattern (see commercial-planner/page.test.tsx): mock the grid and render cells
// from columnDefs so header/cell assertions work without AG Grid's real (layout-dependent) DOM.
vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({
    rowData,
    columnDefs,
  }: {
    rowData: Array<Record<string, unknown>>;
    columnDefs?: Array<Record<string, unknown>>;
  }) => (
    <div data-testid="lineup-wb-grid-mock">
      <div role="row">
        {columnDefs?.map((c, i) => (
          <div role="columnheader" key={(c.colId as string) ?? i}>
            {c.headerName as string}
          </div>
        ))}
      </div>
      {rowData.map((row, ri) => (
        <div role="row" key={(row.id as number) ?? ri}>
          {columnDefs?.map((c, ci) => {
            const params = {
              data: row,
              value: typeof c.valueGetter === 'function' ? (c.valueGetter as (p: unknown) => unknown)({ data: row }) : undefined,
            };
            let content: unknown;
            if (typeof c.cellRenderer === 'function') content = (c.cellRenderer as (p: unknown) => unknown)(params);
            else if (typeof c.valueFormatter === 'function') content = (c.valueFormatter as (p: unknown) => unknown)(params);
            else content = params.value;
            return (
              <div role="cell" key={(c.colId as string) ?? ci}>
                {content as ReactNode}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  ),
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
    localStorage.clear();
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

  it('does not auto-show CPU columns; Processor details preset adds them', async () => {
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
          catalogue_product_fields: [
            { id: 'cat:catalogue_product_line', group: 'catalogue', label: 'Product line (catalogue)', field: 'catalogue_product_line' },
          ],
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

    expect(screen.queryByText(/Upload:\s*CPU/i)).not.toBeInTheDocument();

    await user.click(await screen.findByTestId('lineup-workbench-columns'));
    await user.click(await screen.findByTestId('lineup-columns-preset-processor'));
    await user.click(screen.getByRole('button', { name: /^Done$/i }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    expect(await screen.findByRole('columnheader', { name: /Upload:\s*CPU/i })).toBeInTheDocument();
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

  it('Processor details preset shows spec:cpu when catalogue has key', async () => {
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
      product_specs_flat: { cpu: 'Intel i7' },
      catalogue_product_line: 'NB',
    };
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/lineup-cases?')) return [draftCase];
      if (url.includes('/workbench-column-metadata')) {
        return {
          case_id: 5,
          raw_columns: [],
          parsed_fields: [
            { id: 'parsed:rebate_pct_evidence', group: 'parsed', label: 'Rebate % (evidence)', field: 'rebate_pct_evidence' },
          ],
          catalogue_product_fields: [
            { id: 'cat:catalogue_product_line', group: 'catalogue', label: 'Product line (catalogue)', field: 'catalogue_product_line' },
          ],
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

    expect(screen.queryByText('Spec: CPU')).not.toBeInTheDocument();
    expect(await screen.findByText('NB')).toBeInTheDocument();

    await user.click(await screen.findByTestId('lineup-workbench-columns'));
    await user.click(await screen.findByTestId('lineup-columns-preset-processor'));
    await user.click(screen.getByRole('button', { name: /^Done$/i }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    expect(await screen.findByRole('columnheader', { name: /Spec:\s*CPU/i })).toBeInTheDocument();
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

  it('confirm-with-po: draft case shows Confirm with PO without status ladder', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const draftCase = {
      id: 15,
      import_job_id: null,
      commercial_plan_id: 5,
      file_name: 'historical.xlsx',
      period_label: '26Q1',
      country_code: 'ZA',
      currency_code: 'ZAR',
      commercial_status: 'draft_imported',
      notes: null,
      accepted_at: null,
      accepted_by: null,
      line_count: 10,
      iteration_number: 1,
      product_line: 'Gaming',
      linked_pos: [],
      po_count: 0,
      created_at: null,
    };
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/lineup-cases?')) return [draftCase];
      if (url.includes('/suggested-pos')) {
        return {
          case_id: 15,
          case_distributor_id: 7,
          suggestions: [
            {
              purchase_order_id: 100,
              po_number: 'PO-SHIP-1',
              po_number_norm: 'SHIP1',
              distributor_id: 7,
              distributor_code: 'D1',
              distributor_name: 'Dist',
              matched_product_count: 3,
              total_shipped_units: 50,
              already_linked: false,
              status: 'observed',
            },
          ],
        };
      }
      return [];
    });
    apiPostMock.mockResolvedValue({
      case_id: 15,
      commercial_status: 'po_issued',
      po_count: 1,
      newly_linked_count: 1,
      linked_pos: [],
    });

    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CurrentLineupSection activePlanId={5} />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByTestId('current-lineup-section-toggle'));
    expect(await screen.findByTestId('confirm-with-po-btn-15')).toHaveTextContent('Confirm with PO');
    await user.click(screen.getByTestId('confirm-with-po-btn-15'));
    expect(await screen.findByTestId('confirm-po-suggestions')).toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: /Include PO PO-SHIP-1/i }));
    await user.click(screen.getByTestId('confirm-po-submit'));
    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/v1/commercial-planner/lineup-cases/15/confirm-with-po',
      expect.objectContaining({ po_numbers: ['PO-SHIP-1'] }),
    );
  });

  it('confirm-with-PO: accepted case sends po_numbers list to confirm endpoint', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const acceptedCase = {
      id: 12,
      import_job_id: null,
      commercial_plan_id: 5,
      file_name: 'lineup.csv',
      period_label: '26Q1',
      country_code: 'ZA',
      currency_code: 'ZAR',
      commercial_status: 'accepted',
      notes: null,
      accepted_at: null,
      accepted_by: null,
      line_count: 2,
      iteration_number: 1,
      product_line: null,
      inferred_period_start: null,
      linked_pos: [],
      po_count: 0,
      created_at: null,
    };
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/lineup-cases?')) return [acceptedCase];
      if (url.includes('/suggested-pos')) return { case_id: 12, case_distributor_id: null, suggestions: [] };
      return [];
    });
    apiPostMock.mockResolvedValue({
      case_id: 12,
      commercial_status: 'po_issued',
      iteration_number: 1,
      linked_pos: [],
      po_count: 2,
      newly_linked_count: 2,
    });

    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CurrentLineupSection activePlanId={5} />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByTestId('current-lineup-section-toggle'));
    await user.click(await screen.findByTestId('confirm-with-po-btn-12'));

    await user.type(screen.getByLabelText(/PO number\(s\) — manual entry/i), 'PO-1001,PO-1002');
    await user.click(screen.getByTestId('confirm-po-submit'));

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/v1/commercial-planner/lineup-cases/12/confirm-with-po',
      expect.objectContaining({ po_numbers: ['PO-1001', 'PO-1002'] }),
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

  it('plan-optional: lists unlinked cases grouped by period + product line when no plan selected', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const caseA = {
      id: 31,
      import_job_id: null,
      commercial_plan_id: null,
      file_name: 'consumer.xlsx',
      period_label: '26Q2',
      country_code: 'ZA',
      currency_code: 'ZAR',
      commercial_status: 'draft_imported',
      notes: null,
      accepted_at: null,
      accepted_by: null,
      line_count: 168,
      iteration_number: 1,
      product_line: 'NB',
      inferred_period_start: '2026-04-01',
      linked_pos: [],
      po_count: 0,
      created_at: null,
    };
    const caseB = {
      ...caseA,
      id: 32,
      file_name: 'gaming.xlsx',
      product_line: 'Gaming',
      line_count: 146,
    };
    let requestedUrl = '';
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/lineup-cases') && !url.includes('/lines') && !url.includes('metadata')) {
        requestedUrl = url;
        return [caseA, caseB];
      }
      return [];
    });

    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CurrentLineupSection activePlanId={null} />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByTestId('current-lineup-section-toggle'));

    // No plan_id sent when there is no plan.
    expect(requestedUrl).toContain('/lineup-cases');
    expect(requestedUrl).not.toContain('plan_id');

    // Two product-line groups, both showing the period and Unlinked badge.
    const groups = await screen.findAllByTestId('lineup-case-group');
    expect(groups.length).toBe(2);
    expect(screen.getAllByTestId('lineup-group-period')[0]).toHaveTextContent('26Q2');
    expect(screen.getByTestId('lineup-case-link-31')).toHaveTextContent('Unlinked');
    expect(screen.getByTestId('lineup-case-link-32')).toHaveTextContent('Unlinked');
  });

  it('plan filter still sends plan_id when a plan is selected', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    let requestedUrl = '';
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/lineup-cases') && !url.includes('/lines') && !url.includes('metadata')) {
        requestedUrl = url;
        return [];
      }
      return [];
    });

    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CurrentLineupSection activePlanId={5} />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByTestId('current-lineup-section-toggle'));
    expect(requestedUrl).toContain('plan_id=5');
  });

  it('workbench opens from an unlinked case (no plan required)', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const unlinked = {
      id: 40,
      import_job_id: null,
      commercial_plan_id: null,
      file_name: 'unlinked.xlsx',
      period_label: '26Q2',
      country_code: 'ZA',
      currency_code: 'ZAR',
      commercial_status: 'draft_imported',
      notes: null,
      accepted_at: null,
      accepted_by: null,
      line_count: 1,
      iteration_number: 1,
      product_line: 'NB',
      inferred_period_start: '2026-04-01',
      linked_pos: [],
      po_count: 0,
      created_at: null,
    };
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/workbench-column-metadata')) {
        return {
          case_id: 40,
          raw_columns: [],
          parsed_fields: [{ id: 'parsed:sku_raw', group: 'parsed', label: 'SKU (raw)', field: 'sku_raw' }],
          catalogue_product_fields: [],
          catalogue_spec_keys: [],
          sync_fields: [],
        };
      }
      if (url.includes('/lineup-cases/40/lines')) {
        return { lines: [lineupLineOpenChannel()], dap_semantics_note: 'DAP is evidence-only.' };
      }
      if (url.includes('/lineup-cases') && !url.includes('/lines') && !url.includes('metadata')) {
        return [unlinked];
      }
      return [];
    });

    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CurrentLineupSection activePlanId={null} />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByTestId('current-lineup-section-toggle'));
    await user.click(await screen.findByTestId('lineup-workbench-40'));

    // Working grid renders for an unlinked case.
    expect(await screen.findByTestId('current-lineup-working-grid')).toBeInTheDocument();
  });

  it('assign distributor: converged suggestion assigns the existing dim', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const draftCase = {
      id: 15,
      import_job_id: null,
      commercial_plan_id: 5,
      file_name: 'amazon.xlsx',
      period_label: '26Q1',
      country_code: 'ZA',
      currency_code: 'ZAR',
      commercial_status: 'draft_imported',
      notes: null,
      accepted_at: null,
      accepted_by: null,
      line_count: 10,
      iteration_number: 1,
      product_line: 'NB',
      linked_pos: [],
      po_count: 0,
      created_at: null,
    };
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/suggested-distributors')) {
        return {
          case_id: 15,
          converged: true,
          converged_distributor_id: 21,
          distinct_count: 1,
          suggested_distributors: [
            {
              distributor_id: 21,
              distributor_code: 'MUSTEK',
              distributor_name: 'Mustek',
              matched_product_count: 3,
              total_shipped_units: 240,
              po_count: 2,
              already_assigned: false,
            },
          ],
          already_assigned_distributor_ids: [],
        };
      }
      if (url.includes('/lineup-cases') && !url.includes('/lines') && !url.includes('metadata')) {
        return [draftCase];
      }
      return [];
    });
    apiPostMock.mockResolvedValue({
      case_id: 15,
      distributor_id: 21,
      distributor_created: false,
      updated_lines: 10,
    });

    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CurrentLineupSection activePlanId={5} />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByTestId('current-lineup-section-toggle'));
    await user.click(await screen.findByTestId('assign-distributor-btn-15'));
    expect(await screen.findByTestId('assign-dist-converged')).toBeInTheDocument();
    await user.click(await screen.findByTestId('assign-dist-suggestion-21'));
    await user.click(screen.getByTestId('assign-dist-submit'));

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/v1/commercial-planner/lineup-cases/15/assign-distributor',
      { distributor_id: 21 },
    );
  });

  it('assign distributor: ambiguous evidence lets you pick a candidate', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const draftCase = {
      id: 16,
      import_job_id: null,
      commercial_plan_id: 5,
      file_name: 'amazon.xlsx',
      period_label: '26Q1',
      country_code: 'ZA',
      currency_code: 'ZAR',
      commercial_status: 'draft_imported',
      notes: null,
      accepted_at: null,
      accepted_by: null,
      line_count: 10,
      iteration_number: 1,
      product_line: 'NB',
      linked_pos: [],
      po_count: 0,
      created_at: null,
    };
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/suggested-distributors')) {
        return {
          case_id: 16,
          converged: false,
          converged_distributor_id: null,
          distinct_count: 2,
          suggested_distributors: [
            {
              distributor_id: 29,
              distributor_code: 'PINNACLE',
              distributor_name: 'Pinnacle',
              matched_product_count: 2,
              total_shipped_units: 90,
              po_count: 1,
              already_assigned: false,
            },
            {
              distributor_id: 21,
              distributor_code: 'MUSTEK',
              distributor_name: 'Mustek',
              matched_product_count: 1,
              total_shipped_units: 40,
              po_count: 1,
              already_assigned: false,
            },
          ],
          already_assigned_distributor_ids: [],
        };
      }
      if (url.includes('/lineup-cases') && !url.includes('/lines') && !url.includes('metadata')) {
        return [draftCase];
      }
      return [];
    });
    apiPostMock.mockResolvedValue({
      case_id: 16,
      distributor_id: 21,
      distributor_created: false,
      updated_lines: 10,
    });

    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CurrentLineupSection activePlanId={5} />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByTestId('current-lineup-section-toggle'));
    await user.click(await screen.findByTestId('assign-distributor-btn-16'));
    expect(await screen.findByTestId('assign-dist-ambiguous')).toBeInTheDocument();
    await user.click(await screen.findByTestId('assign-dist-suggestion-21'));
    await user.click(screen.getByTestId('assign-dist-submit'));

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/v1/commercial-planner/lineup-cases/16/assign-distributor',
      { distributor_id: 21 },
    );
  });

  it('assign distributor: create-new requires confirm and posts create payload', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const draftCase = {
      id: 17,
      import_job_id: null,
      commercial_plan_id: 5,
      file_name: 'amazon.xlsx',
      period_label: '26Q1',
      country_code: 'ZA',
      currency_code: 'ZAR',
      commercial_status: 'draft_imported',
      notes: null,
      accepted_at: null,
      accepted_by: null,
      line_count: 10,
      iteration_number: 1,
      product_line: 'NB',
      linked_pos: [],
      po_count: 0,
      created_at: null,
    };
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/suggested-distributors')) {
        return {
          case_id: 17,
          converged: false,
          converged_distributor_id: null,
          distinct_count: 0,
          suggested_distributors: [],
          already_assigned_distributor_ids: [],
        };
      }
      if (url.includes('/lineup-cases') && !url.includes('/lines') && !url.includes('metadata')) {
        return [draftCase];
      }
      return [];
    });
    apiPostMock.mockResolvedValue({
      case_id: 17,
      distributor_id: 99,
      distributor_created: true,
      updated_lines: 10,
    });

    renderWithProviders(
      <QueryClientProvider client={qc}>
        <CurrentLineupSection activePlanId={5} />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByTestId('current-lineup-section-toggle'));
    await user.click(await screen.findByTestId('assign-distributor-btn-17'));
    expect(await screen.findByTestId('assign-dist-none')).toBeInTheDocument();

    await user.click(await screen.findByTestId('assign-dist-create-toggle'));
    await user.type(screen.getByTestId('assign-dist-new-code').querySelector('input')!, 'AMZ');
    await user.type(screen.getByTestId('assign-dist-new-name').querySelector('input')!, 'Amazon Direct');

    // Submit is disabled until confirmation is ticked.
    expect(screen.getByTestId('assign-dist-submit')).toBeDisabled();
    await user.click(await screen.findByTestId('assign-dist-confirm-create'));
    await user.click(screen.getByTestId('assign-dist-submit'));

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/v1/commercial-planner/lineup-cases/17/assign-distributor',
      { new_code: 'AMZ', new_name: 'Amazon Direct', confirm_create: true },
    );
  });

  it('default workbench columns omit SKU but show calc chain and formatted pct', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const draftCase = {
      id: 50,
      import_job_id: null,
      commercial_plan_id: 5,
      file_name: 'gaming.xlsx',
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
      case_id: 50,
      id: 99,
      sku_raw: 'SKU-RAW-1',
      part_number_raw: 'PN-1',
      product_model_name: 'ROG Strix G16',
      product_spec_processor: 'Intel Core i9',
      catalogue_series_name: 'ROG Strix',
      rebate_pct_evidence: 0.06,
      vat_pct_evidence: 0.15,
      pricing_chain_json: {
        outputs: {
          calc_dealer_price_local: 1200.5,
          calc_net_price_local: 1100,
          calc_disti_cost_local: 950.25,
          calc_dap_cost_currency: 800,
          calc_profit_total: 4000,
        },
      },
      calc_dap_cost_currency: 800,
      calc_profit_total: 4000,
    };
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/lineup-cases?')) return [draftCase];
      if (url.includes('/workbench-column-metadata')) {
        return {
          case_id: 50,
          raw_columns: ['Dealer price'],
          parsed_fields: [
            { id: 'parsed:rebate_pct_evidence', group: 'parsed', label: 'Rebate % (evidence)', field: 'rebate_pct_evidence' },
            { id: 'parsed:vat_pct_evidence', group: 'parsed', label: 'VAT % (evidence)', field: 'vat_pct_evidence' },
            { id: 'parsed:sku_raw', group: 'parsed', label: 'SKU (raw)', field: 'sku_raw' },
          ],
          catalogue_product_fields: [
            { id: 'cat:product_model_name', group: 'catalogue', label: 'Model name (catalogue)', field: 'product_model_name' },
            { id: 'cat:product_spec_processor', group: 'catalogue', label: 'Processor (catalogue spec)', field: 'product_spec_processor' },
            { id: 'cat:catalogue_series_name', group: 'catalogue', label: 'Series (catalogue)', field: 'catalogue_series_name' },
          ],
          catalogue_spec_keys: [],
          calc_fields: [
            { id: 'calc:dealer_price', group: 'calculated', label: 'Dealer price (calc)', field: 'calc_dealer_price_local' },
            { id: 'calc:net_price', group: 'calculated', label: 'Net price (calc)', field: 'calc_net_price_local' },
            { id: 'calc:disti_cost', group: 'calculated', label: 'Disti cost (calc)', field: 'calc_disti_cost_local' },
            { id: 'calc:dap', group: 'calculated', label: 'DAP (calc)', field: 'calc_dap_cost_currency' },
            { id: 'calc:profit', group: 'calculated', label: 'Profit total (calc)', field: 'calc_profit_total' },
          ],
          sync_fields: [],
        };
      }
      if (url.includes('/lineup-cases/50/lines')) {
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
    await user.click(await screen.findByTestId('lineup-workbench-50'));

    expect(screen.queryByRole('columnheader', { name: /^SKU$/i })).not.toBeInTheDocument();
    expect(await screen.findByRole('columnheader', { name: /Dealer price \(calc\)/i })).toBeInTheDocument();
    expect(await screen.findByRole('columnheader', { name: /DAP \(calc\)/i })).toBeInTheDocument();
    expect(await screen.findByText('6%')).toBeInTheDocument();
    expect(await screen.findByText('15%')).toBeInTheDocument();
    expect(await screen.findByText(/800/)).toBeInTheDocument();
    expect(await screen.findByRole('columnheader', { name: /Model name \(catalogue\)/i })).toBeInTheDocument();
    expect(await screen.findByRole('columnheader', { name: /Processor \(catalogue spec\)/i })).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: /Upload:\s*Dealer price/i })).not.toBeInTheDocument();
  });
});
