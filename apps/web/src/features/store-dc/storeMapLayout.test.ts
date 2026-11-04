import { describe, expect, it } from 'vitest';

import { projectStores, sellThroughColor, spreadOverlaps, storeMapPanelHeight } from './storeMapLayout';

describe('store map layout', () => {
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
    expect(storeMapPanelHeight.md).toBeGreaterThan(storeMapPanelHeight.xs);
  });
});
