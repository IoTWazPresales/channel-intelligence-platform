import { describe, expect, it } from 'vitest';

import { BASEMAP_BOUNDS, mapViewBox } from '@/features/maps/mapGeometry';

import {
  STORE_MIN_LON_SPAN,
  finiteCoordinates,
  projectStores,
  sellThroughColor,
  spreadOverlaps,
  storeMapBounds,
  unprojectStore,
} from './storeMapLayout';

describe('store map layout', () => {
  it('keeps the Shipments extent when there are no pins', () => {
    expect(storeMapBounds([])).toEqual(BASEMAP_BOUNDS);
    expect(mapViewBox(storeMapBounds([]))).toBe('0 0 1000 646');
    const [pin] = projectStores([{ id: 'one', latitude: 3, longitude: 4 }], BASEMAP_BOUNDS);
    expect(pin.x).toBeCloseTo((26 / 158) * 100);
    expect(pin.y).toBeCloseTo((55 / 102) * 100);
    expect(unprojectStore(pin.x, pin.y, BASEMAP_BOUNDS)).toEqual({ latitude: 3, longitude: 4 });
  });

  it('fits the continent the pins are in, padded, inside the box without distorting the basemap', () => {
    // One country: a spread of about 16 x 12 degrees.
    const points = [
      { id: 'nw', latitude: -22, longitude: 17 },
      { id: 'se', latitude: -34, longitude: 33 },
      { id: 'mid', latitude: -28, longitude: 25 },
    ];
    const bounds = storeMapBounds(points);
    const [, , width, height] = mapViewBox(bounds).split(' ').map(Number);
    expect(width / height).toBeCloseTo(1000 / 646);
    // Continent scale, not a country crop: at least 80 degrees wide, much wider than the pins.
    expect(bounds.maxLon - bounds.minLon).toBeGreaterThanOrEqual(80);
    expect(bounds.maxLon - bounds.minLon).toBeGreaterThan(3 * 16);
    for (const pin of projectStores(points, bounds)) {
      // Generous padding: every pin sits well inside the box.
      expect(pin.x).toBeGreaterThan(30);
      expect(pin.x).toBeLessThan(70);
      expect(pin.y).toBeGreaterThan(30);
      expect(pin.y).toBeLessThan(70);
    }
    // Pin, drag and basemap share the chosen bounds.
    const [first] = projectStores([points[0]], bounds);
    const restored = unprojectStore(first.x, first.y, bounds);
    expect(restored.latitude).toBeCloseTo(-22);
    expect(restored.longitude).toBeCloseTo(17);
  });

  it('widens to fit pins spread over several countries and stays inside the world', () => {
    const wide = storeMapBounds([
      { latitude: 50, longitude: -5 },
      { latitude: -30, longitude: 120 },
    ]);
    expect(wide.maxLon - wide.minLon).toBeGreaterThanOrEqual(125 * 1.5 - 1e-9);
    const everywhere = storeMapBounds([
      { latitude: 80, longitude: -170 },
      { latitude: -80, longitude: 170 },
    ]);
    for (const view of [wide, everywhere]) {
      expect(view.minLat).toBeGreaterThanOrEqual(-90);
      expect(view.maxLat).toBeLessThanOrEqual(90);
      expect(view.minLon).toBeGreaterThanOrEqual(-180);
      expect(view.maxLon).toBeLessThanOrEqual(180);
      const [, , width, height] = mapViewBox(view).split(' ').map(Number);
      expect(width / height).toBeCloseTo(1000 / 646);
    }
  });

  it('does not zoom absurdly far in on a lone pin or a tight group', () => {
    const lone = storeMapBounds([{ id: 'one', latitude: 3, longitude: 4 }]);
    expect(lone.maxLon - lone.minLon).toBeGreaterThanOrEqual(80);
    const [pin] = projectStores([{ id: 'one', latitude: 3, longitude: 4 }], lone);
    expect(pin.x).toBeCloseTo(50);
    expect(pin.y).toBeCloseTo(50);
    const tight = storeMapBounds([
      { id: 'a', latitude: 3, longitude: 4 },
      { id: 'b', latitude: 3.001, longitude: 4.001 },
    ]);
    expect(tight.maxLon - tight.minLon).toBeGreaterThanOrEqual(80);
  });

  it('shows the continent around a country of hundreds of stores, not a crop of the stores', () => {
    // One country, ~300 stores over about 20 x 12 degrees.
    const points = Array.from({ length: 300 }, (_, index) => ({
      id: `s${index}`,
      latitude: -34 + (index % 12),
      longitude: 17 + Math.floor(index / 12) * 0.8,
    }));
    const bounds = storeMapBounds(points);
    expect(bounds.maxLon - bounds.minLon).toBeGreaterThanOrEqual(80);
    // Every store sits in the middle of the box with the dotted outline all around it.
    for (const pin of projectStores(points, bounds)) {
      expect(pin.x).toBeGreaterThan(25);
      expect(pin.x).toBeLessThan(75);
      expect(pin.y).toBeGreaterThan(25);
      expect(pin.y).toBeLessThan(75);
    }
  });

  it('fits a cluster of stores to the tightest view with room around them', () => {
    const members = [
      { latitude: 10, longitude: 20 },
      { latitude: 10.1, longitude: 20.2 },
    ];
    const bounds = storeMapBounds(members, STORE_MIN_LON_SPAN, 1.8);
    expect(bounds.maxLon - bounds.minLon).toBeLessThan(2);
    for (const member of members) {
      const { x, y } = projectStores([{ id: 'm', ...member }], bounds)[0];
      expect(x).toBeGreaterThan(10);
      expect(x).toBeLessThan(90);
      expect(y).toBeGreaterThan(10);
      expect(y).toBeLessThan(90);
    }
    // Identical coordinates cannot be separated: the view stops at the minimum span.
    const same = storeMapBounds([members[0], members[0]], STORE_MIN_LON_SPAN, 1.8);
    expect(same.maxLon - same.minLon).toBeCloseTo(STORE_MIN_LON_SPAN);
  });

  it('treats missing, blank, non-numeric, out of range and 0,0 coordinates as no place', () => {
    expect(finiteCoordinates(null, 5)).toBeNull();
    expect(finiteCoordinates(5, undefined)).toBeNull();
    expect(finiteCoordinates('', '')).toBeNull();
    expect(finiteCoordinates('abc', 5)).toBeNull();
    expect(finiteCoordinates(Number.NaN, 5)).toBeNull();
    expect(finiteCoordinates(91, 5)).toBeNull();
    expect(finiteCoordinates(5, 181)).toBeNull();
    expect(finiteCoordinates(0, 0)).toBeNull();
    expect(finiteCoordinates('-26.2', '28.1')).toEqual({ latitude: -26.2, longitude: 28.1 });
    expect(finiteCoordinates(0, 28)).toEqual({ latitude: 0, longitude: 28 });
  });

  it('keeps the viewBox aspect for outlying pins without distorting the basemap', () => {
    const point = { id: 'outside', latitude: 70, longitude: -100 };
    const bounds = storeMapBounds([point]);
    const [pin] = projectStores([point], bounds);
    expect(pin.x).toBeGreaterThan(0);
    expect(pin.x).toBeLessThan(100);
    expect(pin.y).toBeGreaterThan(0);
    expect(pin.y).toBeLessThan(100);
    const [, , width, height] = mapViewBox(bounds).split(' ').map(Number);
    expect(width / height).toBeCloseTo(1000 / 646);
    const restored = unprojectStore(pin.x, pin.y, bounds);
    expect(restored.latitude).toBeCloseTo(point.latitude);
    expect(restored.longitude).toBeCloseTo(point.longitude);
  });

  it.each([
    { w: 1000, h: 646 },
    { w: 500, h: 323 },
  ])('separates pins 5px apart on a $w by $h map', (mapPx) => {
    const diameter = 14;
    const pins = [
      { id: 'a', x: 50, y: 50 },
      { id: 'b', x: 50 + (3 / mapPx.w) * 100, y: 50 + (4 / mapPx.h) * 100 },
    ];
    const spread = spreadOverlaps(pins, mapPx, diameter);
    const [a, b] = spread;
    const distance = Math.hypot(
      ((b.x - a.x) / 100) * mapPx.w + b.dx - a.dx,
      ((b.y - a.y) / 100) * mapPx.h + b.dy - a.dy
    );
    expect(distance).toBeGreaterThanOrEqual(diameter);
    expect(spread.map(({ id, x, y }) => ({ id, x, y }))).toEqual(pins);
    expect(spreadOverlaps([...pins].reverse(), mapPx, diameter)).toEqual(spread);
  });

  it('fans a large cluster on a compact spiral instead of a huge ring', () => {
    const mapPx = { w: 1000, h: 646 };
    const diameter = 14;
    const pins = Array.from({ length: 190 }, (_, index) => ({
      id: `p${String(index).padStart(3, '0')}`,
      // 7px grid inside ~100px, so every pin chains into one cluster
      x: 50 + (((index % 14) * 7) / mapPx.w) * 100,
      y: 50 + ((Math.floor(index / 14) * 7) / mapPx.h) * 100,
    }));
    const spread = spreadOverlaps(pins, mapPx, diameter);
    expect(spreadOverlaps([...pins].reverse(), mapPx, diameter)).toEqual(spread);
    const screen = spread.map((pin) => ({
      x: (pin.x / 100) * mapPx.w + pin.dx,
      y: (pin.y / 100) * mapPx.h + pin.dy,
    }));
    const centre = {
      x: pins.reduce((sum, pin) => sum + (pin.x / 100) * mapPx.w, 0) / pins.length,
      y: pins.reduce((sum, pin) => sum + (pin.y / 100) * mapPx.h, 0) / pins.length,
    };
    let nearest = Infinity;
    for (let a = 0; a < screen.length; a += 1) {
      expect(Math.hypot(screen[a].x - centre.x, screen[a].y - centre.y)).toBeLessThanOrEqual(
        20 * diameter
      );
      for (let b = a + 1; b < screen.length; b += 1) {
        nearest = Math.min(nearest, Math.hypot(screen[a].x - screen[b].x, screen[a].y - screen[b].y));
      }
    }
    expect(nearest).toBeGreaterThanOrEqual(diameter * 0.9);
  });

  it('fans up to 12 stacked pins on a ring and larger stacks on a bounded spiral', () => {
    const mapPx = { w: 1000, h: 646 };
    const diameter = 16;
    const stack = (count: number) =>
      Array.from({ length: count }, (_, index) => ({ id: `s${String(index).padStart(3, '0')}`, x: 40, y: 40 }));
    const radii = (count: number) =>
      spreadOverlaps(stack(count), mapPx, diameter).map((pin) => Math.hypot(pin.dx, pin.dy));

    const ring = radii(12);
    for (const radius of ring) expect(radius).toBeCloseTo(ring[0]);

    const spiral = radii(13);
    expect(Math.max(...spiral) - Math.min(...spiral)).toBeGreaterThan(diameter);

    // Footprint grows with sqrt(n): 190 stacked pins stay within ~sqrt(190) diameters.
    expect(Math.max(...radii(190))).toBeLessThanOrEqual(diameter * Math.sqrt(190));
  });

  it('puts a higher latitude further north and spreads identical coordinates', () => {
    const projected = projectStores([
      { id: 'south', latitude: 1, longitude: 2 },
      { id: 'north', latitude: 5, longitude: 2 },
    ]);
    const north = projected.find((point) => point.id === 'north');
    const south = projected.find((point) => point.id === 'south');
    expect(north && south && north.y < south.y).toBe(true);
    const same = projectStores([
      { id: 'a', latitude: 3, longitude: 4 },
      { id: 'b', latitude: 3, longitude: 4 },
    ]);
    const spread = spreadOverlaps(same, { w: 1000, h: 646 }, 14);
    expect(spread).toHaveLength(2);
    expect(spread[0].dx === spread[1].dx && spread[0].dy === spread[1].dy).toBe(false);
    expect(sellThroughColor(1, '#111111', '#222222')).toContain('#111111');
    expect(sellThroughColor(null, '#111111', '#222222')).toBe('#222222');
  });
});
