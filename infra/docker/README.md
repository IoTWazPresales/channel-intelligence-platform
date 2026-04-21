# Docker — full stack and local hybrid

Runs **Postgres**, **Redis**, **FastAPI** (with migrations on startup), **Celery worker**, and **Next.js** in containers when you start the full stack.

**No Docker Desktop?** Use **native PostgreSQL** (and optionally native Redis) plus `pnpm dev:api` / `pnpm dev:web`. See **[../../docs/LOCAL_DEV_WINDOWS.md](../../docs/LOCAL_DEV_WINDOWS.md)** and broker/async inventory **[../../docs/ASYNC_AND_BROKER_PATHS.md](../../docs/ASYNC_AND_BROKER_PATHS.md)**. The Compose file here is unchanged for teams/CI that still run containerized dependencies.

## Prerequisites

- **Docker Engine + Compose** (Linux, or any approved runtime on Windows/Mac) *if* you use the commands in this file. Docker Desktop specifically is **not** required if you do not use Docker at all for local dev.

---

## Local development (hybrid) — recommended for day-to-day coding

Run **Postgres + Redis in Docker**, and run the **API + Next.js on your machine** with hot reload. You avoid rebuilding images for every small change.

### Port conflicts (read this first)

| Port | Docker service | If you run locally |
|------|----------------|-------------------|
| **3000** | `web` container | `pnpm dev` / `pnpm dev:web` |
| **8010** | `api` container (host → container `8000`) | `pnpm dev:api` (defaults to **8000** on the host) |

You **cannot** bind two processes to the same port. If the Docker `web` container is up, **Next.js dev on the host will fail** (`EADDRINUSE`). The compose file publishes the API on **8010** so it does not fight a stale `uvicorn` (or Windows phantom listeners) that often still occupies **127.0.0.1:8000** on dev PCs. Use **`http://localhost:8010`** for API docs and curls when the stack is running in Docker.

**Before starting local API + web**, stop the app containers (keeps Postgres + Redis running):

```bash
pnpm docker:stop:app
```

Equivalent:

```bash
docker compose -f infra/docker/docker-compose.yml stop api worker web
```

Then start only the data layer (safe to run anytime; idempotent):

```bash
pnpm docker:deps
```

### One-time: Python API on the host

**Use Python 3.12.x** (project expectation; see root `README.md`). Newer versions (for example **3.14**) often fail to install **`asyncpg`** until wheels catch up. This repo includes `apps/api/.python-version` for **pyenv** / similar tools.

From the **repository root**:

```bash
cd apps/api
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
```

From `apps/api`, create the local upload folder once if it is missing: `storage\uploads` on Windows, or `mkdir -p storage/uploads` on macOS / Linux.

Optional: copy `apps/api/.env.example` to `apps/api/.env` and edit. Defaults in `app/core/config.py` already target `localhost:5432` and `localhost:6379`.

### Every day: run API + web

From the **repository root** (with `pnpm docker:deps` already done and `pnpm docker:stop:app` if you had used full Docker before):

```bash
pnpm dev:all
```

- **Web:** [http://localhost:3000](http://localhost:3000) (hot reload)
- **API:** [http://localhost:8000/docs](http://localhost:8000/docs) (`uvicorn --reload`)

Or use two terminals: `pnpm dev:api` and `pnpm dev:web`.

The browser still calls `http://localhost:8000` (your local Uvicorn), same as the all-Docker setup.

### Wipe the database (hybrid — API container not running)

Uses a **one-off** API container so you do not need a long-running `api` service:

```bash
pnpm docker:db:wipe:run
```

First run may build the `api` image once. Postgres must be reachable (start with `pnpm docker:deps`).

### Wipe the database (full Docker — `api` already running)

```bash
pnpm docker:db:wipe
```

### Celery (optional, hybrid)

Background jobs still expect Redis. With `pnpm docker:deps` running and your **local** API venv active:

```bash
cd apps/api
celery -A app.worker.celery_app worker -l info
```

Avoid `docker compose ... up -d worker` while the API runs on the host: in this compose file the **worker service depends on the `api` service**, so Compose would try to start the **API container** again and reclaim port **8000**.

---

## Start everything (all in Docker)

From the **repository root** (`channel-intelligence-platform`):

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

Or: `pnpm docker:up` (foreground) / `pnpm docker:up:detached` (background).

Then open:

- **Web UI:** [http://localhost:3000](http://localhost:3000)
- **API docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health:** [http://localhost:8000/health](http://localhost:8000/health)

The browser calls the API at `http://localhost:8000` (host port mapping), so `NEXT_PUBLIC_API_URL` stays `http://localhost:8000`.

**Switching from full Docker to hybrid:** run `pnpm docker:stop:app`, then `pnpm docker:deps`, then `pnpm dev:all` on the host.

## Wipe all data (empty DB for real uploads)

**Full stack (`api` container running):**

```bash
pnpm docker:db:wipe
```

**Hybrid (only Postgres + Redis, or nothing long-running on `api`):**

```bash
pnpm docker:db:wipe:run
```

Equivalent (one-off container):

```bash
docker compose -f infra/docker/docker-compose.yml run --rm api python scripts/wipe_database.py
```

## Optional: catalog-only or full demo seed

```bash
docker compose -f infra/docker/docker-compose.yml run --rm api python scripts/seed.py
```

Catalog dimensions only (regions, channels, distributors). Add **`--full`** for legacy sample customers, products, facts, and derived rows (not recommended for production-style use).

## Run in background

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build
```

## Stop and remove containers

```bash
docker compose -f infra/docker/docker-compose.yml down
```

To also remove the Postgres volume (wipes DB):

```bash
docker compose -f infra/docker/docker-compose.yml down -v
```

## Services only (Postgres + Redis)

From repo root:

```bash
pnpm docker:deps
```

Same as: `docker compose -f infra/docker/docker-compose.yml up -d postgres redis`

## Troubleshooting

- **Port already in use (3000 / 8000):** you likely still have Docker `web` / `api` up. Run `pnpm docker:stop:app` or change host ports in `docker-compose.yml` (e.g. `3001:3000` for web).
- **Web cannot reach API:** ensure `NEXT_PUBLIC_API_URL` matches how you open the app (usually `http://localhost:8000`).
- **Migrations fail:** check Postgres is healthy (`docker compose -f infra/docker/docker-compose.yml ps`).
- **Local API cannot connect to DB:** run `pnpm docker:deps` and wait until Postgres is healthy.
- **`pip install` fails on `asyncpg` (compile errors):** install **Python 3.12**, remove `apps/api/.venv`, create the venv again with that interpreter (`py -3.12 -m venv .venv` on Windows if the launcher is available).

More scripts: root [`README.md`](../../README.md) (e.g. `pnpm dev:all`, `pnpm docker:stop:app`).
