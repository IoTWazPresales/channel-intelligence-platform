import { fmtDay, fmtUnits } from './format';
import type { Vessel } from './types';

export type Cluster = {
  id: string;
  vessels: Vessel[];
  x: number;
  y: number;
};

const ASPECT = 646 / 1000; // the map is 1000 x 646: a y percentage is shorter than an x percentage

function dist(a: { x: number; y: number }, b: { x: number; y: number }): number {
  return Math.hypot(a.x - b.x, (a.y - b.y) * ASPECT);
}

/** Vessels within `radius` percent of each other collapse into one cluster (single linkage, soonest ETA first). */
export function clusterVessels(vessels: Vessel[], radius: number): Cluster[] {
  const clusters: Cluster[] = [];
  for (const v of vessels) {
    const hit = clusters.find((c) => c.vessels.some((m) => dist(m, v) <= radius));
    if (hit) {
      hit.vessels.push(v);
      hit.x = hit.vessels.reduce((s, m) => s + m.x, 0) / hit.vessels.length;
      hit.y = hit.vessels.reduce((s, m) => s + m.y, 0) / hit.vessels.length;
    } else {
      clusters.push({ id: v.id, vessels: [v], x: v.x, y: v.y });
    }
  }
  return clusters;
}

export function nearestPort(c: { x: number; y: number }, ports: Array<{ label: string; x: number; y: number }>): string {
  let best = ports[0];
  for (const p of ports) if (dist(c, p) < dist(c, best)) best = p;
  return best ? best.label.charAt(0) + best.label.slice(1).toLowerCase() : '';
}

/** Chip for a cluster: "3 vessels at or near Durban" / "4,013 u · ETA 27–30 Oct". */
export function clusterChip(c: Cluster, ports: Array<{ label: string; x: number; y: number }>): { title: string; sub: string } {
  const etas = c.vessels.map((v) => v.eta).filter((e): e is string => Boolean(e)).sort();
  const first = etas[0];
  const last = etas[etas.length - 1];
  return {
    title: `${c.vessels.length} vessels at or near ${nearestPort(c, ports)}`,
    sub: `${fmtUnits(c.vessels.reduce((s, v) => s + v.units, 0))} u · ETA ${etaRange(first, last)}`,
  };
}

/** "27–30 Oct" within a month, "30 Oct–2 Nov" across two. */
export function etaRange(first: string | undefined, last: string | undefined): string {
  if (!first || !last) return 'no ETA';
  if (first === last) return fmtDay(first);
  const a = fmtDay(first).split(' ');
  const b = fmtDay(last).split(' ');
  return a[1] === b[1] ? `${a[0]}–${b[0]} ${a[1]}` : `${fmtDay(first)}–${fmtDay(last)}`;
}

export type LabelBox = { id: string; x: number; y: number; w: number; h: number };
type Anchor = { id: string; x: number; y: number; priority: number };

function overlaps(a: LabelBox, b: LabelBox): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

/**
 * Place a label box beside each anchor so no two overlap, none covers a box in `avoid` (port names, markers) and none
 * leaves the map. Anchors are tried in priority order (the selected vessel first), at four corners around the anchor;
 * one that fits nowhere gets no label. Sizes, gaps and boxes are percentages of the map, so the caller converts from
 * pixels with the map's real size (a label is the same size in pixels on a phone as on a desk).
 */
export function placeLabels(
  anchors: Anchor[],
  size: { w: number; h: number },
  avoid: LabelBox[] = [],
  gap: { x: number; y: number } = { x: 1.8, y: 1.4 },
): LabelBox[] {
  const placed: LabelBox[] = [];
  for (const a of [...anchors].sort((p, q) => p.priority - q.priority)) {
    const corners: Array<[number, number]> = [
      [a.x + gap.x, a.y - gap.y - size.h], // right, above
      [a.x - gap.x - size.w, a.y - gap.y - size.h], // left, above
      [a.x + gap.x, a.y + gap.y], // right, below
      [a.x - gap.x - size.w, a.y + gap.y], // left, below
    ];
    for (const [x, y] of corners) {
      const box: LabelBox = { id: a.id, x, y, w: size.w, h: size.h };
      const inside = box.x >= 0 && box.y >= 0 && box.x + box.w <= 100 && box.y + box.h <= 100;
      if (inside && !placed.some((p) => overlaps(p, box)) && !avoid.some((p) => overlaps(p, box))) {
        placed.push(box);
        break;
      }
    }
  }
  return placed;
}
