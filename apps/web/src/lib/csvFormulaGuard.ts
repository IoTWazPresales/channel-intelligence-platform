/**
 * One formula guard for every CSV the web app writes (GOV-008 review 2 Nov, minor).
 *
 * A text cell that a spreadsheet would run as a formula (`=`, `+`, `-`, `@`, tab or carriage return first) gets a leading
 * apostrophe. Numbers are never touched, so a negative number stays a number. The dashboard builder export
 * (`features/dashboards/builder/table.ts`) uses the same rule.
 */

const FORMULA_LEAD = /^[=+\-@\t\r]/;

export function guardFormulaText(s: string): string {
  return FORMULA_LEAD.test(s) ? `'${s}` : s;
}

/** The shape AG Grid passes to `processCellCallback` (the part this guard reads). */
export type CsvCellParams = { value?: unknown; formatValue?: (value: unknown) => string };

/**
 * AG Grid `processCellCallback`: exports what the grid shows (its value formatter), guards text, leaves numbers alone.
 * One function for every grid, so two exports compare equal.
 */
export function guardedCsvCell(params: CsvCellParams): string {
  const raw = params.value;
  if (raw == null) return '';
  const shown = typeof params.formatValue === 'function' ? params.formatValue(raw) : String(raw);
  return typeof raw === 'string' ? guardFormulaText(shown) : shown;
}
