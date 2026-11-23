import { describe, expect, it } from 'vitest';

import { clusterSource, pointBounds, pointCollection, sourceMarkers, wrapLongitude } from './clustering';
import { DOT_IMAGE, OSM_ATTRIBUTION, buildMapStyle, dotImage, mapAttribution } from './style';

describe('tenant map style', () => {
  it('requires explicit tile configuration and uses precisely the supplied URLs', () => {
    expect(buildMapStyle({})).toBeNull();
    for (const tilejsonUrl of [
      'https://tiles.example.test/tenant-one/tiles.json',
      'https://other.example.test/vector',
    ]) {
      const glyphsUrl = 'https://fonts.example.test/{fontstack}/{range}.pbf';
      const style = buildMapStyle({ tilejsonUrl, glyphsUrl })!;
      expect(style.sources.openmaptiles).toEqual({ type: 'vector', url: tilejsonUrl });
      expect(style.glyphs).toBe(glyphsUrl);
      expect(JSON.stringify(style)).not.toMatch(/openfreemap|maptiler|south.africa/i);
      expect(style.metadata?.['workbench:attribution']).toContain(OSM_ATTRIBUTION);
    }
  });

  it('has dotted land, a water mask and real detail that appears with zoom', () => {
    const style = buildMapStyle({ tilejsonUrl: 'https://tiles.example.test/vector' })!;
    expect(style.layers.find((layer) => layer.id === 'dotted-land')).toMatchObject({
      type: 'background',
      paint: {
        'background-pattern': DOT_IMAGE,
        'background-opacity': ['interpolate', ['linear'], ['zoom'], 6, 1, 10, 0],
      },
    });
    expect(style.layers.findIndex((layer) => layer.id === 'water'))
      .toBeGreaterThan(style.layers.findIndex((layer) => layer.id === 'dotted-land'));
    for (const layer of ['landcover', 'landuse', 'water', 'transportation', 'building']) {
      expect(style.layers).toEqual(expect.arrayContaining([
        expect.objectContaining({ 'source-layer': layer }),
      ]));
    }
    expect(style.layers.some((layer) => layer.type === 'symbol')).toBe(false);
    const labelled = buildMapStyle({
      tilejsonUrl: 'https://tiles.example.test/vector',
      glyphsUrl: 'https://fonts.example.test/{fontstack}/{range}.pbf',
    })!;
    expect(labelled.layers).toEqual(expect.arrayContaining([
      expect.objectContaining({ 'source-layer': 'place' }),
      expect.objectContaining({ 'source-layer': 'poi' }),
    ]));
  });

  it('always includes OSM, escapes additional attribution and creates a transparent dot sprite', () => {
    expect(mapAttribution({ attribution: '<img>&Provider' }))
      .toBe(`${OSM_ATTRIBUTION} | &lt;img&gt;&amp;Provider`);
    const sprite = dotImage();
    expect(sprite.data).toHaveLength(sprite.width * sprite.height * 4);
    expect(sprite.data.some((value, index) => index % 4 === 3 && value === 90)).toBe(true);
    expect(sprite.width).toBe(4);
    expect(sprite.data[3]).toBe(0);
    const lightStyle = buildMapStyle({ tilejsonUrl: 'https://tiles.example.test/vector' }, 'light')!;
    const darkStyle = buildMapStyle({ tilejsonUrl: 'https://tiles.example.test/vector' }, 'dark')!;
    expect(lightStyle.name).toBe('Workbench light');
    expect(darkStyle.name).toBe('Workbench dark');
    expect(JSON.stringify(lightStyle)).not.toBe(JSON.stringify(darkStyle));
  });
});

describe('MapLibre clustering adapters', () => {
  const point = {
    id: 'customer:store', label: 'Store', latitude: 12, longitude: 34,
    proposed: true, score: 0.5,
  };

  it('keeps stable identity, filters unusable coordinates and enables native clustering', () => {
    const data = pointCollection([point, { ...point, id: 'bad', latitude: NaN }]);
    expect(data.features).toHaveLength(1);
    expect(data.features[0]).toMatchObject({
      id: point.id,
      geometry: { coordinates: [34, 12] },
      properties: { id: point.id, proposed: true, score: 0.5 },
    });
    expect(clusterSource([point])).toMatchObject({
      cluster: true, clusterRadius: 36, clusterMaxZoom: 14,
      clusterProperties: expect.objectContaining({ score_sum: expect.any(Array) }),
    });
  });

  it('deduplicates tile copies and computes means without treating missing scores as zero', () => {
    const cluster = {
      geometry: { type: 'Point' as const, coordinates: [34, 12] },
      properties: {
        cluster: true, cluster_id: 7, point_count: 3,
        score_sum: 1.2, score_count: 2, proposed_count: 1,
      },
    };
    expect(sourceMarkers([cluster, cluster])).toEqual([
      expect.objectContaining({ clusterId: 7, count: 3, score: 0.6, proposed: true }),
    ]);
    expect(sourceMarkers([{
      ...cluster, properties: { ...cluster.properties, score_count: 0 },
    }])[0].score).toBeNull();
  });

  it('fits data on either side of the date line and has no country fallback', () => {
    expect(pointBounds([])).toBeNull();
    const bounds = pointBounds([
      { latitude: 12, longitude: 179 },
      { latitude: 14, longitude: -179 },
    ])!;
    expect(bounds[1][0] - bounds[0][0]).toBe(2);
    expect(pointBounds([{ latitude: 90, longitude: 20 }])![1][1]).toBeLessThan(90);
    expect(wrapLongitude(181)).toBe(-179);
  });
});
