import type { MoneyPart, Vessel } from './types';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "2026-10-27" → "27 Oct". Anything else reads as a dash. */
export function fmtDay(iso: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '');
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]}` : '–';
}

/** "2026-10-27" → "27 Oct 2026". */
export function fmtDayYear(iso: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '');
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}` : '–';
}

export function fmtUnits(n: number): string {
  return Math.round(n).toLocaleString('en-US');
}

const SYMBOL: Record<string, string> = { USD: 'US$' };

function oneCurrency({ currency, amount }: MoneyPart): string {
  const prefix = SYMBOL[currency] ?? `${currency} `;
  if (amount >= 1e6) return `${prefix}${(amount / 1e6).toFixed(2)}M`;
  if (amount >= 1e3) return `${prefix}${Math.round(amount / 1e3)}k`;
  return `${prefix}${Math.round(amount)}`;
}

/**
 * Value per currency, never summed across currencies. "US$" is shown only when every line in the figure is USD;
 * otherwise each currency is listed with its own code ("US$140 · EUR 70").
 */
export function fmtMoney(parts: MoneyPart[]): string {
  const real = parts.filter((p) => p.currency && p.currency !== '?');
  if (!real.length) return '–';
  return real.map(oneCurrency).join(' · ');
}

/** "+14 days", "+1 day" or "On time". */
export function slipShort(v: Pick<Vessel, 'slip_days'>): string {
  if (v.slip_days <= 0) return 'On time';
  return `+${v.slip_days} ${v.slip_days === 1 ? 'day' : 'days'}`;
}

export function daysText(v: Pick<Vessel, 'days_to_eta' | 'overdue' | 'days_overdue'>): string {
  if (v.overdue) return `${v.days_overdue} ${v.days_overdue === 1 ? 'day' : 'days'} overdue`;
  if (v.days_to_eta == null) return 'no ETA';
  if (v.days_to_eta === 0) return 'due today';
  return `in ${v.days_to_eta} ${v.days_to_eta === 1 ? 'day' : 'days'}`;
}

/**
 * The vessel badge: two facts, not one. How far past its ETA at port the vessel is, and how far the ETA has moved from the first
 * report: "2 days overdue · ETA moved +14 days", "ETA moved +7 days", "ETA unchanged".
 */
export function badgeText(v: Pick<Vessel, 'overdue' | 'days_overdue' | 'slip_days'>): string {
  const moved = v.slip_days > 0 ? `ETA moved +${v.slip_days} ${v.slip_days === 1 ? 'day' : 'days'}` : null;
  if (v.overdue) {
    const over = `${v.days_overdue} ${v.days_overdue === 1 ? 'day' : 'days'} overdue`;
    return moved ? `${over} · ${moved}` : over;
  }
  return moved ?? 'ETA unchanged';
}

export function nameUnits(rows: Array<{ name: string; units: number }>, limit?: number): string {
  return (limit ? rows.slice(0, limit) : rows).map((r) => `${r.name} ${fmtUnits(r.units)}`).join(' · ');
}

/** "ETA history": "13 Oct on 29 Sep → 27 Oct on 27 Oct", or "27 Oct in every report since 29 Sep". */
export function historyText(v: Vessel): string {
  const h = v.history;
  if (!h.first_eta) return 'Not in an earlier report';
  if (v.slip_days > 0) return `${fmtDay(h.first_eta)} on ${fmtDay(h.first_report)} → ${fmtDay(h.current_eta)} on ${fmtDay(h.latest_report)}`;
  return `${fmtDay(h.current_eta)} in every report since ${fmtDay(h.first_report)}`;
}
