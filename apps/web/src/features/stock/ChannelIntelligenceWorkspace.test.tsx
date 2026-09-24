import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { ChannelIntelligenceWorkspace } from './ChannelIntelligenceWorkspace';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/channel-intelligence/workspace',
}));

const ROW = {
  customer_id: 3,
  product_id: 7,
  customer_code: 'CUST-3',
  customer_name: 'Customer Three',
  product_sku: 'SKU-7',
  product_name: 'Product 7',
  sales_model_name: null,
  site_label: null,
  data_state: 'ok',
  reason: null,
  velocity_4wk: 1,
  velocity_13wk: 1,
  weeks_of_cover: 2,
  weeks_of_cover_reason: null,
  aged_dead_stock: false,
  velocity_trend: 'flat',
  factors: {},
};

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (url.startsWith('/api/v1/grid-fields/channel-intelligence')) {
      return {
        grid_id: 'channel-intelligence',
        items: [
          { field: 'reason', label: 'Reason', group: 'fact', default_hidden: true },
          { field: 'customer_code', label: 'Customer code', group: 'reference', default_hidden: true },
        ],
      };
    }
    if (url.startsWith('/api/v1/channel-intelligence')) {
      return { items: [ROW], total: 1, page: 1, page_size: 200, data_unavailable: false, grain_policy: 'test' };
    }
    return {};
  }),
}));

/** Renders headers and the first row's cells the way AG Grid would resolve field / valueGetter. */
vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ columnDefs, rowData }: { columnDefs: ColDef[]; rowData: Record<string, unknown>[] }) => {
    const row = rowData[0];
    const cells = columnDefs.map((c) => {
      if (!row) return '';
      if (typeof c.valueGetter === 'function') {
        return String((c.valueGetter as (p: { data: unknown }) => unknown)({ data: row }) ?? '');
      }
      return c.field ? String(row[c.field] ?? '') : '';
    });
    return (
      <div>
        <div data-testid="grid-headers">{columnDefs.map((c) => c.headerName).join('|')}</div>
        <div data-testid="grid-row">{cells.join('|')}</div>
      </div>
    );
  },
}));

function renderWorkspace() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <ChannelIntelligenceWorkspace />
    </QueryClientProvider>,
  );
}

describe('ChannelIntelligenceWorkspace column picker (N-0034 pass-2 host)', () => {
  beforeEach(() => localStorage.clear());

  it('shows the customer name only, and offers the code as its own Reference column', async () => {
    renderWorkspace();
    await waitFor(() => expect(screen.getByTestId('grid-row')).toHaveTextContent('Customer Three'));
    expect(screen.getByTestId('grid-row')).not.toHaveTextContent('CUST-3');
    expect(screen.getByTestId('grid-headers')).not.toHaveTextContent('Customer code');

    fireEvent.click(screen.getByTestId('fact-columns-button-channel-intelligence'));
    expect(await screen.findByText('Reference')).toBeInTheDocument();
    const toggle = await screen.findByTestId('master-column-toggle-customer_code');
    await waitFor(() => expect(toggle.querySelector('input')).not.toBeDisabled());
    fireEvent.click(toggle.querySelector('input')!);

    await waitFor(() => expect(screen.getByTestId('grid-headers')).toHaveTextContent('Customer code'));
    expect(screen.getByTestId('grid-row')).toHaveTextContent('CUST-3');
    expect(screen.getByTestId('fact-columns-button-channel-intelligence')).toHaveTextContent('Columns (1)');
    expect(JSON.parse(localStorage.getItem('cip.grid.channel-intelligence.optional.v1') ?? '{}')).toEqual({
      optionalFields: ['customer_code'],
    });
  });
});
