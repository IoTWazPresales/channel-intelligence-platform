/** Cover-pair status from stored weeks_of_cover. Matches design-lab StockSurface. */

export type CoverPairStatus = 'breach' | 'watch' | 'ok' | 'excess';

export function coverPairStatus(weeks: number | null | undefined): CoverPairStatus | null {
  if (weeks == null || Number.isNaN(weeks)) return null;
  if (weeks < 2) return 'breach';
  if (weeks < 4) return 'watch';
  if (weeks > 8) return 'excess';
  return 'ok';
}

export function coverStatusLabel(status: CoverPairStatus | null | undefined): string {
  if (status === 'breach') return 'Under 2w';
  if (status === 'watch') return '2–4w';
  if (status === 'excess') return 'Over 8w';
  if (status === 'ok') return 'Healthy';
  return 'No cover';
}

export function coverStatusTone(
  status: CoverPairStatus | null | undefined,
): 'danger' | 'warning' | 'info' | 'success' | 'neutral' {
  if (status === 'breach') return 'danger';
  if (status === 'watch') return 'warning';
  if (status === 'excess') return 'info';
  if (status === 'ok') return 'success';
  return 'neutral';
}

export function fmtCoverInt(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return '—';
  return Math.round(Number(v)).toLocaleString('en-ZA');
}
