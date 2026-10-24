/**
 * Dashboard date windows (spec s.2.3): presets resolve on the client to inclusive ISO days, `to` =
 * today; `all_time` sends no dates. Compare: the same-length window just before, or both dates moved
 * back one calendar year (decision D6 as proposed; 29 February becomes 28 February).
 */

import type { CompareMode, DashboardFilters, DatePreset, DateWindow } from './types';

export const DATE_PRESETS: { id: DatePreset; label: string }[] = [
  { id: 'last_13_weeks', label: 'Last 13 weeks' },
  { id: 'last_26_weeks', label: 'Last 26 weeks' },
  { id: 'last_52_weeks', label: 'Last 52 weeks' },
  { id: 'this_year', label: 'This year' },
  { id: 'last_quarter', label: 'Last quarter' },
  { id: 'all_time', label: 'All time' },
  { id: 'custom', label: 'Custom' },
];

export const COMPARE_MODES: { id: CompareMode; label: string }[] = [
  { id: 'none', label: 'No comparison' },
  { id: 'previous_period', label: 'Previous period' },
  { id: 'previous_year', label: 'Previous year' },
];

const DAY = 86_400_000;

/** ISO day of a UTC date. */
export function isoDay(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** A local calendar day as a UTC midnight date (no time-zone drift in day arithmetic). */
export function utcDay(year: number, month0: number, day: number): Date {
  return new Date(Date.UTC(year, month0, day));
}

export function parseDay(s: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return null;
  const d = utcDay(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return Number.isNaN(d.getTime()) ? null : d;
}

export function addDays(d: Date, n: number): Date {
  return new Date(d.getTime() + n * DAY);
}

export function daysBetween(from: Date, to: Date): number {
  return Math.round((to.getTime() - from.getTime()) / DAY);
}

/** Today as a UTC-midnight date of the viewer's local day. */
export function today(now: Date = new Date()): Date {
  return utcDay(now.getFullYear(), now.getMonth(), now.getDate());
}

export function resolvePreset(date: DashboardFilters['date'] | undefined, now: Date = new Date()): DateWindow {
  const preset = date?.preset ?? 'all_time';
  const t = today(now);
  const weeks = (n: number) => ({ from: isoDay(addDays(t, -(7 * n) + 1)), to: isoDay(t) });
  switch (preset) {
    case 'last_13_weeks':
      return weeks(13);
    case 'last_26_weeks':
      return weeks(26);
    case 'last_52_weeks':
      return weeks(52);
    case 'this_year':
      return { from: isoDay(utcDay(t.getUTCFullYear(), 0, 1)), to: isoDay(t) };
    case 'last_quarter': {
      const q = Math.floor(t.getUTCMonth() / 3);
      const startThis = utcDay(t.getUTCFullYear(), q * 3, 1);
      const startPrev = utcDay(t.getUTCFullYear(), q * 3 - 3, 1);
      return { from: isoDay(startPrev), to: isoDay(addDays(startThis, -1)) };
    }
    case 'custom': {
      const from = date?.from && parseDay(date.from) ? date.from : null;
      const to = date?.to && parseDay(date.to) ? date.to : null;
      if (!from && !to) return null;
      return { from: from ?? '2000-01-01', to: to ?? isoDay(t) };
    }
    case 'all_time':
    default:
      return null;
  }
}

/** One calendar year back; 29 February becomes 28 February. */
export function minusOneYear(d: Date): Date {
  const y = d.getUTCFullYear() - 1;
  const m = d.getUTCMonth();
  const day = d.getUTCDate();
  const last = utcDay(y, m + 1, 0).getUTCDate();
  return utcDay(y, m, Math.min(day, last));
}

/** The comparison window, or null when there is none (no compare, or all time). */
export function compareWindow(window: DateWindow, mode: CompareMode | undefined): DateWindow {
  if (!window || !mode || mode === 'none') return null;
  const from = parseDay(window.from);
  const to = parseDay(window.to);
  if (!from || !to) return null;
  if (mode === 'previous_year') return { from: isoDay(minusOneYear(from)), to: isoDay(minusOneYear(to)) };
  const length = daysBetween(from, to) + 1;
  const prevTo = addDays(from, -1);
  return { from: isoDay(addDays(prevTo, -(length - 1))), to: isoDay(prevTo) };
}

/** Sparkline grain: up to 26 weeks by week, up to two years by month, otherwise by quarter. */
export function autoGrain(window: DateWindow): 'week' | 'month' | 'quarter' {
  if (!window) return 'quarter';
  const from = parseDay(window.from);
  const to = parseDay(window.to);
  if (!from || !to) return 'quarter';
  const days = daysBetween(from, to) + 1;
  if (days <= 26 * 7) return 'week';
  if (days <= 731) return 'month';
  return 'quarter';
}

export function windowLabel(window: DateWindow): string {
  return window ? `${window.from} to ${window.to}` : 'All time';
}

/**
 * Delta of a KPI against its comparison (spec s.4): (a - b) / b; null when b is 0 or missing (the same
 * null rule as the API's pct_change). Ratio measures say the change in points instead.
 */
export function kpiDelta(
  current: number | null | undefined,
  previous: number | null | undefined,
  opts: { ratio?: boolean } = {},
): { text: string; direction: 'up' | 'down' | 'flat' } | null {
  if (current == null || previous == null || !Number.isFinite(current) || !Number.isFinite(previous)) return null;
  if (opts.ratio) {
    const pts = (current - previous) * 100;
    const r = Math.round(pts * 10) / 10;
    return { text: `${r > 0 ? '+' : ''}${r.toFixed(1)} pts`, direction: r > 0 ? 'up' : r < 0 ? 'down' : 'flat' };
  }
  if (previous === 0) return null;
  const pct = ((current - previous) / previous) * 100;
  const r = Math.round(pct * 10) / 10;
  return { text: `${r > 0 ? '+' : ''}${r.toFixed(1)}%`, direction: r > 0 ? 'up' : r < 0 ? 'down' : 'flat' };
}

/** Date window of one period bucket (a click on a week / month / quarter / year). */
export function bucketWindow(row: { bucket_start?: unknown; bucket_end?: unknown }): DateWindow {
  const from = typeof row.bucket_start === 'string' ? row.bucket_start : null;
  const to = typeof row.bucket_end === 'string' ? row.bucket_end : null;
  return from && to ? { from, to } : null;
}
