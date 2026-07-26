import type { StewardBulkApplyResponse } from '@/features/import-steward/stewardEngine.types';

import { pollShipmentBulkTask } from './shipmentBulkTaskPoll';

/** Normalize shipment async bulk task payloads to the steward bulk apply envelope. */
export function normalizeShipmentBulkApplyResult(
  importJobId: number,
  raw: Record<string, unknown>
): StewardBulkApplyResponse {
  const action = String(raw.action ?? 'unknown');
  const results = Array.isArray(raw.results)
    ? (raw.results as StewardBulkApplyResponse['results'])
    : [];
  let applied = Number(raw.applied);
  if (!Number.isFinite(applied)) {
    applied = results.filter((r) => r.ok === true).length;
  }
  let failed = Number(raw.failed);
  if (!Number.isFinite(failed)) {
    failed = Math.max(0, results.length - applied);
  }
  return {
    import_job_id: Number(raw.import_job_id ?? importJobId),
    action,
    applied,
    failed,
    results,
  };
}

export async function pollShipmentBulkStewardTask(
  importJobId: number,
  taskId: string,
  _opts: { rowCount: number }
): Promise<StewardBulkApplyResponse> {
  const raw = await pollShipmentBulkTask<Record<string, unknown>>(importJobId, taskId);
  return normalizeShipmentBulkApplyResult(importJobId, raw);
}
