# CURRENT state

**Last updated:** 2026-08-01 (CI alembic fresh-upgrade fix)

**Branch:** `fix/ci-alembic-fresh-upgrade` (off `main` @ `2dfe764`)

**Alembic:** `20260801_0008` on cip / code head

## Done (this session)

- **CI alembic fresh-upgrade:** tip-ORM `0001` already creates post-squash objects; made `0002`–`0008` idempotent; CI assert tip → `20260801_0008`. Empty-DB proof `cip_alembic_empty` → PASS (`EMPTY_DB_REPLAY_OK`).

## Next

1. Commit + push `fix/ci-alembic-fresh-upgrade`; open PR; confirm GitHub CI migrate step green.
2. Then: delete orphaned CST `bulk-resolve` **or** next BACKLOG TRIGGER (Warren pick).

**Env:** local Windows. API `:8001`, web `:3000`.

**Known:** Prior main CI red was DuplicateColumn on `0002` + stale tip assert — not PR #12 regress.
