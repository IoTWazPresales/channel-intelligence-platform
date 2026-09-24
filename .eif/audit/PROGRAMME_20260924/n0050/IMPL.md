# N-0050 implementation evidence: cpor_case_line week-aligned windows (BACKLOG-137)

Run: N0050_IMPL_20260924 (fresh-context implementer). Lenses used: database-specialist, backend-engineer, test-engineering-specialist, release-migration-manager (cip plan).
Commit: **`d8b2e7ac`** on `feat/ns-2-brief-nav-collapse`. Not pushed.
**cip was not written.** cip is still at `20260906_0022`. cip_test.public is now at **`20260924_0023`**.

## Sources and the week convention
- BACKLOG-137, CPOR_SETTLEMENT_SPEC §3 (line windows: "old line closes end of prior week; new line from new week"), §9.3, D-058 ("Weekly grain; a week straddling a boundary is flagged, never silently pro-rated").
- **Week = Monday to Sunday.** Sources: `docs/SPEC_CPOR_V1_AND_LISTING_CAPTURE_V0.md:169` ("Week convention Mon–Sun as tenant config; per-case override allowed (cases usually but not always Mon–Sun)"), and the code's `iso_week_start` (`apps/api/app/services/imports/dsi_coverage.py:22`, `d - timedelta(days=d.weekday())`) plus `_iso_week_start_expr` in `channel_ops.py:149`. A window is week-aligned when `window_start` is a Monday and `window_end` is a Sunday.
- Because the spec allows cases that do not run Monday to Sunday, alignment is **not** a DB CHECK. It is computed and flagged in the service.

## Criteria

### 1. Alembic revision after 0022: PASS
`apps/api/alembic/versions/20260924_0023_cpor_case_line_window.py` (down_revision `20260906_0022`; `alembic heads` = `20260924_0023` only).
- Adds `window_start`, `window_end` (DATE). Backfill: `UPDATE cpor_case_line l SET window_start=c.window_start, window_end=c.window_end FROM cpor_case c WHERE c.id=l.case_id`. Both columns are then set to NOT NULL. `cpor_case.window_*` are NOT NULL, and cip has 0 null or inverted case windows.
- **Backfill for windows that are not week-aligned:** the case window is copied **as-is**. It is not snapped to Monday/Sunday, because snapping would widen or narrow which claims count. It is not pro-rated. These lines are flagged `window_week_straddle` at read time (criterion 2). So settlement numbers do not change: after the backfill, 658/658 lines have a window equal to the case window.
- **Grain:** `uq_cpor_case_line_grain` becomes `UNIQUE (case_id, product_id, distributor_id, pod_quarter, window_start)`. Why this is the smallest correct change:
  - D-058 supersession always starts the successor line in a later week, so `window_start` is enough to tell the two lines apart.
  - Keeping the constraint **name** means the historical-import upsert (`ON CONFLICT ON CONSTRAINT uq_cpor_case_line_grain`, `apply_sync.py`) still works. An exclusion (gist overlap) constraint would also block overlapping windows, but `ON CONFLICT DO UPDATE` cannot target an exclusion constraint, so that upsert would break. It was not chosen. `btree_gist` is installed if Warren wants overlap enforcement later.
  - Also added `ck_cpor_case_line_window_order CHECK (window_end >= window_start)`.
- **Downgrade** can be reversed, and it cannot lose data. If any (case, product, distributor, pod_quarter) holds more than one window, it refuses with `RuntimeError`. Otherwise it restores the old 4-column grain, drops the check and drops both columns. Proven below.

### 2. Model and writers set windows; rollup uses line windows; straddle is FLAGged: PASS
- Model: `apps/api/app/models/cpor.py`. It has `window_start`/`window_end` NOT NULL, the 5-column `UniqueConstraint` and the `window_order` check.
- New helper `apps/api/app/services/cpor/line_window.py`. It holds `is_week_aligned`, `straddle_weeks` (the Mondays of any week cut mid-week), `default_line_window(case)`, `effective_line_window` (the line window, or the case window when the line has none), `line_window_info` and `follow_case_window`.
- Writers:
  - `create_line`: `default_line_window(case)`.
  - `split_layers`: copies the source line's window.
  - `promo_plan_builder.create_case_from_promo_draft`: uses the case window.
  - `historical_import/apply_sync._upsert_line`: writes the case window, conflicts on the 5-column grain and updates `window_end`.
- Case-window edits:
  - `patch_case` (draft/rejected only; EDITABLE_STATUSES) and a historical re-import of an existing case call `follow_case_window`. This moves only the lines still on the **old case window** to the new one. Lines with their own window are left alone. Without this, a re-import that changed the case window would insert duplicate lines instead of updating them.
  - `patch_case` now also returns 400 when `window_end < window_start` (or a window is nulled). Before, the DB would have failed.
- `settlement._claim_in_window(case, sale_date, raw, line=None)` tests the **line** window when it is given a line. `rollup_result_qty_from_claims` now counts, per line, the claims for its product dated inside that line's window.
  - Claims are daily, so a claim is either in or out. Nothing is pro-rated.
  - A line whose window cuts a Mon–Sun week is reported in `window_flags` / `window_week_straddle_lines`.
  - Consolidation lines gain `window_start`, `window_end`, `window_week_aligned`, `straddle_weeks`, and flag `window_week_straddle`. This is API-only. The web does not reference these flags today, so there is no UI change.
- **Behaviour is unchanged for today's data:** every line window equals its case window, so each line gets the same in-window and override claim totals as before. The existing `test_rollup_sets_result_qty` still passes unchanged.
- CST divergence and claim-import `out_of_window` flags stay on the **case** window (the case span, per the BACKLOG regression trap).
- Tests: `apps/api/tests/test_cpor_line_window_n0050.py` (9 tests):
  - the Mon–Sun helpers;
  - model grain and NOT NULL;
  - the single alembic head and its down-revision;
  - a rollup split across a superseded line and its successor (5 + 5; a claim after the case end counts in neither);
  - a mid-week boundary: flagged, whole days counted, no pro-rating;
  - override claims: counted with one window, reported unplaced with two;
  - on **cip_test**, inside a rolled-back transaction:
    - two windows are stored for one grain;
    - a duplicate `window_start` is rejected;
    - `window_end < window_start` is rejected;
    - `follow_case_window` moves only the lines that are on the case window.

### 3. Proof on cip_test only, with numbers: PASS
Evidence: `p0_cip_test_public_to_0022.txt`, `p1_prove_cip_test.txt` (final run), `p1a_prove_cip_test_first_run.txt` (first run; its "violating_groups 2" counted NULL-`pod_quarter` groups, which PG treats as distinct, so the query was corrected), and scripts `run_alembic_cip_test.py` / `prove_cip_test.py`. Every write is preceded by `current_database() = cip_test`. Credentials are never printed. Alembic is pointed at cip_test with `CIP_SMOKE_MIGRATE=1` and both sync URLs swapped (the migrate URL guard).

- **Step 0:** cip_test.public was at `20260818_0019`. It was upgraded to `20260906_0022` (0020, 0021, 0022 applied, rc 0).
- **Phase A: representative copy.** All of cip's `cpor_case` (311) and `cpor_case_line` (658) were copied, read-only COPY out of cip as of 2026-09-24 (at 0022). They went into scratch schema `n0050_scratch` inside cip_test, with its own `alembic_version=20260906_0022`, the PK, the same-named grain unique and the case FK. Dim FKs were omitted because the migration does not touch them. Alembic ran with `search_path=n0050_scratch`.

| step | cases | lines | window cols | windows populated | = case window | lines not week-aligned (flagged) | cases not week-aligned | new-grain violations | grain |
|---|---|---|---|---|---|---|---|---|---|
| A0 before (0022) | 311 | 658 | 0 | n/a | n/a | n/a | n/a | n/a | 4-col |
| A1 upgrade → 0023 | 311 | 658 | 2 | 658 / 658 | 658 | **610** | **292** | **0** | 5-col + check |
| supersede probe | successor line for line 1 (case 4) from `window_start+7` **stored**; same-`window_start` duplicate **rejected** (UniqueViolation); `downgrade` **refused** (rc 1, "1 … groups hold more than one line window"); probe row deleted | | | | | | | | |
| A2 downgrade → 0022 | 311 | 658 | 0 | n/a | n/a | n/a | n/a | n/a | 4-col |
| A3 upgrade again | 311 | 658 | 2 | 658 / 658 | 658 | 610 | 292 | 0 | 5-col + check |

Two groups share the old grain because `pod_quarter` is NULL. PG unique treats NULLs as distinct, so they were already allowed. They were present before and after (`null_key_dup_groups_allowed = 2`). They are not violations.
Scratch schema dropped at the end, which removes the copied rows (`exists after drop: 0`).

- **Phase B: cip_test.public** (the 3 test cases and 4 lines already there):
  - B0 0022: 3 / 4, no window columns.
  - B1 upgrade: 4/4 populated, 4 equal to the case window, 4 not aligned (2 cases), 0 violations.
  - B2 downgrade: 3 / 4, columns gone, 4-column grain.
  - B3 upgrade: same as B1.
  - **cip_test.public is left at `20260924_0023`**, because the tests need it. The tests' own rows were rolled back: 0 `N0050-Q` rows remain.

### 4. Ready for cip (Warren, needs an explicit "run"): READY, NOT APPLIED
Today's read-only cip (2026-09-24, `probe_cip_ro.py`):
- alembic `20260906_0022`.
- `cpor_case` 311, of which 294 are not Mon–Sun and 0 have a null or inverted window.
- `cpor_case_line` 658 (10 with NULL `pod_quarter`).
- Cases with lines that are not week-aligned: **292**, covering **610** lines.
- Old-grain groups with more than one row: 2 (NULL pod).

Commands, from the repo root, in PowerShell:
```powershell
# 1. Backup first (whole DB, custom format)
pg_dump -h localhost -U cip -d cip -Fc -f "C:\Users\warren_eliason\cip_backup_pre_0023_$(Get-Date -Format yyyyMMdd_HHmm).dump"
# 2. Upgrade (from apps/api; DATABASE_URL_SYNC(_MIGRATE) = cip as normal)
(cd apps/api; .venv\Scripts\python.exe -m alembic upgrade head)     # expect: Running upgrade 20260906_0022 -> 20260924_0023
# 3. Verify
.venv\Scripts\python.exe .eif\audit\PROGRAMME_20260924\n0050\probe_cip_ro.py
```
Expected after the upgrade:
- alembic `20260924_0023`;
- 311 cases and 658 lines (unchanged);
- 658/658 windows populated and equal to the case window;
- 610 lines on 292 cases flagged not week-aligned;
- 0 new-grain violations;
- `uq_cpor_case_line_grain` = `UNIQUE (case_id, product_id, distributor_id, pod_quarter, window_start)`.

(If rows are added before the run, the line count moves by the same number.)

Rollback: `alembic downgrade 20260906_0022`. It refuses only if a supersede has already stored two windows for one grain.

**Release ordering (important):** from commit `d8b2e7ac`, the API model selects `cpor_case_line.window_start/window_end`. **Do not restart or rebuild the API against cip with this commit until the cip upgrade has run.** Otherwise every CPOR line read fails with "column does not exist". The currently running API process (older code) is unaffected until it restarts. Run the migration first, then restart the API.

### 5. pytest via cip_test: PASS
`pytest_cip_test.py` (n0048 pattern, prints `pytest DB -> /cip_test`) over all `tests/test_cpor_*.py` plus `test_rbac_n0038_cpor_roles.py`, `test_promo_plan_builder.py`, `test_settlement_desk.py`, `test_settlement_book_read.py` and `test_scaffold_reader_migration_u6.py`: **270 passed, 1 skipped** (`p2_pytest_cip_test.txt`).
- The skip is `test_cpor_settle_confirm_clone.py`. It skips when `cip_ns4_settle_clone` (0020) is not at the script head, so it was already skipping before this change.
- ruff is not installed in the venv, so no lint run.

## Files changed (commit d8b2e7ac)
- `apps/api/alembic/versions/20260924_0023_cpor_case_line_window.py` (new)
- `apps/api/app/services/cpor/line_window.py` (new)
- `apps/api/app/models/cpor.py`
- `apps/api/app/services/cpor/settlement.py`
- `apps/api/app/api/v1/endpoints/cpor_cases.py`
- `apps/api/app/services/cpor/historical_import/apply_sync.py`
- `apps/api/app/services/cpor/promo_plan_builder.py`
- `apps/api/tests/test_cpor_line_window_n0050.py` (new)
- `docs/BACKLOG.md` (BACKLOG-137 status line)

N-0047's modified files (`product_import_sync.py`, `product_master_workflow.py`) were not staged.

## Open questions for Warren (not decided here)
1. **Non-aligned case windows (292 of the 309 cases with lines).** Today they are copied as-is and flagged `window_week_straddle`. Should a future supersede writer on such a case:
   - (a) keep the case's own start/end days for the first and last line;
   - (b) snap new line windows to Mon–Sun inside the case; or
   - (c) treat the case week as the case's own weekday cycle (the spec's "per-case override")?

   Nothing snaps today.
2. **Out-of-window override claims when a product has two windows.** The override was designed against the case window. With several line windows it is unclear which line it belongs to. It is now reported as `override_claim_units_unplaced` and not counted. Options:
   - (a) the last line;
   - (b) the line nearest the claim date;
   - (c) the operator picks.

   No cip data is affected today, because every product has a single window.
3. **Overlap enforcement.** The grain stops two lines with the same `window_start`. It does not stop overlapping windows with different starts. Should an overlap guard (gist exclusion, or a service check in the supersede writer) come with the supersede writer?
4. **Historical staging rows carry per-row `window_start/window_end`.** The case window is their min/max. Lines currently take the **case** window (as the node asks). Should historical lines keep their own row windows?
5. **Pre-existing:** 2 duplicate-grain groups on cip where `pod_quarter` is NULL. NULLs never conflict, so historical re-import of NULL-pod lines inserts instead of updating. This is not changed here. `NULLS NOT DISTINCT` (PG18) would first need those 2 groups resolved.

## Blocked / grants
None. No writes to cip. The programme CLI was not run.
