# Architecture

## System context

The platform is a **decision system** layered on curated commercial data. It is not an ERP replacement. Data flows:

1. **Raw** — uploaded files in object storage (local adapter in dev; S3-compatible later).
2. **Standardized** — inferred columns, field mappings, validation rows.
3. **Curated** — resolved against `dim_*` masters and loaded to `fact_*` tables (incremental evolution).
4. **Derived** — deterministic metrics and recommendations (`stock_risk`, `buy_recommendation`, etc.) with explicit explanations.

## Backend (`apps/api`)

- **FastAPI** modular routers under `app/api/v1/endpoints/`.
- **SQLAlchemy 2.0** models in `app/models/` (dimensions, facts, derived, ingestion, mapping).
- **Alembic** — initial revision uses `metadata.create_all` for a clean bootstrap; subsequent migrations should be incremental `op.add_column` / `op.create_table` as the schema stabilizes.
- **Async** SQLAlchemy for request handlers; **sync** session for Alembic, seed, ingestion processor, Celery tasks.
- **Celery** — `app/worker/tasks.py` exposes `imports.process_job` for async pipeline runs.
- **Ingestion** — `app/ingestion/pipeline.py` orchestrates stages; `parsers/` holds per-source hooks.

## Frontend (`apps/web`)

- **Next.js 15 App Router** with route groups `(app)` for the authenticated-style shell.
- **MUI** themed via `@cip/ui` (dark-first enterprise palette, density toggle persisted in Zustand).
- **AG Grid** community modules registered once in `EnterpriseDataGrid`.
- **TanStack Query** for API data; stub auth via `X-User-Id` / `X-User-Role` headers in `src/lib/api.ts`.

## Key tradeoffs (MVP)

- **Alembic bootstrap**: single migration calling `create_all` trades fine-grained history for speed of first delivery; plan to switch to explicit migrations before production multi-tenant rollout.
- **Synchronous import processing** in `POST /imports/jobs` when `run_sync=true` — convenient for demos; production should default to Celery + larger file limits.
- **Auth**: stub only; menu guards and roles are typed in `@cip/types` for later JWT/RBAC integration.

## Extension points

- Add a source: new `SourceDefinition` row + optional `parser_module` implementation.
- Add a collector: implement `StorageBackend` for S3; schedule Celery beat tasks for external pulls (no scraping in v1).
- Add recommendation domain: new derived table inheriting `RecommendationMixin` + thin service in `app/services/`.
