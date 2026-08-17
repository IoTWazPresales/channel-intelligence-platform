# CURRENT state

**Last updated:** 2026-08-17 (P4 Amazon SKU-twin propose on Article aliases)

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
- Claude-in-browser catch-up: `scripts/claude_catchup.py` reads `.tmp/*junit*` for [6] (`93fee09`). Fixture filename regex no longer matches `dsi_week32.xlsx` (`0f2fc10`).
- **Hygiene batch 2026-08-16:** 054/104/111/101/047/071/057/058; 086+084 closed. Fixture import_job purge 217 kept `#276`/`#763`.
- **P4 Amazon ASIN (2026-08-17):** Job 918 **30 facts** (23 prior + 7 SKU-twin confirms). 7 Amazon aliases 675–681 confirmed via SCM sales model (not auto-confirm-unique). Leftover 21 unresolved: 19 networking not in PM + 2 notebooks with no unique sales model (`B0CND7JMYP`, `B0CZ97VQ4H`). No Alembic. No dim_product create.

## Last recorded test snapshot

2026-08-16 housekeeping (no `ALLOW_TESTS_ON_DEV_DB`): API **1563 passed / 0 failed / 487 errors / 3 skipped** (all 487 errors = cip write-guard in `pytest_runtest_setup`; 0 non-guard errors). Web vitest **532 passed / 0 failed / 0 skipped**. Do not treat the API suite as green against live `cip`.

## Next

1. Optional leftover: 19 Amazon networking ASINs (no PM sales model) and 2 notebooks without a unique sales model (`B0CND7JMYP` Vivobook GO 7520U; `B0CZ97VQ4H` ExpertBook B5402FVA — two I71610 SKUs). Game W27. Skip blocked unless Warren asks.

**Env:** local Windows. Web `:3000` + API `:8001`. No Docker.
