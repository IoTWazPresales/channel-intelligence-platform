# N-0047 IMPL: dim_product launch/retire windows (BACKLOG-034), proven on a clone

Node R2, data_migration. Lenses: database-specialist, data-quality-governance-specialist, test-engineering-specialist.
This was a resumed implementation. The earlier implementer hit a usage limit, so this session also reviewed that work and fixed it.
Commit: **e1fa2b1e** (4 files, staged by explicit path). Nothing was written to `cip`.

## Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | cip counts today by cause (read-only) | PASS | §1 (ro_sql.py, 2026-09-24) |
| 2 | Where inversions are written, the writer fix and its test | PASS | §2; 81 tests passed |
| 3 | Repair rule with reasoning and downstream effect | PASS | §3 |
| 4 | Clone numbers: dry run, apply, second apply | PASS | §4 (`cip_merged_leftover_repair`, vintage 2026-08-19) |
| 5 | cip dry-run prediction and ready-for-cip commands (not run) | PASS | §5 |
| 6 | Dry run performs no writes; `--expect-db` guard; idempotence | PASS | §4 and §5 |
| 7 | Reduce the 2,795 inverted windows on cip | **NEED_HUMAN** | Most of them match the OEM file exactly. Changing them needs a business rule that no one has given (§6 Q1) |

## 1. cip today (read-only, `current_database() = cip`)

`ro_sql.py`, 2026-09-24:

| total | inverted (retired < launch) | launch = retired | placeholder (<= 1970-01-01) | inverted AND Published |
|---|---|---|---|---|
| 18,177 | 2,795 | 698 | 671 | 544 |

Causes, from the read-only dry run (`run_cip_dryrun_readonly.txt`, flags CSV `flags_cip_dryrun_20260924T133513Z.csv`):
- **671 rows are the 1970-01-01..1970-01-01 placeholder** (`epoch_1970_both` = 671; these make up 671 of the 698 launch = retired rows). Cause: the PM file `Specs_new.xlsx` (job 88) stores `ttv_date` / `eop_date` as bare Excel day serials. `_parse_date_val` passed the number to `pd.to_datetime`, which reads it as nanoseconds since 1970, so every value became 1970-01-01. This was a writer bug.
- **2,795 genuinely inverted rows**, which the dry run splits by what the committed PM files say:
  - `same_in_every_pm_file` **2,181**: every committed file (jobs 4/28/31/88) has this same inverted TTV/EOP pair, so the OEM data itself is inverted.
  - `earlier_pm_file_valid_window` **409**: an earlier file had a valid window, and a later file changed one side.
  - `earlier_pm_file_other_inverted` **201**: every file is inverted, but the values differ between files.
  - `single_pm_file` **4**.
  - Transposed pairs, where one file has exactly the reverse of another (`swap` rule): **0**.
- Example rows (identifiers only): id 12 `90NB0VX1-M008J0` Published 2024-07-18 / 2024-06-25 (same in every file); id 42 `90NR0JP8-M00940` Published 2026-04-27 / 2025-06-23 (an earlier file was valid); id 50 `90NB13Y2-M00W40` Published (other inverted); id 54316 `90NX08L1-M05AC0` (single file); id 27 `90NB0651-M00560` 1970 placeholder that re-derives to 2015-06-01 / 2015-04-30.
- How far apart the dates are in the inverted rows after repair (2,887 rows): median 126 days, p25 63, p75 273, max 2,048. 385 rows are at most 31 days apart; 448 are more than 365 days apart. By status: Disabled 1,256, Discarded 949, **Published 555**, Standby 127. By line: NB 1,454, NX 921, NR 390.

## 2. Where inversions are written, and the fix

Code that writes `launch_date` / `retired_date` (searched `apps/api/app` for `retired_date`):
- `apps/api/app/services/catalog/product_import_sync.py` `_staging_tuple` → `_parse_date_val` → bulk upsert (Product Master commit). The PM mapping, the same on all 5 committed PM jobs (read-only query), is **`ttv_date → launch_date`, `eop_date → end_of_life_date` (→ `retired_date`)**.
- `apps/api/app/api/v1/endpoints/products.py:327-330` `PATCH /products/{id}` lets a steward edit these fields with no window check. I left it unchanged; see Q3.

Fixes (commit e1fa2b1e):
- `product_import_sync.py`: `_excel_serial_to_date` plus a numeric branch in `_parse_date_val`. A bare int or float is now read as an Excel serial (epoch 1899-12-30, range 1..2958465, any fractional time of day dropped). Booleans, 0, negatives and NaN give None. Before the fix, a number always came out as 1970-01-01.
- `product_master_workflow.py`: new `pm_row_inverted_window`. `validate_product_master_sync` now adds a per-row **warning** `launch_after_end_of_life`. This is a FLAG, not a BLOCK: commit still stores the file's values as given, and the steward sees the inverted window before committing.
- Tests: `apps/api/tests/test_n0047_dim_product_windows.py` (pure logic, no DB). Command:
  `PYTHONPATH=apps/api apps/api/.venv/Scripts/python.exe -m pytest -c apps/api/pyproject.toml --rootdir apps/api test_n0047_dim_product_windows.py test_product_master_workflow.py test_pm_dataframe_sanitize.py test_pm_mapper_commercial.py test_pm_mapper_regression_full.py`
  Result: **81 passed in 26.34s**. None of these modules is in conftest's `_WRITE_CAPABLE_TEST_MODULES`. (Run from the repo root without `PYTHONPATH`, pytest fails with `No module named 'app'`.)

## 3. Repair rule (`apps/api/scripts/ops/repair_n0047_dim_product_windows.py`)

The evidence is the committed PM files themselves (`import_job` template `product_master`, stage `pm_committed`, oldest first). The script reads them with the commit's own mapping and the fixed parser. Only `launch_date`, `retired_date` and `updated_at` change. The first rule that matches applies:

1. **`rederive_excel_serial`**: a side is <= 1970-01-01 and the newest PM file row for that SKU has a bare number in that column. That side gets the serial's date. This undoes a parser bug using the source's own value, so it is not a guess. If the re-derived window is itself inverted, the row is still written, because it matches the source like every other file window, and it is **also flagged** (`rederived_window_inverted_in_source`).
2. **`null_placeholder`**: a placeholder with no serial to re-derive from becomes NULL (unknown). It is never guessed. 0 rows on cip or the clone.
3. **`swap`**: the window is inverted and some committed file has exactly the two values the other way round. 0 rows. Kept because it is evidence-based. It is a candidate to remove if you would rather not auto-swap at all.
4. **`flag`**: any other inversion is left as is and listed in the flags CSV with its file-history reason. **Never written.**

Why the other inversions are not changed: BACKLOG-034 says to derive corrections from a trusted source or steward review and never to guess or widen windows. For 2,181 rows the trusted source (the OEM spec file) says exactly what `dim_product` holds. Picking a side (null the EOP? use the earlier file's window?) is a domain rule no one has given, so those rows go to Q1 and Q2.

Downstream effect:
- `distributor_sales_inventory._product_evidence_date_outside_launch_retire_window` treats a product as out of window when `retired < d` or `launch > d`. An inverted window, and a 1970 zero-day window, is therefore out of window **for every date**. Those products are never eligible for DSI auto-resolution in window-gated modes.
- The repair gives **579** of the 671 placeholder rows (671 - 92) a real, valid window. Those products can become eligible for evidence dates inside their windows. That changes DSI eligibility outcomes, so affected DSI and shipment jobs need re-validating after apply (the BACKLOG-034 regression trap).
- The other 92 go from ineligible (1970) to ineligible (inverted in source), so their behaviour does not change.
- The shipment SKU-anchor identity tier is not gated by windows and is unaffected.
- Because of those 92, the **inverted count rises 2,795 → 2,887**. It is the same data problem, now honestly visible instead of hidden as 1970.

## 4. Clone runs (`cip_merged_leftover_repair`, alembic 0019, data vintage 2026-08-19)

The previous implementer ran these (logs in this folder). I reviewed each log. Its before-counts equal cip today.

| run | mode | before: inverted / eq / epoch_1970_both | writes by rule | rows updated | after: inverted / eq / epoch |
|---|---|---|---|---|---|
| `run_clone_1_dryrun.txt` | DRY RUN, `transaction_read_only = on` | 2,795 / 698 / 671 | rederive_excel_serial 671 | 0 | projected 2,887 / 27 / 0 |
| `run_clone_2_apply.txt` | APPLY | 2,795 / 698 / 671 (unchanged by run 1 → dry run wrote nothing) | rederive_excel_serial 671 | **671** | 2,887 / 27 / 0 |
| `run_clone_3_apply_again.txt` | APPLY again | 2,887 / 27 / 0 | {} | **0** (idempotent) | 2,887 / 27 / 0 |

Flags after apply (run 3): `same_in_every_pm_file` 2,258, `earlier_pm_file_valid_window` 417, `earlier_pm_file_other_inverted` 208, `single_pm_file` 4 (total 2,887; the 92 re-derived rows moved into these reasons). `dim_product_rows` stayed 18,177 throughout, so no row was deleted. Before-values for rollback: `before_cip_merged_leftover_repair_apply_20260924T132723Z.csv`.

Review of the safety properties:
- **Dry run makes no DB writes.** Without `--apply`, `SET TRANSACTION READ ONLY` is the first statement of the transaction; the server shows `transaction_read_only = on`; `apply_changes` is never called; the transaction is rolled back. Run 2's before-counts are identical to run 1's. The dry run does write the before and flags CSVs to this local evidence folder, but nothing to the DB.
- **`--expect-db`** is required. It is compared with `current_database()` before `run()`, and on a mismatch the script rolls back and exits 2. `current_database()` is printed again just before the UPDATE.
- **Optimistic UPDATE**: `WHERE id = :id AND launch_date IS NOT DISTINCT FROM :old AND retired_date IS NOT DISTINCT FROM :old`, so a row that changed after the plan was made is left alone.
- **Idempotent**: flagged rows are never written, and re-derived rows are no longer placeholders. The unit test `test_repair_is_idempotent_on_its_own_output` covers this, and clone run 3 shows 0 rows written.

## 5. cip prediction and ready-for-cip commands (NOT run: Warren runs)

The read-only dry run on cip (`run_cip_dryrun_readonly.txt`, `transaction_read_only = on`, `rows updated: 0`) predicts:
- 671 writes (`rederive_excel_serial`); 0 swap; 0 null.
- After: inverted 2,887, launch = retired 27, epoch_1970 0, rows 18,177.
- Flags: 2,887 (92 of them `rederived_window_inverted_in_source`).

Commands, run from `apps/api`:
```
.venv/Scripts/python.exe scripts/ops/repair_n0047_dim_product_windows.py --expect-db cip
.venv/Scripts/python.exe scripts/ops/repair_n0047_dim_product_windows.py --expect-db cip --apply
```
Check that the dry run prints `planned writes by rule: {"rederive_excel_serial": 671}` before you apply. Keep the `before_cip_apply_*.csv` it writes; it holds the rollback values. After applying, re-validate the DSI and shipment jobs whose products are in that CSV.

## 6. Questions for Warren

**Q1: 2,181 rows where the OEM spec file itself has EOP (`eop_date`) before TTV (`ttv_date`), identical in every file. 544 of today's inverted rows on cip are Published.**
Today each of these products is out of window for every date. Options:
- (a) Leave them as they are and treat the flag list as a request to the OEM data owner.
- (b) Take TTV/EOP as the wrong semantic for eligibility. For example, `retired_date` should not be EOP, because end of production is not end of sale. Stop mapping `eop_date` → `retired_date` and set those rows' `retired_date` to NULL, which means open-ended.
- (c) For inverted rows only, set `retired_date` to NULL.
- (d) Swap the two dates.

(b) and (c) widen eligibility, which BACKLOG-034 warns against doing blindly.

**Q2: 409 rows where an earlier PM file had a valid window and a later file inverted it.** Options:
- (a) Restore the most recent valid window from the files.
- (b) Flag only, as now.

**Q3: steward PATCH `/products/{id}`** accepts `retired_date < launch_date` without comment. Options:
- (a) Reject it with a 422 (BLOCK).
- (b) Accept it and return a warning (FLAG).
- (c) Leave it as it is.

**Q4: validation warning.** Should `launch_after_end_of_life` stay a warning (FLAG, as implemented), or block commit?

## Files
- Changed (commit e1fa2b1e): `apps/api/app/services/catalog/product_import_sync.py`, `apps/api/app/services/imports/product_master_workflow.py`, `apps/api/scripts/ops/repair_n0047_dim_product_windows.py` (new), `apps/api/tests/test_n0047_dim_product_windows.py` (new).
- Changes I made on review: removed the unused `REPAIR_TAG` constant from the script. Redacted a hard-coded DB password in the evidence probes `probe_history.py`, `probe_mappings.py` and `probe_sources.py`; they now read `PGPASSWORD`. The probes are not committed.
- Not done: ruff and pyflakes are not installed in `apps/api/.venv`, so lint is UNABLE.
