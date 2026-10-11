/** Face label for a delivery's data vintage. Empty vintage stays visible. */
export function inboxVintageLabel(vintage: Record<string, unknown> | null | undefined): string {
  if (!vintage) return 'Vintage unavailable';
  const asOf = vintage.as_of_utc;
  if (typeof asOf === 'string' && asOf.trim()) return `Vintage ${asOf.trim()}`;
  if (Object.keys(vintage).length === 0) return 'Vintage unavailable';
  return 'Vintage recorded';
}
