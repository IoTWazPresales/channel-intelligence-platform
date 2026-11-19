// Mapping-editor logic for customer calendars, kept in step with the API parser
// (apps/api/app/services/cpor/customer_calendar/parser.py + profiles.normalize_header):
// a saved alias and a file header are the same column when `normalizeHeader` agrees, so what the
// user selects here is what a saved mapping reads. Pure functions, tested without the UI.

export const CALENDAR_FIELDS = ['customer_token', 'name', 'kind', 'start_date', 'end_date'] as const;
export const FIELD_LABELS: Record<string, string> = {
  customer_token: 'Customer', name: 'Event name', kind: 'Event kind', start_date: 'Start date', end_date: 'End date',
};

/** Case-, spacing- and non-breaking-space-insensitive; identical to the API's normalize_header. */
export function normalizeHeader(value: unknown): string {
  return String(value ?? '').replace(/ /g, ' ').split(/\s+/).filter(Boolean).join(' ').toLowerCase();
}

type ColumnMap = Record<string, string[]>;

/** header -> field exactly as the parser would read this file with `columnMap` (first alias wins). */
export function selectionsFor(columnMap: ColumnMap, headers: string[]): Record<string, string> {
  const norm = headers.map(normalizeHeader);
  const used = new Set<number>();
  const out: Record<string, string> = {};
  for (const field of CALENDAR_FIELDS) {
    for (const alias of columnMap[field] ?? []) {
      const want = normalizeHeader(alias);
      const at = want ? norm.indexOf(want) : -1;
      if (at < 0) continue;
      if (!used.has(at)) { used.add(at); out[headers[at]] = field; }
      break;
    }
  }
  return out;
}

/** Groups of file headers that normalise to the same text (blank headers ignored). */
export function ambiguousHeaders(headers: string[]): string[][] {
  const groups = new Map<string, string[]>();
  for (const h of headers) {
    const key = normalizeHeader(h);
    if (key) groups.set(key, [...(groups.get(key) ?? []), h]);
  }
  return [...groups.values()].filter(g => g.length > 1);
}

/** Why the selection could not be saved faithfully; empty when it can. */
export function selectionProblems(headers: string[], next: Record<string, string>): string[] {
  const problems: string[] = [];
  const mapped = new Set(headers.filter(h => next[h]));
  for (const group of ambiguousHeaders(headers)) {
    if (group.some(h => mapped.has(h))) {
      problems.push(`Columns ${group.map(h => `"${h}"`).join(' and ')} have the same name; rename one in the file so the intended column is read.`);
    }
  }
  const byField = new Map<string, string[]>();
  for (const h of headers) if (next[h]) byField.set(next[h], [...(byField.get(next[h]) ?? []), h]);
  for (const [field, cols] of byField) {
    if (cols.length > 1) problems.push(`${FIELD_LABELS[field] ?? field} is selected for more than one column (${cols.map(h => `"${h}"`).join(', ')}); keep one.`);
  }
  return problems;
}

/**
 * The saved column map after the user's selection on this file. Every alias that matches one of the
 * file's headers (under `normalizeHeader`) is dropped first, then each selected header is added to
 * its field, so reading this file through the result gives back exactly `next`.
 */
export function applySelections(columnMap: ColumnMap, headers: string[], next: Record<string, string>): ColumnMap {
  const inFile = new Set(headers.map(normalizeHeader).filter(Boolean));
  const out: ColumnMap = {};
  for (const [field, aliases] of Object.entries(columnMap)) out[field] = aliases.filter(a => !inFile.has(normalizeHeader(a)));
  for (const h of headers) {
    const field = next[h];
    if (field && normalizeHeader(h)) (out[field] ??= []).push(h);
  }
  return out;
}
