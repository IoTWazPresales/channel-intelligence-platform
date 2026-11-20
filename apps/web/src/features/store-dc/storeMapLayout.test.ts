import { describe, expect, it } from 'vitest';

import { BASEMAP_BOUNDS, mapViewBox } from '@/features/maps/mapGeometry';

import { projectStores, sellThroughColor, spreadOverlaps, storeMapBounds, unprojectStore } from './storeMapLayout';

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
    const spread = spreadOverlaps(same);
    expect(spread).toHaveLength(2);
    expect(spread[0].dx === spread[1].dx && spread[0].dy === spread[1].dy).toBe(false);
    expect(sellThroughColor(1, '#111111', '#222222')).toContain('#111111');
    expect(sellThroughColor(null, '#111111', '#222222')).toBe('#222222');
  });
});
