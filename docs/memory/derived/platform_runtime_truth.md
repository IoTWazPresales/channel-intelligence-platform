# Platform Runtime Truth

**Last verified:** 2026-06-21  
**Current env snapshot:** `docs/memory/CURRENT.md`  
**Topology matrix:** `docs/DEV_TOPOLOGY.md`

---

## Local development modes

### Windows native (no Docker) — Warren desktop default

| Service | Command | Port / notes |
|---------|---------|----------------|
| API | `pnpm dev:api` | **8001** (`dev-api.js`; may set `CIP_SKIP_API_PORT_PREFLIGHT=1`) |
| Web | `pnpm dev:web` | **3000** |
| Worker | `pnpm dev:worker` | Celery **solo** pool; **sibling beat** on Windows |
| Redis | OS install / Memurai / WSL | **6379** on host for broker |
| Postgres | Local **or** remote Supabase | See `apps/api/.env` — not always `cip` |

See `docs/LOCAL_DEV_WINDOWS.md`.

### Docker Compose (cloud agents / optional)

| Service | Host port |
|---------|-----------|
| Web | 3000 |
| API | **8010** → container 8000 |
| Postgres | 5432 (`cip` / `cip`) |
| Redis | 6379 |
| worker | prefork (Linux image) |
| beat | separate service |

See `infra/docker/README.md`.

---

## Ports (authoritative for agents)

| Service | Local native | Docker |
|---------|--------------|--------|
| Web | 3000 | 3000 |
| API | **8001** | **8010** |
| Postgres | 5432 | 5432 |
| Redis | 6379 | 6379 |

Do not assume API is on 8000 on Windows dev — **8001** is the stabilized native port.

---

## Worker / Redis

- Broker dispatch requires Redis unless `CIP_DEV_CELERY_DISPATCH=in_process_thread`.
- Windows: `dev-worker.js` defaults **`--pool=solo`** (`CIP_CELERY_WORKER_POOL` to override).
- Solo = one concurrent task — validates, applies, compute, and reaper tasks **serialize**.

---

## Database

- Async API: typically `NullPool` + transaction pooler `:6543` on Supabase.
- Sync worker: `SessionLocal` / `database_url_sync` — long jobs; BACKLOG-028 direct primary rewrite.
- **Always** `SELECT current_database()` before destructive ops; project rules expect `cip` for local migrate tests.

---

## Auth (dev)

- Stub headers: `X-User-Id`, `X-User-Role` (web → API).

---

## Operational caveats

- **API `--reload`** during 45+ min validates — avoid; use stable uvicorn for long soaks.
- Mixed Docker + native on same ports causes `EADDRINUSE` / wrong DB.
- Remote Supabase + Windows solo worker = **degraded** for steward async (see topology doc).

---

## Related

- `docs/memory/derived/platform_async_and_background_truth.md`
- `docs/memory/MEMORY_PALACE.md`
