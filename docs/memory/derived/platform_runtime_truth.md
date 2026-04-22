# Platform Runtime Truth

## Native local dev truth (current baseline)
- Primary non-Docker workflow is native API + web (`pnpm dev:api-web`) with local PostgreSQL service.
- API expects Python 3.12 venv under `apps/api/.venv`.
- Default API/web ports are documented as 8000/3000 generally, with `dev:api-web` script currently pinning API to 8001 and proxy target to 8001.
- DB utilities for native path: `pnpm local:db:migrate`, `pnpm local:db:wipe`, `pnpm local:db:seed`.

## Optional Docker truth
- Compose files and `pnpm docker:*` scripts remain in repo for optional full-stack/dependency use.
- Docker full stack maps API container 8000 to host 8010 and web to 3000.
- Docker is optional and not required for current local development path.

## Environment assumptions
- Postgres reachable at configured `DATABASE_URL`/`DATABASE_URL_SYNC` (defaults point to localhost).
- Upload storage path must exist (`LOCAL_STORAGE_PATH`, default local directory).
- CORS includes localhost origins for local Next dev.
- Stub auth headers (`X-User-Id`, `X-User-Role`) are used by web/API integration.

## Worker/Redis runtime truth
- Default async dispatch expects Redis broker/backend + running Celery worker.
- If Redis unavailable locally, PM commit can use explicit dev-only in-process thread dispatch via `CIP_DEV_CELERY_DISPATCH=in_process_thread`.
- This fallback is intentionally scoped and clearly logged as dev-only behavior.

## Operational caveats to keep in view
- Port/source-of-truth drift can occur if old processes or mixed mode setups are running concurrently.
- Runtime docs include both 8000 and 8001 references due to script-level stabilization choices; this should be treated as an active alignment checkpoint for future cleanup.
