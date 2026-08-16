# CURRENT state

**Last updated:** 2026-08-16 (housekeeping: fixture import_job purge + catch-up JSONL marker; confirm HEAD with `git rev-parse`)

**Branch:** `feat/finish-roadmap`

**Last content pin:** `5deadb8` — branched from `origin/main` for finish-roadmap (do not treat a hash in this file as HEAD)

**Alembic (code):** `20260814_0016` (`20260814_0016_customer_term_cover_weeks.py`)

**Alembic on cip:** `20260814_0016` (head) — do not upgrade unless approved

## On this branch

- P0 hygiene (`4effbb5`): `tsc --noEmit` 0; CI lint+typecheck; BACKLOG-070 legacy shim.
- BACKLOG-079 chrome: owning-route PageHeader crumbs/titles from `navPageChrome` (`navConfig`). Did not wrap PvE scorecard or PM-gaps worklist in `MasterDataGridShell`.
- BACKLOG-085 fold: client AG Grid pagination on CST steward / PO gap / PM-gaps worklist.
- **P3-1 U1–U3 VERIFY PASS:** tenant metric overlay + compose evaluator + Settings editor. No migration.
- **CST Article aliases tab:** Opus VERIFY PASS. Compose chrome (`ModuleGridToolbar` + `MasterColumnPickerDialog` + `ModuleDataSection`). Face columns Customer / Article / Sales model / Status. Sales model from `dim_product` join (not stored on alias). Edit is product search-and-pick (`GET /products?q=`). No `MasterDataGridShell`. No Alembic.
- Claude-in-browser catch-up: `scripts/claude_catchup.py` v1.1.0 (`63d05de`). Gitignored `docs/memory/CLAUDE_CATCHUP.md`; marker `docs/memory/claude_catchup_log.jsonl`. Pointer-not-paste for docs/review. Manual only. Not Cursor session tooling. Bare (no `--since`) run 2026-08-16 used last JSONL line as delta floor; deltas populated.
- **cip fixture import_job purge (2026-08-16):** 217 test-fixture jobs deleted in one transaction. Predicate false-positive kept jobs `#276` and `#763` (ACZA Q2 2025 Gaming Lineup **latest** — substring `test` in `latest`). `import_job` remaining 259. Did not delete CST article-alias rows. No migration.

## Last recorded test snapshot

2026-08-16 housekeeping (no `ALLOW_TESTS_ON_DEV_DB`): API **1563 passed / 0 failed / 487 errors / 3 skipped** (all 487 errors = cip write-guard in `pytest_runtest_setup`; 0 non-guard errors). Web vitest **532 passed / 0 failed / 0 skipped**. Do not treat the API suite as green against live `cip`.

## Next

1. P4 Amazon ASIN FLAG on the Article aliases surface. Optional Game W27 after. Skip blocked: Q-003, P6 second company, P5 intel v1, BACKLOG-098 Monday beat, 076/089 unless Warren asks.

**Env:** local Windows. Web `:3000` + API `:8001`. No Docker.
