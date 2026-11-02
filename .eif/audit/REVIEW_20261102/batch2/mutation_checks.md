# Batch 2: mutation checks (new tests run with the fix removed)

| Fix | Test file | With fix removed | Result |
|---|---|---|---|
| M3 | `test_batch2_m3_migrated_report_rows.py` | `... and not definition.get("migrated_from")` removed | 1 failed (`test_migrated_v1_report_keeps_all_522_rows_in_v1_order`), 1 passed (the control, which must pass) |
| M4 | `test_batch2_m4_schedule_recipients.py` (4) | runner reverted to HEAD | 4 failed of 4 |
| M5 | `test_batch2_m5_tenant_scope.py` (5) | `shipping_water.py` and `shipment_inbound_facts.py` reverted to HEAD (migration kept) | 4 failed, 1 passed (the control that checks a tenant still sees its own earlier report) |
| M6 | `test_batch2_m6_overlay_walk.py` (4) | `tenant_restrictions.py` and `catalog.py` reverted to HEAD | 4 failed of 4 |
| M7 | `test_batch2_m7_period_grains.py` (21) | `loader.py`, `graph.py`, `catalog.py`, `default.yaml` reverted to HEAD | 11 failed, 10 passed (the 10 are controls: month/quarter/year still accepted, day-floored facts keep day and week) |
| M8 | `test_batch2_m8_window_weeks_calendar.py` (4) | `calc.py` and `execute.py` reverted to HEAD | 3 failed, 1 passed (platform-calendar control) |
| M9 | `table.test.ts` (+4) | `table.ts` reverted to HEAD | 3 failed, 1 passed (the Unassigned control) |
| Web exporters (minor) | `csvFormulaGuard.test.ts` (4) | `gridFind.tsx` and `dsiProductCandidateExport.ts` reverted to HEAD | 2 failed (grid params carry the guard; DSI token guarded), 2 passed (the helper's own unit tests) |
| Python exporters (minor) | `test_batch2_export_formula_guard.py` (4) | CPOR, lineup xlsx/csv, lineup customer, promo exporters reverted to HEAD | 3 failed, 1 passed (the shared helper's own unit test) |
| Vessel badge (minor) | `onTheWater.rules.test.ts` (+2) | `format.ts` reverted to HEAD | 2 failed, 11 passed |
| Book minors (older guard per unit, partial shipment, orphan quantity, two orphans, audit at load, pointer scope, reclassify scope, remembered sheets) | `test_batch2_book_minors.py` (16), run by `batch2/mutate.py` | each fix broken alone | all 8 mutations caught: 2, 1, 1, 1, 2, 1, 1, 2 tests failed |
| API minors (widget saved report reference, per-week report without dates, port code, NaN body) | `test_batch2_api_minors.py` (4), run by `batch2/mutate.py` | each fix broken alone | all 4 mutations caught (1 test failed each). Note: a report of another tenant is already invisible to the endpoint's session (ORM tenant filter), so the review's stored id 987 was an id that exists nowhere; the test covers both. |
| Vessel card, API side (minor) | `test_batch2_vessel_minors.py` (5) | `on_the_water.py` reverted to HEAD | 4 failed, 1 passed (the unchanged/later ETA control) |
| Cleanup script for the leaked AUD-PARI facts | `test_batch2_aud_pari_cleanup.py` (3), run by `batch2/mutate.py` | each guard removed alone (dry run read-only, expected count, database name) | all 3 mutations caught (1 test failed each) |
