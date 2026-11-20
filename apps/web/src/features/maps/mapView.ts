import { BASEMAP_BOUNDS, type Coordinates, type MapBounds } from './mapGeometry';

/** The whole globe: the outer limit of any view. */
export const WORLD_BOUNDS: MapBounds = { minLat: -90, maxLat: 90, minLon: -180, maxLon: 180 };
/** Tightest view: a dense metro stays readable without zooming into noise. */
export const MIN_VIEW_LON_SPAN = 2;
/** Degrees of latitude per degree of longitude in the 1000/646 box (the basemap's own ratio). */
export const LAT_PER_LON =
  (BASEMAP_BOUNDS.maxLat - BASEMAP_BOUNDS.minLat) / (BASEMAP_BOUNDS.maxLon - BASEMAP_BOUNDS.minLon);

export function lonSpanOf(view: MapBounds): number {
  return view.maxLon - view.minLon;
}

export function latSpanOf(view: MapBounds): number {
  return view.maxLat - view.minLat;
}

function between(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

/**
 * Keep a view inside `limits` without changing its aspect: a view larger than the limits is
 * scaled down, then the view is shifted back inside.
 */
export function clampMapView(view: MapBounds, limits: MapBounds = WORLD_BOUNDS): MapBounds {
  const scale = Math.min(
    1,
    lonSpanOf(limits) / lonSpanOf(view),
    latSpanOf(limits) / latSpanOf(view)
  );
  const lonSpan = lonSpanOf(view) * scale;
  const latSpan = latSpanOf(view) * scale;
  const lon = between(
    (view.minLon + view.maxLon) / 2,
    limits.minLon + lonSpan / 2,
    limits.maxLon - lonSpan / 2
  );
  const lat = between(
    (view.minLat + view.maxLat) / 2,
    limits.minLat + latSpan / 2,
    limits.maxLat - latSpan / 2
  );
  return {
    minLat: lat - latSpan / 2,
    maxLat: lat + latSpan / 2,
    minLon: lon - lonSpan / 2,
    maxLon: lon + lonSpan / 2,
  };
}

export function panMapView(
  view: MapBounds,
  deltaLon: number,
  deltaLat: number,
  limits: MapBounds = WORLD_BOUNDS
): MapBounds {
  return clampMapView(
    {
      minLat: view.minLat + deltaLat,
      maxLat: view.maxLat + deltaLat,
      minLon: view.minLon + deltaLon,
      maxLon: view.maxLon + deltaLon,
    },
    limits
  );
}

/** factor < 1 zooms in, factor > 1 zooms out, around the centre of the view. */
export function zoomMapView(
  view: MapBounds,
  factor: number,
  limits: MapBounds = WORLD_BOUNDS
): MapBounds {
  const next = Math.max(MIN_VIEW_LON_SPAN, lonSpanOf(view) * factor);
  const k = next / lonSpanOf(view);
  const lat = (view.minLat + view.maxLat) / 2;
  const lon = (view.minLon + view.maxLon) / 2;
  return clampMapView(
    {
      minLat: lat - (latSpanOf(view) * k) / 2,
      maxLat: lat + (latSpanOf(view) * k) / 2,
      minLon: lon - next / 2,
      maxLon: lon + next / 2,
    },
    limits
  );
}

/**
 * Where a steward may pan: the dotted basemap, the fitted view and every pin, never past the
 * world. Stored coordinates are untouched by any of this.
 */
export function panLimits(fit: MapBounds, points: readonly Coordinates[]): MapBounds {
  let { minLat, maxLat, minLon, maxLon } = BASEMAP_BOUNDS as MapBounds;
  minLat = Math.min(minLat, fit.minLat);
  maxLat = Math.max(maxLat, fit.maxLat);
  minLon = Math.min(minLon, fit.minLon);
  maxLon = Math.max(maxLon, fit.maxLon);
  for (const point of points) {
    minLat = Math.min(minLat, point.latitude);
    maxLat = Math.max(maxLat, point.latitude);
    minLon = Math.min(minLon, point.longitude);
    maxLon = Math.max(maxLon, point.longitude);
  }
  return {
    minLat: Math.max(WORLD_BOUNDS.minLat, minLat),
    maxLat: Math.min(WORLD_BOUNDS.maxLat, maxLat),
    minLon: Math.max(WORLD_BOUNDS.minLon, minLon),
    maxLon: Math.min(WORLD_BOUNDS.maxLon, maxLon),
  };
}
