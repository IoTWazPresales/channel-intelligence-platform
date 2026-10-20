export function formatVintage(vintage: Record<string, unknown> | null | undefined): string {
  if (!vintage) return 'vintage unknown';
  const grain = typeof vintage.period_grain === 'string' ? vintage.period_grain : null;
  const min = typeof vintage.bucket_min === 'string' ? vintage.bucket_min : null;
  const max = typeof vintage.bucket_max === 'string' ? vintage.bucket_max : null;
  const rows = typeof vintage.row_count === 'number' ? `${vintage.row_count} rows` : null;
  const parts = [grain, min && max ? `${min} → ${max}` : min || max || rows].filter(Boolean);
  return parts.length ? parts.join(' · ') : 'vintage unknown';
}
