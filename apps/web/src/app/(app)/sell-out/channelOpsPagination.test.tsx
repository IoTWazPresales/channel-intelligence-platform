import { fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { apiGet } from '@/lib/api';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { ChannelOpsMovementsTab } from './ChannelOpsMovementsTab';
import { SellOutTab } from './SellOutTab';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(),
}));

const apiGetMock = vi.mocked(apiGet);

function renderWithQuery(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('Channel Operations pagination (BACKLOG-074 U4g)', () => {
  beforeEach(() => {
    apiGetMock.mockReset();
  });

  it('SellOutTab fetches page 2 when Next is clicked (channel-ops API)', async () => {
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/sellout/commercial-summary')) {
        return { total_rows: 0, total_units: 0, total_revenue: 0, latest_period_start: null };
      }
      if (url.includes('/sellout/filter-options')) {
        return { distributors: [], customers: [] };
      }
      if (url.includes('/channel-ops/sell-out')) {
        const page = new URL(url, 'http://test').searchParams.get('page');
        if (page === '2') {
          return {
            total: 120,
            page: 2,
            page_size: 50,
            items: [{ date: '2026-01-02', sku: 'SKU-2', customer_name: 'C2', distributor_name: 'D', units: 2, revenue: 20, unit_price: 10, prior_period_units: null }],
          };
        }
        return {
          total: 120,
          page: 1,
          page_size: 50,
          items: [{ date: '2026-01-01', sku: 'SKU-1', customer_name: 'C1', distributor_name: 'D', units: 1, revenue: 10, unit_price: 10, prior_period_units: null }],
        };
      }
      return {};
    });

    renderWithQuery(<SellOutTab depth="operational" />);

    expect(await screen.findByText('SKU-1')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Go to next page' }));

    await waitFor(() => {
      expect(apiGetMock).toHaveBeenCalledWith(
        expect.stringMatching(/channel-ops\/sell-out.*page=2/),
        expect.any(Object)
      );
    });
    expect(await screen.findByText('SKU-2')).toBeInTheDocument();
  });

  it('ChannelOpsMovementsTab fetches page 2 when Next is clicked', async () => {
    apiGetMock.mockImplementation(async (url: string) => {
      if (url.includes('/sellout/filter-options')) {
        return {
          distributors: [{ id: 7, distributor_code: 'DIST7', distributor_name: 'Dist Seven' }],
        };
      }
      if (url.includes('/channel-ops/movements')) {
        const page = new URL(url, 'http://test').searchParams.get('page');
        if (page === '2') {
          return {
            total: 80,
            page: 2,
            page_size: 50,
            items: [
              {
                product_id: 2,
                sku: 'M-SKU-2',
                product_name: 'Prod 2',
                order_no: 'O2',
                delivery_no: 'D2',
                ship_date: '2026-02-02',
                units_shipped: 5,
                line_state: 'shipped',
                distributor_name: 'Dist Seven',
              },
            ],
          };
        }
        return {
          total: 80,
          page: 1,
          page_size: 50,
          items: [
            {
              product_id: 1,
              sku: 'M-SKU-1',
              product_name: 'Prod 1',
              order_no: 'O1',
              delivery_no: 'D1',
              ship_date: '2026-02-01',
              units_shipped: 3,
              line_state: 'shipped',
              distributor_name: 'Dist Seven',
            },
          ],
        };
      }
      return {};
    });

    renderWithQuery(<ChannelOpsMovementsTab depth="operational" />);

    const combo = await screen.findByRole('combobox', { name: /distributor/i });
    fireEvent.mouseDown(combo);
    fireEvent.click(await screen.findByText(/Dist Seven/));

    expect(await screen.findByText('M-SKU-1')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Go to next page' }));

    await waitFor(() => {
      expect(apiGetMock).toHaveBeenCalledWith(
        expect.stringMatching(/channel-ops\/movements.*page=2/),
        expect.any(Object)
      );
    });
    expect(await screen.findByText('M-SKU-2')).toBeInTheDocument();
  });
});
