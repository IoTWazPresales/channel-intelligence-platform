# AGENTS.md

## Cursor Cloud specific instructions

### Architecture overview

Monorepo (pnpm workspaces) with three services:

| Service | Path | Runtime | Default port |
|---------|------|---------|-------------|
| **Web** (Next.js 15) | `apps/web` | Node 22 | 3000 |
| **API** (FastAPI) | `apps/api` | Python 3.12 | 8001 |
| **Postgres 16** | Docker | — | 5432 |

Redis and the Celery worker are **optional** for most development. Set `CIP_DEV_CELERY_DISPATCH=in_process_thread` in `apps/api/.env` to run background jobs in-process without Redis.

### Starting services

1. **Postgres + Redis (Docker):** `pnpm docker:deps` (idempotent).
2. **API + Web (no worker):** `CIP_DEV_CELERY_DISPATCH=in_process_thread pnpm dev:api-web` from repo root — starts API on `:8001` and web on `:3000`.
3. **Migrations:** `pnpm local:db:migrate` (runs `alembic upgrade head` via the Python venv at `apps/api/.venv`).

See root `README.md` and `infra/docker/README.md` for the full command reference.

### Testing

- **Web unit tests:** `pnpm test:web` (Vitest, 202 tests).
- **API tests:** `pnpm test:api` (pytest). Some import pipeline DB tests require either a disposable test database (`DATABASE_URL=...cip_test`) or `ALLOW_TESTS_ON_DEV_DB=1`. To run all tests safely: create a `cip_test` database in the Postgres container (`docker exec docker-postgres-1 psql -U cip -c "CREATE DATABASE cip_test OWNER cip;"`), run migrations against it, then invoke pytest with the test database URLs.
- **Build (includes type-check + lint):** `pnpm build`.

### Known gotchas

- **`pnpm lint` fails** with ESLint 9 because no flat config file (`eslint.config.js`) exists. `pnpm build` runs Next.js's built-in ESLint check successfully. This is a pre-existing gap — only standalone `eslint .` is broken.
- **`database_url_sync_migrate`**: The Alembic `env.py` references `settings.database_url_sync_migrate` — a field added to `app/core/config.py:Settings` to allow a separate migration-only connection string. If this field is missing, `pnpm local:db:migrate` will fail with `AttributeError`.
- **Docker must be running** before `pnpm docker:deps`. In Cloud Agent VMs, Docker requires `fuse-overlayfs` storage driver and `iptables-legacy`.
- The API dev script (`pnpm dev:api`) performs a port preflight check to ensure no stale process is on `:8001`. If the check fails, set `CIP_SKIP_API_PORT_PREFLIGHT=1`.
