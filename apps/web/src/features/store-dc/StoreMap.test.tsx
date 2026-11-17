import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { apiPost } from '@/lib/api';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { StoreMap } from './StoreMap';
import type { StoreMapPayload } from './types';

const hoisted = vi.hoisted(() => ({
  payload: null as StoreMapPayload | null,
  posted: [] as unknown[],
  postError: null as Error | null,
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async () => hoisted.payload),
  apiPost: vi.fn(async (_url: string, body: { customer_id: number; site_label: string; latitude: number; longitude: number }) => {
    hoisted.posted.push(body);
    if (hoisted.postError) throw hoisted.postError;
    const saved = { ...hoisted.payload!.stores.find((store) => store.customer_id === body.customer_id
      && store.site_label === body.site_label)!, ...body, pinned: true, location_suggestion: null };
    hoisted.payload = { ...hoisted.payload!, stores: hoisted.payload!.stores.map((store) =>
      store.customer_id === body.customer_id && store.site_label === body.site_label ? saved : store) };
    return saved;
  }),
  safeDisplayError: (error: unknown) => (error instanceof Error ? error.message : String(error)),
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

function suggestedPayload(): StoreMapPayload {
  const result = payload();
  result.stores[2].location_suggestion = {
    outcome: 'suggest', reason: 'match', place: 'Example Place',
    latitude: -33.9, longitude: 18.4, licence: 'GeoNames CC BY 4.0',
  };
  return result;
}

describe('StoreMap', () => {
  beforeEach(() => {
    hoisted.posted = [];
    hoisted.postError = null;
    vi.clearAllMocks();
    // jsdom lacks PointerEvent; preserve real pointer coordinates for fireEvent.
    vi.stubGlobal('PointerEvent', class extends MouseEvent {
      pointerId: number;
      constructor(type: string, init: PointerEventInit = {}) {
        super(type, init);
        this.pointerId = init.pointerId ?? 1;
      }
    });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

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

  it('confirms a suggested place through the pin save and leaves a manual store on the pin form', async () => {
    hoisted.payload = {
      ...payload(),
      stores: [
        {
          customer_id: 1,
          customer_name: 'SDC-C1',
          site_label: 'SDC-SITE-B',
          place_name: null,
          latitude: null,
          longitude: null,
          pinned: false,
          location_suggestion: {
            outcome: 'suggest',
            reason: 'match',
            place: 'Example Place',
            latitude: -33.9,
            longitude: 18.4,
            licence: 'GeoNames CC BY 4.0',
          },
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
          place_name: null,
          latitude: null,
          longitude: null,
          pinned: false,
          location_suggestion: {
            outcome: 'manual',
            reason: 'multiple',
            place: null,
            latitude: null,
            longitude: null,
            licence: 'GeoNames CC BY 4.0',
          },
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
    const pin = await screen.findByTestId('store-dot-unconfirmed');
    expect(pin).toHaveAttribute('data-pin-state', 'unconfirmed');
    expect(pin).toHaveAttribute('data-latitude', '-33.9');
    expect(pin).toHaveAttribute('data-longitude', '18.4');
    expect(screen.queryByText('No store has coordinates yet.')).toBeNull();
    expect(screen.getByTestId('store-map-unpinned')).not.toHaveTextContent('SDC-SITE-B');
    expect(screen.getByTestId('store-map-unpinned')).toHaveTextContent('SDC-SITE-C');
    expect(screen.getAllByTestId('store-dot-unconfirmed')).toHaveLength(1);
    fireEvent.mouseEnter(pin);
    const hover = screen.getByTestId('store-map-hover');
    for (const text of ['confirm location', 'Example Place', 'GeoNames CC BY 4.0', 'SDC-SITE-B', 'SDC-C1',
      'Last week 2 units', 'Stock on hand 2', 'Weeks of cover 1']) {
      expect(hover).toHaveTextContent(text);
    }
    vi.spyOn(screen.getByTestId('store-map-canvas'), 'getBoundingClientRect').mockReturnValue({
      x: 0, y: 0, left: 0, top: 0, width: 1000, height: 500, right: 1000, bottom: 500, toJSON: () => ({}),
    });
    fireEvent.pointerDown(pin, { pointerId: 1, button: 0, clientX: 500, clientY: 250 });
    fireEvent.pointerUp(pin, { pointerId: 1, clientX: 500, clientY: 250 });
    expect(pin).toHaveAttribute('data-latitude', '-33.9');
    expect(pin).toHaveAttribute('data-longitude', '18.4');
    fireEvent.click(pin);
    expect(screen.getByTestId('place-suggestion')).toHaveTextContent('Example Place');
    expect(screen.getByTestId('place-suggestion')).toHaveTextContent('GeoNames CC BY 4.0');
    expect(screen.getByTestId('place-manual')).toHaveTextContent('More than one place matches');
    expect(screen.getAllByTestId('confirm-suggestion')).toHaveLength(1);
    expect(hoisted.posted).toEqual([]);
    expect(apiPost).not.toHaveBeenCalled();
    expect(within(screen.getByTestId('store-map-canvas')).getByTestId('confirm-suggestion')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('drop-pin'));
    expect(screen.getByTestId('pin-latitude')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('confirm-suggestion'));
    await waitFor(() => expect(hoisted.posted).toEqual([
      { customer_id: 1, site_label: 'SDC-SITE-B', latitude: -33.9, longitude: 18.4 },
    ]));
    expect(apiPost).toHaveBeenCalledTimes(1);
    expect(apiPost).toHaveBeenCalledWith('/api/v1/store-dc/pins', {
      customer_id: 1, site_label: 'SDC-SITE-B', latitude: -33.9, longitude: 18.4,
    });
    await waitFor(() => expect(screen.queryByTestId('store-dot-unconfirmed')).toBeNull());
    expect(screen.getByTestId('store-dot')).toBeInTheDocument();
  });

  it('shows a failed suggestion confirm beside the suggestion without opening the pin form', async () => {
    hoisted.payload = {
      ...payload(),
      stores: [
        {
          customer_id: 1,
          customer_name: 'SDC-C1',
          site_label: 'SDC-SITE-B',
          place_name: null,
          latitude: null,
          longitude: null,
          pinned: false,
          location_suggestion: {
            outcome: 'suggest',
            reason: 'match',
            place: 'Example Place',
            latitude: -33.9,
            longitude: 18.4,
            licence: 'GeoNames CC BY 4.0',
          },
          last_week_units: 2,
          stock_on_hand: 2,
          weeks_of_cover: 1,
          sell_through: 0.5,
          lines: [],
        },
      ],
    };
    hoisted.posted = [];
    hoisted.postError = new Error('pin refused');
    wrap(<StoreMap />);
    fireEvent.click(await screen.findByTestId('store-dot-unconfirmed'));
    fireEvent.click(screen.getByTestId('confirm-suggestion'));
    expect(await screen.findByTestId('pin-error')).toHaveTextContent('pin refused');
    expect(screen.getByTestId('place-suggestion')).toBeInTheDocument();
    expect(screen.queryByTestId('pin-latitude')).toBeNull();
    expect(screen.getByTestId('confirm-suggestion')).toBeEnabled();
    expect(screen.getByTestId('store-dot-unconfirmed')).toHaveAttribute('data-latitude', '-33.9');
    expect(within(screen.getByTestId('store-map-canvas')).getByTestId('pin-error')).toHaveTextContent('pin refused');
    expect(hoisted.posted).toEqual([
      { customer_id: 1, site_label: 'SDC-SITE-B', latitude: -33.9, longitude: 18.4 },
    ]);
    hoisted.postError = null;
    fireEvent.click(screen.getByTestId('confirm-suggestion'));
    await waitFor(() => expect(screen.queryByTestId('store-dot-unconfirmed')).toBeNull());
    expect(apiPost).toHaveBeenCalledTimes(2);
  });

  it('rejects a pin locally and keeps it in the manual list across customer filters', async () => {
    hoisted.payload = suggestedPayload();
    wrap(<StoreMap />);
    fireEvent.click(await screen.findByTestId('store-dot-unconfirmed'));
    fireEvent.click(within(screen.getByTestId('store-map-canvas')).getByTestId('reject-suggestion'));
    expect(screen.queryByTestId('store-dot-unconfirmed')).toBeNull();
    expect(screen.getAllByTestId('store-dot')).toHaveLength(2);
    expect(screen.getByTestId('store-map-unpinned')).toHaveTextContent('SDC-SITE-B');
    fireEvent.click(screen.getByRole('button', { name: 'SDC-C2' }));
    expect(screen.getByTestId('store-map-unpinned')).not.toHaveTextContent('SDC-SITE-B');
    fireEvent.click(screen.getByRole('button', { name: 'All customers' }));
    expect(screen.queryByTestId('store-dot-unconfirmed')).toBeNull();
    fireEvent.click(screen.getByTestId('drop-pin'));
    expect(screen.getByTestId('pin-latitude')).toBeInTheDocument();
    expect(hoisted.posted).toEqual([]);
    expect(apiPost).not.toHaveBeenCalled();
    fireEvent.change(screen.getByTestId('pin-latitude'), { target: { value: '-30' } });
    fireEvent.change(screen.getByTestId('pin-longitude'), { target: { value: '20' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save pin' }));
    await waitFor(() => expect(hoisted.posted).toEqual([
      { customer_id: 1, site_label: 'SDC-SITE-B', latitude: -30, longitude: 20 },
    ]));
  });

  it('projects and filters confirmed and unconfirmed pins together, with manual stores beside them', async () => {
    hoisted.payload = suggestedPayload();
    hoisted.payload.stores.push({ ...payload().stores[2], customer_id: 2, customer_name: 'SDC-C2', site_label: 'Manual C2' });
    wrap(<StoreMap />);
    const pin = await screen.findByTestId('store-dot-unconfirmed');
    const solid = screen.getAllByTestId('store-dot')[0];
    expect(parseFloat(getComputedStyle(pin).left)).toBeGreaterThan(parseFloat(getComputedStyle(solid).left));
    expect(parseFloat(getComputedStyle(pin).top)).toBeGreaterThan(parseFloat(getComputedStyle(solid).top));
    expect(getComputedStyle(pin).borderStyle).toBe('dashed');
    expect(getComputedStyle(solid).borderStyle).toBe('solid');
    fireEvent.click(screen.getByRole('button', { name: 'SDC-C2' }));
    expect(screen.queryByTestId('store-dot-unconfirmed')).toBeNull();
    expect(screen.getAllByTestId('store-dot')).toHaveLength(1);
    expect(screen.getByTestId('store-map-unpinned')).toHaveTextContent('Manual C2');
    fireEvent.click(screen.getByRole('button', { name: 'SDC-C1' }));
    expect(screen.getAllByTestId('store-dot-unconfirmed')).toHaveLength(1);
    expect(screen.getAllByTestId('store-dot')).toHaveLength(1);
    expect(screen.getByTestId('store-map-unpinned')).not.toHaveTextContent('Manual C2');
    expect(hoisted.posted).toEqual([]);
  });

  it('drags using the current projection and posts the displayed coordinates only on confirm', async () => {
    hoisted.payload = suggestedPayload();
    wrap(<StoreMap />);
    const pin = await screen.findByTestId('store-dot-unconfirmed');
    vi.spyOn(screen.getByTestId('store-map-canvas'), 'getBoundingClientRect').mockReturnValue({
      x: 0, y: 0, left: 0, top: 0, width: 1000, height: 500, right: 1000, bottom: 500, toJSON: () => ({}),
    });
    fireEvent.pointerDown(pin, { pointerId: 1, button: 0, clientX: 400, clientY: 300 });
    fireEvent.pointerMove(pin, { pointerId: 1, clientX: 450, clientY: 275 });
    fireEvent.pointerMove(pin, { pointerId: 1, clientX: 500, clientY: 250 });
    expect(Number(pin.dataset.latitude)).toBeCloseTo(-29.7936, 6);
    expect(Number(pin.dataset.longitude)).toBeCloseTo(20.2444, 6);
    fireEvent.pointerUp(pin, { pointerId: 1, clientX: 500, clientY: 250 });
    const latitude = Number(pin.dataset.latitude);
    const longitude = Number(pin.dataset.longitude);
    expect(latitude).toBeCloseTo(-29.7936, 6);
    expect(longitude).toBeCloseTo(20.2444, 6);
    expect(hoisted.posted).toEqual([]);
    expect(apiPost).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'SDC-C2' }));
    fireEvent.click(screen.getByRole('button', { name: 'All customers' }));
    expect(Number(screen.getByTestId('store-dot-unconfirmed').dataset.latitude)).toBe(latitude);
    fireEvent.click(screen.getByTestId('confirm-suggestion'));
    await waitFor(() => expect(hoisted.posted).toEqual([
      { customer_id: 1, site_label: 'SDC-SITE-B', latitude, longitude },
    ]));
    expect(apiPost).toHaveBeenCalledTimes(1);
  });

  it('can drag a lone suggestion without confirmed pins', async () => {
    hoisted.payload = suggestedPayload();
    hoisted.payload.stores = hoisted.payload.stores.filter((store) => !store.pinned);
    wrap(<StoreMap />);
    const pin = await screen.findByTestId('store-dot-unconfirmed');
    vi.spyOn(screen.getByTestId('store-map-canvas'), 'getBoundingClientRect').mockReturnValue({
      x: 0, y: 0, left: 0, top: 0, width: 1000, height: 500, right: 1000, bottom: 500, toJSON: () => ({}),
    });
    fireEvent.pointerDown(pin, { pointerId: 1, button: 0, clientX: 500, clientY: 250 });
    fireEvent.pointerMove(pin, { pointerId: 1, clientX: 600, clientY: 200 });
    fireEvent.pointerUp(pin, { pointerId: 1, clientX: 600, clientY: 200 });
    expect(Number(pin.dataset.latitude)).toBeCloseTo(-33.668, 6);
    expect(Number(pin.dataset.longitude)).toBeCloseTo(18.632, 6);
    expect(hoisted.posted).toEqual([]);
  });
});
