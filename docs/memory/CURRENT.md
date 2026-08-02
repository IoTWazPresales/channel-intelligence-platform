# CURRENT state

**Last updated:** 2026-08-02 (corpus-safety 2A–2D on main)

**Branch:** `main` (ahead of origin; unpushed corpus-safety commit pending)

**Alembic:** `20260802_0009` on cip / code head · **no migration this unit**

## Done

- **Corpus-safety (2A–2D):** conftest deny-by-default write-capable guard + `_CIP_WRITE_ALLOWLIST` (`test_lineup_case_supersession_delete.py`); steward_audit on lineup case delete paths; import_job **255** → `failed`/`failed` (Celery inspect idle; no other jobs touched); CI action SHAs pinned + tip assert `20260802_0009`. BACKLOG-101 for anonymous actor + bulk apply terminal status.
- Prior: A2-04/05 browser smoke PASS; commercial foundation POD merge.

## Next

1. Rebuild lineup corpus (bulk backfill) — now unblocked by job 255 clear + delete audit + pytest guard.
2. Then A1-09 / B-lane / PR #17 / BACKLOG-101 as chosen.

**Env:** local Windows. Postgres `cip`. Do not run pytest against cip (`ALLOW_TESTS_ON_DEV_DB` unset).
