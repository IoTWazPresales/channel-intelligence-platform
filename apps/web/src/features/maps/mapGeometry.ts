import { BASEMAP_SIZE } from './basemapDots';

// Extent of the existing equirectangular Shipments basemap, not tenant geography.
export const BASEMAP_BOUNDS = { minLat: -44, maxLat: 58, minLon: -22, maxLon: 136 } as const;
export const MAP_ASPECT_RATIO = `${BASEMAP_SIZE.width} / ${BASEMAP_SIZE.height}`;

export type MapBounds = { minLat: number; maxLat: number; minLon: number; maxLon: number };
export type Coordinates = { latitude: number; longitude: number };

export function projectMapPoint(point: Coordinates, bounds: MapBounds = BASEMAP_BOUNDS) {
  return {
    x: ((point.longitude - bounds.minLon) / (bounds.maxLon - bounds.minLon)) * 100,
    y: ((bounds.maxLat - point.latitude) / (bounds.maxLat - bounds.minLat)) * 100,
  };
}

export function unprojectMapPoint(x: number, y: number, bounds: MapBounds = BASEMAP_BOUNDS): Coordinates {
  return {
    latitude: bounds.maxLat - (y / 100) * (bounds.maxLat - bounds.minLat),
    longitude: bounds.minLon + (x / 100) * (bounds.maxLon - bounds.minLon),
  };
}

/** Keep the Shipments extent when pins fit. Extend its viewBox only for outlying coordinates. */
export function mapBoundsForPoints(points: Coordinates[]): MapBounds {
  let { minLat, maxLat, minLon, maxLon }: MapBounds = { ...BASEMAP_BOUNDS };
  for (const point of points) {
    minLat = Math.min(minLat, point.latitude);
    maxLat = Math.max(maxLat, point.latitude);
    minLon = Math.min(minLon, point.longitude);
    maxLon = Math.max(maxLon, point.longitude);
  }
  if (minLat === BASEMAP_BOUNDS.minLat && maxLat === BASEMAP_BOUNDS.maxLat
    && minLon === BASEMAP_BOUNDS.minLon && maxLon === BASEMAP_BOUNDS.maxLon) return BASEMAP_BOUNDS;

  // Uniform scale in the basemap's own coordinate space, with room for edge pins.
  const baseLat = BASEMAP_BOUNDS.maxLat - BASEMAP_BOUNDS.minLat;
  const baseLon = BASEMAP_BOUNDS.maxLon - BASEMAP_BOUNDS.minLon;
  const scale = Math.max((maxLat - minLat) / baseLat, (maxLon - minLon) / baseLon) * 1.08;
  const lat = (minLat + maxLat) / 2;
  const lon = (minLon + maxLon) / 2;
  return {
    minLat: lat - (baseLat * scale) / 2, maxLat: lat + (baseLat * scale) / 2,
    minLon: lon - (baseLon * scale) / 2, maxLon: lon + (baseLon * scale) / 2,
  };
}

const BASEMAP_DOT_STROKE = 2.4;
// A zoomed-in view spreads the same dots further apart, so the dots grow (more slowly than the
// zoom) to keep the continent outline readable instead of sparse; never past this on-screen size.
const BASEMAP_DOT_ZOOM_EXPONENT = 0.75;
const BASEMAP_DOT_MAX_ON_SCREEN = 7;

/**
 * Basemap dot size in viewBox units. At the Shipments extent a dot is 2.4 units. A zoomed-in view
 * magnifies the viewBox, so the stroke is divided by the zoom, then multiplied back by a
 * sub-linear growth so the dots get a little larger on screen instead of vanishing.
 */
export function basemapStrokeWidth(bounds: MapBounds = BASEMAP_BOUNDS): number {
  const zoom = Math.max(
    1,
    (BASEMAP_BOUNDS.maxLon - BASEMAP_BOUNDS.minLon) / (bounds.maxLon - bounds.minLon)
  );
  const onScreen = Math.min(
    BASEMAP_DOT_MAX_ON_SCREEN,
    BASEMAP_DOT_STROKE * zoom ** BASEMAP_DOT_ZOOM_EXPONENT
  );
  return onScreen / zoom;
}

export function mapViewBox(bounds: MapBounds = BASEMAP_BOUNDS): string {
  const topLeft = projectMapPoint({ latitude: bounds.maxLat, longitude: bounds.minLon });
  const bottomRight = projectMapPoint({ latitude: bounds.minLat, longitude: bounds.maxLon });
  return [
    (topLeft.x / 100) * BASEMAP_SIZE.width,
    (topLeft.y / 100) * BASEMAP_SIZE.height,
    ((bottomRight.x - topLeft.x) / 100) * BASEMAP_SIZE.width,
    ((bottomRight.y - topLeft.y) / 100) * BASEMAP_SIZE.height,
  ].join(' ');
}
