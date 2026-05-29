# Channel Intelligence Platform — Current Context

## Branch
`main`

## Head commit
(pending push) — `pm: async Celery validation, bulk row results, wizard resume, proxy timeout`

## Alembic Head
`20260518_0045` — Customer sell-through Phase 0 (`fact_customer_sellthrough`, staging, `customer_report_config`, template seed). Prior: `0043` `fact_dsi_forecast`, `0042` `fact_customer_velocity`. Smoke: **`cip_alembic_smoke`** at `0045`.

## Current State
- API .env confirmed pointing to cip (verified May 27, 2026)

---

## Latest work (May 2026) — Product Master validation at scale

### Backend
- **`validate_product_master_sync`**: row-level `ImportRowResult` rows collected in memory, flushed via **`insert(ImportRowResult)` in 2k chunks** (replaces ~14k individual `db.add()` + one flush).
- **Celery task** `imports.product_master_validate` → `product_master_validate_task` / `run_product_master_validate_job` / `run_pm_validate_worker`.
- **POST `/api/v1/imports/product-master/jobs/{id}/validate`**: returns **202** with `pm_validate.outcome=enqueued` when dispatched; polls via existing **GET …/state**.
- **Activity bell**: `staged_metadata.pm_validate_task` slot (`kind: product_master_validate`) in `background_tasks.py`.
- **DB pools** (Supabase): async `pool_size=5`, `max_overflow=10`, `pool_recycle=300`; sync `prepare_threshold=None`.

### Web
- PM validate mutation accepts **202**; polls state while `validate_queued` / `validate_running`.
- **`?job=N` resume** for PM: steps 3–6 from `stage` / `status` (no read-only stub).
- **Next.js proxy**: `AbortSignal.timeout(600_000)` for validate/commit/apply POST paths.

### Tests
- `tests/test_product_master_workflow.py` — bulk insert assertion (`db.execute`); `from_worker=True` in staged-metadata test.
- `tests/test_async_broker_dispatch.py` — validate job dispatch helper.

---

## Customer Sell-Through Phase 0 (foundation)

- fact_customer_sellthrough, staging, customer_report_config, template `customer_sell_through`
- Pipeline handlers skeleton (parsers `NotImplementedError` — Phase 1)
- Migrations: 0044, 0045

---

## PM mapping (prior commits on main)

- PgBouncer `statement_cache_size=0` on async engine
- PM SKU aliases / mapping UI disposition fixes (`4ba9529`, `224e886`, etc.)

---

## Runtime (local Windows)

- Web: http://localhost:3000
- API: http://localhost:8001
- Worker: Celery + Redis, or `CIP_DEV_CELERY_DISPATCH=in_process_thread`

## Next

- Smoke PM validate on Supabase with 14k+ row file (worker + bell + state poll).
- Restart API + worker after deploy.
