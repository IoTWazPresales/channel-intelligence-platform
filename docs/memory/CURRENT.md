# CURRENT state

**Last updated:** 2026-08-01 (PR #15 BACKLOG-100)

**Branch:** `feat/cst-orphan-and-api-cip-test` @ tip (PR #15 open)

**Alembic:** `20260801_0008` on cip / code head

## Done (this session)

- **CST:** deleted orphan `POST .../cst-candidates/bulk-resolve` (preview-bypass); steward bulk remains canonical.
- **BACKLOG-100:** API suite green on CI `cip_test` (**1760 passed / 0 failed**); hard merge gate restored (no `continue-on-error`).
  - Disposable smoke DBs + tip migrate; `CIP_DEV_CELERY_DISPATCH=in_process_thread` in CI.
  - Merge gate now: alembic + **API** + web vitest + e2e + production build.

## Next

1. Merge PR #15 when hard-gate CI is green.
2. Fresh branch off `main` for **BACKLOG-099** (live API e2e).

**Env:** local Windows. API `:8001`, web `:3000`.
