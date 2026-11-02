# Batch 1 report: B1, M1, M2 from the GOV-008 review of 2 November 2026

Branch `feat/ns-2-brief-nav-collapse`, one agent session (Sonnet 5.5). Scope: B1, M1, M2 only. Nothing was written to `cip`, no migration was applied anywhere, no process was restarted. Acceptance is Warren's; this report accepts nothing. No ledger event was recorded (these fixes have no node). Same-session self-verification only (R2 limits apply: the writer also wrote the tests).

## Result

| Item | What changed | Proof |
|---|---|---|
| **B1** closed lines count as live | One shared rule, `app/services/shipment_live_line.py` (`live_line`, `live_line_sql`, `is_live_state`), built from the existing `CLOSED_LINE_STATES`. Used by every reader below. | 18 new reader tests. With the rule switched off, 16 of 17 first-run tests failed (`batch1/b1_tests_with_rule_disabled.txt`); the 17th (`net_requirement`) already excluded closed rows by its own state test. The `cst_sku_twin_disambiguate` test was added afterwards. |
| **M1** 0050 downgrade | Each `closed_superseded` row goes back to the state it had; orphan-retired open orders return to `open_order`. | 3 tests on `cip_test` (downgrade+upgrade, fixture rows, real retire functions, downgrade, compare every row). 2 fail on the old statement (`batch1/m1_tests_with_old_downgrade.txt`). |
| **M2** undated file | An undated complete-book file's fact write leaves closed facts closed and writes no second open fact for a line already open under another key. Counts reach the job and the Import Center notice. | 6 tests (probes P4, P5, plus three "must not change" cases). 3 fail with the guard off (`batch1/m2_tests_without_guard.txt`). |

## Gates

| Gate | Result |
|---|---|
| Full API pytest on `cip_test` (`apps/api/.venv`) | **3,574 passed, 24 skipped, 0 failed**, 31 min 57 s (`batch1/api_full_pytest_cip_test.log`). Review baseline 3,547; +27 are the new tests. |
| Web `tsc --noEmit` | exit 0, no output (`batch1/web_tsc.log`) |
| Web vitest (full) | **222 files, 1,205 tests passed** (`batch1/web_vitest.log`). No web file changed. |
| Lint | not run |

## B1: cip figures (read-only)

Script `batch1/cip_before_after.py`. Every transaction was set READ ONLY first and a write attempt was refused before any read (`transaction_read_only = on`, `default_transaction_read_only = on`). "Before" = the same code with the rule's closed-state list emptied (old behaviour); "after" = rule on. Raw: `batch1/cip_figures_before.json`, `cip_figures_after.json`, `cip_figures_compare.txt`. Tenant `default`.

cip facts by state: shipped 13,624 / 1,373,781 units; open_order 740 / 48,928; closed_shipped 704 / 51,586; closed_disappeared 694 / 50,707; closed_superseded 56 / 4,518; closed_moved 0.

| Figure | Before | After | Change |
|---|---|---|---|
| v2 `shipments.quantity` | 1,379,393 | 1,373,781 | **−5,612 units** (matches the review) |
| v2 `shipments.lines` | 13,700 | 13,624 | **−76 lines** (matches the review) |
| v2 `shipments.open_quantity` / `open_lines` | 48,928 / 740 | 48,928 / 740 | none (as expected) |
| Cover-distribution open inbound | 124,428 units, 392 distributor-product pairs | 45,316 units, 201 pairs | **−79,112 units, −191 pairs** (review: 79,112 closed beside 45,316 live) |
| Movement lens shipped week | W44, 670 units | W44, 670 units | none (closed rows fall outside that week) |
| Weekly flow, shipped last 13 weeks | 55,883 | 52,146 | −3,737; anchor `2026-10-26` unchanged |
| CPOR intake weighting, all products, all dates (PO-linked, price > 0) | 14,772 rows, weight 1,442,278 units, weighted price 435.78 | 13,917 rows, weight 1,381,250, weighted price 423.20 | −855 rows, −61,028 units, −2.9% on the book-wide average |
| Products with intake evidence | 2,389 | 2,385 | 4 lose all intake evidence; **153 products change** |

Intake notes: the review quoted 820 closed rows / 59,712 units; my book-wide, all-dates count is 855 / 61,028 (different scope, same order of magnitude). Largest per-product shifts: product 68263 average 6,846 → 1,004 (−85%), product 54186 3,521 → 1,036 (−71%). Product 69385 had its only intake evidence from a closed row priced 999,999 (a sentinel); it now has none. Per-product list is in the JSON.

## B1: reader list

**Changed to use the rule** (test = `tests/test_shipment_live_line_b1.py` unless noted)

| Reader | How | Test |
|---|---|---|
| v2 `shipments.quantity`, `shipments.lines` (`semantics/models/default.yaml`) | new model rule `shipment_live_lines` (`query/model/rules.py`, registered in `loader.py`); applies to the whole `shipments` model | `test_v2_shipped_quantity_and_lines_count_only_live_facts` |
| channel_ops `/cover-distribution` open inbound | query moved to `_open_inbound_by_pair`; `twin.kept` now includes the rule | `test_cover_distribution_open_inbound_...` |
| channel_ops `/movement-lens` | `twin.kept`, and the `in_max` date anchor uses `live_line` | `test_movement_lens_shipped_week_...` |
| channel_ops weekly flow (`_cover_weekly_flow`, what the review cited as `/forecasts` 1013-1024; the `/forecasts` endpoint itself reads `fact_dsi_forecast`, not shipments) | `twin.kept` and anchor | `test_forecast_weekly_flow_...` |
| `cpor/intake_weighted_mac.py` `_intake_wavg`, `_disti_cost_proxy_wavg` | via `twin.kept` | `test_intake_weighted_mac_weights_only_live_facts` |
| `shipment_strict_pair.py` `twin_remainder().kept`, `keep_counted_line`, `TWIN_KEPT_SQL` | the rule is inside them; a closed row no longer falls through as kept. This also covers `outerjoin_twin_remainder` users `inbound_lineup_quarter.py:502`, `lineup_po_auto_link.py:476`, and `net_requirement`, `lineup_bulk_rederivation`, `compiler.py` twin join | `test_twin_helpers_never_keep_a_closed_fact` (ORM, raw SQL, outer-join form) |
| Inbound-shipments list (`inbound_shipments.py`) | filters; new `include_closed=true` shows history | `test_inbound_shipments_list_hides_closed_...` |
| Lineup attribution: `lineup_distributor_attribution._eligible_ships_for_products`, `lineup_case_po_attribution_gap` (new `_live_po_bearing_ships`), `lineup_customer_token_stamp` (new `_live_ship_rows_for_pos`, two call sites) | `live_line` in the query | one test each |
| `lineup_bulk_rederivation._shipment_q1_hint` | **not in the review list.** It summed every non-open state, so closed facts counted as the shipped hint | `test_lineup_bulk_rederivation_...` |
| `po_management._observed_groups`, `lineup_po_gap._po_gap_worklist_inner` | **not in the review list.** Sums already used `state='shipped'`, but a closed fact's date could set a PO's quarter and a closed-only PO formed a group | two tests |
| `supply_overview.py` | already excluded closed rows; now spelled with the shared `live_line_sql` and `TWIN_KEPT_SQL` | `test_supply_overview_headline_...` |
| `cst_sku_twin_disambiguate._fetch_windows` | **not in the review list.** It sums inbound quantity as a tie-break | `test_cst_sku_twin_disambiguation_...` |
| `shipment_open_book.exclude_closed_inbound` | now delegates to `live_line` | existing tests |

**Already correct, left as is**
- `shipping.py`: every grid, KPI, tile, aggregate, summary and ETA-shift read goes through `_apply_fact_where_clause` (`keep_counted_line` + `exclude_closed_inbound`) or `twin_remainder`; the single-row "siblings" drill-down (line ~1774) deliberately shows a receipt group's facts with their state.
- `shipping_water.py`, `on_the_water.py`, `brief_signals.py`: filter by explicit state (`shipped`/`open_order`) or `exclude_closed_inbound`.
- `channel_ops_derived_stock.py`, `sell_through_causes.py`, `customer_stock_gap.py`, `customer_stock_gap_cause.py`, `lineup_po_auto_link.py` shipped/open branches, `woc_observation.py`: test `line_state = 'shipped'` explicitly, so closed rows never match.
- `shipping_commercial_kpis.py`, `amount_scale.py`: predicates only; they are applied inside `_apply_fact_where_clause`.

**Not filtered, and why**
- `distributors.py`, `product_usage.py`, `distributor_usage.py`, `distributor_duplicate_groups.py`, `customer_duplicate_groups.py`, `import_job_delete_figures.py`, `distributor_merge_po_consolidation.py`, `shipment_null_distributor_sibling_po_merge.py`, `product_master_gap_resolve.py`: row-linkage counts or FK updates for merge/delete safety. They must see every row, closed ones included.
- `cst_alias_era_derive.py`: `min(pod_date)` / `min(ship_confirm_date)` for first-movement dates. A closed row is still evidence of when a product first moved, and `closed_superseded` rows carry the same dates as their keeper. **Warren's call** if you want these ignored too.
- `data_integrity_audit.py`: audit tool comparing facts with evidence; closed facts are part of what it should see.
- `observation_transitions.py` / `newly_landed.py` / `shipping_digest`: read observation history for a job or for fact ids already filtered by the grid; not a quantity total.
- `shipment_inbound_facts.py`, `shipment_open_book.py`, `shipment_shipped_fact_identity_twin_merge.py`, `shipment_plan_d_cutover.py` (diagnostic), `seed_demo.py`, models, `tenant_scope.py`: writers, closers, maintenance and definitions.
- `lineup_po_reconciliation.py`, `plan_vs_executed.py`, `lineup_case_suggested_pos.py`, `query/handlers/a1_pve.py`: read `shipment_evidence_line`, not facts, and gate on explicit states.

## M1: 0050 downgrade

`20261101_0050_fact_superseded.py` now restores the prior state from what the retire leaves untouched: report type when it fixes the state (order reports are open, `xxomrpt0025_shipment` is shipped); otherwise the superseding fact is an open order → open; otherwise no ship confirm date → open, a confirm date → shipped. On cip this gives the 47 twins back as `shipped` and the 9 orphans (921 units, no confirm date) as `open_order`; not run on cip.

**One case it cannot settle** (pinned by a test so a change is noticed): an orphaned open Shipped-sheet line that has a future confirm date and whose replacement has since closed comes back as `shipped`. A column recording the prior state at retire time would remove the limit, but it needs a new migration; I did not add one.

## M2: undated complete-book file (rule proposed; Warren can overrule)

- Applies only when the file has no report date and only to the tenant's complete-book report types. Older files already wrote nothing.
- A row whose fact key is a closed fact is not written (covers the open upsert and the shipped delete-and-insert path). Counted as "already closed, not re-opened".
- An open row whose order line (report type, order, order line, item, operating unit; order line required) is already open under another key in another job is not written. Counted as "already open under another key, not written twice". Facts of the same job are left to the existing orphan retire.
- Where it shows: `write_shipment_facts_and_close_book` returns `already_closed_not_reopened` and `already_open_not_duplicated`; the job keeps them in `staged_metadata['shipment_undated_write']`; the Import Center "did not close open orders" notice adds "N line(s) already closed, not re-opened". No web file was touched; the extra notice keys are optional.
- Unchanged by design: a dated newer file still re-opens a line it carries again (test pins this); a new line in an undated file is still written; an open fact under the same key is still updated.
- Trade-off: with the old-key fact left open, an undated re-export does not re-key the line; the next dated file does (probe P5 control, tested).

## Not done

- No live cip run of any writer, no restart (the worker needs none for these changes until deployed; per the standing rule, restart it when you deploy).
- Lint not run. No render.
- Other review findings (M3–M9, minors) untouched.
- Working tree still holds unrelated uncommitted files (programme runtime, ops scripts, renders); they are not in the commit.

## Files

Code: `app/services/shipment_live_line.py` (new), `shipment_strict_pair.py`, `imports/shipment_open_book.py`, `imports/shipment_inbound_facts.py`, `imports/cst_sku_twin_disambiguate.py`, `query/model/rules.py`, `query/model/loader.py`, `semantics/models/default.yaml`, `api/v1/endpoints/channel_ops.py`, `inbound_shipments.py`, `services/supply_overview.py`, five `commercial_planner/*` files, `alembic/versions/20261101_0050_fact_superseded.py`.
Tests (new): `test_shipment_live_line_b1.py` (18), `test_fact_superseded_downgrade_m1.py` (3), `test_shipment_undated_write_m2.py` (6).
Evidence: `.eif/audit/REVIEW_20261102/batch1/`.
