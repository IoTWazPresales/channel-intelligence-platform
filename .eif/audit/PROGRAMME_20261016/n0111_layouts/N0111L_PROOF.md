# N-0111 customer layouts: proof

Node N-0111 (stays N-0111). Branch `feat/ns-2-brief-nav-collapse`. Build run `RUN-20261016-N0111-LAYOUTS`; verification is a different run (`RUN-20261016-N0111-VER4`). Same session, same model: self-verification, not independent. N-0099 does the second look.

## Warren's decision (recorded on the node)
A sell-through upload picks a **reporting customer**, not a source. The picker lists only customers ticked as reporting customers (`customer_report_config.reports_expected`, the list the late/missing slots walk). Every upload loads into the one sell-through table with its standard columns. The only per-customer configuration is the **column layout**: the first upload of an unrecognised layout opens the column-mapping step and the layout is saved for that customer; later uploads match a saved layout by headers; a customer may have several. Test and build sources never appear to users.

## What was built (commit `df0841a4`)
- `20261016_0043`: table `customer_sellthrough_layout` (customer, name, header fingerprint, headers, `field_mapping` header -> standard column, `report_structure_type`, origin, soft-hide flag; unique per customer and header set) and `source_definition.is_hidden`.
- `cst_layouts.py`: reporting customers; header sniffing with the parser's own header detection (a header row the aliases do not know is still found, so the mapping step can list the columns); fingerprint that ignores order, case, blank columns, unit stubs (ZAR, EA) and **period-named columns** (`49-2025`, `027.2026`, `week 14`), so next week's file matches the same layout; match, closest-layout prefill, save; one hidden internal source `cst_customer_upload` that jobs hang on (the customer is carried in `staged_metadata`); `create_customer_upload_jobs`.
- Endpoints: `GET /imports/cst/reporting-customers`, `GET /imports/cst/layouts`, `PATCH /imports/cst/layouts/{id}` (rename, hide), `POST /imports/cst/batch-propose` (with `customer_id`: per-file layout or detected mapping), `POST /imports/cst/batch-jobs` (`customer_id` + `layouts`, no `source_id`). `POST /imports/jobs` for this template answers 409 and names the new upload. Hidden sources are not in `GET /imports/sources`.
- Web: the upload window picks the customer (name only), shows its saved layouts (Rename, Remove), a layout chip per file, and for an unrecognised header set the shared `CanonicalColumnMappingPanel` (reused, not rebuilt) with a required-column gate; the Import Center step is named "Reporting customer" and has no source select.
- **Reuse, not a second mapping system:** customer sell-through had no mapping step. The parser already gave a job's `field_mapping` (header -> standard column) priority over aliases; the step is the shared panel; the only new storage is the layout.

## 2. Migration of the existing sources (cip)
Clone proof first (`N0111L_CLONE_PROOF.md`, clone `cip_n0111l`, dropped): upgrade / downgrade / upgrade with every count equal (CST facts 3,197, units 12,394, on-hand 30,832, superseded 390, jobs 610, sources 43, sell-out rows 35,582); dry run wrote nothing; apply saved 7 layouts and hid 26 sources; second apply changed nothing; downgrade with layouts present kept every fact, job and source. Then `20261016_0043` applied to cip as the migration role (counts unchanged) and the migration run on cip (`current_database()=cip` printed first): layouts created 7, sources hidden 26, second run 0 / 0. cip CST facts, jobs and sources unchanged after the migration.

Before / after (`source_migration_cip.md` has the full table, the mapping of each layout and the After table):

| slug | customer | applied jobs | outcome |
|---|---|---|---|
| takealot_cst_week | Takealot | 2 | layout "Imported layout - ASUS WEEK 31"; source hidden |
| cst_raw_20_takealot_w31 | Takealot | 1 | same header set as that layout; source hidden |
| cst_hist_v2_20 | Takealot | 4 | layout "Imported layout - ASUS WEEK 39" (one extra column, Supplier Stock); source hidden |
| cst_raw_52_evetech_sales | Evetech | 1 | layout "Imported layout - EveX_ASUS_LAPTOPS_Reports_Sales_20260727_20260802"; source hidden |
| cst_hist_v2_52 | Evetech | 3 | same header set; source hidden |
| cst_hist_v2_18 | Computer Mania | 4 | layout "Imported layout - Computer Mania week 40" (mtd_delta); source hidden |
| cst_hist_v2_15 | Makro | 4 | layout "Imported layout - Asus Dispo WK1" (pivoted; the four weekly files share it); source hidden |
| cst_hist_v2_57 | Game | 4 | layouts "Imported layout - ASUS Week 40" and "Imported layout - Asus Sales W27" (wide-week); source hidden |
| cst_unit_e_verify_smoke, cst_p4_* (7), cst_soak_52, cst_soak_57, cst_raw_57_game_w27_wide-week, cst_hist_20, cst_hist_52, cst_hist_18, cst_hist_15, cst_hist_57, cst_hist_12, cst_hist_11 | various | 0 | hidden (no applied jobs) |

Mapping is kept exactly as the last job that loaded that header set used it; structure (flat / mtd_delta / pivoted) is the structure that job loaded with. Amazon (299) has no layout: its only source (`cst_p4_amazon`, customer 26 merged into 299) has validated jobs only, so the first Amazon upload opens the mapping step.

**For Warren:** the brief lists `hist` and `RAW` as build/test sources, but `cst_hist_v2_*` and `cst_raw_*` hold the real loaded files (real customers, real fact rows). Their applied jobs are what the 7 layouts came from; all 26 sources are hidden either way. Layout names are placeholders; rename them in the upload window.

## 3. Distributor (Pinnacle): "pick the distributor, layout remembered" - gaps, nothing built
Read-only (`probe_dsi_cip.txt`): one source, "Distributor inventory feed" (id 12), holds the memory (`column_mapping_memory.by_header_norm`, 29 headers) for every distributor.
1. The distributor is detected and confirmed per file after upload, not picked first.
2. The remembered layout is one pool by header, shared by all distributors, not per distributor: one header meaning two things would collide.
3. The wizard still shows "Data provider / feed" with that one source.
4. Layouts are not named, listed, renamed or removable (the layout-coalesce tabs inside a batch exist).
Recorded as BACKLOG-213 with its trigger.

## 4. Proof on cip_test (`test_cst_layouts_db.py`, one rolled-back transaction)
- An unknown-layout file (Afrikaans-style headers no alias knows): the upload says "not mapped yet", saves nothing, makes no job.
- With the mapping from the mapping step: layout "Weekly report" saved for the customer, the job carries the mapping and the customer, the file loads (2 rows, 8 units, 50 on-hand).
- A second file with the same headers: matched to "Weekly report" by itself, no mapping needed, the job's `field_mapping` equals the first job's, loads (4 rows, 18 units, 100 on-hand), still one layout.
- Uploading the first file again: totals unchanged (4 rows, 18 units, 100 on-hand), still one layout.
- Another header set (history file with one more column): another layout, started from the closest one (the four known columns arrive mapped); a name clash gets "(2)".
- A mapping without the product column is refused and saves nothing; a customer not ticked cannot be uploaded for; a hidden layout is not matched; the internal source is hidden and not offered; the migration keeps applied mappings as layouts, hides every source, deletes nothing, and a second run changes nothing; the layout list for the next upload is the migrated one.
- The picker excludes unticked and merged customers; the customers the slot job opens slots for are inside it (the slot job also needs a key account).

## 5. Tests
- Full API pytest on cip_test: 3068 passed, 21 skipped, 0 failed (`pytest_full.txt`).
- Full web vitest (2 workers): 188 files, 878 passed, 0 failed (`vitest_full.txt`).
- New: `test_cst_layouts.py` (pure, 15), `test_cst_layouts_db.py` (7), `test_cst_layouts_api.py` (3), `CstBulkUploadDialog.test.tsx` (5), a page test for the step (1); the RBAC matrix lists the new PATCH route.
- Web `tsc` exit 0; `next lint` on the changed files: 0 errors (5 existing warnings in `page.tsx`).

## 6. Docs, restart
- `docs/memory/CURRENT.md` "History upload: how to upload": pick the customer -> tick Sales-only or Stock-only -> map the columns the first time -> upload sales, then stock. BACKLOG-213.
- Web rebuilt and restarted through `scripts/cip-supervisor-stop.ps1 -Component web|api -Restart`: web build `5a1eUf82TLb0xpzWS8Cvr`; local `/health` 200, `/login` 200, `/api/v1/auth/me` 401, the new `/imports/cst/reporting-customers` 401 without a session.

## Limits
Not rendered (sign-in; the mapping step and window are covered by component tests, no axe run). Same session, not independent. The partial-failure case (some files placed, some not) keeps the window open to show the reason. Pinnacle unchanged.
