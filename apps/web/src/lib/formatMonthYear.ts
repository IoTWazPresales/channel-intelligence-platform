/**
 * Short month and year of a date or ISO timestamp ("Jul 2026"), read in UTC so a date-only value
 * never slips a month at the timezone edge. Null when the value is empty or not a date.
 */
export function formatMonthYear(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString('en-GB', { month: 'short', year: 'numeric', timeZone: 'UTC' });
}
