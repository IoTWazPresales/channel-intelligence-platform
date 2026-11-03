/** Project store coordinates from the points on the map. No fixed geography. */

export type MapPoint = { id: string; latitude: number; longitude: number };

export type Projected = { id: string; x: number; y: number };

export function projectStores(points: MapPoint[]): Projected[] {
  if (points.length === 0) return [];
  let minLat = Math.min(...points.map((point) => point.latitude));
  let maxLat = Math.max(...points.map((point) => point.latitude));
  let minLon = Math.min(...points.map((point) => point.longitude));
  let maxLon = Math.max(...points.map((point) => point.longitude));
  if (maxLat - minLat < 1e-9) {
    minLat -= 1;
    maxLat += 1;
  }
  if (maxLon - minLon < 1e-9) {
    minLon -= 1;
    maxLon += 1;
  }
  const latPad = (maxLat - minLat) * 0.08;
  const lonPad = (maxLon - minLon) * 0.08;
  minLat -= latPad;
  maxLat += latPad;
  minLon -= lonPad;
  maxLon += lonPad;
  const latSpan = maxLat - minLat;
  const lonSpan = maxLon - minLon;
  return points.map((point) => ({
    id: point.id,
    x: ((point.longitude - minLon) / lonSpan) * 100,
    y: ((maxLat - point.latitude) / latSpan) * 100,
  }));
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
