# Platform Master Inventory

## Repo shape
- `apps/web`: Next.js App Router UI, module pages, admin surfaces, query client, shared grid components.
- `apps/api`: FastAPI routers, SQLAlchemy models, import services, pipeline orchestration, Celery tasks.
- `packages/ui`: shared MUI theme/provider.
- `packages/types`: shared typed nav/role contracts.
- `scripts`: local dev runners, Python-venv wrappers, Docker convenience commands.
- `infra`: Docker compose stack and env templates.
- `docs`: architecture/runtime guidance and local dev operational docs.

## Core domains/modules
- **Ingestion/imports**: `app/models/ingestion.py`, `app/api/v1/endpoints/imports*.py`, `app/services/imports/*`, `app/ingestion/pipeline.py`.
- **Catalog and product master**: `app/models/product_catalog.py`, `app/services/catalog/*`, `app/services/imports/pm_*`.
- **Dimensions/facts/derived planning**: `app/models/dimensions.py`, `app/models/facts.py`, `app/models/derived.py`.
- **Operational planning modules**: inventory, forecasts, buy plans, pricing, promotions, lineup, budgets, exceptions.
- **Competition/market**: competition mappings/prices endpoints and market placeholder endpoint.

## Major operational components
- **Web shell/navigation**: `apps/web/src/features/shell/navConfig.ts`, `AppShell.tsx`.
- **API routing root**: `apps/api/app/api/v1/router.py` with modular endpoint registration.
- **DB migration stream**: `apps/api/alembic/versions/*` (initial + incremental revisions through product master async metadata).
- **Async worker**: `apps/api/app/worker/celery_app.py`, `apps/api/app/worker/tasks.py`.
- **Storage**: local storage backend under `app/storage/local.py` used by import file persistence.

## Main workflows present
- Product Master constrained workflow: upload -> mapping -> validate -> background commit.
- Generic import workflow: upload -> infer -> map -> validate/load synchronously (template dependent).
- CRUD-like planning data entry workflows for inventory/forecast/pricing/promotions/lineup/budgets.
- Mapping queue/competition approval workflows for human-in-loop correction.

## High-value scripts
- `pnpm dev:api`, `pnpm dev:web`, `pnpm dev:api-web`, `pnpm dev:worker`, `pnpm dev:all`.
- `pnpm local:db:migrate`, `pnpm local:db:wipe`, `pnpm local:db:seed`.
- `pnpm test:api`, `pnpm test:web`, `pnpm test:e2e`.
- Docker scripts retained under `pnpm docker:*` for optional environments.
