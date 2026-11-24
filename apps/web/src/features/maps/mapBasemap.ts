import { BASEMAP_BOUNDS, type MapBounds } from './mapGeometry';
import { lonSpanOf } from './mapView';

/** How far the view is zoomed in compared to the Shipments extent (1 = same as On the water). */
export function basemapLonZoom(bounds: MapBounds = BASEMAP_BOUNDS): number {
  return Math.max(
    1,
    (BASEMAP_BOUNDS.maxLon - BASEMAP_BOUNDS.minLon) / lonSpanOf(bounds),
  );
}

/** Past this zoom, dotted land is replaced by a soft land/ocean fill (store city zoom). */
export const BASEMAP_LAND_SHADE_ZOOM = 4;

export function basemapUsesLandShade(bounds?: MapBounds): boolean {
  return basemapLonZoom(bounds ?? BASEMAP_BOUNDS) >= BASEMAP_LAND_SHADE_ZOOM;
}

/** Continent dot stroke colours shared by Shipments and Sell-through (MapCanvas.test). */
export function basemapDotStroke(mode: 'light' | 'dark'): string {
  return mode === 'dark' ? 'rgba(160,185,205,0.28)' : 'rgba(40,70,95,0.30)';
}

/** Dot opacity fades when land shade carries the background at tight zoom. */
export function basemapDotStrokeOpacity(bounds?: MapBounds): number {
  return basemapUsesLandShade(bounds) ? 0.18 : 1;
}