# Current state

**Last updated:** 2026-06-21 (PR #5 merged; new branch for DSI async topology)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/dsi-async-topology` (from `main` @ `0540435`) |
| **HEAD (snapshot)** | `0540435` — merge commit for PR #5 (DSI steward perf, close-out Units 1–4, memory palace) |
| **PR** | **#5 merged** 2026-06-21 — no open PR on current branch |
| **Alembic (code)** | `20260609_0049` (`task_run` ledger) — **confirm** with `alembic current` before any migration work |
| **Alembic (Supabase)** | `20260608_0048` applied (alias partial-uniques) per Jun 16 soak |

---

## Database and environment (Warren local)

| Field | Value |
|-------|--------|
| **Active DB** | Remote **Supabase EU** via pooler (`DATABASE_URL` / `DATABASE_URL_SYNC` in `apps/api/.env`) — not local `cip` unless URLs swapped |
| **Risk** | ~~Disk quota / read-only~~ **Verified 2026-06-21 via Supabase MCP:** project `ACTIVE_HEALTHY`, DB **740 MB**, `default_transaction_read_only=off` |
| **Sync engine** | BACKLOG-028: pooler → direct primary rewrite when host resolvable; Windows may keep pooler if `db.*.supabase.co` fails DNS |

---

## Dev topology (this machine)

| Process | Mode |
|---------|------|
| API | `pnpm dev:api` → **:8001** |
| Web | `pnpm dev:web` → **:3000** |
| Worker | `pnpm dev:worker` → Celery **`--pool=solo`** on Windows + **sibling beat** |
| Redis | `localhost:6379` required for broker dispatch |
| Docker | **Not used** on Windows desktop (see `docs/DEV_TOPOLOGY.md`) |

**Known degraded dev constraints:**

- Solo worker = **one task at a time** (validate, apply, compute, reaper queue behind each other).
- Celery `inspect()` often returns **no workers** on Windows solo → reaper is **no-op** but still **consumes queue time**.
- DSI plan compute UI queue grace ≈ **120s**; historical post-validate auto-apply can hold worker **4+ min** → false **"timed out while waiting in queue"** even when task later succeeds.

---

## What is working

- DSI validate via Celery `imports.process_job` (large files — tens of minutes on remote DB).
- DSI steward: async plan **compute** + **apply**, bulk orchestrators, tab counts, shared `ImportStewardCandidateWorkspace` (DSI).
- Shipment / PM import paths (see capability contract per `template_slug`).
- Celery beat reaper `imports.reap_stale_running_jobs` (fail-safe when inspect unavailable).
- `task_run` ledger dual-write at dispatch (read path not fully unified with activity feed).

---

## In progress / not proven live

- **Job #96 class:** queue timeout on Customers tab during resolution refresh — scheduling/topology, not broken compute logic (**next branch theme**).
- **CI:** PR #5 merged with **failing** `test` workflow on pre-merge run — triage on `main` or next PR.
- **Import wizard modularization** — `admin/imports/page.tsx` still ~4k lines; BACKLOG-004 Phase 3 not implemented.
- **`db_transient_retry`** — verify which production paths import it (do not assume all commits use it).

---

## Next (recommended) — `feat/dsi-async-topology`

1. **Windows solo dev:** env flag to disable beat/reaper on desktop (reduce queue noise).
2. **Celery:** queue split (interactive steward vs batch validate/apply).
3. **DSI:** defer historical post-validate auto-apply until steward idle; raise compute poll queue grace / queue-aware UI.
4. **Soak:** Linux worker or Docker stack for long validates; keep Supabase for scheduled soaks (disk OK — 740 MB, verified MCP 2026-06-21).

---

## Blockers requiring Warren

- `alembic upgrade` on `cip` or Supabase without explicit approval.
- Promotion to `main` — only on explicit "promote to main" / "merge to main".
- `.cursor/rules/` changes — explicit approval.

---

## Key references

| Topic | Doc |
|-------|-----|
| Memory index | `docs/memory/MEMORY_PALACE.md` |
| Topology matrix | `docs/DEV_TOPOLOGY.md` |
| Async / Celery | `docs/memory/derived/platform_async_and_background_truth.md` |
| Deferred work | `docs/BACKLOG.md` |
| Import parity | `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` |
