# CURRENT state

**Last updated:** 2026-08-01 (PR #13 merged)

**Branch:** `main` @ `d65fbfc`

**Alembic:** `20260801_0008` on cip / code head

## Done (this session)

- **PR #13 merged** → `d65fbfc` — CI alembic fresh-upgrade (idempotent `0002`–`0008`, tip assert `0008`) + web vitest fixes
  - Proven on CI: Alembic migrate + API + web vitest **green**
  - E2e still red on main CI (pre-existing: Next proxy `ECONNREFUSED :8001` — API not started for Playwright)

## Next

1. Pick next TRIGGER (Warren): delete orphaned CST `bulk-resolve`; **or** next product unit from BACKLOG; **or** CI e2e topology (start API for Playwright / skip e2e until wired).
2. Optional: new feature branch off `main` once next work is chosen.

**Env:** local Windows. API `:8001`, web `:3000`.
