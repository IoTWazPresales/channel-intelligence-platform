# GOV-008 independent verification — N-0047 (BACKLOG-034)

Reviewer: verification-controller (GOV-008), extra lenses database-specialist, data-quality-governance-specialist,
test-engineering-specialist. Model: Sonnet 5 (claude-sonnet-5). No browser used (server-side data migration, no UI).
Independence rung: R2, fresh session, same model family as implementer (no cross-model consult mechanism available
here) — record per brief as the applicable rung.

Node: "Stage 4.1: dim_product inverted launch/retire windows (BACKLOG-034), proven on a clone."
Evidence: commit `e1fa2b1e`, `docs/BACKLOG.md` BACKLOG-034, `apps/api/scripts/ops/repair_n0047_dim_product_windows.py`,
run logs/CSVs in `.eif/audit/PROGRAMME_20260924/n0047/`, clone DB `cip_merged_leftover_repair`, `cip` read-only.

## Criterion 1 — inverted windows re-counted; repair rule stated; clone before/after re-counted

**PASS.**

Re-ran the count query independently against `cip` (read-only) via `ro_sql.py`:

```
apps/api/.venv/Scripts/python.exe .eif/audit/PROGRAMME_20260924/ro_sql.py --db cip
  "SELECT count(*) AS total, count(*) FILTER (WHERE retired_date < launch_date) AS inverted,
          count(*) FILTER (WHERE launch_date = retired_date) AS launch_eq_retired,
          count(*) FILTER (WHERE launch_date='1970-01-01' AND retired_date='1970-01-01') AS epoch_both,
          count(*) FILTER (WHERE retired_date <= '1970-01-01') AS placeholder_retired,
          count(*) FILTER (WHERE launch_date <= '1970-01-01') AS placeholder_launch
   FROM dim_product"
```
Result (VERIFIED, current_database()=cip): `total=18177 inverted=2795 launch_eq_retired=698 epoch_both=671
placeholder_retired=671 placeholder_launch=671`. This matches `run_cip_dryrun_readonly.txt` line 4 exactly.

Repair rule (stated in `repair_n0047_dim_product_windows.py` module docstring and `plan_row`, lines 1–24, 99–137),
first match wins:
- `rederive_excel_serial` — a placeholder side (`<= 1970-01-01`) whose newest committed PM file row has a bare
  numeric serial in that column → decode with the (fixed) `_excel_serial_to_date`. If the result is itself inverted,
  write it anyway and flag `rederived_window_inverted_in_source` (source-faithful).
- `null_placeholder` — placeholder side with no serial evidence → NULL, never guessed.
- `swap` — `retired < launch` and some committed PM file literally has the two values transposed → swap.
- `flag` — any other inversion → left untouched, listed for steward review, never written.

Re-ran the same count query against the clone `cip_merged_leftover_repair` (VERIFIED, current_database() printed):
`total=18177 inverted=2887 launch_eq_retired=27 epoch_both=0 placeholder_retired=0 placeholder_launch=0`. This
matches `run_clone_2_apply.txt` line 25 ("after") and `run_clone_3_apply_again.txt` line 3 ("before", i.e. the state
after the first apply) exactly, and the arithmetic is internally consistent: 2795 + 92 (rows newly inverted by
`rederived_window_inverted_in_source`, per the flags-by-reason count in the same log) = 2887; 698 − 671 (epoch
placeholders, which are `launch==retired` trivially) = 27.

Spot-checked one rederived row against the actual committed source file (not just the script/logs): queried
`import_job`/`raw_file_metadata` for job 88 (`Specs_new.xlsx`), opened the file from local storage
(`apps/api/storage/uploads/imports/06c7117611e848ca8755fc538c938593/Specs_new.xlsx`) and read SKU `90NB0651-M00560`'s
row directly: `ttv_date=42156, eop_date=42124` (raw Excel serials). Independently converted with the Excel epoch
(1899-12-30 + days): `42156 → 2015-06-01`, `42124 → 2015-04-30` — an exact match to the repair log's claimed
rederivation for `id=27 90NB0651-M00560: 1970-01-01..1970-01-01 -> 2015-06-01..2015-04-30`. This is a real value
traceable to the committed source cell, not a script artifact. VERIFIED.

## Criterion 2 — cip apply prepared but not run; script safety properties

**PASS.**

cip counts (above) are identical to the clone's pre-repair `before` block in every field, including
`epoch_1970_both=671` unchanged — confirms nothing has been re-derived/written on `cip`. VERIFIED (re-queried, not
just re-read from the log).

Code inspection of `apps/api/scripts/ops/repair_n0047_dim_product_windows.py`:
- Dry run is read-only: `main()` line ~322, `conn.execute(text("SET TRANSACTION READ ONLY"))` is the *first*
  statement issued on the connection whenever `--apply` is not passed, before `current_database()` is even read.
  `run_cip_dryrun_readonly.txt` line 1 prints `transaction_read_only = on`, confirming the session actually entered
  read-only mode against `cip`. Any UPDATE issued afterward would be rejected by Postgres itself, not merely by
  application logic. VERIFIED (log line + code both agree).
- `--apply` required: `ap.add_argument("--apply", action="store_true", ...)`, default `False`; `apply_changes()` is
  only called inside `if apply:` (line 275). VERIFIED (code read).
- `--expect-db` guard: `main()` compares `current_database()` to `args.expect_db` and returns 2 / rolls back on
  mismatch (lines 325–330), before `run()` is called in either mode. VERIFIED (code read).
- Before-values CSV for rollback: `_write_csv("before", ...)` writes one row per write-candidate with both
  `launch_before/retired_before` and `launch_after/retired_after` columns. Confirmed present on disk and inspected
  header + first row: `id,sku,product_line,lifecycle_status,launch_before,retired_before,launch_after,retired_after,
  rule,flag,source_job` — sufficient to reconstruct a rollback UPDATE. VERIFIED.
- Idempotent: second `--apply` on the clone (`run_clone_3_apply_again.txt`) shows `planned writes by rule: {}`,
  `rows updated: 0`, `before`==`after`. Also structurally guaranteed: `_UPDATE_SQL`'s WHERE clause pins
  `launch_date/retired_date IS NOT DISTINCT FROM` the recorded before-values, so a stale/replayed write is a no-op
  once the row has moved. VERIFIED (log + code).
- Touches only `launch_date`, `retired_date`, `updated_at`: `_UPDATE_SQL` (lines 70–73) sets exactly those three
  columns. VERIFIED (code read).
- No deletes: `grep -in "delete\|drop\|truncate"` over the script returned no matches. VERIFIED.

## Criterion 3 — writer fix (Excel-serial parsing) correct and tested

**PASS.**

`_excel_serial_to_date`/`_parse_date_val` in `apps/api/app/services/catalog/product_import_sync.py` (diff in
`e1fa2b1e`) are wired into the live upsert path, not just the repair script: `_staging_tuple` (line ~149-152) calls
`_parse_date_val(r.get("launch_date"))` / `r.get("end_of_life_date")`, and `_staging_tuple` feeds the real bulk
upsert SQL (`sql_column("launch_date", Date)` etc., lines 193, 253, 306, 341) — so future Product Master imports get
the fix, not only this one-time repair. VERIFIED (code read).

Ran the test suite:
```
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_n0047_dim_product_windows.py -q
34 passed in 5.37s
```
VERIFIED (executed by reviewer). Coverage includes: serial parsing edge cases (`bool True`, `0`, negative, NaN, None,
fractional day, `np.int64`, ISO string, `datetime`, `pd.Timestamp`), the "never becomes epoch" regression guard, the
PM-validate warning (`pm_row_inverted_window`, FLAG-not-BLOCK), and the repair rule (rederive/null/swap/flag,
idempotency, "valid windows untouched"). No other commit-touched test files exist beyond this one (`git show
e1fa2b1e --stat` lists only this test file).

## Criterion 4 — rule never guesses; downstream DSI window-gating claim

**PASS.**

Judged whether any branch of `plan_row` invents a value not evidenced by a committed source cell:
`rederive_excel_serial` uses the literal raw cell from the newest committed PM job (`load_histories`, reading each
`import_job`/`raw_file_metadata` row via the same `read_tabular`/column-mapping path the commit itself uses) —
independently spot-checked above and it decodes to the exact logged value. `null_placeholder` writes NULL when no
source evidence exists. `swap` only fires when a committed file literally has the two values transposed
(`(_parse_date_val(a), _parse_date_val(b)) == (rd, ld)` exact match against history). `flag` never writes. No branch
synthesizes a date. VERIFIED (code read + spot check).

Downstream DSI window-gating claim: `_product_eligible_for_dsi_auto` in
`apps/api/app/services/imports/distributor_sales_inventory.py` (line ~442) calls
`_product_evidence_date_outside_launch_retire_window(p, evidence_date)` and returns `False` (ineligible for
automatic resolution) when true, gated on the same `dim_product.launch_date`/`retired_date` columns this node
repairs. This function is invoked from the live SKU/part-number/alias resolution tiers (lines 963, 977, 995, 1067) —
this is a real, exercised code path, not merely a commit-message assertion. VERIFIED (code read; did not execute a
DSI resolution job end-to-end against the clone, so the *magnitude* of behavior change from this repair is ASSERTED
from the eligibility-code path being real, not independently measured with a before/after DSI resolution diff).

## Criterion 5 — nothing writes to cip

**PASS.** `cip` counts re-queried independently (criterion 1) are byte-for-byte identical to the clone's pre-repair
snapshot; the `cip` dry run entered a Postgres-enforced read-only transaction (verified via the printed
`transaction_read_only = on` plus the code path that issues that statement first); no `--apply` run against `cip`
exists in the evidence folder (`run_cip_dryrun_readonly.txt` is the only `cip` run, and it is the dry run). No writes
were made to `cip` by this review either — reviewer used only `ro_sql.py` (prints `current_database()`, SELECT-only)
and read-only file/pytest operations; a temporary spot-check script
(`apps/api/.tmp_gov008_check_serial.py`) was created to read the source `.xlsx` and deleted after use, and is not
present in the working tree.

## Dims

- **quality.data_integrity** — pass. Repair values are source-evidenced (spot-checked one exactly) or NULL; no
  branch guesses; the writer fix is wired into the real upsert path and covered by 34 passing tests.
- **quality.backup_recovery** — pass. Before-values CSV with full before/after per changed row is written before any
  apply; the WHERE-clause-pinned UPDATE makes the operation naturally reversible from that CSV.
- **quality.migration_safety** — pass. Dry run is Postgres-enforced read-only (verified via printed
  `transaction_read_only=on`, not just claimed); `--expect-db` guard verified in code; `--apply` required; idempotent
  (verified by log and by structural WHERE-clause guard); scope limited to 3 columns; no deletes.
- **verification.referent** — pass. Re-executed the `cip` and clone counts independently via `ro_sql.py` and they
  match the logged/claimed numbers exactly; re-ran the test suite and it passed; traced one rederived value back to
  the literal committed source-file cell and it matched exactly.

## Overall verdict: VERIFIED

## Limitations
- Did not independently re-execute the repair script itself against a fresh clone (would require creating another
  clone database, out of scope for a read-only review); instead independently re-derived the `cip`/clone counts from
  first principles and cross-checked one rederived row against the raw source file, which is a stronger check on the
  logged numbers than re-running the same script again would have been.
- Did not run an end-to-end DSI resolution job before/after the repair to measure the magnitude of the eligibility
  change; confirmed only that the gating code path is real and reads the repaired columns (labelled ASSERTED for
  magnitude, VERIFIED for the code path's existence).
- Independence rung is R2 (fresh session); no independent-model consult mechanism was available to this reviewer, so
  this is same-model-family verification, recorded per the brief rather than upgraded to a cross-model rung.
