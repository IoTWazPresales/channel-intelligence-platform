# Platform Async And Background Truth

## Current async/background paths
- Celery app configured in `app/worker/celery_app.py` using Redis broker/backend settings.
- Tasks registered in `app/worker/tasks.py`:
  - `imports.product_master_commit`
  - `imports.process_job`
- Product Master commit endpoint is the main in-repo enqueue path using `.delay()` under broker mode.

## Product Master async commit truth
- API commit endpoint first executes `try_enqueue_pm_commit_sync` under DB lock.
- Eligible jobs transition to `commit_queued`, then worker transitions to `commit_running`.
- Worker executes `commit_product_master_sync(..., from_worker=True)`.
- Success ends in `pm_committed`/`completed` and clears async metadata.
- Failure marks `commit_failed`, persists top-level message and row-level `pm_commit_worker_failed`.

## Idempotency/concurrency protections now in place
- API guard: duplicate clicks return clean `already_queued`/`already_running`/`already_completed` outcomes.
- Worker guard: execution proceeds only if job status is `commit_queued`.
- Locking: enqueue uses row-level lock to avoid concurrent queue transitions for same job.
- Validation/mapping edits are blocked while commit is queued/running.

## Stale-running behavior
- If status remains `commit_running` beyond stale window, enqueue path can recover job to `commit_failed` with warning row entry (`pm_commit_stale_recovered`) and allow retry.
- This is API-triggered recovery during subsequent enqueue attempts, not a standalone sweeper.

## Progress model exposed to UI
- Server-derived progress object includes phase id/label, rail steps, row result counts, and async commit phase (`queued|running|failed|none`).
- UI polling remains active while validation/commit external activity is in progress.

## Dev-only dispatch truth
- With `CIP_DEV_CELERY_DISPATCH=in_process_thread`, API logs startup warning and enqueue warning.
- Commit execution runs in daemon thread and logs execution warning tagged as dev-only.
- This mode preserves endpoint async UX but does not provide broker isolation or worker resilience.
