/**
 * Table columns, conditional colour and CSV for v2 answers (spec s.4, s.6).
 *
 * - Entity columns show the name only (Warren's rule: names in Customer / Distributor columns,
 *   never codes); attributes their value; the period its bucket key; measures raw numbers.
 * - Headers carry the unit ("Sell-out units (units)").
 * - Colour rules: at most 3, no default thresholds; a tone plus a text marker and a glyph, so colour
 *   is never the only signal.
 * - CSV: UTF-8 BOM, RFC 4180 quoting, and a formula-injection guard on text cells.
 */

import { formatNumber, unitWord, type MeasureUnit } from '@/features/workbench-ui/charts';

import { chartUnit } from './catalog';
import type { ColourRule, ColourTone, V2Column, V2Response, V2Row } from './types';

export type TableCol = {
  /** Row field read for the cell. */
  field: string;
  header: string;
  kind: 'entity' | 'attribute' | 'period' | 'measure';
  /** Breakdown or measure id. */
  id: string;
  unit?: MeasureUnit;
};

export function headerWithUnit(label: string, unit: MeasureUnit | undefined): string {
  const w = unit ? unitWord(unit) : null;
  return w ? `${label} (${w})` : label;
}

export function tableCols(resp: V2Response | undefined, unitOf?: (col: V2Column) => MeasureUnit): TableCol[] {
  const out: TableCol[] = [];
  for (const c of resp?.columns ?? []) {
    if (c.kind === 'measure') {
      const unit = unitOf ? unitOf(c) : chartUnit(c.unit, c.unit == null ? c.id : null);
      out.push({ field: c.fields[0] ?? c.id, header: headerWithUnit(c.label, unit), kind: 'measure', id: c.id, unit });
    } else if (c.id === 'period') {
      out.push({ field: 'bucket_key', header: c.label || 'Period', kind: 'period', id: 'period' });
    } else if (c.fields.length >= 2) {
      // Name only: the id field never becomes a column.
      out.push({ field: c.fields[1], header: c.label, kind: 'entity', id: c.id });
    } else {
      out.push({ field: c.fields[0] ?? c.id, header: c.label, kind: 'attribute', id: c.id });
    }
  }
  return out;
}

/** The cell value: names for entities ("Unassigned" without an id), numbers for measures. */
export function cellValue(row: V2Row, col: TableCol): string | number | null {
  const v = row[col.field];
  if (col.kind === 'measure') {
    if (v == null || v === '') return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  if (v == null || String(v).trim() === '') return 'Unassigned';
  return String(v);
}

/* ------------------------------------------------------------------------------------------------
 * Conditional colour
 * ---------------------------------------------------------------------------------------------- */

export const MAX_RULES = 3;

export const TONE_WORD: Record<ColourTone, string> = { good: 'Good', warn: 'Warning', bad: 'Problem' };

const OP_WORD: Record<ColourRule['op'], string> = { '<': 'below', '<=': 'at or below', '>': 'above', '>=': 'at or above', between: 'between' };

export function ruleMatches(rule: ColourRule, v: number | null): boolean {
  if (v == null || !Number.isFinite(v)) return false;
  switch (rule.op) {
    case '<':
      return v < rule.value;
    case '<=':
      return v <= rule.value;
    case '>':
      return v > rule.value;
    case '>=':
      return v >= rule.value;
    case 'between': {
      const lo = Math.min(rule.value, rule.value2 ?? rule.value);
      const hi = Math.max(rule.value, rule.value2 ?? rule.value);
      return v >= lo && v <= hi;
    }
    default:
      return false;
  }
}

/** First rule (in order) that matches this measure's value. */
export function matchRule(rules: ColourRule[] | undefined, measure: string, v: number | null): ColourRule | null {
  for (const r of (rules ?? []).slice(0, MAX_RULES)) {
    if (r.measure === measure && ruleMatches(r, v)) return r;
  }
  return null;
}

/** "Warning: below 1" — the text marker read out with the value. */
export function ruleText(rule: ColourRule): string {
  const range = rule.op === 'between' ? `${formatNumber(rule.value)} to ${formatNumber(rule.value2 ?? rule.value)}` : formatNumber(rule.value);
  return `${TONE_WORD[rule.tone]}: ${OP_WORD[rule.op]} ${range}`;
}

/* ------------------------------------------------------------------------------------------------
 * CSV
 * ---------------------------------------------------------------------------------------------- */

const BOM = '﻿';

/** A text cell that a spreadsheet would run as a formula gets a leading apostrophe. */
export function guardCell(s: string): string {
  return /^[=+\-@\t\r]/.test(s) ? `'${s}` : s;
}

/** RFC 4180: quote a field holding a comma, quote, CR or LF; double inner quotes. */
export function quoteCell(s: string): string {
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(cols: TableCol[], rows: V2Row[]): string {
  const lines = [cols.map((c) => quoteCell(guardCell(c.header))).join(',')];
  for (const r of rows) {
    lines.push(
      cols
        .map((c) => {
          const v = cellValue(r, c);
          if (v == null) return '';
          if (typeof v === 'number') return String(v);
          return quoteCell(guardCell(v));
        })
        .join(','),
    );
  }
  return `${BOM}${lines.join('\r\n')}\r\n`;
}

/** "{dashboard}-{widget}-{yyyy-mm-dd}.csv" with only safe characters. */
export function exportFileName(dashboard: string, widget: string, ext: 'csv' | 'png', now: Date = new Date()): string {
  const slug = (s: string) =>
    s
      .normalize('NFKD')
      .replace(/[^\w\s-]/g, '')
      .trim()
      .replace(/\s+/g, '-')
      .slice(0, 60) || 'widget';
  const d = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  return `${slug(dashboard)}-${slug(widget)}-${d}.${ext}`;
}

/** Hand a Blob to the browser as a download. */
export function downloadBlob(blob: Blob, filename: string): void {
  if (typeof window === 'undefined' || typeof URL.createObjectURL !== 'function') return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** "Exported 500 rows" / "Exported 500 rows (first 500 of 1,678)". */
export function exportToast(shown: number, total: number, truncated: boolean): string {
  const n = (x: number) => x.toLocaleString('en-US');
  return truncated && total > shown ? `Exported ${n(shown)} rows (first ${n(shown)} of ${n(total)})` : `Exported ${n(shown)} rows`;
}
