import { fetchBulkProvisionalTaskProgress } from '@/features/background-tasks/fetchImportJobProgress';

const TERMINAL = new Set(['SUCCESS', 'FAILURE']);

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export type DsiResolutionPlanApplyResult = {
  import_job_id: number;
  applied: number;
  failed: number;
  skipped_hold: number;
  skipped_not_ready: number;
  results?: unknown[];
};

/** Poll resolution-plan apply Celery task until SUCCESS or FAILURE. */
export async function pollDsiResolutionPlanApplyTask(
  importJobId: number,
  taskId: string,
  options?: { intervalMs?: number; maxAttempts?: number }
): Promise<DsiResolutionPlanApplyResult> {
  const intervalMs = options?.intervalMs ?? 800;
  const maxAttempts = options?.maxAttempts ?? 600;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const status = await fetchBulkProvisionalTaskProgress(importJobId, taskId);
    const state = String(status.state ?? '').toUpperCase();
    if (TERMINAL.has(state)) {
      if (state === 'FAILURE') {
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
        results: Array.isArray(result.results) ? result.results : undefined,
      };
    }
    await sleep(intervalMs);
  }
  throw new Error('Resolution plan apply timed out while polling');
}
