'use client';

import type { DsiCandidateRow } from './dsi-mapping-steward-panel';
import { dsiRawProductTokenForCandidate } from './dsi-mapping-steward-panel';

export type DsiProductCandidateExportRow = {
  token: string;
  rows: number;
  units: number | '';
  value: number | '';
  resolved_receipt_temporal: number | '';
  indeterminate: number | '';
  ignored: number | '';
  reason_code: string;
  distributors: string;
  dominant_month: string;
};

const EXPORT_COLUMNS: (keyof DsiProductCandidateExportRow)[] = [
  'token',
  'rows',
  'units',
  'value',
  'resolved_receipt_temporal',
  'indeterminate',
  'ignored',
  'reason_code',
  'distributors',
  'dominant_month',
];

export function buildDsiProductCandidateExportRows(
  candidates: readonly DsiCandidateRow[]
): DsiProductCandidateExportRow[] {
  return candidates
    .filter((c) => c.entity_type === 'product_identifier')
    .map((c) => {
      const ctx = (c.context ?? {}) as Record<string, unknown>;
      const q = ctx.product_resolution_quality as Record<string, number> | undefined;
      const distIds = Array.isArray(ctx.unresolved_distributor_ids)
        ? ctx.unresolved_distributor_ids.map(String).join('; ')
        : '';
      const ignored =
        (c.status || '').trim() === 'ignored'
          ? Number(c.row_count ?? q?.ignored_rows ?? 0)
          : Number(q?.ignored_rows ?? 0);
      return {
        token: dsiRawProductTokenForCandidate(c) || c.normalized_key || '',
        rows: Number(c.row_count ?? 0),
        units: c.total_units != null ? Number(c.total_units) : '',
        value: c.total_reported_value != null ? Number(c.total_reported_value) : '',
        resolved_receipt_temporal: q?.resolved_receipt_temporal ?? '',
        indeterminate: q?.indeterminate_rows ?? '',
        ignored,
        reason_code: String(ctx.steward_ignore_reason_code ?? ''),
        distributors: distIds,
        dominant_month: String(ctx.dominant_evidence_month ?? ''),
      };
    });
}

function escapeCsvCell(value: string | number): string {
  const s = String(value ?? '');
  if (s.includes(',') || s.includes('"') || s.includes('\n') || s.includes('\r')) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export function dsiProductCandidateExportToCsv(rows: readonly DsiProductCandidateExportRow[]): string {
  const header = EXPORT_COLUMNS.join(',');
  const body = rows.map((row) => EXPORT_COLUMNS.map((col) => escapeCsvCell(row[col])).join(','));
  return [header, ...body].join('\r\n');
}

export function downloadDsiProductCandidateCsv(
  rows: readonly DsiProductCandidateExportRow[],
  filename = 'dsi-product-candidates.csv'
): void {
  const csv = dsiProductCandidateExportToCsv(rows);
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export async function copyDsiProductCandidateCsvToClipboard(
  rows: readonly DsiProductCandidateExportRow[]
): Promise<void> {
  const csv = dsiProductCandidateExportToCsv(rows);
  await navigator.clipboard.writeText(csv);
}
