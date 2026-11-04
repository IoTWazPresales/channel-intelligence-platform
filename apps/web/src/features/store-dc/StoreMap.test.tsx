import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { StoreMap } from './StoreMap';
import type { StoreMapPayload } from './types';

const hoisted = vi.hoisted(() => ({
  payload: null as StoreMapPayload | null,
  posted: [] as unknown[],
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async () => hoisted.payload),
  apiPost: vi.fn(async (_url: string, body: unknown) => {
    hoisted.posted.push(body);
    return {};
  }),
  safeDisplayError: (error: unknown) => String(error),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function payload(): StoreMapPayload {
  return {
    customers: [
      { id: 1, code: 'SDC-C1', name: 'SDC-C1' },
      { id: 2, code: 'SDC-C2', name: 'SDC-C2' },
    ],
    legend: { formula: "last week's units / (last week's units + stock on hand)", best: 'higher', worst: 'lower' },
    stores: [
      {
        customer_id: 1,
        customer_name: 'SDC-C1',
        site_label: 'SDC-SITE-A',
        place_name: null,
        latitude: 1.5,
        longitude: 2.5,
        pinned: true,
        last_week_units: 6,
        stock_on_hand: 4,
        weeks_of_cover: 0.67,
        sell_through: 0.6,
        lines: [{ product_id: 9, sku: 'SDC-SKU', product_name: 'SDC-SKU', units: 6, stock_on_hand: 4, weeks_of_cover: 0.67 }],
      },
      {
        customer_id: 2,
        customer_name: 'SDC-C2',
        site_label: 'SDC-SITE-A',
        place_name: null,
        latitude: 1.5,
        longitude: 2.5,
        pinned: true,
        last_week_units: 1,
        stock_on_hand: 9,
        weeks_of_cover: 9,
        sell_through: 0.1,
        lines: [],
      },
      {
        customer_id: 1,
        customer_name: 'SDC-C1',
        site_label: 'SDC-SITE-B',
        place_name: null,
        latitude: null,
        longitude: null,
        pinned: false,
        last_week_units: 2,
        stock_on_hand: 2,
        weeks_of_cover: 1,
        sell_through: 0.5,
        lines: [],
      },
    ],
  };
}

describe('StoreMap', () => {
  it('draws one dot per store, shows the legend, and saves a pin without writing a place name', async () => {
    hoisted.payload = payload();
    hoisted.posted = [];
    wrap(<StoreMap />);
    expect(await screen.findByRole('button', { name: 'SDC-C1' })).toBeInTheDocument();
    expect(screen.getByTestId('store-map-legend')).toHaveTextContent(/Worst/);
    expect(screen.getByTestId('store-map')).toHaveTextContent(/last week's units/);
    expect(screen.getAllByTestId('store-dot')).toHaveLength(2);
    expect(screen.queryByText(/Durban/i)).toBeNull();
    fireEvent.mouseEnter(screen.getAllByTestId('store-dot')[0]);
    expect(screen.getByTestId('store-map-hover')).toHaveTextContent('Last week');
    expect(screen.getByTestId('store-map-hover')).toHaveTextContent('Stock on hand');
    expect(screen.getByTestId('store-map-hover')).toHaveTextContent('Weeks of cover');
    fireEvent.click(screen.getAllByTestId('store-dot')[0]);
    expect(screen.getByTestId('store-map-lines')).toHaveTextContent('SDC-SKU');
    fireEvent.click(screen.getByRole('button', { name: 'SDC-C2' }));
    await waitFor(() => expect(screen.getAllByTestId('store-dot')).toHaveLength(1));
    fireEvent.click(screen.getByRole('button', { name: 'All customers' }));
    expect(screen.getByTestId('store-map-unpinned')).toHaveTextContent('SDC-SITE-B');
    fireEvent.click(screen.getByTestId('drop-pin'));
    fireEvent.change(screen.getByTestId('pin-latitude'), { target: { value: '3' } });
    fireEvent.change(screen.getByTestId('pin-longitude'), { target: { value: '4' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save pin' }));
    await waitFor(() => expect(hoisted.posted).toEqual([
      { customer_id: 1, site_label: 'SDC-SITE-B', latitude: 3, longitude: 4 },
    ]));
    const canvas = screen.getByTestId('store-map-canvas');
    const list = screen.getByTestId('store-map-unpinned');
    expect(canvas.getAttribute('data-height-xs')).toBe(list.getAttribute('data-height-xs'));
    expect(canvas.getAttribute('data-height-md')).toBe(list.getAttribute('data-height-md'));
    expect(screen.getByTestId('store-map-unpinned-scroll')).toBeInTheDocument();
  });

  it('filters the unpinned list by place name and keeps the store code as the pin key', async () => {
    hoisted.payload = payload();
    hoisted.payload = {
      ...payload(),
      stores: [
        ...payload().stores.filter((store) => store.pinned),
        {
          customer_id: 1,
          customer_name: 'SDC-C1',
          site_label: 'SDC-SITE-B',
          place_name: 'North Shed',
          latitude: null,
          longitude: null,
          pinned: false,
          last_week_units: 2,
          stock_on_hand: 2,
          weeks_of_cover: 1,
          sell_through: 0.5,
          lines: [],
        },
        {
          customer_id: 1,
          customer_name: 'SDC-C1',
          site_label: 'SDC-SITE-C',
          place_name: 'East Yard',
          latitude: null,
          longitude: null,
          pinned: false,
          last_week_units: 1,
          stock_on_hand: 1,
          weeks_of_cover: 1,
          sell_through: 0.5,
          lines: [],
        },
      ],
    };
    hoisted.posted = [];
    wrap(<StoreMap />);
    expect(await screen.findByText('North Shed')).toBeInTheDocument();
    expect(screen.getByTestId('store-map-search')).toBeInTheDocument();
    expect(screen.getByTestId('store-map-unpinned')).toHaveTextContent('North Shed');
    expect(screen.getByTestId('store-map-unpinned')).toHaveTextContent('SDC-SITE-B');
    expect(screen.getByTestId('store-map-unpinned')).toHaveTextContent('East Yard');
    fireEvent.change(screen.getByTestId('store-map-search'), { target: { value: 'north' } });
    expect(screen.getByTestId('store-map-unpinned')).toHaveTextContent('North Shed');
    expect(screen.getByTestId('store-map-unpinned')).not.toHaveTextContent('East Yard');
    fireEvent.click(screen.getByTestId('drop-pin'));
    fireEvent.change(screen.getByTestId('pin-latitude'), { target: { value: '3' } });
    fireEvent.change(screen.getByTestId('pin-longitude'), { target: { value: '4' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save pin' }));
    await waitFor(() => expect(hoisted.posted).toEqual([
      { customer_id: 1, site_label: 'SDC-SITE-B', latitude: 3, longitude: 4 },
    ]));
  });
});
