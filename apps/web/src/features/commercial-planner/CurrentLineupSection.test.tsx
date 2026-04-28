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

import { apiGet } from '@/lib/api';

const apiGetMock = vi.mocked(apiGet);

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
    uploaded: { 'Dealer rebate': '5%' },
    product_specs: { cpu: 'M1' },
    sync_eligible: false,
    sync_skip_reason: 'planner_requires_customer',
    sync_skip_detail: 'Open Channel row: planner lines require a customer_id.',
  };
}

describe('CurrentLineupSection — lineup workbench semantics', () => {
  beforeEach(() => {
    apiGetMock.mockReset();
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

    expect(await screen.findByText(/Open Channel · Channel - Rectron \(Unassigned\)/)).toBeInTheDocument();
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

    expect(await screen.findByText('5%')).toBeInTheDocument();
  });
});
