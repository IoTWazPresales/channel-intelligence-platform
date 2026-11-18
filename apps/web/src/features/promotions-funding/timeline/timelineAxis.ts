const DAY = 86_400_000;
const dayNumber = (iso: string) => Math.floor(Date.parse(`${iso}T00:00:00Z`) / DAY);
export const isoDay = (day: number) => new Date(day * DAY).toISOString().slice(0, 10);

export type DateAxis = { start: number; end: number; days: number };

export function dateAxis(starts: string[], ends: string[], from?: string | null, to?: string | null): DateAxis {
  const today = dayNumber(new Date().toISOString().slice(0, 10));
  const start = from ? dayNumber(from) : starts.length ? Math.min(...starts.map(dayNumber)) : to ? dayNumber(to) : today;
  const end = Math.max(start, to ? dayNumber(to) : ends.length ? Math.max(...ends.map(dayNumber)) : start);
  return { start, end, days: end - start + 1 };
}

export function barPosition(start: string, end: string, axis: DateAxis): { left: number; width: number } | null {
  const first = Math.max(dayNumber(start), axis.start);
  const last = Math.min(dayNumber(end), axis.end);
  if (last < first) return null;
  return { left: (first - axis.start) / axis.days * 100, width: (last - first + 1) / axis.days * 100 };
}
