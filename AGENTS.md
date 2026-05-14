# AGENTS.md

## Cursor Cloud specific instructions

### Services overview

| Service | Port | Role |
|---------|------|------|
| PostgreSQL 16 | 5432 | Primary DB (Docker: `postgres:16-alpine`) |
| Redis 7 | 6379 | Celery broker + cache (Docker: `redis:7-alpine`) |
| FastAPI (API) | 8001 (local) / 8010 (Docker) | Backend REST API |
| Next.js (Web) | 3000 | Frontend app |
| Celery Worker | — | Optional async tasks |

### Starting the dev environment

**Recommended: Hybrid** (Postgres + Redis in Docker, app on host — faster iteration):
```bash
sudo dockerd &>/tmp/dockerd.log &  # if Docker daemon not running; wait ~3s
sudo chmod 666 /var/run/docker.sock
pnpm docker:deps           # Postgres + Redis only
pnpm local:db:migrate      # Alembic migrations via local venv
pnpm dev:api-web           # API on :8001, web on :3000
```

**Alternative: Docker full stack** (all services in containers):
```bash
pnpm docker:up:detached
```
- Web: http://localhost:3000, API docs: http://localhost:8010/docs
- Note: the web Docker build may fail if the latest code has lint errors that block `next build`.

### Known gotchas

1. **Docker daemon must be started manually** in Cloud Agent VMs:
   ```bash
   sudo dockerd &>/tmp/dockerd.log &
   ```
   Wait ~3s for it to be ready. The socket needs `sudo chmod 666 /var/run/docker.sock` unless running commands with sudo.

2. **ESLint requires legacy config mode**: The web app uses ESLint 9 but the project config is in the old `eslintConfig` package.json format. Run lint with: `ESLINT_USE_FLAT_CONFIG=false pnpm lint` or just use `pnpm lint` if a flat config is added later.

4. **API tests DB protection**: Some import pipeline tests refuse to run on the default `cip` database. Use `ALLOW_TESTS_ON_DEV_DB=1` to run the full suite, or use a separate test database.

5. **`seed.py` has a syntax error** on line 43 (extra `)`) that prevents it from running. Use `--commercial-system-reference-only` flag path is blocked too (entire file fails to parse). Migrations already seed the system reference dimensions (OPEN_CHANNEL customer, UNASSIGNED distributor) via migration `20260429_0022`.

6. **Celery without Redis**: Set `CIP_DEV_CELERY_DISPATCH=in_process_thread` in `apps/api/.env` to run background jobs in-process without Redis/Celery.

### Commands reference

See root `README.md` for full script table. Key commands:
- `pnpm test:web` — Vitest
- `pnpm test:api` — pytest (requires `ALLOW_TESTS_ON_DEV_DB=1` for full suite)
- `pnpm build` — Build all packages
- `pnpm docker:up:detached` — Full Docker stack (rebuilds images)
- `pnpm docker:deps` — Just Postgres + Redis
- `pnpm local:db:migrate` — Run Alembic migrations via local venv
