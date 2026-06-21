/** Poll budget for long-running DSI steward Celery tasks (apply plan, bulk provisional). */

export const DEFAULT_INTERVAL_MS = 800;
const MIN_ATTEMPTS = 150;
const MAX_ATTEMPTS = 3600;
/** ~1.2s per row budget for compute / map-heavy work. */
const MS_PER_ROW_BUDGET = 1200;
/** ~4s per row for provisional create over remote Supabase pooler. */
const MS_PER_ROW_APPLY_BUDGET = 4000;

/** Extra poll cycles while Celery stays PENDING (solo-pool queue wait). Resolution-plan compute. */
export const COMPUTE_QUEUE_GRACE_ATTEMPTS = 150;
/** Longer queue grace for apply — waits behind compute on solo worker (base; scales with row count). */
export const APPLY_QUEUE_GRACE_ATTEMPTS = 450;
const APPLY_QUEUE_GRACE_MAX_ATTEMPTS = 7200;

export function stewardAsyncPollMaxAttempts(
  rowCount: number,
  options?: { intervalMs?: number; minAttempts?: number; maxAttempts?: number; msPerRow?: number }
): number {
  const intervalMs = options?.intervalMs ?? DEFAULT_INTERVAL_MS;
  const minAttempts = options?.minAttempts ?? MIN_ATTEMPTS;
  const maxAttempts = options?.maxAttempts ?? MAX_ATTEMPTS;
  const msPerRow = options?.msPerRow ?? MS_PER_ROW_BUDGET;
  const rows = Math.max(1, rowCount);
  const estimatedMs = rows * msPerRow;
  const attempts = Math.ceil(estimatedMs / intervalMs) + 45;
  return Math.min(maxAttempts, Math.max(minAttempts, attempts));
}

export function stewardAsyncPollOptions(rowCount: number) {
  const intervalMs = DEFAULT_INTERVAL_MS;
  return { intervalMs, maxAttempts: stewardAsyncPollMaxAttempts(rowCount, { intervalMs }) };
}

/** Apply poll: execution budget (row-scaled) plus queue grace while state stays PENDING. */
export function stewardAsyncPollApplyOptions(rowCount: number) {
  const intervalMs = DEFAULT_INTERVAL_MS;
  const rows = Math.max(1, rowCount);
  const scaledQueueGrace = Math.ceil((rows * 2000) / intervalMs);
  return {
    intervalMs,
    executionMaxAttempts: stewardAsyncPollMaxAttempts(rowCount, {
      intervalMs,
      msPerRow: MS_PER_ROW_APPLY_BUDGET,
    }),
    queueGraceAttempts: Math.min(
      APPLY_QUEUE_GRACE_MAX_ATTEMPTS,
      Math.max(APPLY_QUEUE_GRACE_ATTEMPTS, scaledQueueGrace)
    ),
  };
}

/** Compute poll: execution budget (row-scaled) plus queue grace while state stays PENDING. */
export function stewardAsyncPollComputeOptions(rowCount: number) {
  const intervalMs = DEFAULT_INTERVAL_MS;
  return {
    intervalMs,
    executionMaxAttempts: stewardAsyncPollMaxAttempts(rowCount, { intervalMs }),
    queueGraceAttempts: COMPUTE_QUEUE_GRACE_ATTEMPTS,
  };
}
