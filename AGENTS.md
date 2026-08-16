# AGENTS.md

## Overview

Channel Intelligence Platform — supply chain intelligence monorepo.

**Before starting any task, read these files in order:**
1. `docs/memory/MEMORY_PALACE.md` — index, read order, conflict rules
2. `docs/memory/CURRENT.md` — authoritative **now**: branch, DB, topology, blockers
3. `CONTEXT.md` — router + changelog (not a history dump)
4. `.cursor/rules/Supply-Chain-Intelligence-Project-Rules.mdc` — architecture,
   domain language, known gotchas, stop conditions
5. `.cursor/rules/engineering-rules.mdc` — general engineering behaviour rules
6. `.cursor/rules/cloud-local-git-handoff.mdc` — when switching between
   **local desktop** and **Cursor cloud**: commit, push, pull via GitHub first

Do not skip this. Context loss is the primary cause of regressions in
AI-assisted development.

**If docs conflict with code or with each other — stop and ask Warren** which
source is correct before implementing. Then update `CURRENT.md`.

**Code is evidence; docs are claims.** `CURRENT.md`, BACKLOG, ROADMAP, and commit
messages saying “done” or “parity” are claims until proven in the **running tree**
(read the section/API, compare to the named canonical). Do not delete backlog or
claim PASS on paper alone. Import/steward UX: see `.cursor/rules/import-parity.mdc`
and `docs/WORKFLOW_DUAL_AGENT.md` confirmation checklist.

**After completing any significant task:** update `docs/memory/CURRENT.md` and
append one line to `CONTEXT.md` changelog. Use `Run cip-context-update` skill.
CURRENT **Branch** is the branch name; confirm HEAD with `git rev-parse`. After
commit, put the new hash on the CONTEXT changelog line if it is still missing.
Deferrals go to `docs/BACKLOG.md` — not chat-only.

**Worker / queue / timeout bugs:** read `docs/DEV_TOPOLOGY.md` before patch
stacking poll budgets or reaper logic.

---

## Fix protocol — find canonical first (no patches)

**Every bug fix, perf fix, or “make X work” task — before writing code.**

The user expects **architecture alignment**, not symptom patches on the wrong
code path. Skipping this protocol is a stop condition.

### 1. Interconnection audit (required first deliverable)

Produce a **path map** in chat before implementation:

| UI / trigger | API route | Celery task | Sync writer | Commit model |
|--------------|-----------|-------------|-------------|--------------|

Steps:

1. Read the importer row in `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` for the
   affected `template_slug`.
2. Grep for **parallel paths** to the same steward action:
   `bulk_*`, `*_apply_sync`, `*_enqueue`, `execute_*`, same page buttons.
3. List **every button on the affected screen** that writes the same entities.
4. Document **commit granularity** (per-row vs per-batch vs set-based SQL).

**Stop rule:** If two paths exist for the same steward action and commit models
differ, assume the **bulk/set-based path is canonical** until proven otherwise.
Do not tune polls, retries, dedupe, or timeouts on the slow path first.

### 2. Does the fix already exist?

- If canonical bulk/sync writer exists → **wire to it** or extend it (minimal
  delta). Do not add a second write mechanism.
- If shipment (or another importer) already solved the same pattern → port that
  pattern; do not reinvent.
- If no canonical path exists → troubleshoot from **facts** (logs, endpoints,
  transaction boundaries), then add **one** new writer at the parity bar
  (set-based chunked `INSERT … ON CONFLICT` where applicable).

### 3. No patches

Do **not** ship symptom-only changes when the root cause is wrong wiring:

- Poll budget / queue grace / client timeout tweaks
- Retry layers on a per-row loop that should be batch
- Dedupe or UI disables that hide duplicate enqueue on a broken path

Those are allowed **only after** the canonical write path is in place, and only
if a measured gap remains.

### 4. First response format

Before code, state:

1. Path map (above)
2. Canonical target (file paths)
3. Why the current path diverges
4. **One** fix direction (wire / extend / replace — not a P0/P1 patch stack)

If the audit cannot be completed, stop and report — do not implement.

---

## Environment Detection

Behaviour differs between local and cloud environments. Detect your environment
before running any service or infrastructure command.

**Local development (Cursor Desktop — Windows/WSL2):**
- Docker is NOT used. Do not run any `docker` or `pnpm docker:*` commands.
- Services run directly via Python venv and Node.
- Postgres and Redis run natively on localhost.
- Detect: `WINDIR` env var is set, or `os.name == 'nt'`, or Docker daemon
  is not accessible via `docker info`.

**Cloud environment (Cursor Cloud agents):**
- Docker IS available and required.
- Services run via Docker Compose.
- Detect: `CURSOR_CLOUD` env var is set, or Docker daemon responds to
  `docker info`.

**If unsure:** run `docker info` before any docker command. If it errors —
you are in local mode. Use direct dev commands instead. Never assume.

---

## Running Services

### Local (no Docker)
pnpm dev:api        → API on :8001 via Python venv
pnpm dev:web        → Web on :3000 via Node
pnpm dev:worker     → Celery worker (requires Redis on :6379)
pnpm dev:api-web    → API + Web together, no Redis/Celery
pnpm dev:all        → API + Web + Worker (requires Redis)

Without Redis: set `CIP_DEV_CELERY_DISPATCH=in_process_thread` in
`apps/api/.env` for synchronous task execution.

### Cloud (Docker)
pnpm docker:up:detached    → Start all services via Docker Compose

Per `.cursor/rules/docker-rebuild-after-stack-edits.mdc`: when changing
anything under `apps/api/`, `apps/web/`, `infra/docker/`, Dockerfiles,
`package.json` scripts affecting compose, or lock files used in images —
run `pnpm docker:up:detached` from repo root.

---

## Runtime Ports

| Service | Port |
|---------|------|
| Web | http://localhost:3000 |
| API (local direct) | http://localhost:8001 |
| API (Docker) | http://localhost:8010 → container :8000 |
| Postgres | localhost:5432, database `cip` |
| Redis | localhost:6379 |

---

## Module Inventory

| Layer | Key Paths |
|-------|-----------|
| **API endpoints** | `apps/api/app/api/v1/endpoints/` |
| **Models** | `apps/api/app/models/` |
| **Services** | `apps/api/app/services/` |
| **Migrations** | `apps/api/alembic/versions/` — head tracked in `docs/memory/CURRENT.md` |
| **Web pages** | `apps/web/src/app/(app)/` |
| **Features** | `apps/web/src/features/` |
| **Shared UI** | `packages/ui/` — MUI theme |
| **Shared types** | `packages/types/` — shared TS types |
| **Infra** | `infra/docker/` — Docker Compose |

---

## Development Environment Setup

**Python:**
- Python 3.12 required — `asyncpg` is incompatible with 3.13+
- Venv lives at `apps/api/.venv`
- Activate: `source apps/api/.venv/bin/activate` (Linux/Mac/WSL)
  or `apps/api/.venv/Scripts/activate` (Windows)

**Node:**
- Node 20+ with pnpm 9
- Run `corepack enable` to activate the correct pnpm version
- Install deps: `pnpm install` from repo root

**Environment variables:**
- Copy `apps/api/.env.example` to `apps/api/.env` and fill in values
- `ESLINT_USE_FLAT_CONFIG=false` required for Next.js + ESLint 9
- `CIP_SKIP_API_PORT_PREFLIGHT=1` to bypass :8001 stale process check
- `CIP_DEV_CELERY_DISPATCH=in_process_thread` when Redis unavailable
- `ALLOW_TESTS_ON_DEV_DB=1` to allow API tests against `cip`

---

## Safe Database Operations

1. **Always verify database identity** before any DB-affecting command.
   `SELECT current_database();` must return `cip`. If it does not — stop.
2. **Check migration state first:** run `alembic current` before generating
   or running any migration.
3. **Never auto-generate migrations** without reviewing the full output.
   Alembic autogenerate can produce destructive DROP operations silently.
4. **Never run `alembic upgrade head`** without explicit user instruction.
5. **Seed scripts are destructive.** `seed.py` (default) wipes all application
   data. Use `--commercial-system-reference-only` for safe reference-only
   seeding.
6. **Tests require opt-in:** `ALLOW_TESTS_ON_DEV_DB=1` must be set before
   running API tests against `cip`.
7. **Migration commands from repo root:** `pnpm local:db:migrate`
8. **Disposable-smoke migrate (BACKLOG-054):** override **both** `DATABASE_URL_SYNC` and
   `DATABASE_URL_SYNC_MIGRATE` to the same non-`cip` database. Alembic hard-fails if the
   migrate URL still points at `cip` while the sync URL points elsewhere, or when
   `CIP_SMOKE_MIGRATE=1` and either URL is unset / still `cip`. Do not block ordinary
   `cip` upgrades when both URLs target `cip`.

---

## Git Staging and Commit Rules

1. **Explicit path staging only.** Use `git add path/to/file` — never
   `git add -A` or `git add .`.
2. **Never commit:** `.env` files, database dumps, log files, `node_modules/`,
   `__pycache__/`, `.venv/`, `.specstory/`.
3. **Never commit `.cursor/rules/` changes** without explicit user approval.
4. **Descriptive commit messages** prefixed with module name:
   `dsi: fix cross-distributor corroboration fallback`.
5. **Pre-push checks:** `pnpm lint` and `pnpm test:web` at minimum.
6. **Never push to main** without explicit instruction from the user.
   Use the words "promote to main" or "merge to main" — nothing else
   authorises a main push.
7. **A committed unit must work from a fresh checkout.** No uncommitted
   dependencies allowed.

---

## Running Tests

**Frontend:**
pnpm test:web                    # Vitest — from repo root
pnpm --filter @cip/web test      # Scoped to web package

**API:**
cd apps/api
source .venv/bin/activate
ALLOW_TESTS_ON_DEV_DB=1 pytest   # Full suite against cip
pnpm test:api                    # From repo root

**Lint:**
pnpm lint                        # All packages
pnpm --filter @cip/web lint      # Web only

---

## Smoke verification (UI)

**Browser automation only.** Prove shipped UI/workflows in Playwright / browser MCP
against the live web app. Do **not** treat `curl`, Invoke-RestMethod, or one-shot
backend/service scripts as smoke proof. See `.cursor/rules/smoke-via-browser.mdc`.
Unit/pytest and SQL path validation remain for logic and SQL — they are not UI smoke.

## Working Safely Without Breaking Existing Features

1. **Read before editing.** Always read the full relevant file before making
   changes. Never assume a file does what its name suggests — verify.
2. **No speculative refactors.** Do not reorganise or rename working code
   unless explicitly asked.
3. **Preserve existing imports and exports.** New features must not change
   the public API of existing working modules.
4. **Make targeted changes.** Understand exactly what you are changing and
   why. Prefer surgical edits over broad rewrites.
5. **Test what you changed.** Run focused tests first, broader tests second.
6. **Handle missing tables gracefully.** Endpoints depending on optional
   fact tables must return `data_unavailable: true` — not 500 errors.
7. **Never weaken validation rules** without explaining the business impact.
8. **Report unrelated failures separately.** Do not chase them or broaden
   scope to fix them.
9. **If the same failure persists after two attempts — stop and report.**
   State what failed, what was tried, likely root cause, safest next options.

---

## Common Error Fixes

| Error | Likely cause | Fix |
|-------|-------------|-----|
| `MissingGreenlet` | Lazy-loading a relationship in async context | Add `joinedload()` for the relationship in the endpoint |
| `CircularImport` in DSI | `dsi_shipment_corroboration` ↔ `distributor_sales_inventory` | Use lazy imports inside function bodies in corroboration module |
| `numpy.bool_` rejection | PM upsert producing numpy scalar types | Cast to Python native `bool()` before persistence |
| Port :8001 in use | Stale API process | Set `CIP_SKIP_API_PORT_PREFLIGHT=1` or kill the process |
| ESLint config error | ESLint 9 + Next.js | Set `ESLINT_USE_FLAT_CONFIG=false` |
| Migration `down_revision` mismatch | Wrong base revision | Run `alembic current` and set `down_revision` correctly |
| Tests writing to `cip` | Missing env flag | Set `ALLOW_TESTS_ON_DEV_DB=1` |
| `asyncpg` build failure | Python 3.13+ | Switch to Python 3.12.x |

---

## When Something Goes Wrong

- **Service won't start** → check port conflicts, venv activation, env vars
- **Migration errors** → run `alembic current`, check `down_revision` chain,
  never force-run against `cip`
- **Test failures on unrelated tests** → report separately, do not broaden
  scope
- **Same failure after two attempts** → stop, report, wait for instruction
- **Docker unavailable in local env** → expected, use direct dev commands
- **Redis unavailable** → set `CIP_DEV_CELERY_DISPATCH=in_process_thread`

---

## Key References

| File | Purpose |
|------|---------|
| `docs/memory/MEMORY_PALACE.md` | Memory index — read order, conflict rules, maintenance |
| `docs/memory/CURRENT.md` | Authoritative current state (short) |
| `CONTEXT.md` | Router + session changelog |
| `docs/DEV_TOPOLOGY.md` | Dev/prod topology matrix and failure modes |
| `docs/BACKLOG.md` | Deferred work with TRIGGER only |
| `.cursor/rules/Supply-Chain-Intelligence-Project-Rules.mdc` | Project architecture, domain language, patterns, gotchas |
| `.cursor/rules/engineering-rules.mdc` | General engineering behaviour rules |
| `docs/COMMERCIAL_PLANNER_AUDIT.md` | Commercial planner gap analysis |
| `README.md` | Full setup instructions |
| `infra/docker/README.md` | Docker Compose details |
