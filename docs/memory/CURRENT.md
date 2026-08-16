# CURRENT state

**Last updated:** 2026-08-16 (CST Article aliases VERIFY PASS on `feat/finish-roadmap`; confirm HEAD with `git rev-parse`)

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

## Last recorded test snapshot

P0 live gates 2026-08-15: lint 0 errors (51 hook warnings); tsc 0; API vs live cip not green (env/data).
P3-1 U3 2026-08-16: overlay API + Settings vitest + default-tenant browser E2E then overlay reverted.
CST aliases 2026-08-16: API `test_cst_article_alias_json.py` **3 passed**; web aliases + page vitest **5 passed**. Browser: `/admin/cst-steward` Article aliases — headers Article/Customer/Sales model/Status; picker Additional columns; Edit dialog Product (sales model / SKU) not product_id. Grid `1 to 25 of 652`.

## Next

1. P4 Amazon ASIN FLAG on the Article aliases surface. Optional Game W27 after. Skip blocked: Q-003, P6 second company, P5 intel v1, BACKLOG-098 Monday beat, 076/089 unless Warren asks.

**Env:** local Windows. Web `:3000` + API `:8001`. No Docker.
