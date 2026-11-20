import { describe, expect, it } from 'vitest';

import {
  CLUSTER_CELL_PX,
  MAX_HIT_PX,
  clusterPins,
  meanSellThrough,
  type ClusterPin,
} from './storeMapClusters';

const MAP = { w: 1000, h: 646 };

/** A pin placed by screen pixel, so the grid arithmetic in a test is plain. */
function atPx(id: string, px: number, py: number): ClusterPin {
  return {
    id,
    x: (px / MAP.w) * 100,
    y: (py / MAP.h) * 100,
    latitude: py,
    longitude: px,
  };
}

describe('clusterPins', () => {
  it('groups pins that share a screen grid cell and leaves other pins single', () => {
    const groups = clusterPins(
      [atPx('a', 105, 105), atPx('b', 110, 112), atPx('c', 118, 108), atPx('far', 500, 300)],
      MAP
    );
    const crowd = groups.find((group) => group.members.length === 3)!;
    expect(crowd.members.map((pin) => pin.id).sort()).toEqual(['a', 'b', 'c']);
    expect(crowd.id).toMatch(/^cluster:/);
    const single = groups.find((group) => group.members.length === 1)!;
    expect(single.id).toBe('far');
    expect(groups).toHaveLength(2);
  });

  it('places a cluster at the centroid of its members, a single pin at its own position', () => {
    const [group] = clusterPins([atPx('a', 106, 106), atPx('b', 112, 110), atPx('c', 108, 114)], MAP);
    expect(group.members).toHaveLength(3);
    expect((group.x / 100) * MAP.w).toBeCloseTo((106 + 112 + 108) / 3);
    expect((group.y / 100) * MAP.h).toBeCloseTo((106 + 110 + 114) / 3);
    expect(group.longitude).toBeCloseTo((106 + 112 + 108) / 3);
    expect(group.latitude).toBeCloseTo((106 + 110 + 114) / 3);
    const [lone] = clusterPins([atPx('only', 321, 123)], MAP);
    expect(lone.x).toBeCloseTo((321 / MAP.w) * 100);
    expect(lone.y).toBeCloseTo((123 / MAP.h) * 100);
    expect(lone.id).toBe('only');
  });

  it('merges groups across a cell edge when they would still overlap on screen', () => {
    // 4px apart but on either side of the 26px cell edge at 104.
    const edge = CLUSTER_CELL_PX * 4;
    const groups = clusterPins([atPx('left', edge - 2, 50), atPx('right', edge + 2, 50)], MAP);
    expect(groups).toHaveLength(1);
    expect(groups[0].members).toHaveLength(2);
  });

  it('keeps pins one cell apart separate, each with room for its click target', () => {
    const groups = clusterPins([atPx('a', 100, 100), atPx('b', 140, 100)], MAP);
    expect(groups).toHaveLength(2);
    for (const group of groups) {
      expect(group.nearestPx).toBeCloseTo(40);
      expect(group.nearestPx).toBeLessThanOrEqual(MAX_HIT_PX);
    }
    const [alone] = clusterPins([atPx('a', 100, 100)], MAP);
    expect(alone.nearestPx).toBe(MAX_HIT_PX);
  });

  it('dissolves as the view zooms in: the same pins, more pixels apart', () => {
    const pins = (scale: number) => [atPx('a', 500, 300), atPx('b', 500 + 6 * scale, 300)];
    expect(clusterPins(pins(1), MAP)).toHaveLength(1);
    expect(clusterPins(pins(8), MAP)).toHaveLength(2);
  });

  it('depends on the map size in pixels, not just the percentages', () => {
    const pins = [
      { id: 'a', x: 50, y: 50, latitude: 0, longitude: 0 },
      { id: 'b', x: 52, y: 50, latitude: 0, longitude: 0 },
    ];
    expect(clusterPins(pins, { w: 1000, h: 646 })).toHaveLength(2);
    expect(clusterPins(pins, { w: 300, h: 194 })).toHaveLength(1);
  });

  it('groups many pins deterministically and keeps every pin exactly once', () => {
    const many = Array.from({ length: 400 }, (_, index) =>
      atPx(`p${String(index).padStart(3, '0')}`, 300 + (index % 20) * 9, 200 + Math.floor(index / 20) * 9)
    );
    const groups = clusterPins(many, MAP);
    expect(groups.reduce((sum, group) => sum + group.members.length, 0)).toBe(400);
    expect(new Set(groups.flatMap((group) => group.members.map((pin) => pin.id))).size).toBe(400);
    expect(groups.length).toBeLessThan(400 / 4);
    expect(clusterPins([...many].reverse(), MAP).map((group) => group.id).sort()).toEqual(
      groups.map((group) => group.id).sort()
    );
  });
});

describe('meanSellThrough', () => {
  it('averages the members that have a sell-through', () => {
    expect(meanSellThrough([1, 0, 0.5])).toBeCloseTo(0.5);
    expect(meanSellThrough([0.2, null, undefined, Number.NaN, 0.4])).toBeCloseTo(0.3);
    expect(meanSellThrough([null, null])).toBeNull();
    expect(meanSellThrough([])).toBeNull();
  });
});
