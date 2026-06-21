# Platform Async And Background Truth

**Last verified:** 2026-06-21  
**Index:** `docs/ASYNC_AND_BROKER_PATHS.md`  
**Topology:** `docs/DEV_TOPOLOGY.md`

---

## Celery configuration

- App: `app/worker/celery_app.py` — Redis broker/backend from settings.
- Base task: `LedgerTask` — dual-writes `task_run` on lifecycle events.
- Beat: `imports.reap_stale_running_jobs` every **120s** (`CIP_RUNNING_JOB_REAPER_INTERVAL_SECONDS`).
- Default queue: `celery` (single queue today — interactive and batch share it).

---

## Registered tasks (`app/worker/tasks.py`)

| Task name | Purpose |
|-----------|---------|
| `imports.process_job` | Full import pipeline (DSI validate, etc.) |
| `imports.dsi_apply` | DSI fact apply |
| `imports.dsi_resolution_plan_compute` | Steward plan generation (read-only) |
| `imports.dsi_resolution_plan_apply` | Steward plan apply (+ post-validate historical auto-apply) |
| `imports.dsi_bulk_provisional_customers` | Bulk provisional customers |
| `imports.shipment_apply` | Shipment evidence apply |
| `imports.shipment_bulk_*` | Shipment bulk steward |
| `imports.product_master_validate` | PM validate |
| `imports.product_master_commit` | PM commit |
| `imports.dsi_soh_reconciliation` | SOH reconcile after apply |
| `imports.dsi_velocity_compute` / `imports.dsi_forecasting` | Intelligence derive |
| `imports.infer_dsi` | DSI inference scaffold |
| `imports.reap_stale_running_jobs` | Stuck `running` import_job reaper |
| `commercial_planner.parse_lineup_case` | Lineup parse |

---

## Dispatch pattern

1. **Broker:** `celery_app.send_task(...)` via `import_dispatch.py` or `*_enqueue.py`.
2. **Dev thread:** `CIP_DEV_CELERY_DISPATCH=in_process_thread` or `detach_from_caller=True`.
3. **Inline sync:** rare; returns `async_poll: false`.

Slot registry: `import_background_slots.py` + `import_job_background_metadata.py`.  
Activity feed: `background_tasks.py` — readers still partially hand-coded per slot kind.

---

## DSI steward async (canonical)

| Step | API | Poll |
|------|-----|------|
| Plan compute | `POST .../dsi-resolution-plan/compute-async` | `GET .../dsi-steward-bulk-task/{task_id}` |
| Plan apply | `POST .../dsi-resolution-plan/apply-async` | same poll route |

Post-validate historical workflow enqueues **`dsi_resolution_plan_apply`** automatically
after validate (`dsi_validate_post_sync.py`) — competes with interactive compute on
**solo** workers.

---

## Reaper behaviour

- Module: `running_import_job_reaper.py`
- Marks `import_job` failed only when `inspect().active()` shows task **not** running.
- **`inspect()` unavailable → no-op** (`inspected: false`) — common on **Windows solo**.
- Does not terminate DB sessions.

---

## UI poll budgets (web)

- `stewardAsyncPoll.ts` — compute queue grace **150×800ms**; apply grace higher (450+ scaled).
- False "worker busy" errors possible when queue wait exceeds compute grace — see `DEV_TOPOLOGY.md`.

---

## Dev-only dispatch

- `CIP_DEV_CELERY_DISPATCH=in_process_thread` — logs warnings; no broker isolation.
- Must not be set in production or shared environments.

---

## Product Master commit (reference implementation)

- Enqueue under row lock; states `commit_queued` → `commit_running`.
- Stale `commit_running` recovery on subsequent enqueue attempts.
- See prior PM-specific docs in archive CONTEXT if needed.

---

## Gaps / backlog

- **Single Celery queue** — no interactive vs batch split (deferred; see BACKLOG / architecture notes in CURRENT.md).
- **`task_run` ledger** — write path populated; not sole read model for activity feed yet.
- **`ASYNC_AND_BROKER_PATHS` audit (2025)** listed only PM commit — superseded by table above.
