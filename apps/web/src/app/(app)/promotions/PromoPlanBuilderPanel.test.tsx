import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { PromoPlanBuilderPanel } from './PromoPlanBuilderPanel';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiGet: get, apiPost: vi.fn() }));
vi.mock('@/features/tenant/useLineIdentifierPreference', () => ({
  useLineIdentifierPreference: () => ({ columns: () => [] }),
}));
vi.mock('@/features/commercial-planner/EntitySearchAutocomplete', () => ({
  EntitySearchAutocomplete: () => null,
}));
vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ rowData, columnDefs }: {
    rowData: Array<{ row_key: string; [key: string]: unknown }>;
    columnDefs: Array<{ field?: string; headerName?: string;
      valueFormatter?: (p: unknown) => string }>;
  }) => <div>{columnDefs.map((col) => <div key={col.field ?? col.headerName}>
    {col.headerName}
    {rowData.map((row) => <span key={row.row_key}>
      {col.valueFormatter
        ? col.valueFormatter({ value: row[col.field ?? ''], data: row })
        : String(row[col.field ?? ''] ?? '')}
    </span>)}
  </div>)}</div>,
}));

describe('sell-through planner presentation', () => {
  it('shows only customer cover and missing quantities as unavailable', async () => {
    get.mockResolvedValue({
      lines: [{ row_key: '1', product_id: 1, srp: null, suggested_estimate_qty: null,
        suggested_cost_basis: null, flags: ['cip_qty_unavailable'],
        promotion_evidence: { listing: { listed: null, data_unavailable: true },
          competitor_price: { data_unavailable: true }, observed_cover: { weeks: 4 } } }],
      budget_check: { tracks: { money: { status: 'not_available', planned_reservation_usd: null } } },
    });
    render(<QueryClientProvider client={new QueryClient()}><PromoPlanBuilderPanel /></QueryClientProvider>);
    fireEvent.change(screen.getByTestId('b4-seed-case-id'), { target: { value: '1' } });
    fireEvent.click(screen.getByTestId('b4-build-draft'));
    await waitFor(() => expect(screen.getByTestId('b4-draft-summary')).toBeInTheDocument());
    expect(screen.getByText('Customer cover 4w')).toBeInTheDocument();
    expect(screen.getAllByText('Not available yet').length).toBeGreaterThan(0);
    expect(screen.queryByText(/Not listed|No competitor price/)).not.toBeInTheDocument();
    expect(screen.getByText('Cost evidence')).toBeInTheDocument();
    expect(screen.queryByText('Buckets')).not.toBeInTheDocument();
    expect(screen.getByTestId('b4-draft-summary')).toHaveTextContent('Not available yet');
  });
});
