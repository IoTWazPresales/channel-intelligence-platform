import { apiGet } from '@/lib/api';

const TERMINAL = new Set(['SUCCESS', 'FAILURE']);

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export type CstResolutionPlanTaskStatus = {
  import_job_id: number;
  task_id: string;
  state: string;
  phase?: string;
  phase_label?: string;
  current_row?: number;
  total_rows?: number;
  pct?: number;
  error?: string;
  result?: Record<string, unknown> | null;
};

export async function fetchCstResolutionPlanTaskProgress(
  importJobId: number,
  taskId: string,
  signal?: AbortSignal
): Promise<CstResolutionPlanTaskStatus> {
  return apiGet<CstResolutionPlanTaskStatus>(
    `/api/v1/imports/jobs/${importJobId}/cst-resolution-plan-task/${encodeURIComponent(taskId)}`,
    { signal }
  );
}

/** Poll a CST resolution-plan Celery task (compute or apply) until SUCCESS or FAILURE. */
export async function pollCstResolutionPlanTask<TResult = Record<string, unknown>>(
  importJobId: number,
  taskId: string,
  options?: { intervalMs?: number; maxAttempts?: number }
): Promise<TResult> {
  const intervalMs = options?.intervalMs ?? 800;
  const maxAttempts = options?.maxAttempts ?? 600;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const status = await fetchCstResolutionPlanTaskProgress(importJobId, taskId);
    const state = String(status.state ?? '').toUpperCase();
    if (TERMINAL.has(state)) {
      if (state === 'FAILURE') {
        throw new Error(status.error ?? 'CST resolution plan task failed');
      }
      const result = status.result;
      if (!result || typeof result !== 'object') {
        throw new Error('CST resolution plan task completed without a result payload');
      }
      return result as TResult;
    }
    await sleep(intervalMs);
  }
  throw new Error('CST resolution plan task timed out while polling');
}
