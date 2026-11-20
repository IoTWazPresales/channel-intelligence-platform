import type { Projected } from './storeMapLayout';

/** Pins in the same screen cell of this side (px) become one numbered marker. */
export const CLUSTER_CELL_PX = 26;
// Two groups whose centres end up closer than this would overlap on screen: they merge.
const MERGE_PX = 12;
/** The Shipments click target. Smaller where neighbours are closer, never larger. */
export const MAX_HIT_PX = 44;

export type ClusterPin = Projected & { latitude: number; longitude: number };

export type PinGroup = {
  /** The pin's own id for one pin; a stable `cluster:` id for a group. */
  id: string;
  /** Centroid of the members, as a share of the map box in percent: their real position. */
  x: number;
  y: number;
  latitude: number;
  longitude: number;
  members: ClusterPin[];
  /** Distance in px to the nearest other group (capped at MAX_HIT_PX): the room for a click target. */
  nearestPx: number;
};

type Centre = { px: number; py: number };

function mean(values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

/** The sell-through a cluster is coloured by: the mean of its members that have one, else null. */
export function meanSellThrough(ratios: readonly (number | null | undefined)[]): number | null {
  const known = ratios.filter((ratio): ratio is number => ratio != null && !Number.isNaN(ratio));
  return known.length ? mean(known) : null;
}

/** Look up the groups within reach (3 x 3 cells of MAX_HIT_PX) of each group. */
function neighbours(centres: Centre[]) {
  const cell = (value: number) => Math.floor(value / MAX_HIT_PX);
  const buckets = new Map<string, number[]>();
  centres.forEach((centre, index) => {
    const key = `${cell(centre.px)}:${cell(centre.py)}`;
    const list = buckets.get(key);
    if (list) list.push(index);
    else buckets.set(key, [index]);
  });
  return (index: number, visit: (other: number, distance: number) => void) => {
    const cx = cell(centres[index].px);
    const cy = cell(centres[index].py);
    for (let dx = -1; dx <= 1; dx += 1) {
      for (let dy = -1; dy <= 1; dy += 1) {
        for (const other of buckets.get(`${cx + dx}:${cy + dy}`) ?? []) {
          if (other === index) continue;
          visit(
            other,
            Math.hypot(centres[index].px - centres[other].px, centres[index].py - centres[other].py)
          );
        }
      }
    }
  };
}

function centresOf(groups: ClusterPin[][], mapPx: { w: number; h: number }): Centre[] {
  return groups.map((members) => ({
    px: (mean(members.map((pin) => pin.x)) / 100) * mapPx.w,
    py: (mean(members.map((pin) => pin.y)) / 100) * mapPx.h,
  }));
}

/**
 * Group pins that fall in the same screen grid cell (`cellPx`, from the current view and map
 * size) into one marker at the centroid of its members. Groups whose centres would still overlap
 * across a cell edge are merged too. Re-run it on every view change: zooming in separates pins,
 * so groups dissolve into single pins.
 */
export function clusterPins(
  pins: readonly ClusterPin[],
  mapPx: { w: number; h: number },
  cellPx: number = CLUSTER_CELL_PX
): PinGroup[] {
  const cells = new Map<string, ClusterPin[]>();
  for (const pin of pins) {
    const key = `${Math.floor(((pin.x / 100) * mapPx.w) / cellPx)}:${Math.floor(((pin.y / 100) * mapPx.h) / cellPx)}`;
    const list = cells.get(key);
    if (list) list.push(pin);
    else cells.set(key, [pin]);
  }

  const cellGroups = [...cells.values()];
  const parent = cellGroups.map((_, index) => index);
  const find = (index: number): number => {
    let root = index;
    while (parent[root] !== root) root = parent[root];
    return root;
  };
  const near = neighbours(centresOf(cellGroups, mapPx));
  cellGroups.forEach((_, index) => {
    near(index, (other, distance) => {
      if (distance < MERGE_PX) parent[find(other)] = find(index);
    });
  });
  const merged = new Map<number, ClusterPin[]>();
  cellGroups.forEach((members, index) => {
    const root = find(index);
    const list = merged.get(root);
    if (list) list.push(...members);
    else merged.set(root, [...members]);
  });

  const groups = [...merged.values()];
  const centres = centresOf(groups, mapPx);
  const nearest = groups.map(() => MAX_HIT_PX);
  const reach = neighbours(centres);
  groups.forEach((_, index) => {
    reach(index, (_other, distance) => {
      nearest[index] = Math.min(nearest[index], distance);
    });
  });

  return groups.map((members, index) => {
    const first = [...members].sort((a, b) => a.id.localeCompare(b.id))[0];
    return {
      id: members.length === 1 ? first.id : `cluster:${first.id}:${members.length}`,
      x: mean(members.map((pin) => pin.x)),
      y: mean(members.map((pin) => pin.y)),
      latitude: mean(members.map((pin) => pin.latitude)),
      longitude: mean(members.map((pin) => pin.longitude)),
      members,
      nearestPx: nearest[index],
    };
  });
}
