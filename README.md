# Channel Intelligence Platform

Production-oriented foundation for a **channel intelligence and commercial planning** product: ingest messy commercial files, standardize entities, and surface **explainable** recommendations across inventory, buy plans, pricing, promos, competition, roadmap, and budgets.

Monorepo layout:

- `apps/web` — Next.js 15 (App Router), MUI enterprise theme, AG Grid, TanStack Query, Zustand
- `apps/api` — FastAPI, SQLAlchemy 2, Alembic, Celery/Redis hooks, local/S3-ready storage abstraction
- `packages/ui` — shared theme tokens and `AppThemeProvider`
- `packages/types` — shared TypeScript types (nav, roles)
- `infra` — Docker Compose, environment examples
- `docs` — architecture, contracts, [local Windows dev](docs/LOCAL_DEV_WINDOWS.md), [async/broker audit](docs/ASYNC_AND_BROKER_PATHS.md)

## Prerequisites

- **Node 20+** and **pnpm** (`corepack enable` / `npx pnpm@9`) — for the web app and repo scripts
- **Python 3.12.x** — for the API on the host (`pnpm dev:api`); **3.13+ may fail** on `asyncpg` until supported
- **PostgreSQL** — local install for native dev, *or* Postgres in Docker/CI if your environment still allows Compose for **dependencies only**
- **Docker / Docker Compose** — **optional** (full stack or Postgres+Redis-only); **not required** if you use a local Postgres service. See [docs/LOCAL_DEV_WINDOWS.md](docs/LOCAL_DEV_WINDOWS.md) when Docker Desktop is unavailable.

## Quick start (Docker Compose — optional full stack)

From the **repository root**:

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

- Web: [http://localhost:3000](http://localhost:3000)
- API (host port **8010** → container 8000): [http://localhost:8010/docs](http://localhost:8010/docs)

The API container runs **Alembic migrations** on startup. **Demo seed is optional** (`seed.py` — use `--full` only if you want sample facts). To **clear every table** before loading real data:

```bash
pnpm docker:db:wipe
```

More detail: [`infra/docker/README.md`](infra/docker/README.md).

## Quick start (local — recommended for day-to-day coding)

**Fully native (no Docker):** install PostgreSQL locally, create the `cip` database (see `apps/api/.env.example`), run `pnpm local:db:migrate`, then **`pnpm dev:api-web`** (or `pnpm dev:api` and `pnpm dev:web` in two terminals). Step-by-step: **[docs/LOCAL_DEV_WINDOWS.md](docs/LOCAL_DEV_WINDOWS.md)**.

**Hybrid (Postgres + Redis in Docker, app on host):** only if your policy still allows Compose for dependencies.

If you **were** using full Docker (`docker compose up` with `api` / `web`), free host ports **3000** (web) and **8010** (API) before running the app on the host:

```bash
pnpm docker:stop:app
```

Details: [`infra/docker/README.md`](infra/docker/README.md).

### 1. Data services

**Option A — Native Postgres:** install and run PostgreSQL; URLs in `apps/api/.env` (copy from `.env.example`).

**Option B — Docker deps only** (when Compose is allowed):

```bash
pnpm docker:deps
```

Equivalent: `docker compose -f infra/docker/docker-compose.yml up -d postgres redis`

Optional: copy `apps/api/.env.example` to `apps/api/.env` or copy `infra/env.example` for a fuller template. Defaults in `app/core/config.py` point at `localhost:5432` and `localhost:6379`. Local dev contract for this repo is **web :3000** and **API :8001**.

**Background jobs:** Product Master commit normally uses **Celery + Redis** (`pnpm dev:worker` with a broker). If you cannot run Redis, set **`CIP_DEV_CELERY_DISPATCH=in_process_thread`** in `apps/api/.env` (dev-only; see [docs/LOCAL_DEV_WINDOWS.md](docs/LOCAL_DEV_WINDOWS.md)).

### 2. API (one terminal)

Use a **3.12** interpreter (see `apps/api/.python-version`). On Windows, if `python --version` is not 3.12, try `py -3.12` after installing 3.12 from [python.org](https://www.python.org/downloads/).

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\activate   # Windows
# macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
```

If `pip install` failed earlier with the wrong Python version, delete the `apps/api/.venv` folder and repeat with 3.12.

Then from **repo root**: `pnpm dev:api` (uses `apps/api/.venv` via `scripts/dev-api.js`, reloads on save, binds **:8001** by default). The script **verifies** that this checkout registers `GET /api/v1/dev/database-wipe`, then **refuses to start** if something on the same port already serves OpenAPI without that path (stale or foreign process). Override only if you must: `CIP_SKIP_API_PORT_PREFLIGHT=1`. Or from `apps/api` with venv active: `uvicorn app.main:app --reload --host 127.0.0.1 --port 8001`.

### 3. Web (second terminal)

From repo root:

```bash
pnpm install
pnpm dev:web
```

**API + web (no Redis):** `pnpm dev:api-web` — API on :8001, web on :3000, **no** Celery worker.

**With Redis:** add **`pnpm dev:worker`** (third terminal, or run it alongside after Redis is up). Use **`pnpm dev:all`** only when you want API + web + worker in one command **and** Redis is running (script prints a reminder).

Optional: clear demo data after migrations — from repo root **`pnpm local:db:wipe`** (native venv), or from `apps/api` with venv active: `python scripts/wipe_database.py`. If you use Docker for Postgres only: **`pnpm docker:db:wipe:run`** (one-off `api` image; needs `pnpm docker:deps`).

Open [http://localhost:3000](http://localhost:3000) (redirects to `/dashboard`).

**Commercial planner — controlled reference data:** `dim_customer` **`OPEN_CHANNEL`** and `dim_distributor` **`UNASSIGNED`** are **global system dimensions** (not tenant-scoped), required for Open Channel sync and intentionally-unassigned distributor sync. They are **not** created from upload tokens.

- **Portable path (all environments):** run **`pnpm local:db:migrate`** / **`alembic upgrade head`** — migration **`20260429_0022`** inserts both rows idempotently.
- **Repair without wiping the DB:** from `apps/api` with venv active: **`python scripts/seed.py --commercial-system-reference-only`**.
- **Default `pnpm local:db:seed` / `pnpm docker:seed`** runs **`scripts/seed.py`** which by default calls **destructive demo seed** (`seed_demo.run` wipes the DB first). That is a dev/demo reset, **not** the production reference-data contract — use migrate or `--commercial-system-reference-only` when you must not wipe.

Plan readiness (`GET .../plans/{id}/readiness`) reports **`system_reference_*_dim_ok`** and admin/setup text if either row is missing.

### Celery worker (optional)

```bash
cd apps/api
celery -A app.worker.celery_app worker -l info
```

Wire `POST /api/v1/imports/jobs/{id}/process` or enqueue `imports.process_job` instead of synchronous processing for large files.

## Scripts

| Command | Description |
|--------|-------------|
| `pnpm local:db:migrate` | `alembic upgrade head` via `apps/api/.venv` (no Docker) |
| `pnpm local:db:wipe` / `pnpm local:db:seed` | Run wipe/seed scripts via venv (no Docker) |
| `pnpm docker:deps` | Postgres + Redis only in Compose (when Docker is available) |
| `pnpm docker:up` / `pnpm docker:up:detached` | Full stack (web **:3000**, API **:8010** → container 8000); see `infra/docker/docker-compose.yml` |
| `pnpm docker:stop:app` | Stop Docker `api`, `worker`, and `web` (frees host **:3000** and **:8010**) |
| `pnpm docker:restart` | `restart` on `api`, `worker`, `web` |
| `pnpm docker:logs` | Follow last 200 lines from `api`, `web`, `worker` |
| `pnpm docker:logs:api` / `:web` / `:worker` | Follow logs for one service |
| `pnpm docker:reseed` | `seed.py --full` inside the running `api` container |
| `pnpm docker:seed` | `seed.py` (catalog-only) inside `api` |
| `pnpm docker:db:wipe` | Wipe application tables via `scripts/wipe_database.py` in `api` |
| `pnpm docker:db:wipe:run` | Wipe DB via one-off API container (hybrid; no long-running `api`) |
| `pnpm docker:e2e` | Playwright e2e (`CIP_E2E_API_URL` defaults to `http://127.0.0.1:8010`) |
| `pnpm dev` | Next dev server |
| `pnpm dev:api` | FastAPI with `--reload` (needs Python venv in `apps/api`) |
| `pnpm dev:api-web` | API + web in parallel (**no** worker — typical without Redis) |
| `pnpm dev:worker` | Celery worker only (**requires Redis**; use with `dev:api-web` or separate terminals) |
| `pnpm dev:all` | API + web + **Celery worker** in parallel (prints notice: **worker needs Redis**; not valid without a broker) |
| `pnpm dev:ports` | Show which processes are listening on :3000, :8001, and stale :8000 |
| `pnpm build` | Build all packages |
| `pnpm test:web` | Vitest (web) |
| `pytest` (in `apps/api`) | Backend tests (requires Python 3.12 venv) |

## Product principles (implemented in code)

- **Explainability**: `RecommendationMixin` on derived entities (`explanation_summary`, `explanation_factors` JSONB, etc.)
- **Messy data**: import pipeline with inferred schema, heuristic mapping, row-level results, mapping queue
- **Human-in-the-loop**: `/admin/mappings`, competition mapping approve/reject
- **Deterministic engines**: `app/services/planning/*`, `app/services/competition/matching.py` (weighted, documented factors)

## Phase status

- **Phase 1** — Monorepo, Docker, DB models + initial migration, seed, app shell, API skeleton, theme, AG Grid wrapper, module routes.
- **Phase 2** — Import jobs, storage, pipeline stages (CSV/XLSX), mapping queue APIs, admin import/mapping UI.

Phases 3–5 are the next iterations (full planning depth, polish, e2e).

## License

Proprietary / internal — adjust as needed.
