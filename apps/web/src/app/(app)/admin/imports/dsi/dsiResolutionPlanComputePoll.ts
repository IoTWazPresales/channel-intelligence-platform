import { fetchBulkProvisionalTaskProgress } from '@/features/background-tasks/fetchImportJobProgress';

import { stewardAsyncPollComputeOptions } from '@/features/import-steward/stewardAsyncPoll';

const TERMINAL = new Set(['SUCCESS', 'FAILURE']);

function assertNotAborted(signal?: AbortSignal): void {
  if (signal?.aborted) {
    throw new DOMException('Resolution plan compute aborted', 'AbortError');
  }
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  assertNotAborted(signal);
  return new Promise((resolve, reject) => {
    const timer = globalThis.setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      globalThis.clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
      reject(new DOMException('Resolution plan compute aborted', 'AbortError'));
    };
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

function isQueuePendingState(state: string): boolean {
  return state.toUpperCase() === 'PENDING';
}

/** Poll resolution-plan compute Celery task until SUCCESS or FAILURE. */
export async function pollDsiResolutionPlanComputeTask(
  importJobId: number,
  taskId: string,
  options?: {
    intervalMs?: number;
    executionMaxAttempts?: number;
    queueGraceAttempts?: number;
    rowCount?: number;
    signal?: AbortSignal;
  }
): Promise<Record<string, unknown>> {
  const scaled = stewardAsyncPollComputeOptions(options?.rowCount ?? 1);
  const intervalMs = options?.intervalMs ?? scaled.intervalMs;
  const executionMaxAttempts = options?.executionMaxAttempts ?? scaled.executionMaxAttempts;
  const queueGraceAttempts = options?.queueGraceAttempts ?? scaled.queueGraceAttempts;

  let pendingOnlyAttempts = 0;
  let executionAttempts = 0;

  while (true) {
    assertNotAborted(options?.signal);

    const status = await fetchBulkProvisionalTaskProgress(importJobId, taskId, options?.signal);
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

    if (isQueuePendingState(state)) {
      pendingOnlyAttempts += 1;
      if (pendingOnlyAttempts > queueGraceAttempts) {
        throw new Error(
          'Resolution plan compute timed out while waiting in queue (worker busy with validate or apply — try again shortly)'
        );
      }
    } else {
      executionAttempts += 1;
      if (executionAttempts >= executionMaxAttempts) {
        throw new Error('Resolution plan compute timed out during compute');
      }
    }

    await sleep(intervalMs, options?.signal);
  }
}
