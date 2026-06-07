/** Poll budget for long-running DSI steward Celery tasks (apply plan, bulk provisional). */

const DEFAULT_INTERVAL_MS = 800;
const MIN_ATTEMPTS = 150;
const MAX_ATTEMPTS = 3600;
/** ~1.2s per row budget on remote DB (provisional create is slower than map). */
const MS_PER_ROW_BUDGET = 1200;

export function stewardAsyncPollMaxAttempts(
  rowCount: number,
  options?: { intervalMs?: number; minAttempts?: number; maxAttempts?: number }
): number {
  const intervalMs = options?.intervalMs ?? DEFAULT_INTERVAL_MS;
  const minAttempts = options?.minAttempts ?? MIN_ATTEMPTS;
  const maxAttempts = options?.maxAttempts ?? MAX_ATTEMPTS;
  const rows = Math.max(1, rowCount);
  const estimatedMs = rows * MS_PER_ROW_BUDGET;
  const attempts = Math.ceil(estimatedMs / intervalMs) + 45;
  return Math.min(maxAttempts, Math.max(minAttempts, attempts));
}

export function stewardAsyncPollOptions(rowCount: number) {
  const intervalMs = DEFAULT_INTERVAL_MS;
  return { intervalMs, maxAttempts: stewardAsyncPollMaxAttempts(rowCount, { intervalMs }) };
}
