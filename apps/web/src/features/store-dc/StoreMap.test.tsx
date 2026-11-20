import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { apiPost } from '@/lib/api';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { StoreMap } from './StoreMap';
import { storeMapBounds } from './storeMapLayout';
import type { StoreMapPayload } from './types';

/** The marker dot inside a pin's click target: the same element the Shipments map draws. */
function dotOf(pin: HTMLElement): HTMLElement {
  return pin.querySelector('[data-marker-dot]') as HTMLElement;
}

const hoisted = vi.hoisted(() => ({
  payload: null as StoreMapPayload | null,
  posted: [] as unknown[],
  postError: null as Error | null,
  confirmed: [] as { url: string; body: unknown }[],
  rejectLabels: [] as string[],
}));

type PinBody = { customer_id: number; site_label: string; latitude?: number; longitude?: number };

// What the server does for a confirm: no coordinates = the proposal, coordinates = the edit.
function applyConfirm(body: PinBody) {
  const store = hoisted.payload!.stores.find((item) => item.customer_id === body.customer_id
    && item.site_label === body.site_label);
  const suggestion = store?.location_suggestion;
  if (!store) throw new Error('Store not found for this customer');
  const latitude = body.latitude ?? (suggestion?.outcome === 'suggest' ? suggestion.latitude : null);
  const longitude = body.longitude ?? (suggestion?.outcome === 'suggest' ? suggestion.longitude : null);
  if (latitude == null || longitude == null) return null;
  const saved = { ...store, latitude, longitude, pinned: true, location_suggestion: null };
  hoisted.payload = { ...hoisted.payload!, stores: hoisted.payload!.stores.map((item) => item === store ? saved : item) };
  return saved;
}

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async () => hoisted.payload),
  apiPost: vi.fn(async (url: string, body: PinBody | { pins: PinBody[] }) => {
    if (url.endsWith('/pins/confirm')) {
      hoisted.confirmed.push({ url, body });
      if (hoisted.postError) throw hoisted.postError;
      const saved = applyConfirm(body as PinBody);
      if (!saved) throw new Error('No proposal for this store; send coordinates');
      return saved;
    }
    if (url.endsWith('/pins/confirm-bulk')) {
      hoisted.confirmed.push({ url, body });
      if (hoisted.postError) throw hoisted.postError;
      const saved = [] as unknown[];
      const failed = [] as { customer_id: number; site_label: string; error: string }[];
      for (const pin of (body as { pins: PinBody[] }).pins) {
        const result = hoisted.rejectLabels.includes(pin.site_label) ? null : applyConfirm(pin);
        if (result) saved.push(result);
        else failed.push({ customer_id: pin.customer_id, site_label: pin.site_label, error: 'No proposal for this store; send coordinates' });
      }
      return { saved, failed };
    }
    const pin = body as Required<PinBody>;
    hoisted.posted.push(pin);
    if (hoisted.postError) throw hoisted.postError;
    const saved = { ...hoisted.payload!.stores.find((store) => store.customer_id === pin.customer_id
      && store.site_label === pin.site_label)!, ...pin, pinned: true, location_suggestion: null };
    hoisted.payload = { ...hoisted.payload!, stores: hoisted.payload!.stores.map((store) =>
      store.customer_id === pin.customer_id && store.site_label === pin.site_label ? saved : store) };
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
        // Far enough from customer 1's site that the two pins are not one cluster.
        latitude: 1.5,
        longitude: 12.5,
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
    hoisted.confirmed = [];
    hoisted.rejectLabels = [];
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
    expect(canvas).toHaveAttribute('data-map-canvas');
    expect(getComputedStyle(canvas).aspectRatio).toMatch(/^1000\s*\/\s*646$/);
    // Same box and basemap; the view zooms to the pins but keeps the 1000/646 aspect.
    const [, , viewWidth, viewHeight] = (within(canvas).getByRole('img').getAttribute('viewBox') ?? '')
      .split(' ')
      .map(Number);
    expect(viewWidth / viewHeight).toBeCloseTo(1000 / 646);
    expect(getComputedStyle(list).height).toBe('646px');
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
    // Same marker as the Shipments map: hollow dashed when proposed, solid when saved.
    expect(getComputedStyle(dotOf(pin)).borderStyle).toBe('dashed');
    expect(dotOf(pin)).toHaveAttribute('data-hollow', 'true');
    expect(dotOf(solid)).toHaveAttribute('data-hollow', 'false');
    expect(getComputedStyle(dotOf(solid)).borderStyle).not.toBe('dashed');
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
    const fitted = storeMapBounds([
      { latitude: 1.5, longitude: 2.5 }, { latitude: -33.9, longitude: 18.4 },
    ]);
    vi.spyOn(screen.getByTestId('store-map-canvas'), 'getBoundingClientRect').mockReturnValue({
      x: 0, y: 0, left: 0, top: 0, width: 1000, height: 500, right: 1000, bottom: 500, toJSON: () => ({}),
    });
    fireEvent.pointerDown(pin, { pointerId: 1, button: 0, clientX: 400, clientY: 300 });
    fireEvent.pointerMove(pin, { pointerId: 1, clientX: 450, clientY: 275 });
    fireEvent.pointerMove(pin, { pointerId: 1, clientX: 500, clientY: 250 });
    // The view is the fit to the pins at pointer down, so a 10% drag moves each axis by 10% of
    // that view's span, from the pin's (-33.9, 18.4). The map itself does not pan.
    const expectedLatitude = -33.9 + 0.1 * (fitted.maxLat - fitted.minLat);
    const expectedLongitude = 18.4 + 0.1 * (fitted.maxLon - fitted.minLon);
    expect(Number(pin.dataset.latitude)).toBeCloseTo(expectedLatitude, 5);
    expect(Number(pin.dataset.longitude)).toBeCloseTo(expectedLongitude, 5);
    fireEvent.pointerUp(pin, { pointerId: 1, clientX: 500, clientY: 250 });
    const latitude = Number(pin.dataset.latitude);
    const longitude = Number(pin.dataset.longitude);
    expect(latitude).toBeCloseTo(expectedLatitude, 5);
    expect(longitude).toBeCloseTo(expectedLongitude, 5);
    expect(screen.getByTestId('map-reset-view')).toBeDisabled();
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

  describe('proposed pins review', () => {
    function manyProposals(): StoreMapPayload {
      const base = suggestedPayload();
      // Ten degrees apart, so each proposal is its own pin rather than one cluster.
      let nextLongitude = 25;
      const proposal = (label: string, confidence: number, place: string, over = {}) => ({
        ...base.stores[2],
        site_label: label,
        location_suggestion: {
          outcome: 'suggest' as const, reason: 'match' as const, place, latitude: -30,
          longitude: (nextLongitude += 10),
          licence: 'GeoNames CC BY 4.0', method: 'contained' as const, confidence, ambiguous: false,
          alternatives: [], ...over,
        },
      });
      return {
        ...base,
        stores: [
          ...base.stores.filter((store) => store.pinned),
          proposal('Label One', 0.9, 'Placeone'),
          proposal('Label Two', 0.85, 'Placetwo'),
          proposal('Label Three', 0.5, 'Placethree', { method: 'fuzzy' }),
        ],
      };
    }

    it('shows a legend with filled confirmed and hollow proposed dots', async () => {
      hoisted.payload = suggestedPayload();
      wrap(<StoreMap />);
      await screen.findByTestId('store-dot-unconfirmed');
      const legend = screen.getByTestId('store-pin-legend');
      expect(legend).toHaveTextContent('Confirmed pin');
      expect(legend).toHaveTextContent('Proposed pin');
      expect(getComputedStyle(within(legend).getByTestId('legend-proposed-dot')).borderStyle).toBe('dashed');
      expect(within(legend).getByTestId('legend-confirmed-dot')).toHaveAttribute('data-hollow', 'false');
      // the dot on the map matches the legend: hollow when proposed
      const dot = dotOf(screen.getByTestId('store-dot-unconfirmed'));
      expect(getComputedStyle(dot).backgroundColor).toMatch(/^(transparent|rgba\(0, 0, 0, 0\))$/);
      expect(getComputedStyle(dot).borderStyle).toBe('dashed');
    });

    it('lists the proposals with a Confirm that uses the confirm route and saves one pin', async () => {
      hoisted.payload = manyProposals();
      wrap(<StoreMap />);
      await screen.findAllByTestId('proposed-pin-row');
      expect(screen.getByTestId('proposed-pins')).toHaveTextContent('Proposed pins (3)');
      const rows = screen.getAllByTestId('proposed-pin-row');
      expect(rows[0]).toHaveTextContent('Label One');
      expect(rows[0]).toHaveTextContent('Placeone');
      expect(apiPost).not.toHaveBeenCalled();
      fireEvent.click(within(rows[0]).getByTestId('proposal-confirm'));
      await waitFor(() => expect(hoisted.confirmed).toEqual([
        { url: '/api/v1/store-dc/pins/confirm', body: { customer_id: 1, site_label: 'Label One' } },
      ]));
      await waitFor(() => expect(screen.getAllByTestId('proposed-pin-row')).toHaveLength(2));
      expect(screen.getAllByTestId('store-dot')).toHaveLength(3);
      expect(screen.getAllByTestId('store-dot-unconfirmed')).toHaveLength(2);
    });

    it('confirms the selected rows in one bulk request', async () => {
      hoisted.payload = manyProposals();
      wrap(<StoreMap />);
      await screen.findAllByTestId('proposed-pin-row');
      fireEvent.click(screen.getByTestId('proposal-select-high'));
      expect(screen.getByTestId('proposal-confirm-selected')).toHaveTextContent('Confirm selected (2)');
      fireEvent.click(screen.getByTestId('proposal-confirm-selected'));
      await waitFor(() => expect(hoisted.confirmed).toEqual([
        {
          url: '/api/v1/store-dc/pins/confirm-bulk',
          body: { pins: [{ customer_id: 1, site_label: 'Label One' }, { customer_id: 1, site_label: 'Label Two' }] },
        },
      ]));
      await waitFor(() => expect(screen.getAllByTestId('proposed-pin-row')).toHaveLength(1));
      expect(screen.getByTestId('proposed-pin-row')).toHaveTextContent('Label Three');
    });

    it('keeps a row the server could not save and shows why beside that row', async () => {
      hoisted.payload = manyProposals();
      hoisted.rejectLabels = ['Label Two'];
      wrap(<StoreMap />);
      await screen.findAllByTestId('proposed-pin-row');
      fireEvent.click(screen.getByTestId('proposal-select-high'));
      fireEvent.click(screen.getByTestId('proposal-confirm-selected'));
      await waitFor(() => expect(screen.getAllByTestId('proposed-pin-row')).toHaveLength(2));
      const rows = screen.getAllByTestId('proposed-pin-row');
      expect(rows[0]).toHaveTextContent('Label Two');
      expect(within(rows[0]).getByTestId('proposal-error')).toHaveTextContent('No proposal');
      expect(within(rows[1]).queryByTestId('proposal-error')).toBeNull();
    });

    it('Edit saves the typed coordinates through the confirm route', async () => {
      hoisted.payload = manyProposals();
      wrap(<StoreMap />);
      const rows = await screen.findAllByTestId('proposed-pin-row');
      fireEvent.click(within(rows[0]).getByTestId('proposal-edit'));
      fireEvent.change(within(screen.getByTestId('proposal-lat')).getByRole('textbox'), { target: { value: '-26.2' } });
      fireEvent.change(within(screen.getByTestId('proposal-lon')).getByRole('textbox'), { target: { value: '28.1' } });
      fireEvent.click(screen.getByTestId('proposal-save'));
      await waitFor(() => expect(hoisted.confirmed).toEqual([
        {
          url: '/api/v1/store-dc/pins/confirm',
          body: { customer_id: 1, site_label: 'Label One', latitude: -26.2, longitude: 28.1 },
        },
      ]));
    });

    it('Skip moves the store to the manual list without saving, and a failed confirm shows an error', async () => {
      hoisted.payload = manyProposals();
      wrap(<StoreMap />);
      const rows = await screen.findAllByTestId('proposed-pin-row');
      fireEvent.click(within(rows[2]).getByTestId('proposal-skip'));
      expect(screen.getAllByTestId('proposed-pin-row')).toHaveLength(2);
      expect(screen.getByTestId('store-map-unpinned')).toHaveTextContent('Label Three');
      expect(apiPost).not.toHaveBeenCalled();
      hoisted.postError = new Error('confirm refused');
      fireEvent.click(within(screen.getAllByTestId('proposed-pin-row')[0]).getByTestId('proposal-confirm'));
      expect(await screen.findByTestId('proposal-error')).toHaveTextContent('confirm refused');
      expect(screen.getAllByTestId('proposed-pin-row')).toHaveLength(2);
    });

    it('says so when no store has a proposal', async () => {
      hoisted.payload = payload();
      wrap(<StoreMap />);
      await screen.findByTestId('store-map-canvas');
      expect(screen.getByTestId('proposed-pins')).toHaveTextContent('No proposed pins');
    });
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
    // A lone pin gets the minimum continent-scale view centred on it: a 10% drag of its span.
    const view = storeMapBounds([{ latitude: -33.9, longitude: 18.4 }]);
    expect(view.maxLon - view.minLon).toBeGreaterThanOrEqual(60);
    expect(Number(pin.dataset.latitude)).toBeCloseTo(-33.9 + 0.1 * (view.maxLat - view.minLat), 5);
    expect(Number(pin.dataset.longitude)).toBeCloseTo(18.4 + 0.1 * (view.maxLon - view.minLon), 5);
    expect(hoisted.posted).toEqual([]);
  });

  describe('pan, zoom and reset', () => {
    const rect = {
      x: 0, y: 0, left: 0, top: 0, width: 1000, height: 646, right: 1000, bottom: 646, toJSON: () => ({}),
    };
    const viewBoxOf = () => (within(screen.getByTestId('store-map-canvas')).getByRole('img').getAttribute('viewBox') ?? '')
      .split(' ').map(Number);

    async function mapReady() {
      hoisted.payload = suggestedPayload();
      wrap(<StoreMap />);
      const canvas = await screen.findByTestId('store-map-canvas');
      await screen.findByTestId('store-dot-unconfirmed');
      vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(rect);
      return canvas;
    }

    it('drags the background to pan the view without touching any stored coordinate', async () => {
      const canvas = await mapReady();
      const before = viewBoxOf();
      const pins = screen.getAllByTestId(/^store-dot/).map((pin) => [pin.dataset.latitude, pin.dataset.longitude]);
      expect(getComputedStyle(canvas).cursor).toBe('grab');
      expect(screen.getByTestId('map-reset-view')).toBeDisabled();
      fireEvent.pointerDown(canvas, { pointerId: 1, button: 0, clientX: 500, clientY: 300 });
      fireEvent.pointerMove(canvas, { pointerId: 1, clientX: 400, clientY: 340 });
      expect(getComputedStyle(canvas).cursor).toBe('grabbing');
      fireEvent.pointerUp(canvas, { pointerId: 1, clientX: 400, clientY: 340 });
      const after = viewBoxOf();
      // Dragging left shows what lies east; dragging down shows what lies north.
      expect(after[0]).toBeGreaterThan(before[0]);
      expect(after[1]).toBeLessThan(before[1]);
      expect(after[2]).toBeCloseTo(before[2]);
      expect(after[3]).toBeCloseTo(before[3]);
      expect(getComputedStyle(canvas).cursor).toBe('grab');
      expect(screen.getAllByTestId(/^store-dot/).map((pin) => [pin.dataset.latitude, pin.dataset.longitude])).toEqual(pins);
      expect(hoisted.posted).toEqual([]);
      expect(apiPost).not.toHaveBeenCalled();
    });

    it('keeps a click without movement from panning or changing the selection', async () => {
      const canvas = await mapReady();
      const before = viewBoxOf();
      fireEvent.pointerDown(canvas, { pointerId: 1, button: 0, clientX: 500, clientY: 300 });
      fireEvent.pointerMove(canvas, { pointerId: 1, clientX: 501, clientY: 301 });
      fireEvent.pointerUp(canvas, { pointerId: 1, clientX: 501, clientY: 301 });
      fireEvent.click(canvas);
      expect(viewBoxOf()).toEqual(before);
      expect(screen.getByTestId('map-reset-view')).toBeDisabled();
      expect(screen.queryByTestId('store-map-lines')).toBeNull();
      // A click on a confirmed pin still selects it.
      fireEvent.click(screen.getAllByTestId('store-dot')[0]);
      expect(screen.getByTestId('store-map-lines')).toBeInTheDocument();
      expect(viewBoxOf()).toEqual(before);
    });

    it('drags a proposed pin, not the map, when the gesture starts on the pin', async () => {
      await mapReady();
      const pin = screen.getByTestId('store-dot-unconfirmed');
      const latitude = pin.dataset.latitude;
      fireEvent.pointerDown(pin, { pointerId: 1, button: 0, clientX: 500, clientY: 300 });
      fireEvent.pointerMove(pin, { pointerId: 1, clientX: 450, clientY: 280 });
      fireEvent.pointerUp(pin, { pointerId: 1, clientX: 450, clientY: 280 });
      expect(pin.dataset.latitude).not.toBe(latitude);
      // The map was not panned: its view is still the automatic fit.
      expect(screen.getByTestId('map-reset-view')).toBeDisabled();
    });

    it('resets the view, and zooms in and out with the buttons', async () => {
      const canvas = await mapReady();
      const before = viewBoxOf();
      fireEvent.pointerDown(canvas, { pointerId: 1, button: 0, clientX: 500, clientY: 300 });
      fireEvent.pointerMove(canvas, { pointerId: 1, clientX: 400, clientY: 300 });
      fireEvent.pointerUp(canvas, { pointerId: 1, clientX: 400, clientY: 300 });
      expect(viewBoxOf()).not.toEqual(before);
      fireEvent.click(screen.getByRole('button', { name: 'Reset view' }));
      expect(viewBoxOf()).toEqual(before);
      expect(screen.getByTestId('map-reset-view')).toBeDisabled();

      fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }));
      const zoomed = viewBoxOf();
      expect(zoomed[2]).toBeLessThan(before[2]);
      expect(zoomed[2] / zoomed[3]).toBeCloseTo(1000 / 646);
      expect(screen.getByTestId('map-reset-view')).toBeEnabled();
      fireEvent.click(screen.getByRole('button', { name: 'Zoom out' }));
      expect(viewBoxOf()[2]).toBeCloseTo(before[2]);
      fireEvent.click(screen.getByRole('button', { name: 'Reset view' }));
      expect(viewBoxOf()).toEqual(before);
    });

    it('pans under a customer filter, and a new filter fits the view to its pins again', async () => {
      const canvas = await mapReady();
      fireEvent.click(screen.getByRole('button', { name: 'SDC-C1' }));
      const filtered = viewBoxOf();
      fireEvent.pointerDown(canvas, { pointerId: 1, button: 0, clientX: 500, clientY: 300 });
      fireEvent.pointerMove(canvas, { pointerId: 1, clientX: 450, clientY: 300 });
      fireEvent.pointerUp(canvas, { pointerId: 1, clientX: 450, clientY: 300 });
      expect(viewBoxOf()[0]).toBeGreaterThan(filtered[0]);
      expect(screen.getAllByTestId('store-dot')).toHaveLength(1);
      fireEvent.click(screen.getByRole('button', { name: 'SDC-C2' }));
      expect(screen.getByTestId('map-reset-view')).toBeDisabled();
    });
  });

  it('does not draw a store with unusable coordinates; it stays in the No coordinates list', async () => {
    const base = payload();
    hoisted.payload = {
      ...base,
      stores: [
        base.stores[0],
        { ...base.stores[1], site_label: 'Blank site', latitude: null, longitude: null },
        { ...base.stores[1], site_label: 'Zero site', latitude: 0, longitude: 0 },
        { ...base.stores[1], site_label: 'Text site', latitude: Number.NaN, longitude: 5 },
      ],
    };
    wrap(<StoreMap />);
    // The canvas is there before the data is, so wait for the usable store's dot itself.
    expect(await screen.findAllByTestId('store-dot')).toHaveLength(1);
    const list = screen.getByTestId('store-map-unpinned');
    for (const label of ['Blank site', 'Zero site', 'Text site']) expect(list).toHaveTextContent(label);
  });

  it('draws pins with the Shipments marker: selection grows the dot and sets the pressed state', async () => {
    hoisted.payload = suggestedPayload();
    wrap(<StoreMap />);
    const solid = (await screen.findAllByTestId('store-dot'))[0];
    expect(solid).toHaveAttribute('aria-pressed', 'false');
    expect(getComputedStyle(dotOf(solid)).width).toBe('11px');
    fireEvent.click(solid);
    expect(solid).toHaveAttribute('aria-pressed', 'true');
    expect(getComputedStyle(dotOf(solid)).width).toBe('16px');
    expect(dotOf(solid).parentElement).toBe(solid);
  });

  describe('clustering', () => {
    const viewBoxOf = () => (within(screen.getByTestId('store-map-canvas')).getByRole('img').getAttribute('viewBox') ?? '')
      .split(' ').map(Number);

    function store(label: string, latitude: number, longitude: number, over: Partial<StoreMapPayload['stores'][number]> = {}) {
      return {
        ...payload().stores[0],
        site_label: label,
        latitude,
        longitude,
        ...over,
      };
    }

    // Three stores within half a degree (a few px at continent scale) and one far away.
    function crowded(): StoreMapPayload {
      return {
        ...payload(),
        stores: [
          store('Near A', 10, 20, { sell_through: 1 }),
          store('Near B', 10.2, 20.2, { sell_through: 0 }),
          store('Near C', 10.1, 20.1, { sell_through: 0.5 }),
          store('Far', -20, 50),
        ],
      };
    }

    it('groups pins in one screen cell into one numbered marker at their centroid', async () => {
      hoisted.payload = crowded();
      wrap(<StoreMap />);
      const cluster = await screen.findByTestId('store-cluster');
      expect(cluster).toHaveAttribute('data-cluster-count', '3');
      expect(cluster).toHaveTextContent('3');
      expect(Number(cluster.dataset.latitude)).toBeCloseTo(10.1, 5);
      expect(Number(cluster.dataset.longitude)).toBeCloseTo(20.1, 5);
      // The members are not drawn on their own; the far store is a normal single pin.
      expect(screen.getAllByTestId('store-dot')).toHaveLength(1);
      expect(screen.getAllByTestId('store-dot')[0]).toHaveAttribute('data-latitude', '-20');
      expect(cluster).toHaveAttribute('data-pin-state', 'confirmed');
      expect(dotOf(cluster)).toHaveAttribute('data-hollow', 'false');
    });

    it('draws the Shipments marker size and never a click target over 44px', async () => {
      hoisted.payload = crowded();
      wrap(<StoreMap />);
      await screen.findByTestId('store-cluster');
      const single = screen.getByTestId('store-dot');
      // Shipments' 11px dot, not the old ~26px pin; 44px click target only where there is room.
      expect(getComputedStyle(dotOf(single)).width).toBe('11px');
      expect(parseFloat(getComputedStyle(single).width)).toBeLessThanOrEqual(44);
      const cluster = screen.getByTestId('store-cluster');
      expect(getComputedStyle(dotOf(cluster)).width).toBe('16px');
      expect(parseFloat(getComputedStyle(cluster).width)).toBeLessThanOrEqual(44);
    });

    it('shows a card with the first stores and the count while hovering a cluster', async () => {
      hoisted.payload = crowded();
      wrap(<StoreMap />);
      fireEvent.mouseEnter(await screen.findByTestId('store-cluster'));
      const card = screen.getByTestId('store-map-cluster-hover');
      expect(card).toHaveTextContent('3 stores here');
      for (const label of ['Near A', 'Near B', 'Near C']) expect(card).toHaveTextContent(label);
      fireEvent.mouseLeave(screen.getByTestId('store-cluster'));
      expect(screen.queryByTestId('store-map-cluster-hover')).toBeNull();
    });

    it('zooms the view to fit the cluster on click, and the cluster dissolves into its pins', async () => {
      hoisted.payload = crowded();
      wrap(<StoreMap />);
      fireEvent.click(await screen.findByTestId('store-cluster'));
      expect(viewBoxOf()[2]).toBeLessThan(20);
      expect(screen.queryByTestId('store-cluster')).toBeNull();
      expect(screen.getAllByTestId('store-dot')).toHaveLength(4);
      expect(screen.getByTestId('map-reset-view')).toBeEnabled();
      fireEvent.click(screen.getByRole('button', { name: 'Reset view' }));
      expect(screen.getByTestId('store-cluster')).toHaveAttribute('data-cluster-count', '3');
    });

    it('dissolves a cluster as the steward zooms in with the buttons', async () => {
      hoisted.payload = {
        ...payload(),
        stores: [store('Twin A', 10, 20), store('Twin B', 10.4, 20), store('Far', -20, 50)],
      };
      wrap(<StoreMap />);
      expect(await screen.findByTestId('store-cluster')).toHaveAttribute('data-cluster-count', '2');
      for (let step = 0; step < 4; step += 1) fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }));
      expect(screen.queryByTestId('store-cluster')).toBeNull();
      expect(screen.getAllByTestId('store-dot')).toHaveLength(3);
    });

    it('draws a cluster with a proposed pin as a dashed ring', async () => {
      hoisted.payload = {
        ...payload(),
        stores: [
          store('Saved', 10, 20),
          store('Proposed', 0, 0, {
            pinned: false,
            latitude: null,
            longitude: null,
            location_suggestion: {
              outcome: 'suggest', reason: 'match', place: 'Example Place',
              latitude: 10.1, longitude: 20.1, licence: 'GeoNames CC BY 4.0',
            },
          }),
        ],
      };
      wrap(<StoreMap />);
      const cluster = await screen.findByTestId('store-cluster');
      expect(cluster).toHaveAttribute('data-pin-state', 'proposed');
      expect(dotOf(cluster)).toHaveAttribute('data-hollow', 'true');
      expect(getComputedStyle(dotOf(cluster)).borderStyle).toBe('dashed');
      expect(cluster).toHaveTextContent('2');
      fireEvent.mouseEnter(cluster);
      expect(screen.getByTestId('store-map-cluster-hover')).toHaveTextContent('(proposed)');
    });

    it('stops clustering at the tightest zoom and fans out pins that still overlap', async () => {
      hoisted.payload = {
        ...payload(),
        stores: [store('Same A', 10, 20), store('Same B', 10, 20), store('Far', -20, 50)],
      };
      wrap(<StoreMap />);
      fireEvent.click(await screen.findByTestId('store-cluster'));
      // Identical coordinates cannot separate: the view stops at about 0.3 degrees of longitude.
      expect(viewBoxOf()[2]).toBeCloseTo((0.3 / 158) * 1000, 3);
      expect(screen.getByRole('button', { name: 'Zoom in' })).toBeDisabled();
      expect(screen.queryByTestId('store-cluster')).toBeNull();
      const dots = screen.getAllByTestId('store-dot');
      expect(dots).toHaveLength(3);
      // Each keeps its real coordinates; only the on-screen position is fanned out.
      expect(dots.filter((dot) => dot.dataset.latitude === '10')).toHaveLength(2);
    });

    it('reaches a proposed pin inside a cluster by zooming in, then confirms it as usual', async () => {
      hoisted.payload = {
        ...payload(),
        stores: [
          store('Saved', 10, 20),
          store('Proposed', 0, 0, {
            pinned: false,
            latitude: null,
            longitude: null,
            location_suggestion: {
              outcome: 'suggest', reason: 'match', place: 'Example Place',
              latitude: 10.1, longitude: 20.1, licence: 'GeoNames CC BY 4.0',
            },
          }),
        ],
      };
      wrap(<StoreMap />);
      fireEvent.click(await screen.findByTestId('store-cluster'));
      const pin = await screen.findByTestId('store-dot-unconfirmed');
      fireEvent.click(pin);
      expect(screen.getByTestId('store-pin-actions')).toBeInTheDocument();
      expect(screen.getByTestId('store-dot-unconfirmed')).toHaveAttribute('data-latitude', '10.1');
    });

    it('keeps the selected pin a single pin at its real position when zoomed back out', async () => {
      hoisted.payload = crowded();
      wrap(<StoreMap />);
      fireEvent.click(await screen.findByTestId('store-cluster'));
      fireEvent.click(screen.getByRole('button', { name: /Near A/ }));
      fireEvent.click(screen.getByRole('button', { name: 'Reset view' }));
      // The other two still cluster; the one being read stays on its own.
      expect(screen.getByTestId('store-cluster')).toHaveAttribute('data-cluster-count', '2');
      const selected = screen.getByRole('button', { name: /Near A/ });
      expect(selected).toHaveAttribute('aria-pressed', 'true');
      expect(selected).toHaveAttribute('data-latitude', '10');
      expect(screen.getByTestId('store-map-lines')).toBeInTheDocument();
    });
  });
});
