# N-0040 implementation: every dim_product.product_line is a sellable BU (D-g)

Implementer: fresh-context subagent, 2026-09-24. Lenses: backend-engineer, frontend-engineer, test-engineering-specialist (plus domain-analyst for wording). Commit **73466a10** on `feat/ns-2-brief-nav-collapse`. Not pushed.

The earlier attempt left nothing behind. At start, `git status` showed changes only under the other implementer's paths (`listing_capture/**`, `market-listings/**`). I did not touch those paths, and the commit contains none of them (`git show --stat HEAD | grep -c "listing_capture|market-listings"` returned 0).

## Criteria

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | One API source plus an endpoint | PASS | `apps/api/app/services/catalog/product_lines.py`: `list_sellable_product_lines(db)` returns the distinct trimmed non-null non-blank `product_line` values, ordered by product count descending, with `null_product_line_count`. It also provides `sellable_line_codes(db)` and `invalidate_sellable_product_lines_cache()`. The cache is a 60 s TTL. It is invalidated in `product_master_workflow.commit_product_master_sync` next to the existing index-cache invalidate. The TTL covers commits that run in a worker process. Endpoint: `GET /api/v1/catalog/product-lines` in `endpoints/catalog.py` returns `{product_lines:[{code,product_count,label}], null_product_line_count}`. There is no label config key (checked `commercial_tenant_profile`: no `product_line_labels`), so label = code. Labels are never used for membership. |
| 2a | H1: resolver constant removed | PASS | `CANONICAL_SHEET_BU_CODES` is deleted. `_bu_codes(None)` returns an empty map, so the sheet and folder tiers fire only on the catalogue codes that callers pass. Matching ignores case and returns the code as stored. |
| 2b | H2: archive config default comes from the service, override kept | PASS | `DEFAULT_ACZA_TENANT_BU_CODES` is deleted. `BackfillArchiveConfig.tenant_bu_codes` is now `frozenset \| None = None`, and an explicit value is still an override. `iter_archive_lineup_files(config, *, sellable_line_codes=...)` uses the override if set, else the codes passed in. |
| 2c | H3: bulk preview gets the codes | PASS | `build_bulk_lineup_preview` loads `sellable_line_codes(db)` once per preview when `tenant_bu_codes` is None. This covers the HTTP endpoint (`execute_bulk_lineup_preview`) and every other caller. I loaded the codes there, not in the endpoint, because it is the single funnel. |
| 2d | H4: single-file parser | PASS | `lineup_case_parser.parse_current_lineup_file` passes `tenant_bu_codes=await sellable_line_codes(db)` to `resolve_lineup_business_unit` and `line_codes=` to `infer_case_product_line`. `lineup_case_product_line.ensure_case_product_line_from_catalogue` does the same. |
| 2e | H5: data-driven filename fallback | PASS | `CANONICAL_PRODUCT_LINES` is deleted. `infer_product_line_from_filename(filename, *, line_codes)` returns the first filename token (split on space, `_`, `-`, `.`) that equals a catalogue code. The words gaming, consumer and notebook, and the phrase "nv ally", are no longer mapped. With no codes it returns None. |
| 2f | H6: PM chips | PASS | `PM_PRODUCT_LINES` is deleted from `pm_mapping_memory.py`. The `imports_product_master` job-state `product_lines` now comes from the service. The web PM chips (`admin/imports/page.tsx:3231`) already render the API list, so they needed no web change. |
| 2g | H11: wording | PASS | `plan_vs_executed.py` reason now reads "business line (each product line in the catalogue)". The resolver docstrings no longer list codes. |
| 3a | Web: shared hook | PASS | `apps/web/src/features/catalog/useProductLines.ts` uses React Query key `['catalog','product-lines']` and returns `lines`, `codes` (both memoised) and `nullProductLineCount`. |
| 3b | H7: dialog BU options | PASS | `TENANT_BU_OPTIONS` is deleted. The options now come from `useProductLines` (`buOptionCodes`). If a proposal's current BU is missing from the catalogue, the list keeps it so the select cannot silently blank it. |
| 3c | H8: archive path codes passed in | PASS, with one deviation | `DEFAULT_TENANT_BU_CODES` is deleted. `parseArchiveRelativePath` and `stageLineupFilesFromList` now **require** the codes, and tests pass them explicitly. The brief said to keep a default parameter for tests only. I did not keep it, because a literal default would trip the guard in criterion 4f and a required parameter is stricter. The "Select archive folder" button is disabled while the codes load, so a quick pick cannot drop the BU folder segment. |
| 3d | H9: copy | PASS | The copy now reads "all product-line folders are included" and "with product-line/year/quarter paths". |
| 4a | Test: the service excludes NULL and blank | PASS | `tests/test_catalog_product_lines.py`, on cip_test inside a transaction that is rolled back. It checks trim folding (3 rows fold to one code), that NULL, `''` and `'   '` are excluded and counted (+3), the count ordering, the cache, and the endpoint payload shape. I added it to the conftest `_WRITE_CAPABLE_TEST_MODULES`. |
| 4b | Test: PF, XB and PT resolve through the sheet and folder tiers | PASS | `test_lineup_business_unit_resolution.py`: `test_every_catalogue_line_resolves_via_sheet_tier[PF/XB/PT]` and `..._folder_tier[PF/XB/PT]`. Also `test_no_line_codes_means_no_label_tier` and `test_code_outside_catalogue_does_not_resolve`. The existing sheet and folder tests now inject `_LINE_CODES`. |
| 4c | Test: H5 assertion replaced | PASS | `test_lineup_period_inference.py`: the fallback now matches any catalogue code (NB, PT, XB). Also "words are not product lines" and "no codes gives None". The `Gaming_NR_Q2` fallback case now yields NR. |
| 4d | Test: archive path with injected codes | PASS | Web: `lineupBackfillArchivePath.test.ts` has 7 tests (PT recognised, NX not a BU, empty list gives no BU). API: `tests/test_lineup_backfill_archive_config.py` (injected codes, no built-in default, override wins). |
| 4e | Test: dialog options from a mocked endpoint | PASS | `admin/imports/BulkLineupBackfillDialog.test.tsx`. It mocks the endpoint to return NB, PT and LM and stages a `Product Lineup/PT/2026/Q1/…` folder. It asserts the staged path is `PT\2026\Q1`, the posted `folder_paths` match, and the BU select options are `['', 'NB', 'PT', 'LM']`. |
| 4f | Test: literal code-set guard | PASS | `tests/test_bu_code_literal_guard.py` scans `apps/api/app` and `apps/web/src` for `.py`, `.ts` and `.tsx` files, excluding tests, `__tests__` and `design-lab`. `apps/api/scripts/ops` is outside the scanned roots. It fails on 3 or more quoted two-letter upper-case codes in a comma list, including lists that span lines. A self-test checks the pattern against the old shapes. Before the change, a grep with the same pattern hit only H7 and H8; the multi-line H6 tuple is covered by the multi-line regex. |
| 5 | Proof (D-g): before and after | PASS, in-process fallback | See the proof section below. Result: **0 persisted changes**. Auto BU changed for 0 of 36 cases, final BU for 0 of 36, collision groups are 3 = 3 = 3 (identical), and all 7 supersession pairs are unchanged. |
| 6 | NULL rows reported, not edited | PASS | 10 rows. See the findings section below. |
| 7 | Checks | PASS | Listed below. |

## Checks run

- API (cip_test via `DATABASE_URL`/`DATABASE_URL_SYNC` = `…cip:cip@localhost:5432/cip_test`, the credentials `ro_sql.py` already uses; `.env` was not read). I ran `(cd apps/api && .venv/Scripts/python.exe -m pytest …)` in a subshell, because `test_migration_0064_column_on_disposable_db` loads `alembic.ini` from the working directory. It fails from the repo root before and after this change. Files: test_catalog_product_lines, test_bu_code_literal_guard, test_lineup_backfill_archive_config, test_lineup_business_unit_resolution, test_lineup_period_inference, test_lineup_bulk_backfill_preview, test_lineup_bulk_backfill_apply_integration, test_commercial_planner_api, test_plan_vs_executed, test_pm_mapper_commercial, test_product_master_workflow, test_openapi, test_commercial_planner_phase2, test_commercial_planner_intelligence. Result: **200 passed, 2 skipped** (both skips are pre-existing, in apply_integration).
- Web: `pnpm --filter @cip/web exec vitest run BulkLineupBackfillDialog.test.tsx lineupBackfillArchivePath.test.ts (+ lineupBackfillStewardOverrides.test.ts)`. Result: 10 passed.
- `pnpm --filter @cip/web exec tsc --noEmit` exited 0.
- `ESLINT_USE_FLAT_CONFIG=false … eslint` on the 5 changed or added web files exited 0.
- I did not restart servers or rebuild the web app. The orchestrator must rebuild before any rendered check.

## Proof (D-g), in-process

I could not use a clone. N-0039 recorded that `CREATE DATABASE` is denied for role cip, and the lineup archive tree (OneDrive) is outside the allowed roots, so the guard denied the path. I followed the brief's fallback. `prove_n0040_inprocess.py` runs the **old** code, copied from `git show HEAD:` into `old_resolver.py`, `old_period_inference.py` and `old_archive_config.py`, and the **new** code over every persisted case's own inputs. It reads those inputs in a read-only session on cip, which printed `current_database() = cip (read-only session)`. It writes nothing. Full output: `proof_output.txt`.

- Inputs per case:
  - Line rows come from `commercial_lineup_line`. Each line gets a synthetic token that resolves exactly when the line has a `product_id`, and its BU comes from `dim_product.product_line`.
  - `sheet_name`, `folder_path` and the steward or slice `business_unit` come from the case import job's `lineup_parse_options`.
  - The filename is `case.file_name`.
  - I left out shipment hints. That is conservative: the shipment tier is independent of the code set.
- Code sets:
  - Old: the resolver default {NB,NR,NV,NX}, which is what the preview endpoint used (H3 gap), and the archive/web set {NB,NR,NV,NX,PF,XB}.
  - New: 14 codes from the catalogue: NB=6848, NX=5173, PF=2049, NR=1910, PT=1311, LM=561, XB=183, PD=93, AI=11, NV=10, NL=8, CB=6, AX=3, AZ=1.

| Measure | Old | New | Persisted |
|---|---|---|---|
| Cases | 36 | 36 | 36 (discovery counted 44; cip has 36 today) |
| Auto BU (tier) changed, old to new | — | **0** | — |
| Final BU (manual, else auto) changed | — | **0** | — |
| Final BU ≠ persisted BU | 0 | 0 | — |
| Active collision groups (period\|customer\|BU, 2 or more members) | 3 | 3 (identical) | 3: `2026-01-01\|52\|NR` [90,127], `2026-04-01\|18\|NB` [121,128], `2025-04-01\|299\|XB` [137,138] |
| Supersession pairs unchanged | — | **7 of 7** | 9→122, 119→120, 130→146, 141→117, 142→133, 143→136, 144→121 |
| Effective case product_line inference changed | — | 3: case 131 (1 of 9 rows resolved) Gaming→NR; 141 (0 rows) Consumer→None; 143 (0 rows) Gaming→None | 131=NB, 141=NB, 143=PF (steward and apply values; not recomputed) |

Why 0 persisted changes: every one of the 36 cases has a non-null `product_line` and `business_unit`. `ensure_case_product_line_from_catalogue` only fills a NULL value, and `superseded_by_case_id` is persisted. Nothing recomputes them. The 3 inference differences would only show on a new import of an under-resolved file. There the old code emitted "Gaming" or "Consumer", which are not `product_line` values; the new code emits a real code or nothing. Every PF and XB case in the data resolves at the product tier, so no persisted case sat on a PF or XB label tier.

Repair needed on cip: **none**.

## Findings for Warren

1. **NULL product_line rows (not edited).** 10 `dim_product` rows have NULL or blank `product_line`: ids 1 and 70820–70828 (SKU-ALPHA-01, SKU-HL-01, SKU-RES-01…07, SKU-STEP2-TEST, SKU-RES-ILIKE). They look like test pollution, and discovery found one `cpor_case_line` using them. The new source excludes them and reports `null_product_line_count` (10 today). A steward decision is needed: retire them, or give each a product line.
2. **Label-tier widening risk (as discovery noted).** A sheet tab or folder named after any of the 14 codes, for example `AI`, `PT`, `LM`, `PD` or `CB`, now claims that BU when the product and shipment tiers fail. The `bu_label_product_mismatch` flag and the product-first ordering are unchanged.
3. **The filename fallback lost word aliases.** "notebook" used to map to NB and "gaming" to Gaming. D-g says only product-line values count, so these are gone. The fallback now also finds codes such as `PD` in "Gaming Desktop PD" (cases 134 and 135 would give PD, not PF), but only when fewer than 25% of rows resolve. Both of those cases resolve 63 of 63 rows, so the catalogue majority PF wins. **Question:** should a filename token ever beat the folder BU for an under-resolved file? For example, should a `PF\…\… PD ….xlsx` file give PD or PF? Options: (a) keep the current behaviour, where the filename is the fallback in product-line inference only and the folder still sets `business_unit`; (b) prefer the folder or sheet label over the filename for `product_line` as well.
4. **Deferred, not changed:** `COMMERCIAL_SEMANTICS.md` A1-07 still says NB/NR/NV/NX. It is docs, but outside this node's code sweep, so I left it for the knowledge steward. The H10 Plan BU free-text box in `InboundShipmentsWorkspace` is optional and could become a select fed by `useProductLines`. The L2 `PlanVsExecutedView` options are data-derived and legitimate.

## Files changed (commit 73466a10)

API:
- new `app/services/catalog/product_lines.py`
- `api/v1/endpoints/catalog.py`
- `api/v1/endpoints/imports_product_master.py`
- `services/commercial_planner/lineup_business_unit_resolution.py`
- `lineup_backfill_archive_config.py`
- `lineup_bulk_backfill_preview.py`
- `lineup_case_parser.py`
- `lineup_case_product_line.py`
- `lineup_period_inference.py`
- `plan_vs_executed.py`
- `services/imports/pm_mapping_memory.py`
- `product_master_workflow.py`

API tests:
- new `test_catalog_product_lines.py`
- new `test_bu_code_literal_guard.py`
- new `test_lineup_backfill_archive_config.py`
- `test_lineup_business_unit_resolution.py`
- `test_lineup_period_inference.py`
- `conftest.py` (write-capable list)

Web:
- new `features/catalog/useProductLines.ts`
- `features/commercial-planner/lineupBackfillArchivePath.ts` and its `.test.ts`
- `app/(app)/admin/imports/BulkLineupBackfillDialog.tsx`
- new `BulkLineupBackfillDialog.test.tsx`

Evidence (not committed; for the orchestrator): `IMPL.md`, `prove_n0040_inprocess.py`, `proof_output.txt`, `probe_cases.py`, `old_resolver.py`, `old_period_inference.py`, `old_archive_config.py`.

## Blocked / grants

- A real clone proof (full bulk preview re-run over the archive tree) needs two grants: `CREATEDB` for role cip (or an operator-created `cip_n0040_clone`), and read access to the OneDrive Product Lineup tree. Without them, the in-process proof above is the evidence.
- Process note: some early shell calls used `cd apps/api && …` before I switched to absolute paths, `pnpm --dir`, and subshells. Nothing ran outside the repo.
