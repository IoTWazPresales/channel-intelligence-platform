/** How many dashboard grid cells a chart needs so it is fully visible. */

export const DASHBOARD_ROW_HEIGHT = 36;
export const DASHBOARD_MARGIN = 8;

export type Slot = { w: number; h: number };

/** Grid rows whose pixel height covers `px`, including the gap between rows. */
export function gridRowsForPixels(px: number): number {
  return Math.max(4, Math.ceil((px + DASHBOARD_MARGIN) / (DASHBOARD_ROW_HEIGHT + DASHBOARD_MARGIN)));
}

/**
 * Grow one widget's height so a long chart or table is visible.
 * Width stays whatever that widget already has, so a neighbour is not pushed to a new size.
 * Never shrinks a cell the viewer has already made taller.
 */
export function slotForSeries(visual: string, rowCount: number, current: Slot, topN?: number): Slot | null {
  const n = Math.max(0, rowCount);
  if (n === 0 || visual === 'kpi') return null;
  const capped = Math.min(n, 24);
  const shown = topN && topN > 0 ? Math.min(capped, topN) : capped;
  let px = 220;
  if (visual === 'hbar') px = shown * 34 + 156;
  else if (visual === 'table' || visual === 'pivot') px = shown * 32 + 128;
  else if (visual === 'pie' || visual === 'donut' || visual === 'scatter') px = 320;
  else px = 200 + shown * 6;
  const h = Math.max(current.h, gridRowsForPixels(px));
  if (h === current.h) return null;
  return { w: current.w, h };
}
