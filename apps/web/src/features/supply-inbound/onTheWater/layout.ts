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

// UN/LOCODE the importer stores in `deliver_port`, as the map's port ids.
const DELIVER_PORT_IDS: Record<string, string[]> = { ZADUR: ['DURBAN'], ZAJNB: ['DURBAN', 'CITY DEEP'], MUPLU: ['PORT LOUIS'] };

/**
 * Ports a vessel is heading to or coming from: the origins and stops in its lane label ("Chongqing / Shenzhen → Durban →
 * City Deep") and its discharge port, as upper-case map labels. A phone-width map names only these ports and Durban.
 */
export function portsInUse(vessels: Vessel[], ports: Array<{ id: string; label: string }>): Set<string> {
  const names = new Map(ports.map((p) => [p.label.toUpperCase(), p.id]));
  const used = new Set<string>(['DURBAN']);
  const add = (name: string) => {
    const id = names.get(name.trim().toUpperCase());
    if (id) used.add(id);
  };
  for (const v of vessels) {
    for (const stop of v.lane_label.split('→')) for (const name of stop.split('/')) add(name);
    for (const id of DELIVER_PORT_IDS[(v.deliver_port ?? '').toUpperCase()] ?? []) used.add(id);
  }
  return used;
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
    sub: `${fmtUnits(c.vessels.reduce((s, v) => s + v.units, 0))} u · ETA at port ${etaRange(first, last)}`,
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
/** `size` (percent of the map) overrides the common size for this anchor: a label is as wide as its text. */
type Anchor = { id: string; x: number; y: number; priority: number; size?: { w: number; h: number } };

/**
 * The width in px a vessel label draws: its title (12 px bold) or its second line (11 px), whichever is longer, plus padding and
 * border. The label is `nowrap`, so it is as wide as its text whatever box the placement reserved: "4 vessels at or near Durban" with
 * "3,494 u · ETA at port 31 Oct–5 Nov" draws about 201 px, and a fixed 160 px box let it cover the end of "CITY DEEP".
 */
export function labelWidthPx(title: string, sub: string): number {
  return Math.ceil(Math.max(title.length * 7.2, sub.length * 5.6) + 24);
}

/** What a port name draws at 11 px / 600 weight / .04em letter-spacing, per capital letter, in px (measured in the render). */
export const PORT_NAME_PX_PER_LETTER = 8.4;

/**
 * The box a port's name occupies, as a percentage of the map, for `placeLabels` to keep clear. The name starts 12 px beside its
 * dot (GOV-008 batch 3: the box was 7.6 px a letter and 7 px short, so a vessel label could sit over the end of "CITY DEEP").
 */
export function portNameBox(
  p: { id: string; label: string; x: number; y: number; label_side?: 'left' | 'right' | 'above' },
  pctX: (px: number) => number,
  pctY: (px: number) => number,
): LabelBox {
  const w = pctX(p.label.length * PORT_NAME_PX_PER_LETTER + 16);
  const side = p.label_side ?? (p.x > 82 ? 'left' : 'right');
  if (side === 'above') return { id: `p:${p.id}`, x: p.x - w / 2, y: p.y - pctY(26), w, h: pctY(18) };
  return { id: `p:${p.id}`, x: side === 'left' ? p.x - pctX(6) - w : p.x + pctX(6), y: p.y - pctY(9), w, h: pctY(18) };
}

function overlaps(a: LabelBox, b: LabelBox): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

/**
 * Place a label box beside each anchor so no two overlap, none covers a box in `avoid` (port names, markers) and none
 * leaves the map. Anchors are tried in priority order (the selected vessel first), at four corners around the anchor;
 * one that fits nowhere (after the four corners, and the same four one box higher or lower) gets no label. Sizes, gaps and boxes are percentages of the map, so the caller converts from
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
    const own = a.size ?? size;
    const corners: Array<[number, number]> = [
      [a.x + gap.x, a.y - gap.y - own.h], // right, above
      [a.x - gap.x - own.w, a.y - gap.y - own.h], // left, above
      [a.x + gap.x, a.y + gap.y], // right, below
      [a.x - gap.x - own.w, a.y + gap.y], // left, below
      // When a label as wide as its text fits no corner, it is tried one box higher or lower (still beside its anchor) before it
      // is dropped, so a crowded corner of the map loses its label only when nothing nearby is free.
      [a.x + gap.x, a.y - 2 * gap.y - 2 * own.h], // right, one box higher
      [a.x - gap.x - own.w, a.y - 2 * gap.y - 2 * own.h], // left, one box higher
      [a.x + gap.x, a.y + 2 * gap.y + own.h], // right, one box lower
      [a.x - gap.x - own.w, a.y + 2 * gap.y + own.h], // left, one box lower
    ];
    for (const [x, y] of corners) {
      const box: LabelBox = { id: a.id, x, y, w: own.w, h: own.h };
      const inside = box.x >= 0 && box.y >= 0 && box.x + box.w <= 100 && box.y + box.h <= 100;
      if (inside && !placed.some((p) => overlaps(p, box)) && !avoid.some((p) => overlaps(p, box))) {
        placed.push(box);
        break;
      }
    }
  }
  return placed;
}
