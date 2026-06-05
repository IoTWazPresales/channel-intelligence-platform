export function fmtShortDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function fmtOptionalCell(value: unknown): string {
  if (value == null || value === '') return '—';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return '—';
    }
  }
  return String(value);
}

export function fmtCellForKey(key: string, value: unknown): string {
  if (value == null || value === '') return '—';
  if (key.includes('date') || key.endsWith('_at')) {
    const s = typeof value === 'string' ? value : String(value);
    if (s && /^\d{4}-\d{2}-\d{2}/.test(s)) return fmtShortDate(s);
  }
  return fmtOptionalCell(value);
}
