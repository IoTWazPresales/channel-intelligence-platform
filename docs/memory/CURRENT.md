# CURRENT state

**Last updated:** 2026-08-01 (CI alembic + web vitest fix)

**Branch:** `fix/ci-alembic-fresh-upgrade` (PR #13)

**Alembic:** `20260801_0008` on cip / code head

## Done (this session)

- **CI alembic fresh-upgrade:** idempotent `0002`–`0008`; CI assert tip → `20260801_0008`; empty-DB PASS.
- **Web vitest CI red:** HTML `readFetchError` leak; `CurrentLineupSection` token-array guard; stale guide/PO chip assertions. Focused 99/99 PASS locally.

## Next

1. Wait for PR #13 CI green → merge.
2. Then: delete orphaned CST `bulk-resolve` **or** next BACKLOG TRIGGER (Warren pick).

**Env:** local Windows. API `:8001`, web `:3000`.
