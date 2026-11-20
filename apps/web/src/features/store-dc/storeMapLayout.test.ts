import { describe, expect, it } from 'vitest';

import { BASEMAP_BOUNDS, mapViewBox } from '@/features/maps/mapGeometry';

import {
  projectStores,
  sellThroughColor,
  spreadOverlaps,
  storeMapBounds,
  unprojectStore,
} from './storeMapLayout';

describe('store map layout', () => {
  it('keeps the Shipments extent for in-bounds stores, including a lone pin and an empty map', () => {
    for (const points of [[], [{ id: 'one', latitude: 3, longitude: 4 }]]) {
      expect(storeMapBounds(points)).toEqual(BASEMAP_BOUNDS);
      expect(mapViewBox(storeMapBounds(points))).toBe('0 0 1000 646');
    }
    const [pin] = projectStores([{ id: 'one', latitude: 3, longitude: 4 }]);
    expect(pin.x).toBeCloseTo((26 / 158) * 100);
    expect(pin.y).toBeCloseTo((55 / 102) * 100);
    expect(unprojectStore(pin.x, pin.y, BASEMAP_BOUNDS)).toEqual({ latitude: 3, longitude: 4 });
  });

  it('extends the same viewBox for outlying pins without distorting the basemap', () => {
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
