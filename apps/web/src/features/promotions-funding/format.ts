import { formatLocalMoney } from '@/features/cpor/fxDisplay';

/** Compact money matching the Promotions & Funding lab (R486k), with the case currency. */
export function fmtCompact(amount: number | null | undefined, currency = 'ZAR'): string {
  if (amount == null || Number.isNaN(amount)) return '—';
  const abs = Math.abs(amount);
  const sign = amount < 0 ? '-' : '';
  const prefix = currency.toUpperCase() === 'ZAR' ? 'R' : currency.toUpperCase() === 'USD' ? '$' : `${currency.toUpperCase()} `;
  if (abs >= 1_000_000) return `${sign}${prefix}${(abs / 1_000_000).toFixed(1)}m`;
  if (abs >= 1_000) return `${sign}${prefix}${Math.round(abs / 1_000)}k`;
  return `${sign}${prefix}${Math.round(abs).toLocaleString('en-ZA')}`;
}

export function fmtInt(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  return Math.round(v).toLocaleString('en-ZA');
}

export function fmtMoney(amount: number | null | undefined, currency = 'ZAR'): string {
  return formatLocalMoney(amount, currency);
}

export function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  const pct = Math.abs(v) <= 1 ? v * 100 : v;
  return `${Math.round(pct)}%`;
}
