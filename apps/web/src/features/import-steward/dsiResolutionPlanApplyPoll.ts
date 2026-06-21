import { fetchBulkProvisionalTaskProgress } from '@/features/background-tasks/fetchImportJobProgress';

import { stewardAsyncPollApplyOptions } from './stewardAsyncPoll';

const TERMINAL = new Set(['SUCCESS', 'FAILURE']);

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Celery queue wait — not STARTED/PROGRESS (see task_track_started on worker). */
function isQueuePendingState(state: string): boolean {
  return state.toUpperCase() === 'PENDING';
}

export type DsiResolutionPlanApplyResult = {
  import_job_id: number;
  applied: number;
  failed: number;
  skipped_hold: number;
  skipped_not_ready: number;
  processed?: number;
  partial_success?: boolean;
  interrupted?: boolean;
  error?: string;
  results?: unknown[];
};

function parseApplyResult(
  importJobId: number,
  status: { state?: string; result?: unknown; error?: string }
): DsiResolutionPlanApplyResult {
  if (String(status.state ?? '').toUpperCase() === 'FAILURE') {
    throw new Error(status.error ?? 'Resolution plan apply task failed');
  }
  const result = status.result as Record<string, unknown> | undefined;
  if (!result || typeof result !== 'object') {
    throw new Error('Resolution plan apply completed without a result payload');
  }
  return {
    import_job_id: Number(result.import_job_id ?? importJobId),
    applied: Number(result.applied ?? 0),
    failed: Number(result.failed ?? 0),
    skipped_hold: Number(result.skipped_hold ?? 0),
    skipped_not_ready: Number(result.skipped_not_ready ?? 0),
    processed: Number(result.processed ?? result.applied ?? 0),
    partial_success: Boolean(result.partial_success),
    interrupted: Boolean(result.interrupted),
    error: typeof result.error === 'string' ? result.error : undefined,
    results: Array.isArray(result.results) ? result.results : undefined,
  };
}

/** One-shot status read for recovery after a client-side timeout. */
export async function fetchDsiResolutionPlanApplyResultIfTerminal(
  importJobId: number,
  taskId: string
): Promise<DsiResolutionPlanApplyResult | null> {
  const status = await fetchBulkProvisionalTaskProgress(importJobId, taskId);
  const state = String(status.state ?? '').toUpperCase();
  if (!TERMINAL.has(state)) return null;
  return parseApplyResult(importJobId, status);
}

/** Poll resolution-plan apply Celery task until SUCCESS or FAILURE. */
export async function pollDsiResolutionPlanApplyTask(
  importJobId: number,
  taskId: string,
  options?: {
    intervalMs?: number;
    executionMaxAttempts?: number;
    queueGraceAttempts?: number;
    rowCount?: number;
  }
): Promise<DsiResolutionPlanApplyResult> {
  const scaled = stewardAsyncPollApplyOptions(options?.rowCount ?? 1);
  const intervalMs = options?.intervalMs ?? scaled.intervalMs;
  const executionMaxAttempts = options?.executionMaxAttempts ?? scaled.executionMaxAttempts;
  const queueGraceAttempts = options?.queueGraceAttempts ?? scaled.queueGraceAttempts;

  let pendingOnlyAttempts = 0;
  let executionAttempts = 0;

  while (true) {
    const status = await fetchBulkProvisionalTaskProgress(importJobId, taskId);
    const state = String(status.state ?? '').toUpperCase();
    if (TERMINAL.has(state)) {
      return parseApplyResult(importJobId, status);
    }

    if (isQueuePendingState(state)) {
      pendingOnlyAttempts += 1;
      if (pendingOnlyAttempts > queueGraceAttempts) {
        const late = await fetchDsiResolutionPlanApplyResultIfTerminal(importJobId, taskId);
        if (late) return late;
        throw new Error('Resolution plan apply timed out while waiting in queue (worker busy)');
      }
    } else {
      executionAttempts += 1;
      if (executionAttempts >= executionMaxAttempts) {
        const late = await fetchDsiResolutionPlanApplyResultIfTerminal(importJobId, taskId);
        if (late) return late;
        throw new Error('Resolution plan apply timed out during apply');
      }
    }

    await sleep(intervalMs);
  }
}
