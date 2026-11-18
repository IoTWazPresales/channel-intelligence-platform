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
