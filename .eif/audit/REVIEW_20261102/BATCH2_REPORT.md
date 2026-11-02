# Batch 2 report: M3-M9 and the minors from the GOV-008 review of 2 November 2026

Branch `feat/ns-2-brief-nav-collapse`, one agent session (Sonnet 5.5). Same-session self-verification only: the writer also wrote the tests (R2 limits apply). **No acceptance is claimed.** No node, no ledger event.

**Boundaries kept.** Nothing was written to `cip`: no data write, no migration applied to it, no restart, no deploy. Every run that touched a database ran on `cip_test` (`apps/api/.venv`, URL forced to `cip_test` by `batch1/run_on_cip_test.py`). I did not open a connection to `cip` at all in this batch, so no read-only setting was needed. One migration was written and tested on `cip_test`, not applied to `cip`: `20261102_0051` (below). One slip: I ran a `cd` once and returned to the root in the next call (the project rule is never to `cd`); nothing was changed by it.

## Gate

| Gate | Result |
|---|---|
| Full API pytest on `cip_test` | **3,645 passed, 25 skipped, 0 failed**, 26 min 17 s (`batch2/api_full_pytest_cip_test.log`). Batch 1: 3,574 / 24. +72 new tests, so one more skip than before: see below |
| Web `tsc --noEmit` | exit 0 (`batch2/web_tsc.log`) |
| Web vitest, full | **223 files, 1,215 tests passed** (`batch2/web_vitest.log`). Batch 1: 222 / 1,205 |
| Web lint (`ESLINT_USE_FLAT_CONFIG=false`, the repo's legacy config) | exit 0, **0 errors, 50 warnings** (the same 50 as before; `batch2/web_lint.log`) |
| API lint | **not run**: `ruff` is not installed in `apps/api/.venv` |

Web numbers were taken before the batch 3 edits and are repeated, after them, in `BATCH3_REPORT.md`.

## Result per finding

"Proof" = the new test fails with the fix removed. All mutation runs are in `batch2/mutation_checks.md`; the ones for the book minors, the API minors and the cleanup script ran through `batch2/mutate.py`, which breaks one fix at a time and restores the file.

| Finding | What changed | Test | Proof |
|---|---|---|---|
| **M3** migrated v1 report rows | `saved_report_payload` applies the 500-row cap and value sort only to definitions with no `migrated_from` (the key the migration script writes). Migrated reports export and deliver the handler's rows, in its order, untruncated. | `test_batch2_m3_migrated_report_rows.py` (2): the review's 522-row probe; control: a v2-authored equivalent report keeps the cap | 1 of 2 fails without the fix (the other is the control) |
| **M4** one bad recipient | `_deliver_schedule_async` tries each recipient alone. A failure rolls back, alerts ops with the full text, and writes a failed row **only for that recipient**; the others continue. The timeout label is set only for a real statement timeout (`is_statement_timeout`); the recipient sees `recipient_safe_error` (no `[SQL: ...]`, no parameters). A deactivated or revoked recipient gets no row at all (it was never notified, by D-0132). Result: `ok: false`, `failed_recipients`, `deliveries`. | `test_batch2_m4_schedule_recipients.py` (4): [viewer, deactivated, admin] -> admin still gets it; SQL text absent and label `[FAILED]`; real timeout labelled `[TIMEOUT]`; the text scrubber | 4 of 4 fail with the runner reverted |
| **M5a** history query tenant | `_HISTORY_SQL` ties both the current observation and the history observations to the fact's tenant through the observation's import job. | `test_batch2_m5_tenant_scope.py` (2 of its 5) | fail without the fix; the control (a tenant still sees its own earlier report) passes |
| **M5b** `fact_upsert_key` | The shipped replace reads and deletes by `(tenant_id, key)`; sticky POD and the closed-key guard are per tenant; the delete-job restore only uses the same tenant's evidence. **Migration `20261102_0051`** makes the constraint `UNIQUE (tenant_id, fact_upsert_key)` under the same name. The code is safe on the old constraint too: a key shared by two tenants then fails loudly (the load raises) instead of deleting the other tenant's fact. Key strings are unchanged, so no fact needs re-keying. | same file (3 more): P8 on the old constraint (B's load raises, A's fact survives); P8 after the migration (both facts live, A's reload replaces only A's); the downgrade refuses when two tenants hold one key | all fail without the fix |
| **M5c** mapping memory, aliases | **Not done: needs a decision, see Needs Warren.** | none | none |
| **M6** `priced_units` bypass | A measure is restricted by the governed metric of any legacy-keyed measure that reads the same column of the same model with any aggregate, filter or rule, and by any calculated measure over one (transitively). Several anchors: hidden wins; narrowed grains intersect. A measure that only inherits a restriction keeps its own label. | `test_batch2_m6_overlay_walk.py` (4): walks the whole model catalog, hides each legacy metric in turn, compares with an independent column/dependency rule, and checks the non-admin catalog list | 4 of 4 fail with the old code |
| **M7** grains, pending | New time floor `period_start` (lineup, sell-in): day and week refused with a plain reason. One rule, `period_grains_for`, drives both planner and catalog: the catalog stops offering CST day and open-shipment period; prior-year and running total say `requires: ["period"]`. A pending measure refuses with its reason ("... is not available yet. ..."), not "Unknown measure". | `test_batch2_m7_period_grains.py` (21): refusals, a walk that every grain the catalog offers plans and every grain it omits is refused, breakdowns, pending reasons | 11 fail without the fix; the other 10 are controls (month/quarter/year still accepted, day-floored facts keep day and week) |
| **M8** per-week totals | `window_weeks` takes the tenant calendar (`plan.calendar`) so the open edges are the calendar's own buckets. The review's cases: Sunday week 14 / 14 (was 14 / 7); retail month 2.8 / 2.8 (was 2.8 / 3.16). | `test_batch2_m8_window_weeks_calendar.py` (4) | 3 fail without the fix; 1 control (platform calendar unchanged) |
| **M9** widget CSV | `toCsv` writes exact text (`UX3405MA` stays `UX3405MA`; `ACBU`; a name is not re-cased); the formula guard is kept (`'=SUM(A1)`); a percent column exports the number its header says (0.86 -> 86). | `table.test.ts` (+4) | 3 fail without the fix; 1 control (missing values still read Unassigned) |

## The minors

| Minor | What changed | Test | Proof |
|---|---|---|---|
| Older-report guard and operating unit | `superseded_scopes`: a file is older only if **every** scope it carries (report type, operating unit; BOM is one scope) has a newer applied report in that same scope. A file with one superseded and one current unit writes the current unit only (`skip_scopes`). | `test_batch2_book_minors.py` | mutation caught (2 tests) |
| Partial shipment | The close compares the shipped sheet's quantity for the same unit, order and item with the open quantity. The line still closes as `closed_shipped`; the gap is **flagged**: per fact in the audit event (`shipped_quantity`, `missing_quantity`, `partial_shipments`, `partial_missing_units`), on the job, and as an Import Center notice ("Some closed orders shipped less than was open ... 40 unit(s)"). Open 100, 60 shipped -> 40 flagged. | same file | caught (1 test; the full-shipment control passes) |
| Remembered sheets | The source remembers every sheet it showed (`seen_sheet_names`). A new or renamed sheet reopens the sheet dialog, listed and unselected, and the mapping state says what changed (`sheet_changes`). An unchanged workbook still skips the dialog; memory from before this field asks once. | same file (6) | caught (2 tests) |
| Orphan retire | Quantity check (a replacement with another quantity is flagged and left open, not retired); a replacement serves one orphan (a second orphan with no order line is `ambiguous`, left open and flagged); the load writes its own `shipped_fact_orphan_open_retire` audit event listing what it retired and what it flagged. The script's count check follows the new plan. | same file | caught (quantity, two orphans, audit event) |
| `refresh_superseded_pointers` | At load it only looks at keepers the job just wrote (`written_by_job`); the scripts still repair the whole table. | same file | caught |
| Widget saved report | `_check_saved_report_ref` on create, replace and add widget: the report must exist in the tenant and be viewable. A report of another tenant is already invisible to the endpoint's session (ORM tenant filter), so the review's stored id 987 was an id that exists nowhere: the test covers both. | `test_batch2_api_minors.py` (4) | caught |
| `units_per_week` without dates | `POST` and `PATCH /saved-reports` refuse it ("needs execution dates"), as promotion does; a fixed window is accepted. | same file | caught |
| Formula guard on other exporters | New `export_literal_guard`: CPOR case workbook, lineup workbook and CSV, lineup customer slice, promo template store text as text (cell type `s`); AG Grid CSV (`gridFind`, products grid) and the DSI candidate export guard text and leave numbers alone (`csvFormulaGuard.ts`). | `test_batch2_export_formula_guard.py` (4), `csvFormulaGuard.test.ts` (4) | 3 of 4 and 2 of 4 fail; the rest are the helpers' own unit tests |
| Vessel badge, no ETA | `eta_shift_days` (signed) beside `slip_days`; the badge says "ETA pulled in N days", the history text no longer says "every report" for a moved ETA. A vessel with no ETA is drawn at the start of its lane (0%, `position_known: false`), the progress bar says so. | `test_batch2_vessel_minors.py` (5), `onTheWater.rules.test.ts` (+2) | 4 of 5 and 2 of 2 fail; 1 control |
| Port code `XXX` | UN/LOCODE shape `[A-Z]{2}[A-Z0-9]{3}` required. | API minors | caught |
| Raw NaN body | Validation errors echo the input; NaN and Infinity are not JSON, so the 422 itself became a 500. A handler writes them as text (`"nan"`); `delay_days` also refuses non-finite numbers. | API minors | caught |
| `reclassify_unconfirmed_shipped` | **Scoped**: needs `import_job_id` and/or `loaded_on_or_before` (facts created on or before a day) and raises with neither. `preview_unconfirmed_shipped_ids` takes the same scope; `scripts/ops/close_open_book.py` got `--reclass-job` and `--reclass-loaded-on-or-before` and skips the reclassification without one. | book minors | caught |
| AUD-PARI facts | **Not touched on cip.** `scripts/ops/remove_leaked_test_shipment_facts.py`: dry run default (READ ONLY), `--apply --expect-db NAME --expect-count N`, one audit event with every removed row, refuses if anything points at them. Plan: `batch2/AUD_PARI_CLEANUP_PLAN.md` (clone first). Not run on any database but `cip_test`. | `test_batch2_aud_pari_cleanup.py` (3) | the three guards each caught (2 of the 3 tests; the delete-and-audit test is not mutation-checked) |
| Docs | `docs/memory/CURRENT.md` deployment boundary corrected (cip at `20261101_0050`; code head 0051 not applied). The paragraph is in `docs/memory/CURRENT.md`; `.eif/CURRENT.md` is generated and was not edited. D-0132 added to `.eif/DECISIONS.md` as **PROPOSED** (see Needs Warren). | none | n/a |

## Migrations written, not applied to cip

- `apps/api/alembic/versions/20261102_0051_fact_upsert_key_per_tenant.py`: `uq_fact_inbound_shipment_fact_upsert_key` becomes `UNIQUE (tenant_id, fact_upsert_key)`. Upgrade cannot fail on existing data (the wider key is implied by the narrower). Downgrade refuses if two tenants hold one key. Tested inside rolled-back transactions on `cip_test` (upgrade, the P8 load, downgrade refusal). `cip_test` itself is still at `20261101_0050`. The model (`facts.py`) already declares the new constraint.

## Test counts and mutation checks

New tests this batch: **72 Python** (all 72 pass in the full run) and **10 web** (`table.test.ts` +4, `onTheWater.rules.test.ts` +2, `csvFormulaGuard.test.ts` 4), plus the changed `gridFind.test.ts` expectation.

Checked with the fix removed (a mutation run for each fix, restored after):
- **Python: 72 tests -> 50 fail with their fix removed; 17 are controls that must pass and did** (M3 1, M5 1, M7 10, M8 1, export guard 1 (the helper's own test), vessel 1, book minors 2); **5 were not mutation-checked**: four sheet-memory tests (the remember/store round trip, "nothing remembered", "unchanged workbook", "memory from before the seen list") and the cleanup script's delete-and-audit test.
- **Web: 10 tests -> 7 fail with their fix removed, 3 pass** (the "missing values read Unassigned" control and the two unit tests of the new guard helper).

The extra skip (25 vs 24): `test_shipment_resolved_entities.py::test_branch_bill_to_variants_resolve_same_root_distributor` catches every exception, including its own failed assert, and skips with "DB not available". On `cip_test` both MUSTEK aliases exist (both point at distributor 1343) but `resolve_shipment_distributor_id_from_line` returns `None`, so the assert fails and it skips. This batch did not touch that resolver; it looks like `cip_test` data state. I did not establish when it changed. The test hides failures behind a skip and should not catch `AssertionError`.

## Needs Warren

1. **Mapping memory and alias reuse across tenants (M5c).** `source_definition.column_mapping_memory` (header mappings, remembered sheets, cleared tokens) and the alias tables carry no tenant, and the loader reuses them automatically. Scoping them is a schema decision: either `tenant_id` on `source_definition` and the alias tables (a migration and a backfill to `default`), or a per-tenant namespace inside the JSON with a fallback to the current un-namespaced memory for `default`. One tenant on cip today, so nothing is exposed now. Not done.
2. **D-0132 status.** The programme ledger records it as accepted by you on 26 October (EIF 2778); I wrote it into `.eif/DECISIONS.md` as PROPOSED because the brief said so. Confirm, or tell me to mark it accepted.
3. **Apply `20261102_0051` to cip** (as the table owner, after a dry run) and **deploy batches 1-2**: code, then the migration, then restart the worker as well (validate and apply run there). Not done.
4. **AUD-PARI cleanup**: the go for the clone proof, then for `cip` (`AUD_PARI_CLEANUP_PLAN.md`).
5. **Partial shipment**: the 40 missing units are flagged, not re-opened or labelled. Do you want a different state for the remainder (for example an open line for the 40, or `closed_cancelled`)?
6. **Orphan retire with another quantity**: left open and flagged. The alternative is to retire it anyway (the replacement is the current truth). Your call.
7. **M3**: migrated reports keep the v1 rows (my reading of the code comment). If you would rather they take the v2 cap and order, it is one condition.
8. **Batch 1 carry-overs still open**: the M2 undated-file rule; `cst_alias_era_derive` still counts closed rows for first-movement dates.

## Not done

- M5c (above). No live run of anything on `cip`. No restart. API lint (no `ruff`). No render in this batch (batch 3).
- The change to `import_job_delete_figures._shipments` (restores only from the same tenant's earlier loads) has **no test of its own**; it is covered only by the existing delete-figures tests.
- `catalog_for_tenant_cached` has no TTL and "on-hand for a product absent from the latest report is a null row" (both in the review's minor list, neither in this brief) are untouched.
- The earlier-listed review item "cancelled remainder labelled `closed_shipped`" is not fixable from the data (the sheets do not say why a line is gone); the partial-shipment flag is the part that can be done.

## Files

Code: `report_delivery.py`, `report_schedule_runner.py`, `shipping_water.py`, `shipment_inbound_facts.py`, `import_job_delete_figures.py`, `alembic/versions/20261102_0051_*`, `models/facts.py`, `query/model/{tenant_restrictions,graph,loader,catalog,calc,execute}.py`, `semantics/models/default.yaml`, `shipment_open_book.py`, `shipment_shipped_fact_identity_twin_merge.py`, `shipment_field_mapping.py`, `imports.py`, `dashboards.py`, `saved_reports.py`, `main.py`, `on_the_water.py`, `export_literal_guard.py` (new), the four exporters, `scripts/merge_shipped_fact_identity_twins.py`, `scripts/ops/close_open_book.py`, `scripts/ops/remove_leaked_test_shipment_facts.py` (new); web `table.ts`, `csvFormulaGuard.ts` (new), `gridFind.tsx`, `products/page.tsx`, `dsiProductCandidateExport.ts`, `format.ts`, `types.ts`, `OnTheWater.tsx` (progress bar only).
Tests: `test_batch2_*.py` (11 files). Evidence: `.eif/audit/REVIEW_20261102/batch2/`.
