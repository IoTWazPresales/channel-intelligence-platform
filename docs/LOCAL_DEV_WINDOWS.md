# Local development on Windows without Docker Desktop

Broker/Celery surface area for this repo: **[ASYNC_AND_BROKER_PATHS.md](ASYNC_AND_BROKER_PATHS.md)**.

This document is for **local development only**. Production deployment patterns (containers, managed Postgres/Redis, separate workers) are unchanged unless your platform team adopts different hosting.

Company policy may forbid **Docker Desktop** while still allowing **native** installs. This repo supports a **fully native** stack on Windows:

| Layer | Native approach |
|--------|------------------|
| Web | `pnpm dev:web` (Next.js on the host) |
| API | `pnpm dev:api` (FastAPI in `apps/api/.venv`) |
| API + web (no worker) | **`pnpm dev:api-web`** (one terminal) |
| PostgreSQL | Local install (Windows service or manual `postgres`); create DB/user matching `.env` |
| Redis | Optional: local [Redis for Windows](https://redis.io/docs/latest/operate/oss_and_stack/install/install-redis/install-redis-on-windows/) / Memurai / WSL `redis-server` **if approved** |
| Celery worker | Optional: `pnpm dev:worker` when Redis is available |

**Docker Compose files under `infra/docker/` are not removed.** They remain the reference for full-stack parity and for CI or teammates who still use containerized dependencies. This guide only adds a **supported path that does not require Docker Desktop**.

---

## Required software (native path)

1. **Node.js 20+** and **pnpm 9** (see root `README.md`).
2. **Python 3.12.x** — create `apps/api/.venv` and `pip install -r requirements.txt`.
3. **PostgreSQL 16** (or compatible) listening on **localhost:5432** with a database and role matching your URLs (defaults below assume user/password/db **`cip`**).

---

## One-time: PostgreSQL

1. Install PostgreSQL for Windows from your approved source.
2. Create role and database (example matches `apps/api/.env.example` defaults):

```sql
CREATE USER cip WITH PASSWORD 'cip';
CREATE DATABASE cip OWNER cip;
```

3. Copy `apps/api/.env.example` → `apps/api/.env` and adjust `DATABASE_URL` / `DATABASE_URL_SYNC` if you use different credentials.

4. Run migrations from repo root:

```powershell
pnpm local:db:migrate
```

5. Create upload directory once: `apps/api/storage/uploads` (or set `LOCAL_STORAGE_PATH` in `.env`).

---

## Recommended startup order

1. PostgreSQL running and migrated (`pnpm local:db:migrate` after `.env` is correct).  
2. (Optional) Redis if you use **`pnpm dev:worker`** or default Product Master commit dispatch.  
3. **`pnpm dev:api-web`** (API + web, no worker), **or** two steps: `pnpm dev:api` then `pnpm dev:web`.  
4. (Optional) **`pnpm dev:worker`** — **requires Redis**; see [ASYNC_AND_BROKER_PATHS.md](ASYNC_AND_BROKER_PATHS.md).

**Which script:** **`dev:api-web`** — everyday UI + API without a worker. **`dev:worker`** — when Redis is up and you need broker-backed jobs (e.g. default Product Master commit). **`dev:all`** — same as running all three in parallel; only when Redis is up (stderr notice).

**`pnpm dev:all`** is **not** a valid one-command workflow **without** Redis. Without a worker, use **`dev:api-web`** and set `CIP_DEV_CELERY_DISPATCH=in_process_thread` for PM commit if needed.

## Every day: API + web

From repository root (typical when Redis / worker is not running):

```powershell
pnpm dev:api-web
```

Or two terminals:

```powershell
pnpm dev:api
pnpm dev:web
```

- Web: [http://localhost:3000](http://localhost:3000)
- API: [http://localhost:8000/docs](http://localhost:8000/docs)

If port **3000** or **8000** is taken, use `pnpm dev:ports` and stop the conflicting process.

---

## Redis and Celery (recommended when possible)

**Product Master “Commit”** is implemented as a **background job** that normally uses **Celery + Redis**. With a local broker:

1. Start Redis on **127.0.0.1:6379** (any approved method).
2. In `apps/api/.env`, keep default `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` (see `.env.example`).
3. In a third terminal: `pnpm dev:worker`.

This matches production behavior (separate worker process, broker-backed queue).

---

## Without Redis (explicit dev-only mode)

If you **cannot** run Redis or a worker, set in `apps/api/.env`:

```env
CIP_DEV_CELERY_DISPATCH=in_process_thread
```

Effects:

- **Product Master commit** still returns **202** quickly, but work runs in a **daemon thread inside the API process** instead of Celery.
- A **warning** is logged on each enqueue so the mode is obvious in logs.
- **Not for production** — no process isolation, reload/kill stops the thread, and load is not offloaded.

Other code paths that assume Redis (caching, future tasks) may still require a broker; this setting only changes **how Product Master commit is dispatched** after `try_enqueue_pm_commit_sync`.

---

## Database utilities without Docker

From repo root (uses `apps/api/.venv`):

| Script | Command |
|--------|---------|
| Migrations | `pnpm local:db:migrate` |
| Wipe app tables | `pnpm local:db:wipe` |
| Seed | `pnpm local:db:seed` |

These replace **`pnpm docker:db:wipe`** / **`pnpm docker:db:wipe:run`** when nothing is running in Docker.

---

## End-to-end tests (Playwright)

`pnpm docker:e2e` defaults the API URL to **:8010** (Docker host port). For native API on **8000**:

```powershell
$env:CIP_E2E_API_URL = "http://127.0.0.1:8000"
pnpm test:e2e
```

---

## Features degraded without approved infrastructure

| Missing component | Impact |
|-------------------|--------|
| Redis + worker (and `CIP_DEV_CELERY_DISPATCH` not `in_process_thread`) | Product Master commit enqueue may **503** after DB rollback when `.delay()` cannot reach the broker. |
| Redis + worker (default `broker`) | Full parity with intended async commit. |
| `CIP_DEV_CELERY_DISPATCH=in_process_thread` only | PM commit runs in-process; **no** separate worker scaling; **uvicorn reload** can interrupt a running thread. |
| Docker-based one-liner | You manage Postgres (and optionally Redis) yourself; no `docker compose up` for deps. |

---

## What was not changed

- Application business logic, models, and migrations.
- `infra/docker/docker-compose.yml` and existing `pnpm docker:*` scripts (for environments where Compose is still allowed).

## Manual / tribal knowledge (still required)

- **Python 3.12** for `asyncpg` wheels; wrong version breaks `pip install`.
- **Port hygiene:** `pnpm dev:ports` when :3000 / :8000 are busy; Docker app containers must be stopped if they bind those ports.
- **First-time DB:** create role/database to match `DATABASE_URL` (defaults assume user/db `cip`).
- **Upload path:** `apps/api/storage/uploads` (or `LOCAL_STORAGE_PATH`) must exist for uploads.
