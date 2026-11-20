import {
  BASEMAP_BOUNDS,
  projectMapPoint,
  unprojectMapPoint,
} from '@/features/maps/mapGeometry';
import type { Coordinates, MapBounds } from '@/features/maps/mapGeometry';
import { clampMapView } from '@/features/maps/mapView';

export type MapPoint = { id: string; latitude: number; longitude: number };

export type Projected = { id: string; x: number; y: number };

const BASE_LAT_SPAN = BASEMAP_BOUNDS.maxLat - BASEMAP_BOUNDS.minLat;
const BASE_LON_SPAN = BASEMAP_BOUNDS.maxLon - BASEMAP_BOUNDS.minLon;
// Continent scale: a country, or one pin, still shows the dotted continent around it.
export const DEFAULT_MIN_LON_SPAN = 60;
// Generous room so the outline, not the pins, is the focus of the box.
const FIT_PADDING = 1.5;

/** Real coordinates, or null. Missing, blank, non-numeric, out of range and 0,0 are not a place. */
export function finiteCoordinates(latitude: unknown, longitude: unknown): Coordinates | null {
  if (latitude == null || longitude == null || latitude === '' || longitude === '') return null;
  const lat = Number(latitude);
  const lon = Number(longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  if (lat === 0 && lon === 0) return null;
  return { latitude: lat, longitude: lon };
}

/**
 * With no pins, keep the Shipments extent. Otherwise fit the continent or region the pins are in
 * inside the same box: padded generously, at least 60 degrees wide, with the basemap's own
 * degrees-per-pixel ratio so the dots are not distorted, and never past the world. The
 * projection stays shared by the basemap, the pins and dragging.
 */
export function storeMapBounds<T extends Coordinates>(points: readonly T[]): MapBounds {
  if (points.length === 0) return BASEMAP_BOUNDS;
  let minLat = Infinity;
  let maxLat = -Infinity;
  let minLon = Infinity;
  let maxLon = -Infinity;
  for (const point of points) {
    minLat = Math.min(minLat, point.latitude);
    maxLat = Math.max(maxLat, point.latitude);
    minLon = Math.min(minLon, point.longitude);
    maxLon = Math.max(maxLon, point.longitude);
  }
  const lonSpan = Math.max(
    DEFAULT_MIN_LON_SPAN,
    (maxLon - minLon) * FIT_PADDING,
    (maxLat - minLat) * FIT_PADDING * (BASE_LON_SPAN / BASE_LAT_SPAN)
  );
  const latSpan = (lonSpan / BASE_LON_SPAN) * BASE_LAT_SPAN;
  const lat = (minLat + maxLat) / 2;
  const lon = (minLon + maxLon) / 2;
  return clampMapView({
    minLat: lat - latSpan / 2,
    maxLat: lat + latSpan / 2,
    minLon: lon - lonSpan / 2,
    maxLon: lon + lonSpan / 2,
  });
}

export const unprojectStore = unprojectMapPoint;

export function projectStores(points: MapPoint[], bounds = storeMapBounds(points)): Projected[] {
  return points.map((point) => ({ id: point.id, ...projectMapPoint(point, bounds) }));
}

export type SpreadPin = Projected & { dx: number; dy: number };

const RING_MAX = 12;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

/** Overlapping dots move on screen only. Stored coordinates stay as the steward saved them. */
export function spreadOverlaps(
  pins: Projected[],
  mapPx: { w: number; h: number },
  diameter = 14
): SpreadPin[] {
  const remaining = new Set(pins);
  const placed: SpreadPin[] = [];
  for (const first of remaining) {
    const list = [first];
    remaining.delete(first);
    // Connected neighbours form a cluster, including across any bucket boundary.
    for (let index = 0; index < list.length; index += 1) {
      for (const pin of remaining) {
        const dx = ((pin.x - list[index].x) / 100) * mapPx.w;
        const dy = ((pin.y - list[index].y) / 100) * mapPx.h;
        if (Math.hypot(dx, dy) < diameter) {
          list.push(pin);
          remaining.delete(pin);
        }
      }
    }
    if (list.length === 1) {
      placed.push({ ...first, dx: 0, dy: 0 });
      continue;
    }
    list.sort((a, b) => a.id.localeCompare(b.id));
    const centreX = list.reduce((sum, pin) => sum + pin.x, 0) / list.length;
    const centreY = list.reduce((sum, pin) => sum + pin.y, 0) / list.length;
    // Small clusters fan on a ring (the old 12px minimum radius). Larger ones lay out on a
    // golden-angle spiral so the footprint grows with sqrt(n) instead of linearly with n.
    const ring = list.length <= RING_MAX;
    const radius = Math.max(12, (diameter + 2) / (2 * Math.sin(Math.PI / list.length)));
    list.forEach((pin, index) => {
      const angle = ring ? (index / list.length) * Math.PI * 2 : index * GOLDEN_ANGLE;
      const spread = ring ? radius : diameter * Math.sqrt(index + 0.5);
      placed.push({
        ...pin,
        dx: ((centreX - pin.x) / 100) * mapPx.w + Math.cos(angle) * spread,
        dy: ((centreY - pin.y) / 100) * mapPx.h + Math.sin(angle) * spread,
      });
    });
  }
  return placed;
}

export function sellThroughColor(ratio: number | null, best: string, worst: string): string {
  if (ratio == null || Number.isNaN(ratio)) return worst;
  const mix = Math.round(Math.min(1, Math.max(0, ratio)) * 100);
  return `color-mix(in srgb, ${best} ${mix}%, ${worst})`;
}
