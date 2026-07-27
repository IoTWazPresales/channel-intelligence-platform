import type { DsiBulkAction, DsiBulkApplyResponse, DsiBulkPreviewResponse } from '@/app/(app)/admin/imports/dsi/dsiSteward.types';

/** Align with API `DsiBulkStewardBody` caps in mappings.py */
export const DSI_BULK_STEWARD_MAX_CANDIDATE_IDS = 200;
export const DSI_BULK_STEWARD_MAX_IGNORE_CANDIDATE_IDS = 1000;

export function dsiBulkStewardChunkSize(action: DsiBulkAction): number {
  return action === 'ignore' ? DSI_BULK_STEWARD_MAX_IGNORE_CANDIDATE_IDS : DSI_BULK_STEWARD_MAX_CANDIDATE_IDS;
}

export function chunkDsiBulkCandidateIds(ids: readonly number[], chunkSize: number): number[][] {
  if (ids.length <= chunkSize) return [[...ids]];
  const out: number[][] = [];
  for (let i = 0; i < ids.length; i += chunkSize) {
    out.push(ids.slice(i, i + chunkSize));
  }
  return out;
}

function mergeBulkTotals(totalsList: Array<Record<string, unknown>>): Record<string, unknown> {
  if (totalsList.length === 0) return {};
  if (totalsList.some((t) => t.plan_only)) return totalsList[0] ?? {};
  let ok_count = 0;
  let not_ok_count = 0;
  let staging_rows_affected = 0;
  let total_units_affected = 0;
  let total_reported_value_affected = 0;
  for (const t of totalsList) {
    ok_count += Number(t.ok_count ?? 0);
    not_ok_count += Number(t.not_ok_count ?? 0);
    staging_rows_affected += Number(t.staging_rows_affected ?? 0);
    total_units_affected += Number(t.total_units_affected ?? 0);
    total_reported_value_affected += Number(t.total_reported_value_affected ?? 0);
  }
  return {
    ok_count,
    not_ok_count,
    staging_rows_affected,
    total_units_affected,
    total_reported_value_affected,
  };
}

export function mergeDsiBulkPreviewResponses(
  importJobId: number,
  action: DsiBulkAction,
  parts: readonly DsiBulkPreviewResponse[]
): DsiBulkPreviewResponse {
  const results = parts.flatMap((p) => p.results ?? []);
  return {
    import_job_id: importJobId,
    action,
    results,
    totals: mergeBulkTotals(parts.map((p) => p.totals ?? {})),
  };
}

export function mergeDsiBulkApplyResponses(
  importJobId: number,
  action: DsiBulkAction,
  parts: readonly DsiBulkApplyResponse[]
): DsiBulkApplyResponse {
  const results = parts.flatMap((p) => p.results ?? []);
  let applied = 0;
  let failed = 0;
  for (const p of parts) {
    applied += Number(p.applied ?? 0);
    failed += Number(p.failed ?? 0);
  }
  return {
    import_job_id: importJobId,
    action,
    applied,
    failed,
    results,
    totals: mergeBulkTotals(parts.map((p) => p.totals ?? {})),
  };
}
