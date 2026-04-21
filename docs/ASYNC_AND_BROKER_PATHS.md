# Async, Celery, and Redis usage (audit)

**Scope:** `apps/api` application code and worker registration. **Purpose:** local dev without Docker Desktop; production architecture unchanged.

| Path | What it does | Classification |
|------|----------------|----------------|
| `app/worker/celery_app.py` | Instantiates Celery with `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` (Redis URLs). Imported whenever `app.worker.tasks` loads. | **Requires Redis** for any `.delay()` / worker consumption; app **starts** without connecting until tasks are sent (lazy broker). |
| `app/worker/tasks.py` → `product_master_commit_task` | Celery task; runs `run_product_master_commit_job`. | **Requires Redis + worker** in normal (`broker`) dispatch. |
| `app/worker/tasks.py` → `process_import_job_task` | Celery task wrapping `process_import_job_sync`. | **Registered only** — no `.delay()` / `send_task` in this repo. **Works natively** today via sync paths; **would require** Redis+worker if something enqueued it later. |
| `app/worker/tasks.py` → `run_product_master_commit_job` | Shared body for Celery + dev thread. | **Works natively** when called from thread with DB; **requires** worker process when invoked via Celery. |
| `app/api/v1/endpoints/imports_product_master.py` → POST commit | `try_enqueue` then `product_master_commit_task.delay()` **or** daemon thread calling `run_product_master_commit_job` when `CIP_DEV_CELERY_DISPATCH=in_process_thread`. | **broker:** **Requires Redis + worker** or enqueue fails → **503** + rollback (clear failure). **in_process_thread:** **Explicit dev-only fallback** (no broker). |
| `app/api/v1/endpoints/imports.py` → `create_job` | Optional `process_import_job_sync` in request when `run_sync` and not Product Master. | **Works natively** (sync in API process). |
| `app/api/v1/endpoints/imports.py` → `POST /jobs/{id}/process` | `process_import_job_sync` in request. | **Works natively**. |
| `app/core/config.py` → `redis_url` | Declared default; **no reads** in `app/` at time of audit. | **Works natively** (unused placeholder for future cache/session). |
| `app/core/config.py` → `celery_broker_url`, `celery_result_backend` | Used by `celery_app`. | **Requires Redis** for real async tasks. |
| `app/core/config.py` → `cip_dev_celery_dispatch` | Selects PM commit dispatch mode. | **Dev-only** configuration surface. |

## Summary

- **Only production enqueue path** for Celery in this codebase: **Product Master commit** (`product_master_commit_task.delay`).
- **General imports** use **synchronous** `process_import_job_sync` in the API; no Celery trigger.
- **`redis_url`:** not wired into runtime paths yet.
- **`process_import_job_task`:** available for future/async import processing; not triggered from API today.

## Risks still unresolved (by design / ops)

| Risk | Mitigation |
|------|------------|
| Worker crash / broker down with default `broker` | Existing **503** + job rollback + message; docs list requirement. |
| `in_process_thread` misuse in shared env | **Startup + per-job WARNING** logs; must not be set in production. |
| `process_import_job_task` enqueued from outside repo | Out of scope; would need broker + worker. |
