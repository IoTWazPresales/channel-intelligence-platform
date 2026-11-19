import type { TimelineBar, TimelineCase } from '@/features/promotions-funding/plannerLayout/timelineModel';

export type CustomerRowBar<T extends TimelineCase = TimelineCase> = TimelineBar<T> & {
  /** 0-based sub-lane inside the customer's row; only above 0 when two promotions overlap in time. */
  lane: number;
};

export type CustomerRow<T extends TimelineCase = TimelineCase> = {
  /** Stable key: the trimmed, lower-cased customer name; `unassigned` when the case has no customer name. */
  key: string;
  /** Display name as the first case wrote it; empty when the case has no customer name. */
  customer: string;
  bars: CustomerRowBar<T>[];
  laneCount: number;
};

export const UNASSIGNED_KEY = 'unassigned';

/**
 * One row per customer (case-insensitive name), customers in name order and the nameless group last.
 * Inside a row each promotion is a bar; bars that overlap in time go to extra sub-lanes so none is hidden.
 * The window end day is inclusive, so a bar may reuse a lane only when it starts after the last bar there ended.
 */
export function customerRows<T extends TimelineCase>(bars: readonly TimelineBar<T>[]): CustomerRow<T>[] {
  const groups = new Map<string, { customer: string; bars: TimelineBar<T>[] }>();
  const ordered = [...bars].sort((a, b) => (a.start === b.start ? a.id - b.id : a.start < b.start ? -1 : 1));
  for (const bar of ordered) {
    const name = (bar.row.customer_name ?? '').trim();
    const key = name === '' ? UNASSIGNED_KEY : name.toLowerCase();
    const group = groups.get(key);
    if (group) group.bars.push(bar);
    else groups.set(key, { customer: name, bars: [bar] });
  }
  const rows: CustomerRow<T>[] = [];
  for (const [key, group] of groups) {
    const laneEnds: string[] = [];
    const placed = group.bars.map((bar) => {
      let lane = laneEnds.findIndex((end) => end < bar.start);
      if (lane === -1) lane = laneEnds.length;
      laneEnds[lane] = bar.end;
      return { ...bar, lane };
    });
    rows.push({ key, customer: group.customer, bars: placed, laneCount: Math.max(1, laneEnds.length) });
  }
  return rows.sort((a, b) =>
    a.key === b.key ? 0 : a.key === UNASSIGNED_KEY ? 1 : b.key === UNASSIGNED_KEY ? -1 : a.key < b.key ? -1 : 1,
  );
}
