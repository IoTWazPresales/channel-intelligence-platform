# N-0116 backend execution unit: case identity and widget date context

Run `RUN-20261024-N0116-IMPL-CODEX`, branch `feat/ns-2-brief-nav-collapse`.
This bounded backend unit extends the original scope; it does not accept or complete N-0116.

- S19 uses existing local breakdown metadata, base join and tenant predicate to return CPOR
  case_id/case_name. Named local columns are ORM-validated; case filters use the existing integer
  ID validator. Duplicate/null names, typed filters, tenant isolation and portfolio parity are tested.
  The CPOR starter's existing table now includes cases and outcomes, still eight widgets.
- S17 validates/preserves optional dashboard ignore_filters and fixed_window in definition_v2,
  without a new writer or migration. Fixed dates override caller dates, widget-owned filters stay,
  and fixed-window definitions are v2-only. Existing create/edit/promote/report paths retain them.
- Saved report downloads now use the existing v2 delivery query helper for v2-only definitions.
  XLSX/PDF and delivery context declare requested dates, truncation and returned/group counts.
  Legacy execution/access checks remain. No scheduled job or external delivery was triggered.
- Display comparison is validated as a boolean for the frontend continuation.

## Executed evidence

Identity probe: `cip_test / 20261023_0048`; never production cip.

`apps/api/.venv/Scripts/python.exe apps/api/scripts/db_on.py pytest --junitxml=../../.eif/audit/PROGRAMME_20261024/api-original-scope.xml`

Result: **3,376 passed, 21 skipped, 7 existing warnings, exit 0, 660.52 seconds**.
The full run collected before the later authenticated-test file existed; those tests are outside
this backend commit, with separate results in the continuing execution record.

Focused regression evidence: S19 red 3 failures, final 81 passed; S17 final 47 passed; export
regressions red 2 failures, final related set 55 passed. The later real delivery integration
passed in `fixed-delivery-db-corrected.xml` (3 tests: two mocked exports, one real rolled-back
delivery). Initial delivery fixtures lacked required customer/tenant rows; corrected in the test.

Code/evidence review is documented in `VERIFY_ORIGINAL_SCOPE.md`, a bounded fresh-context review,
not an attested R3 independent-model gate. Final frontend/browser evidence and the unresolved
full-screen focus regression belong to the next execution unit. Root lint passed with 50 existing
warnings. Full web pre-push verification is still running when this report is written.

Original stock-cover/restock/value/open-case semantics, missing model/calculation/calendar
capabilities and original acceptance remain open, never accepted permanent deferrals. No migration,
deployment, API/worker restart, main change or control-plane staging bypass occurred.
