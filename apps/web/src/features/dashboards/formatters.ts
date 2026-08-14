export function formatMetricValue(v: unknown): string {
  if (v == null) return '—';
  if (typeof v === 'number') {
    if (Math.abs(v) <= 1.5 && Number.isFinite(v)) return `${(v * 100).toFixed(1)}%`;
    return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  return String(v);
}

export function formatVintage(vintage: Record<string, unknown> | null | undefined): string {
  if (!vintage) return 'vintage unknown';
  const table = typeof vintage.source_table === 'string' ? vintage.source_table : null;
  const grain = typeof vintage.period_grain === 'string' ? vintage.period_grain : null;
  const min = typeof vintage.bucket_min === 'string' ? vintage.bucket_min : null;
  const max = typeof vintage.bucket_max === 'string' ? vintage.bucket_max : null;
  const rows = typeof vintage.row_count === 'number' ? `${vintage.row_count} rows` : null;
  const parts = [table, grain, min && max ? `${min} → ${max}` : min || max || rows].filter(Boolean);
  return parts.length ? parts.join(' · ') : 'vintage unknown';
}

export function rowCategoryLabel(row: Record<string, unknown>): string {
  const parts = [
    row.bucket_key != null ? String(row.bucket_key) : null,
    row.customer_id != null ? `C${row.customer_id}` : null,
    row.product_id != null ? `P${row.product_id}` : null,
    row.distributor_id != null ? `D${row.distributor_id}` : null,
    row.site_label != null ? String(row.site_label) : null,
  ].filter(Boolean);
  return parts.join(' · ') || 'row';
}
