import { fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { LineupGroupsPanel } from './LineupGroupsPanel';
import type { LineupPlanRow } from './lineupTypes';

const apiPost = vi.fn(async (_url: string, _body?: unknown): Promise<unknown> => ({ changed: 1 }));
vi.mock('@/lib/api', () => ({
  apiPost: (url: string, body?: unknown) => apiPost(url, body),
  safeDisplayError: (e: unknown) => String(e),
}));

const rows = [
  {
    id: 1,
    customer_id: 3,
    customer_name: 'Customer A',
    customer_code: 'A',
    channel_code: null,
    period_start: '2026-01-01',
    period_label: '26Q1',
    sku: 'S1',
    planned_volume_units: 4,
    approval_status: 'draft',
  },
  {
    id: 2,
    customer_id: 3,
    customer_name: 'Customer A',
    customer_code: 'A',
    channel_code: null,
    period_start: '2026-01-01',
    period_label: '26Q1',
    sku: 'S2',
    planned_volume_units: 6,
    approval_status: 'approved',
  },
  {
    id: 3,
    customer_id: 4,
    customer_name: 'Customer B',
    customer_code: 'B',
    channel_code: null,
    period_start: '2026-01-01',
    period_label: '26Q1',
    sku: 'S1',
    planned_volume_units: 1,
    approval_status: 'approved',
  },
] as LineupPlanRow[];

function renderPanel(
  onOpen = vi.fn(),
  slice: { customerId: number; periodStart: string } | null = null
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  renderWithProviders(
    <QueryClientProvider client={qc}>
      <LineupGroupsPanel rows={rows} slice={slice} onOpen={onOpen} />
    </QueryClientProvider>
  );
  return onOpen;
}

describe('LineupGroupsPanel (Final wave b)', () => {
  it('lists one row per customer and period with counts', () => {
    renderPanel();
    expect(screen.getByTestId('lineup-group-counts-3|2026-01-01')).toHaveTextContent('2 lines');
    expect(screen.getByTestId('lineup-group-counts-3|2026-01-01')).toHaveTextContent(
      '1 pending · 1 approved · 0 rejected'
    );
    expect(screen.getByTestId('lineup-group-counts-4|2026-01-01')).toHaveTextContent('1 lines');
  });

  it('approves a whole line-up through the group endpoint, pending items only', async () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('lineup-group-approve-3|2026-01-01'));
    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith('/api/v1/lineup/items/group-approval', {
        customer_id: 3,
        period_start: '2026-01-01',
        approval_status: 'approved',
        only_pending: true,
      })
    );
  });

  it('disables decisions for a line-up with nothing pending, and opens a slice', () => {
    const onOpen = renderPanel(vi.fn(), { customerId: 4, periodStart: '2026-01-01' });
    expect(screen.getByTestId('lineup-group-reject-4|2026-01-01')).toBeDisabled();
    expect(screen.getByTestId('lineup-group-open-4|2026-01-01')).toHaveTextContent('Viewing');
    fireEvent.click(screen.getByTestId('lineup-group-open-3|2026-01-01'));
    expect(onOpen).toHaveBeenCalledWith(
      expect.objectContaining({ customerId: 3, periodStart: '2026-01-01' })
    );
  });

  it('links each group to the workbench scoped to that customer and period', () => {
    renderPanel();
    expect(screen.getByTestId('lineup-group-workbench-3|2026-01-01')).toHaveAttribute(
      'href',
      '/commercial-planner?customer=3&period=2026-01-01'
    );
    expect(screen.getByTestId('lineup-group-workbench-4|2026-01-01')).toHaveTextContent('Open in workbench');
    expect(screen.getByTestId('lineup-group-workbench-4|2026-01-01')).toHaveAttribute(
      'href',
      '/commercial-planner?customer=4&period=2026-01-01'
    );
  });
});
