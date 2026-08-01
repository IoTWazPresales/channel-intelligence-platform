# CURRENT state

**Last updated:** 2026-08-01 (CI e2e topology)

**Branch:** `fix/ci-e2e-topology` (off `main` @ `52fbd3e`)

**Alembic:** `20260801_0008` on cip / code head

## Done (this session)

- **CI e2e topology:** stale getting-started/navigation assertions; live wipe/products gated (`CIP_E2E_*`); proxy disabled when no live API; BACKLOG-099.
- **CLI Playwright (CI=true):** 3 passed / 2 skipped.
- **Browser smoke:** `/getting-started` shows session-auth copy + Admin → Import Center; `/admin/imports` shows **Data & imports**.

## Next

1. Commit + push + open PR; merge when CI green.
2. Then: orphaned CST `bulk-resolve` **or** BACKLOG TRIGGER (Warren pick).

**Env:** local Windows. API `:8001`, web `:3000`.
