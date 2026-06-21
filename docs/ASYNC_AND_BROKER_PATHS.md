# Async, Celery, and Redis — index

**Last verified:** 2026-06-21

**Canonical detail:** [`docs/memory/derived/platform_async_and_background_truth.md`](memory/derived/platform_async_and_background_truth.md)

**Topology:** [`docs/DEV_TOPOLOGY.md`](DEV_TOPOLOGY.md)

---

## Quick reference

| Path | Role |
|------|------|
| `scripts/dev-worker.js` | Dev worker; **Windows → `--pool=solo`**; spawns sibling **beat** on Windows |
| `app/worker/celery_app.py` | Celery app, beat schedule (reaper every 120s), task routes |
| `app/worker/tasks.py` | Registered tasks (see derived doc for full list) |
| `app/services/imports/import_dispatch.py` | Shared enqueue: broker → dev thread → sync fallback |
| `app/services/imports/*_enqueue.py` | Per-domain dispatch (DSI plan, shipment bulk, PM, etc.) |
| `app/services/task_run_ledger.py` | `task_run` dual-write at dispatch |
| `CIP_DEV_CELERY_DISPATCH=in_process_thread` | Dev-only when Redis unavailable |

---

## Enqueue paths (high level)

| Flow | Task name | Trigger |
|------|-----------|---------|
| DSI / generic validate | `imports.process_job` | `imports.py` validate / revalidate |
| DSI apply | `imports.dsi_apply` | DSI apply endpoint |
| DSI plan compute | `imports.dsi_resolution_plan_compute` | `mappings.py` compute-async |
| DSI plan apply | `imports.dsi_resolution_plan_apply` | mappings apply-async + post-validate historical |
| Shipment apply | `imports.shipment_apply` | shipment evidence apply |
| PM validate / commit | `imports.product_master_validate` / `imports.product_master_commit` | PM endpoints |
| Maintenance | `imports.reap_stale_running_jobs` | Celery beat |

**Not true anymore:** "Only PM commit uses Celery" — see derived truth doc.

---

## Dev vs prod

| | Dev (Windows native) | Docker / prod |
|--|-------------------|---------------|
| Worker pool | `solo` (one task at a time) | `prefork` (configurable concurrency) |
| Beat | Sibling process on Windows | `beat` service or `worker --beat` |
| Fallback | `in_process_thread` | Must not use in production |

---

## When debugging async issues

1. Read **`docs/memory/CURRENT.md`** and **`docs/DEV_TOPOLOGY.md`**
2. Read derived truth doc for the specific importer row
3. Run fix protocol (`AGENTS.md`) before tuning poll timeouts
