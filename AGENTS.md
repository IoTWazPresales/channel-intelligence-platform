# AGENTS.md

## Overview

Channel Intelligence Platform — supply chain intelligence monorepo. See `CONTEXT.md` for full handoff context and `.cursor/rules/Supply-Chain-Intelligence-Project-Rules.mdc` for detailed project rules, architecture patterns, domain language, and known gotchas.

## Module Inventory

| Layer | Key Paths |
|-------|-----------|
| **API** | `apps/api/app/api/v1/endpoints/` — FastAPI route files per module |
| **Models** | `apps/api/app/models/` — SQLAlchemy 2 async models |
| **Services** | `apps/api/app/services/` — Business logic, calculators, import pipelines |
| **Migrations** | `apps/api/alembic/versions/` — 38 migrations, head = `20260517_0038` |
| **Web pages** | `apps/web/src/app/(app)/` — Next.js 15 App Router pages |
| **Features** | `apps/web/src/features/` — Extracted React components per domain |
| **Shared UI** | `packages/ui/` — MUI theme, `packages/types/` — shared TS types |
| **Infra** | `infra/docker/` — Docker Compose (Postgres 16, Redis 7) |

## Safe Database Operations

1. **Always verify database identity** before any DB-affecting command: `SELECT current_database();` must return `cip`.
2. **Check migration state first:** `alembic current` before generating or running migrations.
3. **Never auto-generate migrations** without reviewing the output. Alembic autogenerate can produce destructive operations.
4. **Never run `alembic upgrade head` in production** without explicit instruction.
5. **Seed scripts are destructive.** `seed.py` (default) wipes application data. Use `--commercial-system-reference-only` for safe reference-data-only seeding.
6. **Tests require opt-in:** Set `ALLOW_TESTS_ON_DEV_DB=1` before running API tests against `cip`.

## Git Staging and Commit Rules

1. **Explicit path staging only.** Use `git add path/to/file` — never `git add -A` or `git add .`.
2. **Never commit:** `.env` files, database dumps, log files, `node_modules/`, `__pycache__/`, `.venv/`.
3. **Never commit `.cursor/rules/` changes** without explicit user approval.
4. **Descriptive commit messages** prefixed with module name: `commercial-planner: add line override UI`.
5. **Pre-push checks:** `pnpm lint` and `pnpm test:web` at minimum.

## Error Handling Without Breaking Working Features

1. **Read before editing.** Always read the full file (or relevant section) before making changes.
2. **No speculative refactors.** Do not reorganize or rename working code unless explicitly asked.
3. **Preserve existing imports and exports.** Adding a new feature should not change the public API of existing modules.
4. **Test your changes.** Run `pnpm test:web` for frontend changes. For API changes, run tests from `apps/api/` with venv active.
5. **If in doubt, add — don't modify.** New endpoints, new components, new utility functions are safer than modifying existing ones.
6. **Handle missing tables gracefully.** API endpoints that depend on optional fact tables should return `data_unavailable: true` rather than 500 errors.
7. **Never weaken validation rules** without explaining the business/data impact.

## Cursor Cloud specific instructions

### Development environment

- **Python 3.12** is required for the API (`asyncpg` incompatible with 3.13+). The venv lives at `apps/api/.venv`.
- **Node 20+** with **pnpm 9** for the web app. `corepack enable` activates the correct pnpm version.
- **ESLint** needs `ESLINT_USE_FLAT_CONFIG=false` due to Next.js + ESLint 9 interaction.
- **API port preflight:** `dev-api.js` checks for stale processes on :8001. Set `CIP_SKIP_API_PORT_PREFLIGHT=1` to bypass.

### Running services

- `pnpm dev:api-web` starts API (:8001) + Web (:3000) without Redis/Celery.
- `pnpm dev:all` adds the Celery worker but **requires Redis on :6379**.
- Without Redis, set `CIP_DEV_CELERY_DISPATCH=in_process_thread` in `apps/api/.env` for synchronous task execution.

### Running tests

- **Frontend:** `pnpm test:web` (Vitest)
- **API:** `cd apps/api && source .venv/bin/activate && ALLOW_TESTS_ON_DEV_DB=1 pytest` (or `pnpm test:api` from root)
- **Lint:** `pnpm lint` (all packages) or `pnpm --filter @cip/web lint`

### Key references

- Full setup instructions: `README.md`
- Project rules and patterns: `.cursor/rules/Supply-Chain-Intelligence-Project-Rules.mdc`
- Handoff context: `CONTEXT.md`
- Commercial planner audit: `docs/COMMERCIAL_PLANNER_AUDIT.md`
- Docker details: `infra/docker/README.md`

### Docker rule

Per `.cursor/rules/docker-rebuild-after-stack-edits.mdc`: when changing anything under `apps/api/`, `apps/web/`, `infra/docker/`, Dockerfiles, `package.json` scripts affecting compose, or lock files used in images — run `pnpm docker:up:detached` from repo root. If Docker is unavailable, say so explicitly.
