# Current state

**Last updated:** 2026-06-23 (DSI customer alias scope + duplicate groups admin; cloud handoff)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/dsi-async-topology` |
| **HEAD (snapshot)** | `7fc8109` — pushed; alias-scope map fix, customer duplicate groups admin, BACKLOG-044 |
| **PR** | None open |
| **Alembic (code)** | `20260609_0049` (`task_run` ledger) |
| **Alembic (DB)** | `20260609_0049` on local `cip` |

---

## Database and environment (Warren local)

| Field | Value |
|-------|--------|
| **Active DB** | **Local PostgreSQL 18.3** — database `cip` @ `127.0.0.1:5432` |
| **Topology** | **B** — Windows native API + worker, local `cip`, Redis on localhost |
| **Cloud handoff** | Push branch → cloud `git pull origin feat/dsi-async-topology`; read this file + `CONTEXT.md` |

---

## Dev topology (this machine)

| Process | Mode |
|---------|------|
| API | `pnpm dev:api` → **:8001** |
| Web | `pnpm dev:web` → **:3000** |
| Worker | `pnpm dev:worker` → Celery solo, `-Q interactive,batch,celery` |
| Docker | **Not used** on Windows desktop |

---

## What is working

- **DSI customer map bulk apply** — shared `dsi_customer_alias_scope.py` (0048 scope, batch dedupe, ON CONFLICT DO NOTHING); fixes Res Q IT UniqueViolation class; tests `test_dsi_bulk_map_customers_scope.py`.
- **Provisional bulk** — refactored to same alias-scope module.
- **Steward UI** — tab counts invalidate with steward queries; no optimistic cache remove on partial resolution-plan apply.
- **Customer duplicate groups** — `GET /api/v1/customers/duplicate-groups` + `/admin/customers/duplicates` (read-only, paginated, FK ref counts); tests pass.
- Phase A (038–043), DSI validate/steward async, local `cip` clone.

---

## In progress / not proven live

- **Job #96 soak** on local `cip` after alias-scope fix (Warren to apply Res Q IT maps + revalidate DSI).
- **Shipment backfill ops** — 2023 ACZA landed-only upload: validate → steward products → apply → re-apply 2026 current job → revalidate DSI (evidence vs fact — see session).
- **Web CI flakes** — pre-existing.

---

## Next (recommended)

1. **Cloud:** `git pull origin feat/dsi-async-topology` on cloud agent workspace.
2. **Warren local:** finish Res Q IT + remaining customer steward maps; shipment 2023 backfill job when ready.
3. **Soak** job #96 compute queue on local `cip`.
4. **BACKLOG-044** shipment steward + resolution intelligence parity (parked); **BACKLOG-033** bitemporal evidence/fact (parked).

---

## Blockers requiring Warren

- Promotion to `main` — explicit instruction only.
- **Do not commit** `.env`, `*.dump`, `.cip-alembic-smoke-pg/`, `celerybeat-schedule.*`.

---

## Key references

| Topic | Doc |
|-------|-----|
| **Roadmap** | `docs/memory/ROADMAP.md` |
| Deferred work | `docs/BACKLOG.md` (incl. BACKLOG-044 shipment parity) |
| Topology | `docs/DEV_TOPOLOGY.md` |
