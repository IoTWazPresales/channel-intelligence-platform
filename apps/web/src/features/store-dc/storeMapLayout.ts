import { mapBoundsForPoints, projectMapPoint, unprojectMapPoint } from '@/features/maps/mapGeometry';

export type MapPoint = { id: string; latitude: number; longitude: number };

export type Projected = { id: string; x: number; y: number };

// Use the Shipments projection for both the basemap and pin/drag coordinates.
export const storeMapBounds = mapBoundsForPoints;
export const unprojectStore = unprojectMapPoint;

export function projectStores(points: MapPoint[], bounds = storeMapBounds(points)): Projected[] {
  return points.map((point) => ({ id: point.id, ...projectMapPoint(point, bounds) }));
}

export type SpreadPin = Projected & { dx: number; dy: number };

/** Overlapping dots move on screen only. Stored coordinates stay as the steward saved them. */
export function spreadOverlaps(pins: Projected[], gap = 12): SpreadPin[] {
  const groups = new Map<string, Projected[]>();
  for (const pin of pins) {
    const bucket = `${Math.round(pin.x * 10) / 10}:${Math.round(pin.y * 10) / 10}`;
    const list = groups.get(bucket) ?? [];
    list.push(pin);
    groups.set(bucket, list);
  }
  const placed: SpreadPin[] = [];
  for (const list of groups.values()) {
    list.forEach((pin, index) => {
      if (list.length === 1) {
        placed.push({ ...pin, dx: 0, dy: 0 });
        return;
      }
      const angle = (index / list.length) * Math.PI * 2;
      placed.push({ ...pin, dx: Math.cos(angle) * gap, dy: Math.sin(angle) * gap });
    });
  }
  return placed;
}

export function sellThroughColor(ratio: number | null, best: string, worst: string): string {
  if (ratio == null || Number.isNaN(ratio)) return worst;
  const mix = Math.round(Math.min(1, Math.max(0, ratio)) * 100);
  return `color-mix(in srgb, ${best} ${mix}%, ${worst})`;
}
