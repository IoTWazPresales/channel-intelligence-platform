# GOV-008 independent review — N-0050 (BACKLOG-137, cpor_case_line week-aligned windows)

Reviewer: verification-controller (independent session), lenses: database-specialist,
release-migration-manager, test-engineering-specialist. Model: Claude Sonnet 5
(claude-sonnet-5). No browser used (schema/data node, brief says none needed).
Did not open `.eif/audit/PROGRAMME_20260924/n0050/` (implementer's audit folder,
including IMPL.md) — all evidence below is from the repo, git history and direct
read-only SQL.

## Acceptance criterion 1: migration written; upgrade/downgrade proven on cip_test; NOT applied to cip; listed ready-for-cip

### (a) Upgrade adds window columns, backfills verbatim (no pro-rating), changes grain so two windows/SKU coexist, D-058 preserved

**PASS.** VERIFIED.

- `apps/api/alembic/versions/20260924_0023_cpor_case_line_window.py` (revision `20260924_0023`,
  `down_revision = "20260906_0022"`):
  - `upgrade()` adds `window_start`/`window_end` (Date, nullable at first), backfills with
    `UPDATE cpor_case_line l SET window_start=c.window_start, window_end=c.window_end FROM cpor_case c WHERE c.id=l.case_id`
    — a straight copy, no date arithmetic/snapping — then sets both NOT NULL.
  - Adds `ck_cpor_case_line_window_order` = `window_end >= window_start`.
  - Drops and recreates `uq_cpor_case_line_grain` as
    `(case_id, product_id, distributor_id, pod_quarter, window_start)` — same name (so the
    historical-import `ON CONFLICT ON CONSTRAINT uq_cpor_case_line_grain` upsert keeps working),
    now able to hold two rows for the same SKU with different `window_start`.
  - Re-verified directly on cip_test (not from implementer output), read-only SQL via
    `ro_sql.py --db cip_test`:
    ```
    select constraint_name, constraint_type from information_schema.table_constraints
     where table_name='cpor_case_line' and constraint_type in ('UNIQUE','CHECK')
    -> ck_cpor_case_line_window_order (CHECK), cpor_case_line_window_end_not_null (CHECK),
       cpor_case_line_window_start_not_null (CHECK), uq_cpor_case_line_grain (UNIQUE), ...

    select column_name, ordinal_position from information_schema.key_column_usage
     where constraint_name='uq_cpor_case_line_grain' order by ordinal_position
    -> case_id(1), product_id(2), distributor_id(3), pod_quarter(4), window_start(5)
    ```
  - D-058 ("terms never mutate after approval… changes supersede with week-aligned windows",
    `docs/STEWARD_ENGINE_DECISIONS.md:714-722`) is respected: `follow_case_window()`
    (`apps/api/app/services/cpor/line_window.py:69-97`) is the only code path that moves a
    line's window onto a new case window, and its one caller in `patch_case`
    (`apps/api/app/api/v1/endpoints/cpor_cases.py:801-848`) is gated by
    `if case.status not in EDITABLE_STATUSES: raise 409` (`EDITABLE_STATUSES` = draft/rejected,
    file:810-814) — so an approved case's line windows cannot be rewritten via that path.
    The other caller is historical re-import (`apply_sync.py:200-208`), which is a distinct,
    explicitly out-of-approval-flow re-sync path, same pattern as the rest of that module.
  - `git show d8b2e7ac -- docs/BACKLOG.md`: BACKLOG-137 entry updated to
    "Code done + cip_test proven, cip `alembic upgrade head` pending Warren's 'run'" —
    matches the "listed ready-for-cip, not applied" requirement.
  - Rollup uses **line** windows, not case windows: `settlement.py` `_claim_in_window(case, sale_date, raw, line=None)`
    now takes an optional `line` and uses `effective_line_window(line, case)` when given;
    `rollup_result_qty_from_claims` iterates lines and sums each line's own in-window claims
    per product (file: `apps/api/app/services/cpor/settlement.py:33-155`). A straddling week
    (start/end not Mon/Sun) is recorded as `window_week_straddle` in `window_flags`/`line_flags`,
    never pro-rated — `line_window.py:33-42` computes whole boundary weeks, and the rollup counts
    whole-day claims only (no fractional units anywhere in the diff).

### (b) Downgrade is lossless or refuses

**PASS** (code review; not executed by this reviewer — see limitations). ASSERTED.

`downgrade()` (`20260924_0023_...py:59-78`) first runs
`SELECT count(*) FROM (SELECT case_id,product_id,distributor_id,pod_quarter FROM cpor_case_line GROUP BY 1,2,3,4 HAVING count(DISTINCT window_start)>1) d`
and raises `RuntimeError(f"downgrade refused: {collisions} ... groups hold more than one line window; the pre-0023 grain cannot store them")`
if any group has more than one window — i.e. it refuses rather than silently collapsing two
supersession windows into one grain row. Only when no such collision exists does it restore the
old 4-column unique constraint and drop `window_start`/`window_end`. Dropping the two columns is
the expected effect of reverting the feature (that data has nowhere to live in the old schema),
not an unsafe silent loss of other data.

### (c) cip is still at 20260906_0022 and cpor_case_line has no window columns

**PASS.** VERIFIED, read-only SQL, this session:

```
$ ro_sql.py --db cip "select version_num from alembic_version"
current_database() = cip
version_num
20260906_0022

$ ro_sql.py --db cip "select column_name from information_schema.columns
   where table_name='cpor_case_line' and column_name in ('window_start','window_end')"
current_database() = cip
column_name
(no rows)
```

### (d) cip_test's current alembic version; no copied production rows left in cip_test

**PASS.** VERIFIED, read-only SQL, this session:

```
$ ro_sql.py --db cip_test "select version_num from alembic_version"
-> 20260924_0023   (head; confirms upgrade was actually run on cip_test, not just written)

$ ro_sql.py --db cip_test "select count(*) from cpor_case"        -> 3
$ ro_sql.py --db cip_test "select count(*) from cpor_case_line"   -> 4
$ ro_sql.py --db cip        "select count(*) from cpor_case"      -> 311
$ ro_sql.py --db cip        "select count(*) from cpor_case_line" -> 658
```
cip_test's 3 cases / 4 lines are a small hand-built fixture (row contents inspected: case_id 2
and 3, product_id 1 and 6, window 2026-04-01..2026-06-30 for all four), not a subset or copy of
cip's 311/658 rows. Judgment: no production data was left behind in cip_test.

### (e) Claim rollup uses line windows; a straddling week is FLAGged, never pro-rated

**PASS.** VERIFIED by reading the service and its tests.

- Service: see (a) above — `settlement.py:33-155`, `line_window.py:29-42,57-66`.
- Tests (`apps/api/tests/test_cpor_line_window_n0050.py`, read in full):
  - `test_rollup_splits_claims_by_line_window_without_prorating` — supersede shape (old line
    Mon5–Sun11, new line Mon12–Sun18 Jan): claim on 11 Jan (2 units) goes to `old`, claim on
    12 Jan (5 units) goes to `new`; a claim after case end (20 Jan, 7 units) lands nowhere;
    asserts `old.result_qty==5.0`, `new.result_qty==5.0`, `window_week_straddle_lines==0`.
  - `test_rollup_flags_mid_week_boundary_and_counts_whole_days` — case window Thu1–Sat31 Jan
    (non-aligned): claim on 31 Dec and 1 Feb excluded (outside window, not partial-counted);
    asserts `result_qty==6.0` (only the 1 Jan claim), `window_week_straddle_lines==1`,
    `flag["flag"]=="window_week_straddle"`, `flag["straddle_weeks"]==["2025-12-29","2026-01-26"]`
    — i.e. flagged, never pro-rated.
  - `test_override_claim_single_window_counts_multi_window_unplaced` — an out-of-window override
    claim is placed only when the product has exactly one window (`single.result_qty==4.0`,
    `unplaced==0.0`); with two windows for the product it is reported unplaced
    (`old.result_qty==0.0`, `new.result_qty==0.0`, `override_claim_units_unplaced==4.0`) rather
    than guessed onto either line.
  - These three tests were **run** this session (see (f)) and **PASSED**.

### (f) Run the node's tests; if conftest refuses on cip because write-capable, do NOT repoint, record UNABLE and read them

**PASS with a stated, acceptable limitation.**

```
$ apps/api/.venv/Scripts/python.exe -m pytest tests/test_cpor_line_window_n0050.py -v -rs
tests/test_cpor_line_window_n0050.py::test_week_alignment_is_monday_to_sunday PASSED
tests/test_cpor_line_window_n0050.py::test_default_and_effective_window_fall_back_to_case PASSED
tests/test_cpor_line_window_n0050.py::test_model_grain_includes_window_start PASSED
tests/test_cpor_line_window_n0050.py::test_migration_follows_0022_single_head PASSED
tests/test_cpor_line_window_n0050.py::test_rollup_splits_claims_by_line_window_without_prorating PASSED
tests/test_cpor_line_window_n0050.py::test_rollup_flags_mid_week_boundary_and_counts_whole_days PASSED
tests/test_cpor_line_window_n0050.py::test_override_claim_single_window_counts_multi_window_unplaced PASSED
tests/test_cpor_line_window_n0050.py::test_db_grain_holds_two_windows_rejects_duplicate_and_inverted SKIPPED
tests/test_cpor_line_window_n0050.py::test_db_follow_case_window_moves_only_lines_on_case_window SKIPPED
7 passed, 2 skipped in 6.36s

short test summary:
SKIPPED [1] ...:185: schema test runs on cip_test only (current_database()=cip)
SKIPPED [1] ...:209: schema test runs on cip_test only (current_database()=cip)
```
This session's pytest env is pointed at `cip` (write-capable target), so the two DB-backed tests
self-skipped by their own guard (`if db != "cip_test": pytest.skip(...)`) rather than running or
writing to cip. Per instruction, I did **not** repoint the DB myself. UNABLE to execute those 2
tests in this session; I instead **read** them (full text above/inline in the file):
- `test_db_grain_holds_two_windows_rejects_duplicate_and_inverted` inserts two lines with
  disjoint windows on the same (case,product,distributor) key (succeeds, count==2), then in
  nested savepoints proves a duplicate `window_start` raises `IntegrityError` and an inverted
  window (`end < start`) raises `IntegrityError`; runs inside a transaction the fixture always
  rolls back (`tx.rollback()` in `finally`), i.e. it never commits to cip_test even when run.
- `test_db_follow_case_window_moves_only_lines_on_case_window` proves `follow_case_window` moves
  only lines still on the case's old window and leaves a line with its own distinct window
  untouched; same rollback-only fixture.
- Both tests' schema assumptions (grain columns, check constraint) were independently
  cross-checked against live cip_test via read-only SQL in (a)/(d) above and matched.

## Criterion 2: Nothing writes to cip

**PASS.** VERIFIED. This reviewer issued only `ro_sql.py` reads against `cip` (all confirmed
`current_database() = cip` in output) and made no edits to product source, no commits, and no
alembic invocation. cip's alembic version (20260906_0022) and column set (no window_start/
window_end) are unchanged from before this node, consistent with cip never having been written.

## Overall verdict: VERIFIED_WITH_LIMITATIONS

All six sub-criteria of criterion 1 and criterion 2 PASS. The verdict is
VERIFIED_WITH_LIMITATIONS rather than VERIFIED because:
1. Two of the node's nine tests could not be executed in this session (they self-skip against a
   non-`cip_test` database) — their content was read and their factual claims about cip_test's
   schema were independently re-derived via read-only SQL instead.
2. The downgrade path was verified by code review, not by executing `alembic downgrade` (this
   reviewer has read-only SQL access only, no alembic/write grant on cip_test).

## Limitations
- Did not open `.eif/audit/PROGRAMME_20260924/n0050/` (implementer's audit folder / IMPL.md) —
  by design, per the reviewer brief.
- No browser used — not applicable to a schema/data-migration node with no rendered UI surface
  in scope.
- `verification.independence`/GOV-008 rung: this is a fresh session (different from the
  implementation run) — R2 fresh-context independence achieved. Model used for this review:
  Claude Sonnet 5 (claude-sonnet-5).
