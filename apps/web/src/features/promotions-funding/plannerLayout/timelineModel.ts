import { addDaysIso } from '@/features/promotions-funding/plannerCards';

export type TimelineCase = {
  id: number;
  case_code: string;
  case_name?: string | null;
  customer_name?: string | null;
  status: string;
  window_start?: string | null;
  window_end?: string | null;
};

export type TimelineBar<T extends TimelineCase = TimelineCase> = {
  id: number;
  row: T;
  start: string;
  end: string;
  leftPct: number;
  widthPct: number;
};

export type TimelineModel<T extends TimelineCase = TimelineCase> = {
  start: string;
  end: string;
  todayPct: number;
  bars: TimelineBar<T>[];
  /** Cases left off the axis because they carry no window dates. */
  undated: number;
};

const DAY_MS = 86_400_000;

function ms(iso: string): number {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return Date.UTC(y, m - 1, d);
}

function daysBetween(a: string, b: string): number {
  return Math.round((ms(b) - ms(a)) / DAY_MS);
}

function monthStart(iso: string): string {
  return `${iso.slice(0, 7)}-01`;
}

function monthEnd(iso: string): string {
  const [y, m] = iso.split('-').map(Number);
  return new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10);
}

export const TIMELINE_MONTH_PX = 72;
export const TIMELINE_DEFAULT_VIEW_MONTHS = 6;
export const TIMELINE_WINDOW_MONTHS_BACK = 3;
export const TIMELINE_WINDOW_MONTHS_FORWARD = 3;

export function addMonthsIso(iso: string, months: number): string {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(Date.UTC(y, m - 1 + months, d)).toISOString().slice(0, 10);
}

/** Roughly three months before and after today, snapped to month edges — the default scroll focus. */
export function defaultTimelineViewWindow(today: string): { start: string; end: string } {
  return {
    start: monthStart(addMonthsIso(today, -TIMELINE_WINDOW_MONTHS_BACK)),
    end: monthEnd(addMonthsIso(today, TIMELINE_WINDOW_MONTHS_FORWARD)),
  };
}

export function axisMonthCount(axisStart: string, axisEnd: string): number {
  let n = 0;
  let cur = monthStart(axisStart);
  while (cur <= axisEnd) {
    n += 1;
    cur = addDaysIso(monthEnd(cur), 1);
  }
  return n;
}

/** Month ticks for long axes: thin labels instead of stacking every month. */
export function monthTicksForAxis(
  axisStart: string,
  axisEnd: string,
  maxLabels = 14,
): { label: string; leftPct: number }[] {
  const all = monthTicks(axisStart, axisEnd);
  if (all.length <= maxLabels) return all;
  const step = Math.ceil(all.length / maxLabels);
  return all.filter((_, i) => i % step === 0 || i === all.length - 1);
}

/** Scroll offset so the default view window is centred in the viewport. */
export function scrollLeftForViewWindow(
  viewStart: string,
  axisStart: string,
  axisEnd: string,
  trackWidthPx: number,
  viewportPx: number,
): number {
  const total = daysBetween(axisStart, axisEnd) + 1;
  const leftPct = (Math.max(0, daysBetween(axisStart, viewStart)) / total) * 100;
  const anchorPx = (leftPct / 100) * trackWidthPx;
  return Math.max(0, Math.min(anchorPx - viewportPx / 4, trackWidthPx - viewportPx));
}

/** Left and width as percentages of the axis; the window end day is inclusive. */
export function barGeometry(start: string, end: string, axisStart: string, axisEnd: string) {
  const total = daysBetween(axisStart, axisEnd) + 1;
  const leftPct = (daysBetween(axisStart, start) / total) * 100;
  const widthPct = ((daysBetween(start, end) + 1) / total) * 100;
  return { leftPct, widthPct };
}

export function monthTicks(axisStart: string, axisEnd: string): { label: string; leftPct: number }[] {
  const total = daysBetween(axisStart, axisEnd) + 1;
  const out: { label: string; leftPct: number }[] = [];
  let cur = monthStart(axisStart);
  while (cur <= axisEnd) {
    const label = new Date(ms(cur)).toLocaleDateString('en-GB', { month: 'short', year: 'numeric', timeZone: 'UTC' });
    out.push({ label, leftPct: (Math.max(0, daysBetween(axisStart, cur)) / total) * 100 });
    cur = addDaysIso(monthEnd(cur), 1);
  }
  return out;
}

/** Our case windows on one date axis. Cases without both dates are counted, not drawn. */
export function buildTimeline<T extends TimelineCase>(cases: readonly T[], today: string): TimelineModel<T> {
  const dated = cases
    .filter((c) => c.window_start)
    .map((c) => {
      const start = String(c.window_start).slice(0, 10);
      const rawEnd = c.window_end ? String(c.window_end).slice(0, 10) : start;
      return { c, start, end: rawEnd < start ? start : rawEnd };
    })
    .sort((a, b) => (a.start === b.start ? a.c.id - b.c.id : a.start < b.start ? -1 : 1));
  const undated = cases.length - dated.length;
  const lo = dated.reduce((m, d) => (d.start < m ? d.start : m), today);
  const hi = dated.reduce((m, d) => (d.end > m ? d.end : m), today);
  const start = monthStart(lo);
  const end = monthEnd(hi);
  const total = daysBetween(start, end) + 1;
  return {
    start,
    end,
    todayPct: (daysBetween(start, today) / total) * 100,
    undated,
    bars: dated.map((d) => ({
      id: d.c.id,
      row: d.c,
      start: d.start,
      end: d.end,
      ...barGeometry(d.start, d.end, start, end),
    })),
  };
}

/** One tick per Monday on the axis (the week view); the label is the day and month, e.g. "2 Nov". */
export function weekTicks(axisStart: string, axisEnd: string): { label: string; leftPct: number }[] {
  const total = daysBetween(axisStart, axisEnd) + 1;
  const out: { label: string; leftPct: number }[] = [];
  // getUTCDay: 0 = Sunday ... 1 = Monday. Move forward to the first Monday on or after the axis start.
  const dow = new Date(ms(axisStart)).getUTCDay();
  let cur = addDaysIso(axisStart, (8 - dow) % 7);
  while (cur <= axisEnd) {
    const label = new Date(ms(cur)).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' });
    out.push({ label, leftPct: (daysBetween(axisStart, cur) / total) * 100 });
    cur = addDaysIso(cur, 7);
  }
  return out;
}

export type StatusLane = {
  key: 'live' | 'approved' | 'planned' | 'ended' | 'cancelled' | 'other';
  label: string;
};

/**
 * The bar colour lanes of the planner timeline: Live, Approved, Planned, Ended (plus Cancelled).
 * Planned covers draft, proposed and rejected (a plan still being worked); Ended covers ended and settled.
 * An unknown status keeps its own name instead of being folded into a lane.
 */
export function statusLane(status: string): StatusLane {
  switch (status) {
    case 'active':
      return { key: 'live', label: 'Live' };
    case 'approved':
      return { key: 'approved', label: 'Approved' };
    case 'draft':
    case 'proposed':
    case 'rejected':
      return { key: 'planned', label: 'Planned' };
    case 'ended':
    case 'settled':
      return { key: 'ended', label: 'Ended' };
    case 'cancelled':
      return { key: 'cancelled', label: 'Cancelled' };
    default:
      return { key: 'other', label: status };
  }
}

/**
 * Bars grouped by customer name (case-insensitive, earliest start first inside a group), with the first row
 * of each customer marked so the label is drawn once. A case with no customer name is its own group, last.
 */
export function orderByCustomer<T extends TimelineCase>(
  bars: readonly TimelineBar<T>[],
): { bar: TimelineBar<T>; firstOfCustomer: boolean }[] {
  const name = (b: TimelineBar<T>) => (b.row.customer_name ?? '').trim().toLowerCase();
  const sorted = [...bars].sort((a, b) => {
    const an = name(a);
    const bn = name(b);
    if (an !== bn) return an === '' ? 1 : bn === '' ? -1 : an < bn ? -1 : 1;
    if (a.start !== b.start) return a.start < b.start ? -1 : 1;
    return a.id - b.id;
  });
  return sorted.map((bar, i) => ({
    bar,
    firstOfCustomer: i === 0 || name(bar) === '' || name(sorted[i - 1]) !== name(bar),
  }));
}
