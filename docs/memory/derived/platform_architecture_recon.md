# Platform Architecture Recon

## Frontend architecture truth
- Next.js App Router (`apps/web/src/app`) with authenticated-style route group `(app)`.
- Shared shell/nav + MUI enterprise theming from `@cip/ui`; density and drawer state in Zustand.
- Data access via TanStack Query and `apiGet/apiPost/...` wrappers in `apps/web/src/lib/api.ts`.
- Same-origin API proxy path exists (`/api/v1/...`) with optional direct URL override via `NEXT_PUBLIC_API_URL`.

## API architecture truth
- FastAPI app in `app/main.py` with CORS middleware, no-store headers, and `/health`.
- Modular endpoint registration in `app/api/v1/router.py` spanning planning, admin, imports, and dev wipe.
- Async request DB access (`AsyncSession`) in handlers, sync session usage for heavy sync workflows/services.
- Import/product workflows split into service modules under `app/services/imports`.

## DB and migration structure
- SQLAlchemy model groups: dimensions, facts, derived, ingestion, mapping, lineup, promo export, product catalog.
- Alembic migration chain from initial schema (`20260412_0001`) through product master/catalog/mapping revisions to `20260425_0011`.
- Data model supports canonical (`dim_*`), operational facts (`fact_*`), derived recommendation-style tables, and ingestion lineage tables.

## Worker/background structure
- Celery app configured via Redis broker/backend (`celery_app.py`).
- Registered tasks: `imports.process_job` and `imports.product_master_commit`.
- Product Master commit dispatch can use broker path or explicit dev-only in-process thread mode.

## Import architecture
- Generic imports use `app/ingestion/pipeline.py` (`process_import_job_sync`) with template handler routing.
- Product Master uses dedicated constrained workflow (`imports_product_master.py` + `product_master_workflow.py`) instead of legacy one-shot loader.
- Product Master commit writes canonical product + catalog/EAV via `pm_commit_catalog.py` and sync upsert services.

## Job/state/progress architecture
- Import job source of truth: `import_job` with stage/status/metadata columns.
- Product Master exposes server-derived progress object in `GET /imports/product-master/jobs/{id}/state`.
- Async commit states include queued/running/failed/completed semantics tied to DB status and `pm_commit_meta`.

## Runtime modes currently supported
- Native local (Windows-friendly): local Postgres + API/web; optional Redis/worker.
- Dev fallback mode: `CIP_DEV_CELERY_DISPATCH=in_process_thread` for PM commit only.
- Optional Docker compose full-stack remains documented but is not required for local operation.
