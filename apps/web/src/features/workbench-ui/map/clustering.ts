import type { MapGeoJSONFeature } from 'maplibre-gl';

export const POINT_SOURCE = 'workbench-points';

export type Coordinates = { latitude: number; longitude: number };

export type WorkbenchPoint = Coordinates & {
  id: string;
  label: string;
  proposed: boolean;
  score: number | null;
};

export type SourceMarker = Coordinates & {
  key: string;
  pointId?: string;
  clusterId?: number;
  count: number;
  proposed: boolean;
  score: number | null;
};

export function usableCoordinates(point: Coordinates): boolean {
  return Number.isFinite(point.latitude)
    && Number.isFinite(point.longitude)
    && Math.abs(point.latitude) <= 90
    && Math.abs(point.longitude) <= 180;
}

export function pointCollection(points: readonly WorkbenchPoint[]) {
  return {
    type: 'FeatureCollection' as const,
    features: points.filter(usableCoordinates).map((point) => ({
      type: 'Feature' as const,
      id: point.id,
      geometry: {
        type: 'Point' as const,
        coordinates: [point.longitude, point.latitude],
      },
      properties: {
        id: point.id,
        proposed: point.proposed,
        score: Number.isFinite(point.score) ? point.score : null,
      },
    })),
  };
}

/** MapLibre/Supercluster owns clustering; these properties preserve the existing colour mean. */
export function clusterSource(points: readonly WorkbenchPoint[]) {
  return {
    type: 'geojson' as const,
    data: pointCollection(points),
    cluster: true,
    clusterRadius: 36,
    clusterMaxZoom: 14,
    clusterProperties: {
      score_sum: ['+', ['coalesce', ['get', 'score'], 0]],
      score_count: ['+', ['case', ['==', ['get', 'score'], null], 0, 1]],
      proposed_count: ['+', ['case', ['get', 'proposed'], 1, 0]],
    },
  };
}

/** Source queries can return the same point/cluster from several neighbouring tiles. */
export function sourceMarkers(
  features: readonly Pick<MapGeoJSONFeature, 'geometry' | 'properties'>[],
): SourceMarker[] {
  const found = new Map<string, SourceMarker>();
  for (const feature of features) {
    if (feature.geometry.type !== 'Point') continue;
    const [longitude, latitude] = feature.geometry.coordinates;
    const properties = feature.properties ?? {};
    const clustered = properties.cluster === true || properties.cluster === 1;
    const key = clustered ? `cluster:${properties.cluster_id}` : `point:${properties.id}`;
    if (found.has(key)) continue;
    if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) continue;
    if (!clustered && typeof properties.id !== 'string') continue;
    const scoreCount = Number(properties.score_count ?? 0);
    found.set(key, {
      key,
      longitude,
      latitude,
      pointId: clustered ? undefined : properties.id,
      clusterId: clustered ? Number(properties.cluster_id) : undefined,
      count: clustered ? Number(properties.point_count) : 1,
      proposed: clustered
        ? Number(properties.proposed_count ?? 0) > 0
        : properties.proposed === true || properties.proposed === 1,
      score: clustered
        ? (scoreCount > 0 ? Number(properties.score_sum) / scoreCount : null)
        : (typeof properties.score === 'number' ? properties.score : null),
    });
  }
  return [...found.values()];
}

/** Fit the shortest longitude arc, including stores on opposite sides of the date line. */
export function pointBounds(
  points: readonly Coordinates[],
): [[number, number], [number, number]] | null {
  const valid = points.filter(usableCoordinates);
  if (!valid.length) return null;
  const longitudes = valid.map((point) => (point.longitude + 360) % 360).sort((a, b) => a - b);
  let largestGap = -1;
  let gapIndex = 0;
  for (let i = 0; i < longitudes.length; i += 1) {
    const next = i + 1 === longitudes.length ? longitudes[0] + 360 : longitudes[i + 1];
    if (next - longitudes[i] > largestGap) {
      largestGap = next - longitudes[i];
      gapIndex = i;
    }
  }
  const west = longitudes[(gapIndex + 1) % longitudes.length];
  let east = longitudes[gapIndex];
  if (east < west) east += 360;
  const latitude = (value: number) => Math.max(-85.051129, Math.min(85.051129, value));
  return [
    [west, latitude(Math.min(...valid.map((point) => point.latitude)))],
    [east, latitude(Math.max(...valid.map((point) => point.latitude)))],
  ];
}

export function wrapLongitude(longitude: number): number {
  return ((longitude + 180) % 360 + 360) % 360 - 180;
}
