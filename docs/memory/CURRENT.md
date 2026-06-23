# Current state

**Last updated:** 2026-06-22 (DSI customer sim + provisional dedup + product plan fix; topology **B**)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/dsi-async-topology` |
| **HEAD (snapshot)** | `9f3206f` — Phase A + local DB docs pushed; **2 commits unpushed** (`38b2c9e` provisional dedup, `9f3206f` product plan fix) |
| **PR** | None open — ready to open after soak |
| **Alembic (code)** | `20260609_0049` (`task_run` ledger) |
| **Alembic (DB)** | `20260609_0049` on local `cip` (verified post-restore 2026-06-22) |

---

## Database and environment (Warren local)

| Field | Value |
|-------|--------|
| **Active DB** | **Local PostgreSQL 18.3** — database `cip` @ `127.0.0.1:5432` (`DATABASE_URL` / `DATABASE_URL_SYNC` in `apps/api/.env`) |
| **Topology** | **B** — Windows native API + worker, local `cip`, Redis on localhost (see `docs/DEV_TOPOLOGY.md`) |
| **Clone source** | Supabase EU **read-only** `pg_dump` (2026-06-22); Supabase untouched |
| **Verification anchors** | `dim_product` **18,158** · `alembic_version` **20260609_0049** · API `GET /api/v1/products?limit=1` → `total: 18158` |
| **Supabase (backup)** | URLs **commented** in `.env` for rollback; MCP 2026-06-21: **740 MB**, `ACTIVE_HEALTHY` |
| **Sync engine** | Local direct primary — BACKLOG-028 pooler rewrite N/A on localhost |
| **Migrate superuser** | `DATABASE_URL_SYNC_MIGRATE` in `.env` (local `postgres` only — not app runtime) |

**Rollback assets (repo root, untracked — do not commit):**

| File | Purpose |
|------|---------|
| `local_cip_backup.dump` | Pre-migration local `cip` (~264 MB) |
| `supabase_public.dump` | Supabase clone source (~47 MB compressed) |
| Commented Supabase lines in `apps/api/.env` | Fast repoint to remote |

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

**Restart API + worker** after `.env` DB repoint (done 2026-06-22).

---

## What is working

- **Local `cip`** — full Supabase `public` clone; row-count parity verified vs remote (7 anchor tables).
- Phase A code complete (038–043) on branch — **soak not yet run** on job #96 scenario.
- **DSI customer sim-name plan tier** (`575276f`) — `customer_sim_name_to_ids` cache + unique match before provisional; **wired + unit-tested**, not proven live.
- **Provisional create-path dedup** (`38b2c9e`) — `pick_provisional_customer_for_reuse` via `normalize_customer_name_for_similarity`; 2+ → log + create; **wired + unit-tested**.
- **Ambiguous product plan** (`9f3206f`) — no crash when `product_ambiguous_eligible` absent; **unit-tested**.
- DSI validate/steward async paths; shipment/PM imports per capability contract.
- `task_run` ledger dual-write at dispatch.

---

## In progress / not proven live

- **Job #96 soak** — verify compute no longer false-queue-timeouts on **local `cip`** after worker restart.
- **Web CI flakes** — `api.test.ts`, `wipeAvailability.test.ts`, `DsiCandidateStewardPanel` timeout (pre-existing; separate from Phase A).
- **Import wizard modularization** — BACKLOG-004 Phase 3 not started.

---

## Next (recommended)

1. **`git push`** — publish `38b2c9e` + `9f3206f` to `origin/feat/dsi-async-topology`.
2. **Soak:** restart `pnpm dev:worker`, re-run DSI historical validate + Customers tab compute (job #96 class) on **local `cip`**.
3. **Open PR** from `feat/dsi-async-topology` when soak passes.
4. **BACKLOG-001** shipment steward workspace (Phase C) per [`docs/memory/ROADMAP.md`](ROADMAP.md).

---

## Blockers requiring Warren

- Promotion to `main` — only on explicit "promote to main" / "merge to main".
- `.cursor/rules/` changes — explicit approval.
- **Do not commit** `apps/api/.env`, `*.dump`, or `pg_restore*.log`.

---

## Key references

| Topic | Doc |
|-------|-----|
| **Roadmap** | `docs/memory/ROADMAP.md` |
| Topology matrix | `docs/DEV_TOPOLOGY.md` |
| Windows local setup | `docs/LOCAL_DEV_WINDOWS.md` |
| Async / Celery | `docs/memory/derived/platform_async_and_background_truth.md` |
| Deferred work | `docs/BACKLOG.md` |
