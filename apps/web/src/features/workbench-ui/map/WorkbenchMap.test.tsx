import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { StoreMapStore } from '@/features/store-dc/types';
import { StoreMapPrototype } from '@/features/store-dc/StoreMapPrototype';

import { WorkbenchMap } from './WorkbenchMap';
import type { Coordinates, WorkbenchPoint } from './clustering';

const fake = vi.hoisted(() => {
  type Feature = {
    type: 'Feature';
    geometry: { type: 'Point'; coordinates: number[] };
    properties: Record<string, unknown>;
  };
  type Collection = { type: 'FeatureCollection'; features: Feature[] };
  type Listener = (event: Record<string, unknown>) => void;

  class Control {
    constructor(public options: Record<string, unknown>) {}
  }

  class FakeMap {
    static instances: FakeMap[] = [];
    listeners = new Map<string, Listener[]>();
    canvas = document.createElement('canvas');
    controls: Control[] = [];
    data: Collection = { type: 'FeatureCollection', features: [] };
    features: Feature[] | null = null;
    zoom = 5;
    removed = false;
    source = {
      setData: vi.fn((data: Collection) => { this.data = data; }),
      getClusterExpansionZoom: vi.fn(async () => 11),
    };
    dragPan = {
      isEnabled: vi.fn(() => true),
      disable: vi.fn(),
      enable: vi.fn(),
    };
    fitBounds = vi.fn();
    flyTo = vi.fn();
    easeTo = vi.fn();
    resize = vi.fn();
    remove = vi.fn(() => { this.removed = true; });
    addImage = vi.fn();
    addLayer = vi.fn();
    hasImage = vi.fn(() => false);

    constructor(public options: { container: HTMLElement }) {
      FakeMap.instances.push(this);
      options.container.appendChild(this.canvas);
    }

    on(name: string, listener: Listener) {
      this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener]);
      return this;
    }

    emit(name: string, event: Record<string, unknown> = {}) {
      for (const listener of this.listeners.get(name) ?? []) listener(event);
    }

    addControl(control: Control) { this.controls.push(control); }
    getCanvas() { return this.canvas; }
    getContainer() { return this.options.container; }
    getCenter() { return { lng: 34, lat: 12 }; }
    getZoom() { return this.zoom; }
    project() { return { x: 400, y: 240 }; }
    unproject() { return { lng: 35, lat: 13 }; }
    addSource(_id: string, source: { data: Collection }) { this.data = source.data; }
    getSource() { return this.source; }
    querySourceFeatures() { return this.features ?? this.data.features; }
  }
  return { Map: FakeMap, Control };
});

vi.mock('maplibre-gl', () => ({
  Map: fake.Map,
  NavigationControl: fake.Control,
  AttributionControl: fake.Control,
}));

vi.mock('@/features/settings/useMapSettings', () => ({
  useMapSettings: () => ({
    settings: {
      tilejsonUrl: 'https://tiles.example.test/vector',
      glyphsUrl: 'https://fonts.example.test/{fontstack}/{range}.pbf',
    },
    pending: false,
    error: null,
  }),
}));

const settings = {
  tilejsonUrl: 'https://tiles.example.test/vector',
  glyphsUrl: 'https://fonts.example.test/{fontstack}/{range}.pbf',
};
const point: WorkbenchPoint = {
  id: '1:Store A', label: 'Store A', latitude: 12, longitude: 34,
  proposed: false, score: 0.25,
};

async function loadMap() {
  await waitFor(() => expect(fake.Map.instances).toHaveLength(1));
  const map = fake.Map.instances[0];
  act(() => map.emit('load'));
  await waitFor(() => expect(map.addLayer).toHaveBeenCalled());
  return map;
}

beforeEach(() => {
  fake.Map.instances.length = 0;
});

describe('shared map lifecycle and interaction', () => {
  it('does not initialise WebGL or request tiles without configuration', async () => {
    render(
      <WorkbenchMap
        settings={{}} points={[]} fitKey="empty" selectedKey={null}
        onSelect={vi.fn()} colorForScore={() => '#ffffff'}
      />,
    );
    expect(screen.getByTestId('workbench-map-not-configured')).toHaveTextContent('Map tiles are not configured');
    expect(screen.getByRole('link', { name: 'Settings > Map' })).toHaveAttribute('href', '/settings#map-settings');
    await act(async () => undefined);
    expect(fake.Map.instances).toHaveLength(0);
  });

  it('uses native cluster expansion, compact collapsible attribution and cleans up', async () => {
    const view = render(
      <WorkbenchMap
        settings={settings} points={[point]} fitKey="all" selectedKey={null}
        onSelect={vi.fn()} colorForScore={() => '#ffffff'}
      />,
    );
    const map = await loadMap();
    expect(map.controls.some((control) =>
      control.options.compact === true
      && String(control.options.customAttribution).includes('OpenStreetMap contributors')
    )).toBe(true);
    map.features = [{
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [34, 12] },
      properties: {
        cluster: true, cluster_id: 9, point_count: 3,
        score_sum: 0.5, score_count: 2, proposed_count: 1,
      },
    }];
    act(() => map.emit('sourcedata', { sourceId: 'workbench-points' }));
    const cluster = screen.getByTestId('workbench-map-cluster');
    expect(cluster).toHaveTextContent('3');
    expect(cluster).toHaveAttribute('data-pin-state', 'proposed');
    fireEvent.click(cluster);
    await waitFor(() => expect(map.source.getClusterExpansionZoom).toHaveBeenCalledWith(9));
    await waitFor(() => expect(map.easeTo).toHaveBeenCalledWith({
      center: [34, 12], zoom: 11, duration: 600,
    }));
    fireEvent.click(screen.getByRole('button', { name: 'Reset view' }));
    expect(map.fitBounds).toHaveBeenCalled();
    view.unmount();
    expect(map.remove).toHaveBeenCalledOnce();
  });
});

const stores: StoreMapStore[] = [
  {
    customer_id: 1, customer_name: 'Account A', site_label: 'Store A',
    place_name: null, latitude: 12, longitude: 34, pinned: true,
    last_week_units: 10, stock_on_hand: 30, sell_through: 0.25,
    weeks_of_cover: 3, lines: [],
  },
  {
    customer_id: 1, customer_name: 'Account A', site_label: 'Store B',
    place_name: null, latitude: null, longitude: null, pinned: false,
    last_week_units: 2, stock_on_hand: 8, sell_through: 0.2,
    weeks_of_cover: 4, lines: [],
    location_suggestion: {
      outcome: 'manual', reason: 'none', place: null,
      latitude: null, longitude: null, licence: '',
    },
  },
];

describe('store list and map link', () => {
  it('links list selection, map selection, hover facts and staged placement without saving', async () => {
    const confirm = vi.fn();

    function Harness() {
      const [selected, setSelected] = useState<string | null>(null);
      const [draft, setDraft] = useState<Coordinates | null>(null);
      const mapped = draft ? stores : [stores[0]];
      const points = [
        { id: '1:Store A', latitude: 12, longitude: 34 },
        ...(draft ? [{ id: '1:Store B', ...draft }] : []),
      ];
      return (
        <StoreMapPrototype
          stores={stores}
          mapStores={mapped}
          points={points}
          scopeKey="all"
          selectedKey={selected}
          saving={false}
          errors={{}}
          onSelect={setSelected}
          onAdjust={(_key, coordinates) => setDraft(coordinates)}
          onConfirm={confirm}
          onSkip={vi.fn()}
        />
      );
    }

    render(<Harness />);
    const map = await loadMap();
    fireEvent.click(screen.getByRole('button', { name: 'Store A' }));
    await waitFor(() => expect(map.flyTo).toHaveBeenCalledWith({
      center: [34, 12], zoom: 15, duration: 700,
    }));
    expect(screen.getByTestId('prototype-store-detail')).toHaveTextContent('25%');
    expect(screen.getByTestId('workbench-map-pin')).toHaveAttribute('aria-pressed', 'true');

    fireEvent.mouseEnter(screen.getByTestId('workbench-map-pin'));
    expect(screen.getByTestId('workbench-map-hover')).toHaveTextContent('Last week');
    expect(screen.getByTestId('workbench-map-hover')).toHaveTextContent('Stock on hand');
    expect(screen.getByTestId('workbench-map-hover')).toHaveTextContent('Account A');

    fireEvent.click(screen.getByRole('button', { name: 'Store B' }));
    expect(screen.getByTestId('prototype-store-detail')).toHaveTextContent('No place match');
    fireEvent.click(screen.getByRole('button', { name: 'Drop pin' }));
    act(() => map.emit('click', { lngLat: { lat: 13, lng: 35 } }));
    expect(confirm).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getAllByTestId('workbench-map-pin')).toHaveLength(2));
    const proposed = screen.getAllByTestId('workbench-map-pin')
      .find((button) => button.getAttribute('data-point-id') === '1:Store B')!;
    expect(proposed).toHaveAttribute('data-pin-state', 'proposed');
    fireEvent.click(screen.getByRole('button', { name: 'Store A' }));
    fireEvent.click(proposed);
    expect(within(screen.getByTestId('prototype-store-detail')).getByText('Store B')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Store B' })).toHaveAttribute('aria-pressed', 'true');
    expect(confirm).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Confirm location' }));
    expect(confirm).toHaveBeenCalledWith([{
      customer_id: 1, site_label: 'Store B', latitude: 13, longitude: 35,
    }]);
    expect(within(screen.getByTestId('store-map-aside')).getByTestId('proposed-pins')).toBeInTheDocument();
  });
});
