import { fetchBackgroundTasksList } from '@/features/background-tasks/fetchImportJobProgress';

import { DEFAULT_INTERVAL_MS } from './stewardAsyncPoll';

const STEWARD_BULK_KINDS = new Set(['dsi_resolution_plan_compute', 'dsi_resolution_plan_apply']);

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Wait until no resolution-plan compute/apply Celery task is active for this job. */
export async function waitForDsiStewardBulkIdle(
  importJobId: number,
  options?: { maxWaitMs?: number; intervalMs?: number }
): Promise<void> {
  const maxWaitMs = options?.maxWaitMs ?? 180_000;
  const intervalMs = options?.intervalMs ?? DEFAULT_INTERVAL_MS;
  const deadline = Date.now() + maxWaitMs;

  while (Date.now() < deadline) {
    const data = await fetchBackgroundTasksList();
    const blocking = (data?.tasks ?? []).find(
      (t) =>
        t.import_job_id === importJobId &&
        t.status === 'running' &&
        STEWARD_BULK_KINDS.has(String(t.kind ?? ''))
    );
    if (!blocking) {
      return;
    }
    if (blocking.kind === 'dsi_resolution_plan_apply') {
      throw new Error('A resolution plan apply is already running for this job.');
    }
    await sleep(intervalMs);
  }
  throw new Error('Timed out waiting for resolution plan compute to finish before apply.');
}
