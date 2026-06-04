import { apiGet } from '@/lib/api';

import type { BulkProvisionalTaskProgress } from '@/features/background-tasks/importJobProgress.types';

const TERMINAL = new Set(['SUCCESS', 'FAILURE']);

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function fetchShipmentBulkTaskProgress(
  importJobId: number,
  taskId: string,
  signal?: AbortSignal
): Promise<BulkProvisionalTaskProgress> {
  return apiGet<BulkProvisionalTaskProgress & { result?: unknown }>(
    `/api/v1/shipment-evidence/import-jobs/${importJobId}/shipment-bulk-task/${encodeURIComponent(taskId)}`,
    { signal }
  );
}

/** Poll a shipment bulk steward Celery task until SUCCESS or FAILURE, returning its result payload. */
export async function pollShipmentBulkTask<TResult = Record<string, unknown>>(
  importJobId: number,
  taskId: string,
  options?: { intervalMs?: number; maxAttempts?: number }
): Promise<TResult> {
  const intervalMs = options?.intervalMs ?? 800;
  const maxAttempts = options?.maxAttempts ?? 600;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const status = (await fetchShipmentBulkTaskProgress(importJobId, taskId)) as BulkProvisionalTaskProgress & {
      result?: unknown;
    };
    const state = String(status.state ?? '').toUpperCase();
    if (TERMINAL.has(state)) {
      if (state === 'FAILURE') {
        throw new Error(status.error ?? 'Shipment bulk steward task failed');
      }
      const result = status.result;
      if (!result || typeof result !== 'object') {
        throw new Error('Shipment bulk task completed without a result payload');
      }
      return result as TResult;
    }
    await sleep(intervalMs);
  }
  throw new Error('Shipment bulk steward task timed out while polling');
}
