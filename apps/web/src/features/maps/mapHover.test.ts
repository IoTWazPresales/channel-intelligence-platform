import { describe, expect, it } from 'vitest';

import { basemapDotStroke, basemapLonZoom, basemapUsesLandShade } from './mapBasemap';
import { BASEMAP_BOUNDS } from './mapGeometry';
import { mapHoverOpensRight } from './mapHover';

describe('shared map hover and basemap', () => {
  it('opens the hover card to the right of markers east of the map midpoint', () => {
    expect(mapHoverOpensRight(40)).toBe(false);
    expect(mapHoverOpensRight(55)).toBe(false);
    expect(mapHoverOpensRight(56)).toBe(true);
  });

  it('uses the Shipments basemap dot stroke colours', () => {
    expect(basemapDotStroke('dark')).toBe('rgba(160,185,205,0.28)');
    expect(basemapDotStroke('light')).toBe('rgba(40,70,95,0.30)');
  });

  it('switches to land shade when the steward zooms in past continent scale', () => {
    expect(basemapUsesLandShade(BASEMAP_BOUNDS)).toBe(false);
    const continent = { minLat: -20, maxLat: 20, minLon: 0, maxLon: 60 };
    expect(basemapLonZoom(continent)).toBeGreaterThan(2);
    expect(basemapUsesLandShade(continent)).toBe(false);
    const city = { minLat: -34, maxLat: -33.5, minLon: 18, maxLon: 18.4 };
    expect(basemapUsesLandShade(city)).toBe(true);
  });
});