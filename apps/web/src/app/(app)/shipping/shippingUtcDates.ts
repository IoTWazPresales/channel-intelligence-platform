/** UTC calendar helpers aligned with API ``shipping._utc_today`` / ISO week bounds. */

export function utcTodayYmd(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10);
}

/** Parse YYYY-MM-DD as a UTC calendar date (noon UTC to avoid DST edge noise). */
export function utcDateFromYmd(ymd: string): Date {
  const [y, m, d] = ymd.split('-').map((x) => Number(x));
  return new Date(Date.UTC(y, m - 1, d, 12, 0, 0));
}

export function addUtcDaysYmd(ymd: string, days: number): string {
  const d = utcDateFromYmd(ymd);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Monday-start ISO week containing ``ymd`` (UTC calendar). */
export function utcIsoWeekBoundsYmd(ymd: string): { weekStart: string; weekEnd: string } {
  const d = utcDateFromYmd(ymd);
  const dow = d.getUTCDay(); // 0=Sun … 6=Sat
  const diffToMonday = dow === 0 ? -6 : 1 - dow;
  d.setUTCDate(d.getUTCDate() + diffToMonday);
  const weekStart = d.toISOString().slice(0, 10);
  const end = new Date(d);
  end.setUTCDate(end.getUTCDate() + 6);
  const weekEnd = end.toISOString().slice(0, 10);
  return { weekStart, weekEnd };
}

/**
 * Smart-preset date window matching commercial-summary overdue KPI:
 * ``promise_date < utc_today`` ≡ ``date_to = utc_today - 1 day`` (inclusive).
 */
export function overdueSmartPresetDates(now: Date = new Date()): {
  referenceDate: string;
  dateTo: string;
} {
  const referenceDate = utcTodayYmd(now);
  return { referenceDate, dateTo: addUtcDaysYmd(referenceDate, -1) };
}

export function arrivingOrLandedWeekPresetDates(now: Date = new Date()): {
  weekStart: string;
  weekEnd: string;
} {
  return utcIsoWeekBoundsYmd(utcTodayYmd(now));
}
