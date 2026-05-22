import { fetchBulkProvisionalTaskProgress } from '@/features/background-tasks/fetchImportJobProgress';

import type { DsiBulkApplyResponse, DsiBulkTaskStatusResponse } from './dsiSteward.types';

const TERMINAL = new Set(['SUCCESS', 'FAILURE']);

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Poll bulk provisional Celery task until SUCCESS or FAILURE. */
export async function pollDsiBulkProvisionalTask(
  importJobId: number,
  taskId: string,
  options?: { intervalMs?: number; maxAttempts?: number }
): Promise<DsiBulkApplyResponse> {
  const intervalMs = options?.intervalMs ?? 800;
  const maxAttempts = options?.maxAttempts ?? 600;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const status = await fetchBulkProvisionalTaskProgress(importJobId, taskId);
    const state = String(status.state ?? '').toUpperCase();
    if (TERMINAL.has(state)) {
      if (state === 'FAILURE') {
        throw new Error(status.error ?? 'Bulk provisional customer task failed');
      }
      const result = status.result;
      if (!result || typeof result !== 'object') {
        throw new Error('Bulk provisional task completed without a result payload');
      }
      return result as DsiBulkApplyResponse;
    }
    await sleep(intervalMs);
  }
  throw new Error('Bulk provisional customer task timed out while polling');
}

export type { DsiBulkTaskStatusResponse };
