# N-0048 — cpor_case status vs workflow_status drift (BACKLOG-139) — implementation evidence

Implementation subagent, 2026-09-24. This work picks up where a previous implementer stopped at its usage limit: its uncommitted diff (4 API files and the repair script) was reviewed, kept, tested and finished. Lenses applied: database-specialist, backend-engineer, test-engineering-specialist.
Nothing was written to `cip`. All writes went to the assigned clone `cip_ns4_settle_clone` (alembic `20260902_0020`, data to 2026-09-02).

## Acceptance criteria

### 1. Drift measured on cip, read-only, with event history: PASS
`ro_sql.py` (read-only session), `current_database() = cip`, 2026-09-24:

| status | workflow_status | origin | count |
|---|---|---|---|
| cancelled | draft | native | 1 |
| cancelled | ended | historical_import | 1 |
| settled | ended | historical_import | 2 |
| (all other 310 rows agree) | | | |

The same 4 rows as N-0030 (2026-09-21): 4 of 311 rows in total. Each row's history:

| id | case_code | status / workflow_status | events (cpor_case_event) |
|---|---|---|---|
| 3 | BATCH0-SMOKE-001 (intelligence_exclude=true) | cancelled / draft | `created` 2026-07-09 16:44:20; `transition_cancel` draft→cancelled 16:44:20.99 ("batch0 soft void") |
| 309 | C26761655 | settled / ended | `historical_import` ×2 on 2026-08-13 (job 978); `transition_settle` ended→settled 2026-08-26 16:51 by admin |
| 310 | C26759823 | cancelled / ended | `historical_import` 2026-08-13 (job 978); `transition_cancel` ended→cancelled 2026-08-16 17:14 (no actor recorded) |
| 311 | C26760971 | settled / ended | `historical_import` 2026-08-13 (job 978); `transition_settle` ended→settled 2026-09-08 14:17 by admin |

**Root cause (all 4 rows):** each one's last event is a `transition_cancel` or `transition_settle`. At the start of this node, `transition_case` (`apps/api/app/api/v1/endpoints/cpor_cases.py`) set `workflow_status` only on propose, approve, reject and resend. It left `workflow_status` at its old value on activate, end, settle and cancel.

### 2. Owner column, with reasoning from code: PASS (`status` owns; `workflow_status` is a projection)
All reads and writes of `cpor_case.workflow_status`, from a repo-wide grep of `apps/` (the other `workflow_status` hits are `promo_plan_export`, a separate table: `promo_exports.py` and `seed_demo.py`):
- **Writes:** create endpoint `cpor_cases.py:747` (`"draft"`); `promo_plan_builder.py:1034` (`"draft"`); `transition_case` (propose/approve/reject/resend only, before this change); historical import `historical_import/apply_sync.py:194,207` (`= status`); payment-evidence shell `payment_evidence/apply_sync.py:67` (`"imported"`, while `status` = `"draft"`).
- **Reads:** serialised only: `_case_json` `cpor_cases.py:260`, the `case_supersession.py:51` snapshot, and the web type `apps/web/src/features/promotions-funding/types.ts` (tests only; no web component filters or branches on it). **No reader filters on `workflow_status`.**
- `status` is what every lifecycle rule uses: `lifecycle.py` (the transition table, `can_transition`, `EDITABLE_STATUSES`), the settle gates and every list/filter. BACKLOG-139 "Behavior to retain" states the lifecycle is on `status`.

**Decision (recorded as proposed):** `status` owns the lifecycle. `workflow_status` is the projection `workflow_status_for(status)` in `apps/api/app/services/cpor/lifecycle.py`: `proposed` → `pending_approval` (keeps the value the propose/resend path already wrote), and every other status maps to itself. Every writer now calls it. That is option (a) in BACKLOG-139. The column is not dropped (the model, API contract and web type still carry it), so no schema change is needed.

**Row values that could be a business judgement:** none of the 4 repairs needs one. Each row's `status` came from an explicit, event-logged transition, and the repair changes only `workflow_status` to match it (`status` is never touched). Questions for Warren are below (they don't block this node).

### 3. Writer fixed, with a test: PASS
- `cpor_cases.py:1433-1434`: one `case.workflow_status = workflow_status_for(case.status)` after every transition branch. It replaces the 4 hand-written assignments.
- `historical_import/apply_sync.py:194,207` and `payment_evidence/apply_sync.py:67` now use `workflow_status_for(...)`. The payment-evidence shell used to write `"imported"` while `status` was `"draft"`; it now writes `"draft"`. No cip row has `workflow_status='imported'` (measured above), and the case's source is already recorded in `origin='payment_evidence'` plus the `shell_from_payment_evidence` event.
- `create` and `promo_plan_builder` write `status="draft", workflow_status="draft"`, which already equals the projection. They were left unchanged.
- New test `apps/api/tests/test_cpor_workflow_status_projection.py` (mocked, no DB):
  - it checks the projection for every lifecycle status;
  - it is parametrised over **every legal transition** (14 cases, including ended→settle, ended→cancel and draft→cancel, the 3 shapes that drifted); each case starts from a stale `workflow_status` and asserts the result equals the projection;
  - it covers the payment-evidence shell writer;
  - `plan_repair` on the **4 cip shapes** plus controls: exactly ids 3, 309, 310 and 311 are planned, with `after == status`;
  - idempotence: running the plan a second time gives no changes.
- **Negative control:** I removed the one projection line and reran the test: `14 failed, 5 passed`. I then restored the line (the diff stat is unchanged).

### 4. Idempotent repair script, proven on the clone: PASS (the clone has 3 of the 4 rows)
Script: `apps/api/scripts/ops/repair_n0048_cpor_case_status_drift.py`.
- Dry run is the default (the transaction is rolled back). `--apply` commits. `--expect-db` must equal `current_database()`, otherwise it exits 2. `--db` picks the database.
- It prints `current_database()` at connect and again before the write.
- The UPDATE is guarded on the old value (`workflow_status IS NOT DISTINCT FROM :old`). Each repaired row gets one `cpor_case_event` (`workflow_status_repair`, before/after in the payload, actor `ops:N-0048`). `status` and `updated_at` are not changed.
- Before-values go to `.eif/audit/PROGRAMME_20260924/n0048/before_<db>_<mode>_<utc>.json`.

The clone (vintage 2026-09-02) has **3 of the 4 rows**: ids 3, 309 and 310. It lacks **311**, because 311 was settled on 2026-09-08, after the clone was taken; on the clone 311 is ended/ended. The unit test `test_repair_plans_exactly_the_four_cip_shapes...` covers all 4 cip shapes, 311 included.

| run | file | before (rows / status≠ws / ws≠projection) | rows updated | after |
|---|---|---|---|---|
| guard: `--expect-db cip` on clone | `clone_0_expectdb_guard.txt` | — | STOP, exit 2 | — |
| dry run | `clone_1_dryrun.txt` | 311 / 3 / 3 | 3 (rolled back) | 311 / 0 / 0 |
| apply | `clone_2_apply.txt` | 311 / 3 / 3 | 3 | 311 / 0 / 0 |
| second apply | `clone_3_second_apply.txt` | 311 / 0 / 0 | **0** | 311 / 0 / 0 |

Checked afterwards (`clone_4_after.txt`, clone): rows 3, 309 and 310 now have `workflow_status` equal to `status`; `updated_at` is unchanged; there are 3 `workflow_status_repair` events; the count by status is unchanged (cancelled 23, draft 3, ended 75, settled 210). `cpor_case` has no user triggers.
cip afterwards, read-only: 4 rows still drift and there are 0 repair events, so cip is untouched.
Before-values files: `before_cip_ns4_settle_clone_dryrun_20260924T125900Z.json` and `before_cip_ns4_settle_clone_apply_20260924T125939Z.json`.

### 5. Tests pass; ready-for-cip command: PASS
`tests/conftest.py` treats `test_cpor_cases_api.py` as write-capable and refuses it when the database is `cip`, even though the file is fully mocked. So the whole set was run with `DATABASE_URL(_SYNC)` pointed at `cip_test` through `.eif/audit/PROGRAMME_20260924/n0048/pytest_cip_test.py` (it rewrites only the database name and prints no URL):

```
apps/api/.venv/Scripts/python.exe .eif/audit/PROGRAMME_20260924/n0048/pytest_cip_test.py -q -p no:cacheprovider \
  tests/test_cpor_cases_api.py tests/test_cpor_workflow_status_projection.py tests/test_cpor_case_supersession.py \
  tests/test_cpor_historical_import_h1.py tests/test_cpor_historical_unit_c.py tests/test_cpor_payment_evidence_code.py \
  tests/test_cpor_payment_evidence_parser.py tests/test_payment_evidence_overlay.py
pytest DB -> /cip_test
90 passed in 17.13s
```

**Ready-for-cip (Warren runs, from `apps/api`; expected result: 4 rows, ids 3/309/310/311, then 0 on the second apply):**
```
.venv/Scripts/python.exe scripts/ops/repair_n0048_cpor_case_status_drift.py --expect-db cip
.venv/Scripts/python.exe scripts/ops/repair_n0048_cpor_case_status_drift.py --expect-db cip --apply
.venv/Scripts/python.exe scripts/ops/repair_n0048_cpor_case_status_drift.py --expect-db cip --apply   # idempotence: rows updated 0
```
Note: the dry run executes the UPDATE inside a transaction and rolls it back, so it is a write attempt on cip. That is why this node did not run it on cip. Deploy the code fix before the repair, otherwise the next settle or cancel creates new drift.

## Files changed
- `apps/api/app/services/cpor/lifecycle.py`: `workflow_status_for` projection
- `apps/api/app/api/v1/endpoints/cpor_cases.py`: one projection after every transition
- `apps/api/app/services/cpor/historical_import/apply_sync.py`: uses the projection
- `apps/api/app/services/cpor/payment_evidence/apply_sync.py`: shell case uses the projection (`imported` → `draft`)
- `apps/api/scripts/ops/repair_n0048_cpor_case_status_drift.py` (new)
- `apps/api/tests/test_cpor_workflow_status_projection.py` (new)
- `docs/BACKLOG.md`: BACKLOG-139 status line
- Evidence: this folder (`IMPL.md`, `clone_*.txt`, `before_*.json`, `pytest_cip_test.py`)

Commit: see the orchestrator's report and `git log` (the commit is created after this file is written).

## Questions for Warren (FLAG, not blocking)
1. **Case 3 `BATCH0-SMOKE-001`** is a smoke-test row (cancelled, `intelligence_exclude=true`). The repair only aligns its `workflow_status`. Should the row stay in cip? Options: keep as is (the current behaviour), or retire it in a separate, explicit step.
2. **Case 310 `C26759823`** was cancelled from `ended` on 2026-08-16, and the event has no actor. The lifecycle allows ended→cancelled (zero payable). The repair follows `status`, so the cancel stands. If the cancel was a mistake, the right fix is a separate status correction, not this repair.
3. **Observation, out of scope:** re-applying a historical import job overwrites `status` on an existing `historical_import` case (`historical_import/apply_sync.py:204`). Re-running job 978 would put 309, 310 and 311 back to `ended` and lose their settle/cancel. The projection keeps the two columns aligned but does not stop that overwrite. Should a re-import skip cases that have lifecycle transitions after the import? I did not change this; it needs a decision.

## Blocked / grants needed
None.
