/** S16: align calendar buckets by position in each window and categorical grains by identity.
 * Missing values stay null; duplicate grains are refused rather than summed. No totals come from rows.
 */
import { addDays, isoDay, parseDay, utcDay } from './dates';
import { breakdownColumns, catOf, num } from './shape';
import { validFixedWindow } from './requestFor';
import type { DateWindow, DefinitionV2, V2Response, V2Row } from './types';

export const previousField = (index: number) => `__previous_m${index}`;
type Grain = 'week' | 'month' | 'quarter' | 'year';

function floor(d: Date, grain: Grain): Date {
  if (grain === 'week') return addDays(d, -((d.getUTCDay() + 6) % 7));
  return utcDay(d.getUTCFullYear(), grain === 'year' ? 0 : grain === 'quarter' ? Math.floor(d.getUTCMonth() / 3) * 3 : d.getUTCMonth(), 1);
}
function slot(day: string, from: string, grain: Grain): number {
  const a = floor(parseDay(from)!, grain), b = floor(parseDay(day)!, grain);
  if (grain === 'week') return Math.round((b.getTime() - a.getTime()) / (7 * 86_400_000));
  const months = (b.getUTCFullYear() - a.getUTCFullYear()) * 12 + b.getUTCMonth() - a.getUTCMonth();
  return months / (grain === 'quarter' ? 3 : grain === 'year' ? 12 : 1);
}
function bucket(from: string, index: number, grain: Grain) {
  const base = floor(parseDay(from)!, grain);
  const width = grain === 'quarter' ? 3 : grain === 'year' ? 12 : 1;
  const start = grain === 'week' ? addDays(base, index * 7) : utcDay(base.getUTCFullYear(), base.getUTCMonth() + index * width, 1);
  const end = grain === 'week' ? addDays(start, 6) : addDays(utcDay(start.getUTCFullYear(), start.getUTCMonth() + width, 1), -1);
  return { bucket_key: isoDay(start), bucket_start: isoDay(start), bucket_end: isoDay(end) };
}

export type Compared = { ok: true; response: V2Response; note: string } | { ok: false; note: string };
export type ComparisonData = { result?: V2Response; window: DateWindow; previousWindow: DateWindow; label: string; loading?: boolean; error?: unknown; stale?: boolean };

export function mergeComparison(current: V2Response, previous: V2Response, def: DefinitionV2, window: DateWindow, priorWindow: DateWindow, label: string): Compared {
  const period = def.query.breakdowns?.includes('period') ?? false;
  const grain = def.query.period?.grain ?? 'quarter';
  if (!current.ok || !previous.ok) return { ok: false, note: 'Comparison was refused; current figures remain visible.' };
  if (period && (!window || !priorWindow || !validFixedWindow(window) || !validFixedWindow(priorWindow) || !['week', 'month', 'quarter', 'year'].includes(grain))) {
    return { ok: false, note: 'Comparison needs valid date ranges and a calendar grain.' };
  }
  const cats = breakdownColumns(current).filter((c) => c.id !== 'period');
  const rows = new Map<string, V2Row>();
  let outside = 0;
  for (const [answer, dates, prior] of [[current, window, false], [previous, priorWindow, true]] as const) {
    const seen = new Set<string>();
    for (const row of answer.rows) {
      if (period && (typeof row.bucket_start !== 'string' || !parseDay(row.bucket_start) || isoDay(parseDay(row.bucket_start)!) !== row.bucket_start)) {
        return { ok: false, note: 'Comparison cannot align periods without bucket dates. Current figures remain visible.' };
      }
      const index = period ? slot(row.bucket_start as string, dates!.from, grain as Grain) : 0;
      if (period && (index < 0 || index > slot(window!.to, window!.from, grain as Grain))) { outside++; continue; }
      const key = JSON.stringify([index, ...cats.map((c) => catOf(row, c).key)]);
      if (seen.has(key)) return { ok: false, note: 'Comparison needs one row per grouping; duplicate rows were not added together.' };
      seen.add(key);
      const target = rows.get(key) ?? {
        ...row, ...(period ? bucket(window!.from, index, grain as Grain) : {}),
        ...(period ? { __previous_period: '—' } : {}),
        ...Object.fromEntries(def.query.measures.flatMap((m, i) => [[m, null], [previousField(i), null]])),
      };
      def.query.measures.forEach((m, i) => { target[prior ? previousField(i) : m] = num(row[m]); });
      if (prior && period) target.__previous_period = `${row.bucket_start} to ${row.bucket_end ?? row.bucket_start}`;
      rows.set(key, target);
    }
  }
  if (period && rows.size) {
    // A categorical x axis also needs buckets missing in BOTH answers. Seed only
    // observed category identities, leaving both-empty answers as the no-data state.
    const categories = new Map<string, V2Row>();
    for (const row of rows.values()) {
      const key = JSON.stringify(cats.map((c) => catOf(row, c).key));
      categories.set(key, Object.fromEntries(cats.flatMap((c) => c.fields.map((field) => [field, row[field]]))));
    }
    const count = slot(window!.to, window!.from, grain as Grain) + 1;
    if (count * categories.size > 5000) return { ok: false, note: 'Comparison needs more than 5,000 calendar/category positions. Narrow the date range or filters. Current figures remain visible.' };
    for (let index = 0; index < count; index++) for (const dimensions of categories.values()) {
      const key = JSON.stringify([index, ...cats.map((c) => catOf(dimensions, c).key)]);
      if (!rows.has(key)) rows.set(key, {
        ...dimensions, ...bucket(window!.from, index, grain as Grain), __previous_period: '—',
        ...Object.fromEntries(def.query.measures.flatMap((m, i) => [[m, null], [previousField(i), null]])),
      });
    }
  }
  const extra = def.query.measures.map((id, i) => {
    const col = current.columns.find((c) => c.id === id);
    return { id: previousField(i), kind: 'measure' as const, fields: [previousField(i)], label: `${col?.label ?? id}, ${label}`, unit: col?.unit };
  });
  return { ok: true, response: {
    ...current, rows: [...rows.values()], columns: [...current.columns, ...extra,
      ...(period ? [{ id: '__previous_period', kind: 'breakdown' as const, label: 'Previous bucket', fields: ['__previous_period'] }] : [])],
    totals: { ...current.totals, ...Object.fromEntries(def.query.measures.map((m, i) => [previousField(i), previous.totals[m] ?? null])) },
    truncated: current.truncated || previous.truncated,
  }, note: [
    `${label}: ${priorWindow ? `${priorWindow.from} to ${priorWindow.to}` : 'all time'}.`,
    period ? 'Calendar buckets align by position in each date range; boundary buckets may be partial. Missing values are not zero.' : 'Categories match by identity. Missing values are not zero.',
    current.truncated || previous.truncated ? 'Comparison is incomplete because a query was truncated.' : '',
    outside ? `${outside} buckets outside the current range were not plotted.` : '',
  ].filter(Boolean).join(' ') };
}
