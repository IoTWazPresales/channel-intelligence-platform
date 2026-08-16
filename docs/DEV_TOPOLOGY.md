# Development and deployment topology

**Purpose:** Which stacks are supported, what breaks in each, and what agents must check
before blaming application code.

**Authoritative current env:** `docs/memory/CURRENT.md` (Warren's machine may differ).

---

## Topology matrix

| Mode | API | Worker | DB | Redis | Use for |
|------|-----|--------|-----|-------|---------|
| **A — Windows native + remote Supabase** | venv :8001 | solo, no beat default, `-Q interactive,batch,celery` | Remote Supabase | localhost | Long Celery soaks / remote parity — **degraded** for queue timeouts |
| **B — Windows + local `cip` (Warren default)** | venv :8001 | solo or `in_process_thread` | localhost `cip` | localhost | **Daily dev** — fast loop, migrations, DSI work (2026-06-22) |
| **C — Docker Compose (cloud / optional local)** | :8010 | prefork Linux, `-Q interactive,batch,celery` | container Postgres | container | **Closest to prod**; use for soak |
| **D — Customer on-prem (target prod)** | customer VPC | prefork, multi-queue | customer Postgres | customer Redis | Production; web may be SaaS → VPN to API |

---

## Failure modes by mode

| Symptom | Likely cause in **A** | Likely cause in **C/D** |
|---------|----------------------|-------------------------|
| Plan compute "timed out in queue" | Solo worker busy with validate/apply/reaper backlog | Worker saturated or wrong queue |
| `inspect returned no workers` | Windows solo — **expected** | Worker down or network partition |
| `ReadOnlySqlTransaction` | Supabase disk / replica routing | Misconfigured read replica |
| Validate 15–45 min | Remote DB latency + row count | Normal at scale; optimize SQL |
| Reaper `marked_failed: 0` always | Inspect unavailable — **no-op** | Inspect works — jobs may be reaped |

---

## Process boundaries (do not merge)

| Component | Runs as | Notes |
|-----------|---------|-------|
| **Next.js web** | Separate Node process | Never run Celery in web |
| **FastAPI** | Separate process | Must not run 19-minute validates synchronously in request path |
| **Celery worker** | Separate process(es) | Batch + interactive should be **queues**, not one solo thread in prod |
| **Celery beat** | Separate process in Docker; **disabled by default** on Windows solo dev | Set `CIP_ENABLE_DEV_BEAT=1` for local reaper; prod uses Docker `beat` service |
| **Postgres** | One primary per tenant | Pooler ≠ same as direct primary for long sync writes |
| **Redis** | One broker per env | Required for broker dispatch |

---

## Agent preflight (worker / queue bugs)

Before changing poll timeouts or reaper logic:

1. Read **`docs/memory/CURRENT.md`** — which mode (A/B/C)?
2. `celery inspect ping` or worker logs — pool mode (`solo` vs `prefork`)?
3. Is a long task already running (`process_job`, `dsi_resolution_plan_apply`)?
4. Is DB remote and under disk/read-only pressure?

If mode **A** and symptom is queue timeout → **scheduling/topology**, not broken compute code.

---

## Recommended defaults

| Activity | Recommended topology |
|----------|---------------------|
| UI / steward UX | **B** (Warren) or A |
| Migrations / alembic | B (`cip`) |
| 100k+ row DSI validate soak | C or D |
| Production | D |
| CI unit tests | B with disposable DB |

---

## Related docs

- `docs/LOCAL_DEV_WINDOWS.md` — Windows native setup
- `infra/docker/README.md` — Compose ports (API **8010** on host)
- `docs/memory/derived/platform_runtime_truth.md`
- `docs/memory/derived/platform_async_and_background_truth.md`

---

## Lineup parse worker restart (BACKLOG-111)

After any commit that changes `lineup_case_parser.py` or month-split allocation, **restart the Celery worker** (`pnpm dev:worker`) before enqueueing parse jobs. A long-lived worker keeps the old module in memory; `CIP_DEV_CELERY_DISPATCH=in_process_thread` loads current API-process code instead. Worker boot logs `celery worker code pin sha=… lineup_case_parser_mtime=…`. Do **not** reintroduce `uniform_half` on the parse path (D-028).
