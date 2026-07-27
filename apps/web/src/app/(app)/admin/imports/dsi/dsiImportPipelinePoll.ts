import { fetchDsiImportPipelineProgress } from '@/features/background-tasks/fetchImportJobProgress';
import type { ImportJobPipelineProgress } from '@/features/background-tasks/importJobProgress.types';

/** @deprecated Use ``ImportJobPipelineProgress`` from background-tasks. */
export type DsiImportPipelineProgress = ImportJobPipelineProgress & { job_id?: number };

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Poll ``/dsi-progress`` until validation/revalidation completes or fails. */
export async function pollDsiImportPipelineUntilDone(
  importJobId: number,
  options?: { intervalMs?: number; maxAttempts?: number }
): Promise<DsiImportPipelineProgress> {
  const intervalMs = options?.intervalMs ?? 1500;
  const maxAttempts = options?.maxAttempts ?? 600;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const progress = await fetchDsiImportPipelineProgress(importJobId);
    const phase = String(progress.phase ?? '').trim();
    if (phase === 'complete') {
      return progress;
    }
    if (phase === 'failed') {
      throw new Error('DSI import validation failed on the server');
    }
    await sleep(intervalMs);
  }
  throw new Error('DSI import validation timed out while polling progress');
}
