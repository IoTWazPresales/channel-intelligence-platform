import { apiGet } from '@/lib/api';

import type { StewardBulkApplyResponse } from '@/features/import-steward/stewardEngine.types';

const TERMINAL = new Set(['SUCCESS', 'FAILURE']);

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export type CstBulkTaskStatus = {
  import_job_id: number;
  task_id: string;
  state: string;
  phase?: string;
  phase_label?: string;
  current_row?: number;
  total_rows?: number;
  pct?: number;
  error?: string;
  result?: StewardBulkApplyResponse | Record<string, unknown> | null;
};

export async function fetchCstBulkTaskProgress(
  importJobId: number,
  taskId: string,
  signal?: AbortSignal
): Promise<CstBulkTaskStatus> {
  return apiGet<CstBulkTaskStatus>(
    `/api/v1/imports/jobs/${importJobId}/cst-steward-bulk-task/${encodeURIComponent(taskId)}`,
    { signal }
  );
}

/** Poll a CST bulk Celery/dev task until SUCCESS or FAILURE. */
export async function pollCstBulkStewardTask<TResult = StewardBulkApplyResponse>(
  importJobId: number,
  taskId: string,
  options?: { intervalMs?: number; maxAttempts?: number }
): Promise<TResult> {
  const intervalMs = options?.intervalMs ?? 800;
  const maxAttempts = options?.maxAttempts ?? 600;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const status = await fetchCstBulkTaskProgress(importJobId, taskId);
    const state = String(status.state ?? '').toUpperCase();
    if (TERMINAL.has(state)) {
      if (state === 'FAILURE') {
        throw new Error(status.error ?? 'CST bulk steward task failed');
      }
      const result = status.result;
      if (!result || typeof result !== 'object') {
        throw new Error('CST bulk steward task completed without a result payload');
      }
      return result as TResult;
    }
    await sleep(intervalMs);
  }
  throw new Error('CST bulk steward task timed out while polling');
}
