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
| Redis | Optional: local [Redis for Windows](https://redis.io/docs/latest/operate/oss_and_stack/install/install-redis/install-redis-on-windows/) / Memurai / WSL `redis-server` **if approved** — must accept TCP on the host/port in `CELERY_BROKER_URL` (default **127.0.0.1:6379**) |
| Celery worker | Optional: `pnpm dev:worker` when Redis is available (script **preflights** broker TCP and uses **`--pool=solo` on Windows** unless you set `CIP_CELERY_WORKER_POOL`) |

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

### Migrations: `must be owner of table dim_customer` (or similar)

PostgreSQL only allows the **table owner** (or a superuser) to run `ALTER TABLE ... ADD COLUMN`. The Customers Phase 1 revision `20260426_0012` alters `dim_customer`, so Alembic must connect as that owner.

The initial revision `20260412_0001` uses `Base.metadata.create_all()`, which assigns **ownership of every created table to the database role used for that migration**. If that first upgrade was run as **`postgres`** (or you restored a dump owned by another role), later runs of `pnpm local:db:migrate` as **`cip`** can fail with `InsufficientPrivilege: must be owner of table dim_customer`.

**Diagnose (any SQL client, connected to database `cip`):**

```sql
SELECT tablename, tableowner
FROM pg_tables
WHERE schemaname = 'public' AND tablename = 'dim_customer';
```

**Fix (pick one; lowest blast radius first):**

1. **Reassign ownership to `cip`** (recommended when objects should be owned by the app role). Connect as a superuser (often `postgres`) to database `cip`, then:

   ```sql
   ALTER TABLE public.dim_customer OWNER TO cip;
   ```

   If many tables are owned by the wrong role, broader repair is appropriate for **local dev only**:

   ```sql
   REASSIGN OWNED BY postgres TO cip;
   ```

   (Replace `postgres` with whatever `tableowner` shows from the diagnostic query.)

2. **Run migrations as a superuser only for Alembic** (optional; avoids changing table ownership). In `apps/api/.env`, set `DATABASE_URL_SYNC_MIGRATE` to a superuser sync URL (see `apps/api/.env.example`), run `pnpm local:db:migrate`, then **remove** `DATABASE_URL_SYNC_MIGRATE` so the API continues to use `DATABASE_URL_SYNC` as `cip`.

**Do not** stamp Alembic to head without applying revisions, or otherwise bypass migration history.

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
- API: [http://localhost:8001/docs](http://localhost:8001/docs)

If port **3000** or **8001** is taken, use `pnpm dev:ports` and stop the conflicting process.

---

## Redis and Celery (recommended when possible)

**Product Master “Commit”** is implemented as a **background job** that normally uses **Celery + Redis**. With a local broker:

1. Start Redis on **127.0.0.1:6379** (any approved method).
2. In `apps/api/.env`, keep default `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` (see `.env.example`).
3. In a third terminal: `pnpm dev:worker`.

This matches production behavior (separate worker process, broker-backed queue).

### Reproducible no-Docker broker path (Windows)

Docker is **not** required. For **real** Product Master commit (default `CIP_DEV_CELERY_DISPATCH=broker`), you need **Redis listening where `CELERY_BROKER_URL` points** (defaults use logical DB **1** on the same TCP port **6379** as DB 0/2 — one `redis-server` process covers all).

1. **Install / start Redis** using an approved option (examples only — follow your IT policy):
   - **Memurai** or **Redis for Windows** on the host, **or**
   - **WSL** (e.g. Ubuntu): `sudo apt install redis-server` then start `redis-server` so it listens on `0.0.0.0:6379` or `127.0.0.1:6379` (WSL2 usually forwards **Windows `localhost:6379`** to the instance — verify with `Test-NetConnection 127.0.0.1 -Port 6379` from PowerShell or `redis-cli -h 127.0.0.1 ping`).
2. **Verify broker TCP** before the worker: `pnpm dev:worker` runs a short TCP preflight to the host/port parsed from `CELERY_BROKER_URL`. If Redis is down, the script **exits with a clear error** (no silent hang in Celery).
3. **Three processes** (separate terminals from repo root):
   - `pnpm dev:api`
   - `pnpm dev:web`
   - `pnpm dev:worker`
4. **Windows Celery pool:** `scripts/dev-worker.js` passes **`--pool=solo`** on Windows by default (prefork is unreliable there). To use another pool: set `CIP_CELERY_WORKER_POOL` (e.g. `prefork` on macOS/Linux overrides are rarely needed). **Do not** change production Linux workers unless you know your deployment needs a non-default pool.

**Escape hatches (explicit only):**

| Variable | Purpose |
|----------|---------|
| `CIP_SKIP_REDIS_PREFLIGHT=1` | Skip the TCP check (CI / exotic networking only — **not** normal dev). |
| `CIP_REDIS_PREFLIGHT_TIMEOUT_MS` | Preflight timeout in ms (default `3000`). |

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
| Migrations | `pnpm local:db:migrate` (Alembic uses `DATABASE_URL_SYNC_MIGRATE` when set, else `DATABASE_URL_SYNC`) |
| Wipe app tables | `pnpm local:db:wipe` |
| Seed | `pnpm local:db:seed` |

These replace **`pnpm docker:db:wipe`** / **`pnpm docker:db:wipe:run`** when nothing is running in Docker.

---

## End-to-end tests (Playwright)

`pnpm docker:e2e` defaults the API URL to **:8010** (Docker host port). For native API on **8001**:

```powershell
$env:CIP_E2E_API_URL = "http://127.0.0.1:8001"
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
- **Port hygiene:** `pnpm dev:ports` when :3000 / :8001 are busy (and also check stale :8000 listeners); Docker app containers must be stopped if they bind those ports.
- **First-time DB:** create role/database to match `DATABASE_URL` (defaults assume user/db `cip`).
- **Upload path:** `apps/api/storage/uploads` (or `LOCAL_STORAGE_PATH`) must exist for uploads.
