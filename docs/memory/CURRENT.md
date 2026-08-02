# CURRENT state

**Last updated:** 2026-08-02 (ROADMAP v3.1 on main)

**Branch:** `main` (docs tip after ROADMAP open-decisions sync)

**Alembic:** `20260801_0008` on cip / code head

## Done (this session)

- **PR #15 merged** — CST orphan `bulk-resolve` deleted; **BACKLOG-100 shipped**.
  - CI API suite hard gate on `cip_test` (1760 passed); merge gate = alembic + API + web vitest + e2e + build.
- **ROADMAP v3.1** — open decisions #1/#2 → resolved (Q-001/Q-002); still open = Q-003 hosting, Q-004 CST formats; branch/location = deferred by design.

## Next

1. Fresh `feat/` branch off `main` for **BACKLOG-099** (live API e2e in CI) **or** Warren pick other TRIGGER.
2. Roadmap residual: P0 BACKLOG-087 · P2 hosting (Q-003) · P3 BACKLOG-098 · B-lane soak · P4–P6 · Lane X.

**Env:** local Windows. API `:8001`, web `:3000`.
