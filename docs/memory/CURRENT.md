# Current state

**Last updated:** 2026-06-21 (Phase A BACKLOG-038–043 implemented on `feat/dsi-async-topology`)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/dsi-async-topology` |
| **HEAD (snapshot)** | uncommitted Phase A — beat/queue split, defer auto-apply, poll grace, CI test fix |
| **PR** | None open — ready to open after soak |
| **Alembic (code)** | `20260609_0049` (`task_run` ledger) |
| **Alembic (DB via `.env`)** | `20260609_0049` @ `alembic current` 2026-06-21 |

---

## Database and environment (Warren local)

| Field | Value |
|-------|--------|
| **Active DB** | Remote **Supabase EU** via pooler (`DATABASE_URL` / `DATABASE_URL_SYNC` in `apps/api/.env`) |
| **Supabase health** | **740 MB**, `read_only=off`, `ACTIVE_HEALTHY` (2026-06-21 MCP) |
| **Sync engine** | BACKLOG-028 direct-primary rewrite when host resolvable |

---

## Dev topology (this machine)

| Process | Mode |
|---------|------|
| API | `pnpm dev:api` → **:8001** |
| Web | `pnpm dev:web` → **:3000** |
| Worker | `pnpm dev:worker` → Celery **solo**, **no beat by default** on Windows, `-Q interactive,batch,celery` |
| Redis | `localhost:6379` required for broker dispatch |
| Docker | **Not used** on Windows desktop |

**Phase A changes (structural, not poll-only):**

- Beat + reaper **off by default** on Windows solo (`CIP_ENABLE_DEV_BEAT=1` to re-enable).
- **Queue split:** interactive steward tasks vs batch validate/apply/reaper.
- Historical post-validate auto-apply **deferred** on Windows until steward idle (`CIP_DEFER_DSI_POST_VALIDATE_AUTO_APPLY=0` for immediate).
- Compute poll queue grace **scaled** like apply (base 450 attempts + row scaling).

**Restart worker after pull** to pick up queue subscription and beat change.

---

## What is working

- Phase A code complete (038–043) — **soak not yet run** on job #96 scenario.
- DSI validate/steward async paths; shipment/PM imports per capability contract.
- `task_run` ledger dual-write at dispatch.

---

## In progress / not proven live

- **Job #96 soak** — verify compute no longer false-queue-timeouts after worker restart.
- **Web CI flakes** — `api.test.ts`, `wipeAvailability.test.ts`, `DsiCandidateStewardPanel` timeout (pre-existing; separate from Phase A).
- **Import wizard modularization** — BACKLOG-004 Phase 3 not started.

---

## Next (recommended)

1. **Soak:** restart `pnpm dev:worker`, re-run DSI historical validate + Customers tab compute (job #96 class).
2. **Open PR** from `feat/dsi-async-topology` when soak passes.
3. **Phase B/C** per [`docs/memory/ROADMAP.md`](ROADMAP.md) — local `cip` policy, BACKLOG-001 shipment workspace.

---

## Blockers requiring Warren

- Promotion to `main` — only on explicit "promote to main" / "merge to main".
- `.cursor/rules/` changes — explicit approval.

---

## Key references

| Topic | Doc |
|-------|-----|
| **Roadmap** | `docs/memory/ROADMAP.md` |
| Topology matrix | `docs/DEV_TOPOLOGY.md` |
| Async / Celery | `docs/memory/derived/platform_async_and_background_truth.md` |
| Deferred work | `docs/BACKLOG.md` |
