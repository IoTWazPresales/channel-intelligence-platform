import {
  mapBoundsForPoints,
  projectMapPoint,
  unprojectMapPoint,
} from '@/features/maps/mapGeometry';

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
    // Keep the old 12px fan radius, growing it for larger clusters.
    const radius = Math.max(12, (diameter + 2) / (2 * Math.sin(Math.PI / list.length)));
    list.forEach((pin, index) => {
      const angle = (index / list.length) * Math.PI * 2;
      placed.push({
        ...pin,
        dx: ((centreX - pin.x) / 100) * mapPx.w + Math.cos(angle) * radius,
        dy: ((centreY - pin.y) / 100) * mapPx.h + Math.sin(angle) * radius,
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
