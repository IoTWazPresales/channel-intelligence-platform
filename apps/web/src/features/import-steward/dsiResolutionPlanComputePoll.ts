import { fetchBulkProvisionalTaskProgress } from '@/features/background-tasks/fetchImportJobProgress';

import { stewardAsyncPollOptions } from './stewardAsyncPoll';

const TERMINAL = new Set(['SUCCESS', 'FAILURE']);

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Poll resolution-plan compute Celery task until SUCCESS or FAILURE. */
export async function pollDsiResolutionPlanComputeTask(
  importJobId: number,
  taskId: string,
  options?: { intervalMs?: number; maxAttempts?: number; rowCount?: number }
): Promise<Record<string, unknown>> {
  const scaled = stewardAsyncPollOptions(options?.rowCount ?? 1);
  const intervalMs = options?.intervalMs ?? scaled.intervalMs;
  const maxAttempts = options?.maxAttempts ?? scaled.maxAttempts;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const status = await fetchBulkProvisionalTaskProgress(importJobId, taskId);
    const state = String(status.state ?? '').toUpperCase();
    if (TERMINAL.has(state)) {
      if (state === 'FAILURE') {
        throw new Error(status.error ?? 'Resolution plan compute task failed');
      }
      const result = status.result as Record<string, unknown> | undefined;
      if (!result || typeof result !== 'object') {
        throw new Error('Resolution plan compute completed without a result payload');
      }
      return result;
    }
    await sleep(intervalMs);
  }
  throw new Error('Resolution plan compute timed out while polling');
}
