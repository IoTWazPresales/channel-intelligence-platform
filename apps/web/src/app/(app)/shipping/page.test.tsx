import React from 'react';
import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import InboundShipmentsPage from './page';

const replaceSpy = vi.fn();
let searchString = '';

const mockState = vi.hoisted(() => ({
  apiGetMock: vi.fn(async () => ({ total: 0, skip: 0, limit: 50, items: [] })),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceSpy, push: vi.fn() }),
  usePathname: () => '/shipping',
  useSearchParams: () => new URLSearchParams(searchString),
}));

vi.mock('@/components/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <div>{title}</div>,
}));

vi.mock('@/components/masterGrid/MasterDataGridShell', () => ({
  MasterDataGridShell: ({
    rows,
    onUrlChange,
    url,
  }: {
    rows: unknown[];
    onUrlChange: (patch: Record<string, string | null>) => void;
    url: { page: number };
  }) => (
    <div>
      <div data-testid="shipping-grid">{rows.length} rows</div>
      <button type="button" onClick={() => onUrlChange({ page: String(url.page + 1) })}>
        Next
      </button>
    </div>
  ),
}));

vi.mock('@/components/masterGrid/MasterColumnPickerDialog', () => ({
  MasterColumnPickerDialog: () => null,
}));

vi.mock('./ShippingCommercialSummary', () => ({
  ShippingCommercialSummary: () => null,
}));

vi.mock('./ShippingLineupQuarterSummary', () => ({
  ShippingLineupQuarterSummary: () => null,
}));

vi.mock('./InboundShipmentsColumnsDialog', () => ({
  InboundShipmentsColumnsDialog: () => null,
}));

vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => mockState.apiGetMock(...args),
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return renderWithProviders(
    <QueryClientProvider client={client}>
      <InboundShipmentsPage />
    </QueryClientProvider>,
  );
}

describe('Inbound shipments page pagination (BACKLOG-074 U4b)', () => {
  beforeEach(() => {
    replaceSpy.mockReset();
    searchString = '';
    mockState.apiGetMock.mockReset();
    mockState.apiGetMock.mockImplementation(async (url: string) => {
      if (String(url).includes('/shipping/lines')) {
        return {
          total: 120,
          skip: searchString.includes('skip=50') ? 50 : 0,
          limit: searchString.includes('limit=25') ? 25 : 50,
          items: [{ id: 1, distributor_name: 'Dist A', line_state: 'open_order', status: 'scheduled' }],
        };
      }
      if (String(url).includes('/shipping/summary')) {
        return { total_lines: 0, by_line_state: [], by_status: [], by_distributor: [] };
      }
      if (String(url).includes('/shipping/filter-options')) {
        return { distributors: [], customers: [] };
      }
      if (String(url).includes('/shipping/lineup-plan-periods')) {
        return { items: [] };
      }
      if (String(url).includes('/shipping/inbound-optional-columns')) {
        return { items: [] };
      }
      return {};
    });
  });

  it('fetches with skip/limit from URL', async () => {
    searchString = 'skip=50&limit=25';
    renderPage();
    await screen.findByTestId('shipping-grid');
    expect(mockState.apiGetMock).toHaveBeenCalledWith(
      expect.stringMatching(/skip=50/),
      expect.anything(),
    );
    expect(mockState.apiGetMock).toHaveBeenCalledWith(
      expect.stringMatching(/limit=25/),
      expect.anything(),
    );
  });

  it('syncs next page to URL skip param', async () => {
    renderPage();
    await screen.findByTestId('shipping-grid');
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(replaceSpy).toHaveBeenCalled();
    const last = String(replaceSpy.mock.calls.at(-1)?.[0] ?? '');
    expect(last).toContain('skip=50');
  });

  it('resets skip in URL when search filter changes', async () => {
    searchString = 'skip=100';
    renderPage();
    await screen.findByTestId('shipping-grid');
    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'acme' } });
    expect(replaceSpy).toHaveBeenCalled();
    const last = String(replaceSpy.mock.calls.at(-1)?.[0] ?? '');
    expect(last).not.toContain('skip=100');
  });
});
