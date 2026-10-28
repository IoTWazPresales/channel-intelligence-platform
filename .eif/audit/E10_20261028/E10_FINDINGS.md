# E10 independent review of E6–E9: findings (2026-10-28)

Review only. Implementation change scope: NONE. No product code changed, no node or R3 acceptance claimed.
Branch `feat/ns-2-brief-nav-collapse`, reviewed commit `a4118c30` (pushed as `31d96a7a`).

Independence rung: different chat session and fresh model pass (Opus 5.5), same operator workspace.
It is not a separate `--run` recorded in the programme ledger, so it does not satisfy GOV-008 provenance by itself.

## Verdict

**E10: UNVERIFIED. The E6–E9 claim does not pass.**

| Unit | Result |
|---|---|
| E6 tenant overlay (spec keys, counterpart policy) | Committed tests pass. No defect found in the probes. Non-owner RLS was not tested. |
| E7 fact models | FAIL on `shipments` semantics. `sellin` and `recorded_prices` cannot be verified because their tables are empty on `cip`. |
| E8 calendar math | FAIL. Three value defects. `share_of_total` and `running_total` are correct. |
| E9 starters | NOT MET. Cover, restock, value and open still refuse. |

## Evidence

- `probe_e10.py` writes `probe_output.txt`.
  - Part A seeds `cip_test` and rolls the data back.
  - Part B runs read-only on `cip`, with `set_config('cip.product_lines','*',true)` and a 60 s statement timeout.
- `run_focused.py` writes `focused_tests.txt`.
  - It runs the committed tests `test_query_tenant_overlay_e6.py`, `test_query_model_e7_e8.py`, `test_query_model_graph.py` and `test_query_model_db.py` on `cip_test`.
  - Result: **53 passed**.
  - These tests check prior-year, running total and share as SQL text only, not as values. That is why the defects below pass the suite.

## Defects

1. **Prior year is null whenever a date window is set** (A1 compared with A1b).
   - With a 2026-03..04 window, the March 2026 prior year comes back None. It should be 100.
   - Without the window it is correct (100).
   - Cause: the compiler widens the window only for the previous period, so rows from a year earlier are never read.

2. **Sunday-week calendar with a previous-period comparison loses the first bucket** (A2 compared with A2b).
   - With the window starting mid-week on 2026-03-04, the rows add up to 14 against a total of 19. Without the comparison they add up to 19.
   - Cause: the row trimming and widening use the Gregorian, Monday-week `bucket_start_of` and `prev_bucket_start`, not the tenant calendar.

3. **Previous period is always null on the 4-4-5 retail calendar** (A3).
   - P04 FY26 should show the P03 FY26 value, 22.
   - Cause: the previous-period join uses `bucket_start - interval '1 month'`, which never lands on a retail period start.
   - Prior year on retail calendars has the same `interval '1 year'` shape and is likely affected too. That was not probed.

4. **Shipments count open order lines alongside their shipped twins** (B1/B2).
   - On `cip` there are 1,775 `open_order` lines totalling 127,870 units. None has a `ship_confirm_date`.
   - Under the strict-pair twin rule (D-0057/D-0065), only 85,250 open units should count.
   - A request with no window sums every line state, so about 42,620 units are double counted.
   - With a period breakdown and no window, the open lines form a null period bucket.

5. **Shipments group customers by `customer_id`** (B3).
   - 1,231 lines have a null `customer_id` but a set `resolved_customer_id`, so they show as Unassigned.
   - The customer stock-gap reader uses `resolved_customer_id`. The two surfaces disagree.

6. **Retail calendar CASE performance** (B7, risk rather than a defect).
   - At week grain the platform path takes 265 ms. The `retail_445` CASE path takes 1,858 ms, about 7× slower.
   - At 10× data volume this would approach the 10 s statement timeout.

## Not verified (coverage limits)

- `sellin` day floor: `fact_sales_sellin` is empty on `cip`.
- `recorded_prices` values: `fact_pricing` is empty on `cip`. The source does match `/pricing`.
- Not run:
  - non-owner RLS and performance as a non-owner role
  - authenticated caller matrix
  - accessibility and journey checks in the browser
  - export and delivery parity
  - full regression suite
- Prior year on the retail and Sunday-week calendars.

## Correct as probed

- `share_of_total` adds up to 1.0.
- `running_total` is correct per customer partition.
- Lineup: no case has a null `commercial_status` (0 of 36).

## Proposed fix unit (not authorised by this review)

Calendar-aware bucket arithmetic: the previous and year-ago bucket joins and the window widening should go through `BusinessCalendar`, not intervals. Prior year should widen the window. The `shipments` model should apply the twin rule and `resolved_customer_id`. The calendar CASE should be replaced, for example with a calendar dimension join. Add value-level tests for every calculated kind on every calendar type.
