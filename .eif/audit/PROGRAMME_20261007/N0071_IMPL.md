# N-0071 implementation run (RUN-20261007-N0071-IMPL)

Node: N-0071 "open->shipped fact double-count policy (BACKLOG-062)". Risk R2, facet data_migration, touches existing code.
Lenses: backend-engineer (owner), test-engineering-specialist, database-specialist (proves nothing rewrites fact rows).
Accepted decision: D-0057 (Warren 2026-10-07), accept as built. Totals skip an open line when its strict shipped twin exists. Fact rows are not rewritten; they stay as imported, so the change can be undone. No cip data write.
Working tree: dirty, on 9c28bdcf. Nothing is committed or staged.

## 1. Discovery

Full table and numbers: `.eif/audit/PROGRAMME_20261007/N0071_DISCOVERY.md` (baseline BLN-N0071).

cip facts (read-only; each script prints `current_database()` = `cip` and runs `SET TRANSACTION READ ONLY`):
- 15,255 shipment fact rows. 1,775 are open_order (all scheduled).
- **552 open rows have a strict shipped twin: 42,956 units, amount 27.8M.** All are scheduled, none has a pod_date, and they belong to one tenant.
- Open qty compared with the twin's shipped qty: 471 equal, 71 lower, **10 higher (904 open units)**. In all 552 pairs a twin has the same order_line.

Readers that totalled open plus shipped without the exclusion (the counts are what each one over-stated today):

| Reader | Over-count today |
|---|---|
| Brief card "N inbound shipments not received" | 552 lines |
| Dashboard `late_risk` (the same count) | 552 lines |
| Lineup quarter summary (pipeline / unattributed units) | up to 42,956 units (32,591 PO-linked) |
| Shipping `/summary` by line state and total (disagreed with the grid, which already skipped the twin) | 552 lines |
| Shipping ETA-shift scope, no-filter path (the filtered path already skipped the twin) | 552 lines in scope |
| CPOR intake MAC qty and disti cost proxy | up to 32,591 units PO-linked |

Already wired in the dirty tree, kept: supply overview, the shipping fact filter (grid, KPI tiles, cohorts, commercial summary, newly-landed scoping), channel ops (movement, weekly flow, cover distribution), net requirement in-transit, PO auto-link, PO reconciliation pipeline, and the 1H rederivation hint.

Not changed, on purpose:
- Readers that only sum shipped rows need nothing, because the rule only drops open rows: derived stock, PO management, PO gap, WOC observation.
- DSI SOH reconciliation sums landed rows into a derived table at import. It is a no-op today because no open row has a pod_date, and it is a write path.
- Distributor attribution matches by distributor set, not by a total.
- Import, steward, merge and audit paths own the stored rows and must see them.

**Performance finding.** On cip, N-0065's row-level security calls `cip_product_id_visible` for every scanned row. The as-built correlated `EXISTS` re-scans the table for each open row. Under that RLS:
- the ORM form hit a **120 s** statement timeout;
- the supply-overview FILTER form hit a **240 s** timeout.

Every screen already wired with the old helper paid this cost.

## 2. Design

One rule, one module: every reader that totals shipment lines filters through `app/services/shipment_strict_pair.py`, so no two screens disagree. The rule and key are unchanged from D-0057: tenant (when the model has it) + trimmed lower-case operating unit + order number + item code; blank order or item never pairs; only `open_order` rows are dropped.

The evaluation changed, not the meaning. The twin test is now an uncorrelated key lookup, `(key) IN (SELECT key FROM shipped rows)`. Postgres computes the shipped keys once and hashes them.
- The old `shipped_twin.id <> id` is replaced by `line_state <> 'shipped'`. This is equivalent for every row the rule can drop, because an open row is never its own shipped twin.
- The subquery drops NULL order and item values, so `NOT IN` cannot become NULL. A test pins this.
- Readers call it inside `OR` / `NOT` / `FILTER`, which keeps it a hashed subplan.
- Equivalence on cip: the new predicate drops the same 552 ids. Their md5 matches an independent key-join formulation (`4a4aef04...`), and count, units and amount equal the old predicate's.
- Speed on cip: ORM form 0.41 s (was >120 s); 15-aggregate FILTER form 2.5 s (was >240 s).

Readers changed: brief + dashboard (one shared statement, so the two numbers agree), lineup quarter summary, shipping `/summary`, shipping ETA-shift scope (every path), and CPOR intake MAC (both queries).

`/summary` also returns `open_lines_skipped_shipped_twin`, an additive field, so the stored-but-skipped rows stay visible.

The pipeline views keep showing open separately (PO reconciliation, PO auto-link proposals, supply overview pipeline vs shipped). They show it minus the twin, as built.

Out of scope: the shipment sheet picker default Shipped + Unship (N-0072's area, untouched). No migration, index or fact rewrite.

## 3. Files changed (this run; uncommitted)

| File | Change |
|---|---|
| `apps/api/app/services/shipment_strict_pair.py` | Correlated EXISTS replaced by an uncorrelated key lookup. New `open_has_shipped_twin(model)`. Same rule; module docstring records D-0057 and the reason. |
| `apps/api/app/services/brief_signals.py` | New `inbound_not_received_count_stmt(user)` with the exclusion; the brief card uses it. |
| `apps/api/app/api/v1/endpoints/dashboard.py` | `late_risk` uses the shared statement; unused `FactInboundShipment` import removed. |
| `apps/api/app/services/commercial_planner/inbound_lineup_quarter.py` | `lineup_quarter_summary` fact read skips open twins. |
| `apps/api/app/api/v1/endpoints/shipping.py` | Module-level import (the local import in `_apply_fact_where_clause` is gone). ETA-shift scope skips twins on every path. `/summary` counts match the grid and add `open_lines_skipped_shipped_twin`. |
| `apps/api/app/services/cpor/intake_weighted_mac.py` | `_intake_wavg` and `_disti_cost_proxy_wavg` skip open twins. |
| `apps/api/tests/test_shipment_strict_pair.py` | New: 19 tests (rule edge cases plus one per changed reader), SQLite in-memory, no cip. |

No write path, migration or fact UPDATE/DELETE was added. Every change is a read predicate or a read-only count.

## 4. Tests and results

Commands run from `apps/api` (subshell), `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider ...`:

1. `tests/test_shipment_strict_pair.py`: **19 passed**. Covered:
   - exact twin skipped;
   - case and edge-space insensitive;
   - partial ship skipped as built (pinned; see open item 1);
   - different order / item / operating unit / tenant kept;
   - blank or NULL order or item never paired;
   - NULL-key shipped row does not hide an unrelated open row;
   - shipped and arrived never dropped;
   - raw SQL and ORM agree;
   - fact rows unchanged;
   - readers: brief/dashboard statement, lineup quarter summary, ETA-shift scope, shipping `/summary`, CPOR intake MAC.
2. Negative control: a pytest plugin (`.eif/audit/PROGRAMME_20261007/n0071_mutant_plugin.py`) replaced the exclusion with `true()` in the four reader modules. **All 5 reader tests failed** as expected.
3. Required suites plus the touched areas: `test_shipment_strict_pair, test_shipment_sheet_selection, test_inbound_lineup_quarter, test_brief_signals, test_brief_signals_href, test_grid_fields, test_intake_weighted_mac, test_promo_plan_builder, test_supply_plan_unit_coverage, test_dashboard_freshness, test_shipping_amount_scale, test_shipping_commercial_kpis, test_shipping_distributor_display, test_shipping_newly_landed, test_plan_vs_executed`: **186 passed, 13 errors**.
   - All 13 errors are the conftest cip guard refusing write-capable modules (`test_shipping_commercial_kpis.py`, `test_shipping_newly_landed.py`).
   - Those modules were NOT run; `ALLOW_TESTS_ON_DEV_DB` was not set.
4. Other consumers of the helper: `test_channel_ops_api, test_channel_ops_derived_stock, test_cover_policy, test_lineup_1h_rederivation, test_lineup_net_requirement, test_lineup_po_auto_link, test_lineup_po_auto_link_actions, test_lineup_po_reconciliation`: **56 passed, 20 errors**. All 20 are the same cip guard (`test_lineup_po_auto_link*.py`), not run.
5. `python -m compileall` on the changed files: ok. `import app.main`: ok. ruff and pyflakes are not installed in the venv, so no lint ran.
6. No frontend files changed, so tsc and eslint are not applicable to this node.

cip read-only scripts (all SELECT, read-only transaction, print `current_database()`): `N0071_probe.py`, `N0071_probe_new.py`, `N0071_probe_old_orm.py`, `N0071_probe_size.py`, `N0071_probe_activity.py`. Outputs are next to them.

## 5. Quality dimensions

- **data_integrity: pass.** Read-only change. Stored rows are untouched: a test asserts the rows and `updated_at` are unchanged. The ids dropped on cip equal the ids from an independent formulation (md5 match).
- **backup_recovery: na.** No data write, no schema change. Undo is a code revert.
- **migration_safety: na.** No migration and no fact rewrite (D-0057).

## 6. Ledger (run RUN-20261007-N0071-IMPL)

- Ledger revisions: lease acquire 1600; baseline.add BLN-N0071 1629; node.baseline 1630; decision.add (proposed, partial ship) 1631; finding.defer 1632 (RLS) and 1633 (unwired readers / convening); evidence.add 1634 and 1639-1642.
- Stages: challenge 1635, design 1637, implement 1638.
- node.quality: data_integrity pass 1643; backup_recovery na 1644; migration_safety na 1646.
- validate 1648; lease release 1650.
- Not recorded: node.verification, complete.
- `program.py verify`: integrity_ok true. The gate issues listed are acknowledged debt on N-0006, N-0013, N-0014, N-0015 and N-0016, none on N-0071.
- Two ledger writes first failed with `RUNTIME_INTEGRITY: Permission denied` (a concurrent writer) and succeeded on an identical retry.

## 7. Open items

1. **Partial ship (decision for Warren, proposed in the ledger, not built).** 10 strict pairs have open qty above the shipped twin's total, 904 open units. As built (D-0057) the whole open line is skipped. Options: keep as built; count open minus shipped; or list the 10 lines for a manual check.
2. **N-0065 RLS performance** (finding.defer). `cip_product_id_visible` runs per row. Correlated or nested-loop reads over RLS fact tables can become very slow. Only this helper was fixed here; other correlated reads were not surveyed.
3. DSI SOH reconciliation is unwired; it is a no-op today because no open row has a pod_date (finding.defer).
4. Not run: the cip-guarded modules listed in section 4. They need a disposable database (for example `cip_test`) for GOV-008 or CI.
5. This is self-verification by the implementation run. GOV-008 verification needs another run. The live screens were not exercised; no services were restarted.
6. The node's acceptance criterion 1 still reads "nothing is built until then". D-0057 now meets it, and the node text was not changed.

---

## Round 2 (same run, RUN-20261007-N0071-IMPL)

Why round 2:
- **GOV-008 FAILED (narrow)**, RUN-20261007-N0071-VER, `N0071_VERIFY.md` section 5. Three Supply overview columns still counted an open row and its shipped twin together: `eta_past_no_pod_lines` ("Unreceived past ETA"), `overdue_commercial_lines`, and `oldest_eta_past` / `oldest_days_past_eta`.
- **New decision D-0065** (Warren 2026-10-07): partial shipments count the remainder.
  - When an open line's quantity is above its strict shipped twins' total (summed per key), quantity totals count open minus shipped.
  - When open is at or below shipped, the open line is still skipped.
  - In line counts, an open line with a remainder above 0 still counts as one line.
  - Fact rows are never rewritten.

Working tree: dirty, on a86eff94. Nothing committed or staged. Lease taken at ledger rev 1661; stage moved back to implement at rev 1662.

### R2.1 What changed

**One rule, in `apps/api/app/services/shipment_strict_pair.py`.** The key is unchanged: tenant + `lower(trim(coalesce(operating_unit,'')))` + `lower(trim(order_no))` + `lower(trim(item_code))`; a blank or NULL order or item never pairs. New pieces:

| Piece | Use |
|---|---|
| `keep_counted_line(model)` | Filter for line counts and row lists: `id NOT IN (ids of open lines whose shipped twins cover them)`. A partly shipped open line stays. |
| `skipped_open_twin_line(model)` | The same set, positive form, for a `FILTER` count. |
| `twin_remainder(model)` / `outerjoin_twin_remainder(stmt, model)` | For quantity readers: a left join on fact id giving `counted_quantity` (the remainder for an open twin line, else the stored quantity), plus `kept` and `is_partial_twin`. |
| `OPEN_TWIN_REMAINDER_SQL`, `TWIN_KEPT_SQL`, `TWIN_COUNTED_QTY_SQL` | The same, as SQL text for raw readers. |

The D-0057 helpers (`exclude_open_when_shipped_twin`, `open_has_shipped_twin`, `OPEN_HAS_SHIPPED_TWIN_SQL`) are kept, unchanged in meaning, for the readers not moved yet (R2.5 item 1). The docstring now warns against the positive-WHERE form (the verifier's 35.8 s observation).

**How it is evaluated (database-specialist).** N-0065 row security makes the planner estimate about 25 to 50 rows for any scan of `fact_inbound_shipment`. Two plans failed on cip before the final form:

| Form tried | cip result | Why |
|---|---|---|
| Self-join of open rows to grouped shipped totals | 21.2 s for a plain count | Nested loop: 1,775 x 13,325 key comparisons (`N0071_r2_explain.py`) |
| Final form inside a plain subquery joined to a selective filter (current-incoming KPI) | 20.7 s | The window was re-run once per outer row (707 loops) |
| **Final: one scan, window `sum(...) OVER (PARTITION BY key)`; remainder as a `MATERIALIZED` CTE** | **0.47 to 0.49 s** | One sort of 15k rows; the CTE is computed once per statement |

The `NOT IN` filter is a hashed subplan over 542 ids. `id` is the primary key, so it cannot go NULL.

**Readers:**

| Reader | Change |
|---|---|
| `supply_overview.py` | **Change A.** The headline SQL moved into `_headline_sql(today_sql, week_start_sql)`. It is the same SQL, plus `WITH twin_rem AS MATERIALIZED (...)`, `LEFT JOIN twin_rem` and one `WHERE ... AND (twin_rem.fact_id IS NULL OR twin_rem.counted_qty > 0)`. Every column now follows the rule: `eta_past_no_pod_lines`, `oldest_eta_past`, `oldest_days_past_eta`, `overdue_commercial_lines`, and the landed counts (a no-op today). `open_units`, `pipeline_units` and `landed_units` sum the counted quantity (D-0065). `shipped_*` and `arrived_*` are never adjusted. |
| `brief_signals.py` (`inbound_not_received_count_stmt`, shared with the dashboard `late_risk`) | `keep_counted_line`. It is a line count, so a partly shipped open line counts once. |
| `commercial_planner/inbound_lineup_quarter.py` (`lineup_quarter_summary`) | Remainder join; each row is accumulated with its counted quantity. |
| `api/v1/endpoints/shipping.py` | Four changes: |
| | - `_apply_fact_where_clause` (grid, KPI tiles, cohorts, newly-landed scope) and the ETA-shift scope use `keep_counted_line`. |
| | - `/summary` uses `keep_counted_line`; `open_lines_skipped_shipped_twin` uses `skipped_open_twin_line`. `/summary` has no unit totals, so it is a line count only. |
| | - `_aggregate_currency_qty_lines` and the arriving-by-distributor totals sum the counted quantity. |
| | - **Amount:** the amount of a partly shipped open line is not added, which is what D-0057 did. Value of a remainder is open item 2 (proposed decision, not picked). |
| `cpor/intake_weighted_mac.py` (`_intake_wavg`, `_disti_cost_proxy_wavg`) | Weight = counted quantity (the remainder for a partial line); covered open lines are skipped. |
| `tests/test_shipment_sheet_selection.py` | The strict-key text test now reads `_OPEN_TWIN_REMAINDER`; the old alias import in supply_overview was removed. |

Why the shipping grid moved too: `/summary` and the lines grid must give the same line counts (GOV-008 check 4). Moving `/summary` to D-0065 therefore meant moving `_apply_fact_where_clause`. The KPI quantity totals that sit on that filter then had to sum the remainder, or they would have counted the shipped part twice.

No write path, migration, index or fact UPDATE/DELETE was added. Every change is a read predicate, a read-only join or a read-only count.

### R2.2 Tests

`apps/api/tests/test_shipment_strict_pair.py`: **39 passed** (19 from round 1 + 20 new). Run from `apps/api` in a subshell with `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`.

New tests:
- **Remainder rule** (`test_partial_ship_counts_the_remainder`, parametrized; each case also checks that ORM and raw SQL agree):
  - open 10 vs shipped 6: counts 4, still one line;
  - open 6 vs shipped 6: skipped;
  - open 5 vs shipped 6: skipped;
  - two shipped twins 3 + 4 against open 10: counts 3;
  - three twins 3 + 3 + 4: skipped.
- **Other rule tests:**
  - only the strict key is summed (other operating unit, order or tenant ignored);
  - NULL open quantity is skipped;
  - blank keys never pair;
  - the line-rule forms agree (`keep_counted_line`, the join's `kept`, raw SQL, and the skipped count);
  - fact rows are not rewritten.
- **Supply overview, change A.** These run the real `_headline_sql` on SQLite, with dates converted to julian day numbers so the SQL's date arithmetic runs:
  - `eta_past_no_pod_lines` and `oldest_eta_past` / `oldest_days_past_eta` skip a covered twin;
  - `overdue_commercial_lines` skips a covered twin;
  - open / pipeline units count the remainder.
- **One per reader using the remainder:**
  - brief count keeps the partial line;
  - lineup quarter summary units (25, against 21 under D-0057);
  - ETA-shift scope keeps the partial line;
  - `/summary` counts the partial line once;
  - shipping KPI quantity counts the remainder, and the amount excludes the partial line;
  - CPOR intake MAC is weighted by the remainder ((6x200 + 4x100) / 10 = 160);
  - CPOR disti cost proxy, the same.
- `test_partial_ship_is_skipped_as_built` was renamed `test_d0057_helper_still_skips_a_partial_ship`; it now pins the kept D-0057 helper.

**Own mutation checks** (`.eif/audit/PROGRAMME_20261007/n0071_r2_mutant.py`; it edits the file, runs the test file, then restores it byte for byte):

| Mutant | Result | sha256 before = after |
|---|---|---|
| `remainder_zero`: remainder always 0 (ORM and SQL text), every open twin skipped | **14 failed**, 25 passed. Every remainder, supply and reader test failed. | `306e0b2f...08b2` |
| `supply_no_rule`: change A undone (the `AND {_KEPT}` guard removed from the headline) | **3 failed** (the three supply overview tests) | `430d7809...e968` |

**Round 1 suites, re-run:**

| Run | Result |
|---|---|
| Group 1 (15 modules, as round 1 section 4 item 3) | **206 passed, 13 errors** (round 1: 186 + 13; the 20 extra passes are the new tests) |
| Group 2 (8 modules, item 4) | **56 passed, 20 errors** (same as round 1) |

All 33 errors are still the conftest guard refusing write-capable modules on `cip`. Those modules were not run, and `ALLOW_TESTS_ON_DEV_DB` was not set.

Other checks: `compileall` on the changed files passed, and `import app.main` passed. ruff and pyflakes are not installed, so no lint ran. No frontend file changed.

### R2.3 cip read-only numbers

Scripts:
- `N0071_r2_probe.py` (`before` run 14:51Z on the round-1 code, `after` run 15:2xZ); outputs `N0071_r2_probe_before_out.json` and `N0071_r2_probe_after_out.json`.
- `N0071_r2_explain.py` (plans).
- `N0071_r2_nowrite.py` (proof that nothing was written).

Each script printed `current_database()` = `cip` and `transaction_read_only` = on, with `row_security` on, and rolled back. The real reader functions were called on an async psycopg session. Before = round-1 code; after = round 2.

| Measure | Before | After | Note |
|---|---|---|---|
| `eta_past_no_pod_lines` ("Unreceived past ETA") | 1,218 | **696** | 686 under strict skip, plus the 10 partial lines (all 10 are past ETA with no POD) |
| `oldest_eta_past` / `oldest_days_past_eta` | 2026-05-07 / 153 | **2026-05-08 / 152** | The oldest row was a covered twin |
| `overdue_commercial_lines` | 375 | **364** | Equals the shipping overdue KPI (364 before and after). None of the 10 partial lines is in the promise window. |
| `open_lines` = brief / dashboard count | 1,561 = 1,561 | **1,571 = 1,571** | +10 partial lines, each counted once |
| `open_units` | 114,496 | **114,832** | +336 |
| `pipeline_lines` / `pipeline_units` | 1,223 / 84,914 | **1,233 / 85,250** | **+336 units** |
| `/summary` total / open_order / skipped | 14,703 / 1,223 / 552 | **14,713 / 1,233 / 542** | 14,713 + 542 = 15,255 stored rows |
| Lineup 26Q3 `unattributed_units` (round-1 filter swapped in vs round 2) | 1,269,445 | **1,269,781** | +336 |
| Shipping KPI current-incoming / overdue (after) | n/a | 54,721 units, 707 lines / 25,271 units, 364 lines | The 10 partial lines are in neither cohort, so no change today |

**About "904 units".** 904 is the *open* quantity on the 10 partial lines. Their shipped twins total 568. **The remainder that now enters pipeline units is 336, not 904.**
- Independent self-join (`INDEPENDENT_PAIRS` in the probe): 552 pairs = 542 covered + 10 partial; 904 open units, remainder 336; no key has more than one shipped twin on cip today.
- The helper's partial set equals the independent set (ids, open quantity, remainder): `helper_equals_independent_partial: true`.

**Timings on cip under row security** (after):

| Reader | Time |
|---|---|
| Supply overview headline | 1.4 to 1.5 s (round 1: 1.9 s) |
| Brief / dashboard count | 0.3 to 0.5 s |
| `/summary` (5 statements) | 2.7 to 3.6 s |
| Shipping KPI `_aggregate_currency_qty_lines` (2 statements each) | 2.6 s current-incoming, 1.8 s overdue |
| ETA-shift metrics, whole call | 3.4 s |
| CPOR intake MAC + disti proxy (sample product 12572) | 0.41 s |
| `keep_counted_line` count | 0.5 to 0.6 s |
| Lineup quarter summary | 9.6 to 10.4 s |

The lineup quarter summary is the one reader above a few seconds. Its cost is in the reader: it loads every fact row through the ORM and attributes each in Python. The round-1 filter swapped into the same reader took 9.1 to 12.2 s. The rule adds nothing measurable; it is recorded as open item 4.

**No write:**
- 15,255 rows; `max(updated_at)` = `max(created_at)` = 2026-09-21 18:15:13+02; 0 rows updated in the last 12 h (database time 2026-10-07 17:22+02).
- The 10 partial lines all have `product_id` and `distributor_id`, and none has a `purchase_order_id`.

### R2.4 Quality dimensions

- **data_integrity: pass** (self-verification). Fact rows are not touched; `test_remainder_does_not_rewrite_fact_rows` and `test_fact_rows_are_not_rewritten` pass, and cip shows 0 rows updated. On cip the helper's partial set equals an independent self-join, and the covered set is still 542 + 10 = the round-1 552. The readers on the rule now agree: supply `open_lines` = brief = 1,571; supply overdue = shipping overdue KPI = 364; `/summary` = grid rule.
- **backup_recovery: na.** No data write, no schema change. Undo is a code revert.
- **migration_safety: na.** No migration, index or fact rewrite (D-0057, D-0065).

### R2.5 Open items

1. **Readers still on D-0057 (they skip a partial line whole).** These were not in this round's scope:
   - `channel_ops.py` (movement, weekly flow, cover distribution);
   - `lineup/net_requirement.py` (in-transit);
   - `lineup_po_auto_link.py`;
   - `lineup_po_reconciliation.py` (evidence read model);
   - `lineup_bulk_rederivation.py` (1H hint).

   On cip today, the 10 partial lines carry `product_id` and `distributor_id` but no PO. So the PO readers are unaffected, but channel ops and net requirement can under-count by up to 336 units and 10 lines against the D-0065 screens. Moving them is mechanical (`twin_remainder` / `keep_counted_line`). Recorded as finding.defer.
2. **Value of a remainder (Warren's call, proposed decision, not built).** Shipping KPI value-by-currency does not add the amount of a partly shipped open line, which is what D-0057 did. No KPI cohort contains a partial line today, so the impact on cip is 0. Options:
   - (a) keep: value 0 for the open line;
   - (b) pro-rata: amount x remainder / open quantity;
   - (c) full stored amount, which double counts the shipped part.
3. **Shipping grid rows.** The lines grid now lists the 10 partial open lines with their *stored* quantity (rows are shown as imported). Tile and summary totals use the remainder. A user who sums the grid's quantity column by hand will see the full open quantity.
4. **Lineup quarter summary takes about 10 s** on cip. That is the reader's own ORM load, not this rule (open item 2 of round 1, N-0065 RLS performance, still applies).
5. **Not run:** 33 cip-guarded tests (they need a disposable database). Live screens were not exercised, and no service was restarted.
6. **Self-verification only.** GOV-008 needs a different run. This handback is blocked by policy; the ledger is at validate.

### R2.6 Ledger (run RUN-20261007-N0071-IMPL, round 2)

| Event | Ledger rev | Payload (`.eif/audit/PROGRAMME_20261007/`) |
|---|---|---|
| `node.lease.acquire` (node rev 15) | 1661 | `N0071_r2_lease.json` |
| `node.stage` implement (stage note cites the FAILED verification and D-0065) | 1662 | `N0071_r2_s_implement.json` |
| `evidence.add`: helper, supply overview, readers, tests, this file | 1687 to 1691 | `N0071_r2_ev_*.json` |
| `decision.add` (proposed): value of a remainder | 1692 | `N0071_r2_decision_amount.json` |
| `finding.defer`: readers still on D-0057 | 1693 | `N0071_r2_finding_d0057_readers.json` |
| `node.quality` data_integrity pass / backup_recovery na / migration_safety na | 1694 / 1695 / 1696 | `N0071_r2_q1.json` to `N0071_r2_q3.json` |
| `node.stage` validate | 1697 | `N0071_r2_s_validate.json` |
| `node.lease.release` | 1698 | `N0071_r2_release.json` |

Ledger revisions 1663 to 1686 are other runs' events.

- `node.patch`, `node.verification` and complete were **not** recorded.
- `program.py verify`: integrity_ok true. The only gate issues are acknowledged debt on N-0006, N-0013, N-0014, N-0015 and N-0016; none is on N-0071.
- There was no `RUNTIME_INTEGRITY` retry this round.

---

## Round 3 (same run, RUN-20261007-N0071-IMPL)

Why round 3:
- **R2.5 item 1:** five readers still used the D-0057 helper, which skips a partly shipped open line whole.
- **New decision (Warren 2026-10-07, N-0071):** the value of a partly shipped open line is pro-rata, `amount x remainder / open quantity`. This applies to every shipment reader that totals open quantity or value. A covered (skipped) line counts 0, and a line with no shipped twin counts its stored amount.
- **R2.5 item 3:** the shipping grid listed the 10 partial lines with their stored quantity and no remainder.

Working tree: dirty, on 1714b78d. Nothing was committed or staged. Lease taken at ledger rev 1708; stage moved back to implement at rev 1709.

### R3.1 What changed

**Helper (`apps/api/app/services/shipment_strict_pair.py`).** The rule and key are unchanged.

| Piece | Change |
|---|---|
| `TwinRemainder.counted_amount` | New. No twin: the stored `amount`. Partly shipped: `amount * counted_qty / nullif(quantity, 0)`. Covered: 0. A zero open quantity gives NULL, which a SUM ignores. |
| `TWIN_COUNTED_AMOUNT_SQL` | New. The same expression as SQL text, for raw readers. |
| `twin_remainder(model, row_filter=...)` and `outerjoin_twin_remainder(..., row_filter=...)` | New optional argument. It limits the rows whose shipped quantity is summed. The PO reconciliation passes the active-evidence predicate, so a superseded `shipment_evidence_line` row cannot add to a shipped total. The predicate is a no-op when bitemporal read is on, which is the default. |
| Docstring | Records the pro-rata decision. Notes that no product reader uses the D-0057 helpers any more: a grep of `app/` finds them only in the helper module. They are kept for the tests that pin D-0057 and for probes. |

**Readers moved from D-0057 to the remainder.** The change is mechanical: a `twin_remainder` outer join, a `twin.kept` filter, and a sum of `counted_quantity`.

| Reader | File |
|---|---|
| Channel ops movement lens: `shipped_units` for the latest week | `api/v1/endpoints/channel_ops.py` |
| Channel ops weekly flow: `_cover_weekly_flow` shipped by week | same |
| Channel ops cover distribution: `inbound_open` per distributor x product | same |
| Net requirement in-transit: `_in_transit_by_dist_product` | `services/lineup/net_requirement.py` (see coordination below) |
| PO auto-link: proposals' `open_order_units` (and `shipped_units`, unchanged for shipped rows) | `services/commercial_planner/lineup_po_auto_link.py`. Rows are read with their counted quantity; `ship_qty` comes from it. |
| PO reconciliation: `pipeline_units` from the evidence read model | `services/commercial_planner/lineup_po_reconciliation.py`, with `row_filter=active_evidence_line_predicate` |
| 1H rederivation hint: `_shipment_q1_hint` | `services/commercial_planner/lineup_bulk_rederivation.py`. This one has a fast path, explained next. |

**1H hint fast path (database-specialist).** `_shipment_q1_hint` runs once per lineup line.
- Plain remainder join: 9 calls took **4.69 s** on cip (about 0.5 s each, one window over the table per call). D-0057 took 0.09 s.
- Fix: the reader now sums the stored quantity of non-open rows directly, because the rule never adjusts them. It runs the remainder join only for the open_order ids that fall in its window.
- On cip no open line has a ship_confirm_date, so the join never runs: **0.03 s for 9 calls**.
- The totals are the same, and the test and mutant cover the case where the join does run.

**Pro-rata value.** `shipping._aggregate_currency_qty_lines` now sums `twin.counted_amount`. This covers KPI value-by-currency for current incoming, overdue and landed.
- Before this round, a partial line added no amount (round 2).
- The `case` import is no longer used and was removed.
- **No other value total of open lines exists in the readers from rounds 1 to 3.** The search covered `amount` sums in `app/`:
  - `/summary`, supply overview and the lineup quarter summary total no money.
  - `po_management` and the PO reconciliation total shipped value only.
  - The CPOR intake MAC and disti proxy weight `unit_price` by the counted quantity. That already gives `remainder x unit_price`, which equals pro-rata whenever `amount = quantity x unit_price`. **Not changed.**

**Shipping grid "Still to ship" (R2.5 item 3, done; backend only).**
- `grid_fields.py`: the `inbound-shipments` spec gets `static_keys=(("still_to_ship", "Still to ship"),)`. The picker therefore offers it under `/grid-fields/inbound-shipments` and the `/inbound-optional-columns` alias.
- `shipping.py`:
  - `_fact_to_dict` emits `still_to_ship`.
  - `/lines` fills it from `_still_to_ship_by_id(db, rows)`: one statement, run only when the page has open_order rows.
  - Open line: the remainder, or the stored quantity when it has no twin. Shipped or arrived line: blank.
- `quantity` stays the stored quantity.
- The web grid takes optional columns from the registry (`useFactColumns('inbound-shipments')` and the generic formatter), so **no web file changed**. The column was not seen in the browser (no service restart).

**Coordination on `net_requirement.py` (N-0065 round 3).**
- Re-read right before the edit: sha256 `581c51d4...`. The only diff against HEAD was round 1's import plus filter line, so N-0065's latest-snapshot change was not in the file yet.
- My change is limited to the import line and `_in_transit_by_dist_product`. After the edit: `9544127e...`, `git diff --stat` 7+/1-. It does not touch the forecast or stock subqueries N-0065 targets.
- The mutation test for this file ran **in memory** (pytest plugin `n0071_r3_mutant_plugin.py`). The shared file was never rewritten, and its hash was the same before and after.

No write path, migration, index or fact UPDATE/DELETE was added. Every change is a read predicate, a read-only join, a read-only count or a serializer field.

### R3.2 Tests

`apps/api/tests/test_shipment_strict_pair.py`: **55 passed**. That is 39 from rounds 1 and 2, plus 16 new.

New tests:
- **Pro-rata value**, `test_partial_line_value_is_pro_rata`. Six cases; each also checks that the ORM form and the SQL text agree:
  - open 10 / shipped 6 / amount 1000 -> **400**;
  - fully open -> 1000;
  - two twins 3 + 4 -> 300;
  - covered 6/6 -> skipped;
  - over-covered 5/6 -> skipped;
  - partial line with NULL amount -> NULL.
- `test_covered_line_counted_amount_is_zero_without_kept_filter`.
- `test_shipping_kpi_value_is_pro_rata`: USD 2,000 and EUR 500. Here 600 + 1000 are shipped, 400 is the pro-rata share of the 1000 partial line, and the EUR 500 line is fully open with no twin. The full stored amount would give USD 2,600.
- The round-2 KPI test (`test_shipping_kpi_quantity_counts_remainder`) now expects 340, not 300.
- **One test per moved reader** (the D-0057 result is in brackets). The SQLite tables are created per test, and helpers are monkeypatched where the reader needs data from elsewhere:

  | Test | Result |
  |---|---|
  | `test_channel_ops_movement_shipped_units_count_remainder` | 25 (21) |
  | `test_channel_ops_weekly_flow_counts_remainder` | 25 (21) |
  | `test_channel_ops_cover_inbound_open_counts_remainder` | 25 (21) |
  | `test_net_requirement_in_transit_counts_remainder` | `{(4,3): 25}` (21); a landed line is excluded |
  | `test_1h_hint_counts_remainder` | 25 (21) |
  | `test_po_auto_link_open_order_units_count_remainder` | open 9 (5), shipped 16; one proposal |
  | `test_po_reconciliation_pipeline_counts_remainder` | 9 (5), on a SQLite `shipment_evidence_current` |
  | `test_shipping_grid_still_to_ship` | partial 4, plain 5, covered 0 if asked; `quantity` stays 10; picker label "Still to ship", group fact |

**Own mutation checks.** Script `n0071_r3_mutant.py`; output in `n0071_r3_mutant_out.txt` and `n0071_r3_mutant_hint_rerun_out.txt`. Each check edits one file, runs the test file, then restores the file byte for byte (sha256 before = after for each).

| Mutant | Result |
|---|---|
| `pro_rata_full`: value of a partial line = full stored amount (ORM and SQL) | **4 failed**: both KPI tests, plus pro-rata cases `open10_shipped6_amount1000_counts400` and `two_twins_summed_counts300` |
| `pro_rata_full_orm` (ORM only) | **4 failed** (the same 4) |
| `channel_ops`: stored quantity in all three readers | **3 failed** (the three channel ops tests) |
| `net_requirement`: in memory, through the plugin | **1 failed** |
| `po_auto_link`: `ship_qty` = stored quantity | **1 failed**. The first attempt could not open the file for writing (Windows `Errno 22`, so nothing was written, hash unchanged). The retry ran. |
| `po_reconciliation` | **1 failed** |
| `hint_1h` (re-run after the fast path) | **1 failed** |
| `grid_still_to_ship`: stored quantity | **1 failed** |

The covered and fully-open pro-rata cases pass under the mutant, which is correct: the mutant changes only the partial branch.

**Round-1/2 suites, re-run:**

| Run | Result |
|---|---|
| Group 1 (15 modules) | **222 passed, 13 errors** (round 2: 206 + 13; the 16 extra passes are the new tests). `test_grid_fields` passes, including the inbound picker-to-payload parity check with `still_to_ship`. |
| Group 2 (8 modules) | **56 passed, 20 errors** (same as round 2) |
| Wider: every `test_shipping*`, `test_channel_ops*`, `test_lineup*`, `test_supply*`, `test_inbound*`, `test_cover*` | **322 passed, 2 failed, 70 errors** |

- The 70 errors in the wider run are all the cip write guard (counted by module).
- The 2 failures are in `test_lineup_open_channel.py`: `test_sync_eligibility_open_channel_missing_account` and `test_sync_skip_detail_unassigned_placeholder_reference_data`. They assert message text ("OPEN_CHANNEL") in `lineup_open_channel.py`. That file is in the dirty tree from another run; N-0071 did not touch it and nothing here calls it. Recorded, not fixed.

Other checks:
- `compileall` on the 8 changed app files passed, and `import app.main` passed.
- ruff and pyflakes are not installed, so no lint ran. Unused imports were checked by hand: `case` was removed from shipping.py, and no `exclude_open_when_shipped_twin` import is left in any reader.

### R3.3 cip read-only numbers

Scripts:
- `N0071_r3_probe.py`, run as `before` (07:12Z, round-2 code) and `after` (07:3xZ, round 3); output in `N0071_r3_probe_before_out.json` and `N0071_r3_probe_after_out.json`.
- `N0071_r3_timing.py` (D-0057 form vs D-0065 form, alternating, 3 runs each); output in `N0071_r3_timing_out.json`.
- `N0071_r2_nowrite.py`, re-run.

Each script printed `current_database()` = `cip` and `transaction_read_only` = on, ran with `row_security` on, and rolled back. The real reader functions were called.

**The 10 partial lines** are the same set as round 2: 904 open units, 568 shipped, **remainder 336**. All have `product_id` and `distributor_id`, none has a PO, ship_confirm_date or POD, and all are USD.

| id | open / shipped / remainder | stored amount | pro-rata |
|---|---|---|---|
| 299 | 120 / 100 / 20 | 130,920 | 21,820 |
| 300 | 120 / 100 / 20 | 130,920 | 21,820 |
| 302 | 120 / 100 / 20 | 144,000 | 24,000 |
| 308 | 60 / 50 / 10 | 63,060 | 10,510 |
| 100351 | 108 / 36 / 72 | 75,600 | 50,400 |
| 100374 | 108 / 36 / 72 | 48,060 | 32,040 |
| 100797 | 36 / 18 / 18 | 56,628 | 28,314 |
| 100962 | 60 / 40 / 20 | 53,220 | 17,740 |
| 100963 | 160 / 80 / 80 | 155,360 | 77,680 |
| 107364 | 12 / 8 / 4 | 22,536 | 7,512 |
| **Total** | **904 / 568 / 336** | **880,304 USD** | **291,836 USD** |

- The helper's `counted_amount` equals the independent computation line by line (`helper_pro_rata_equals_independent: true`).
- **Value of every kept open line (USD):**
  - pro-rata (now): 371,231,405;
  - round 2 (partial line = 0): 370,939,569;
  - stored amount: 371,819,873.

  The +291,836 against round 2 is exactly the pro-rata total. The stored total would add the 588,468 already shipped a second time.
- **Shipping KPI cohorts:** current incoming is 54,721 units, 707 lines, USD 69,441,565.4; overdue is 25,271 units, 364 lines, USD 53,240,831. None of the 10 lines is in either cohort (as in round 2), so pro-rata changes no KPI tile on cip today.
- **Grid "Still to ship"** for the 10 lines equals their remainder (`grid_still_to_ship_equals_remainder: true`); 0.29 to 0.35 s for one page.

**Readers moved, before -> after:**

| Reader | Before | After | Why |
|---|---|---|---|
| Channel ops cover `inbound_open`, all pairs (`N0071_r3_timing`) | 86,482 | **86,818 (+336)** | The 10 lines are open, have no POD, and have distributor and product, so all 336 enter |
| Channel ops cover, items shown (pairs with a WOC observation) | 15,540 | **15,634 (+94)** | 21-3975: 0 -> 18 (line 100797); 29-4504: 1,476 -> 1,548 (100374); 29-9659: 84 -> 88 (107364). The other 7 lines' pairs have no WOC row. |
| Channel ops movement `shipped_units` (W37) | 1,079 | 1,079 | The 10 lines have no ship_confirm_date or POD, so they have no in_date |
| Channel ops weekly flow, shipped over 13 weeks | 43,987 | 43,987 | Same reason |
| Net requirement in-transit (235 pairs) | 37,715 | 37,715 | PO-linked only; the 10 lines have no PO |
| PO auto-link (154 proposals) open / shipped units | 5,121 / 47,079 | 5,121 / 47,079 | No PO on the 10 lines |
| PO reconciliation `pipeline_units` (cases 120, 126, 114) | 0 / 0 / 0 | 0 / 0 / 0 | No PO on the 10 lines |
| 1H hint, the 9 products of the 10 lines | unchanged | unchanged | No ship_confirm_date on the open lines |

**The screens now agree.**
- The supply overview pipeline went from 84,914 to 85,250 in round 2 (+336).
- The channel ops cover `inbound_open` now goes from 86,482 to 86,818 (+336).
- Both add the same 336 remainder of the same 10 lines. Before this round, channel ops added 0 for them while supply added 336.

All other readers on the rule now count the same lines in the same way: brief, dashboard, shipping grid and summary, KPIs, lineup quarter, CPOR, net requirement, PO auto-link, PO reconciliation, 1H hint. The PO and net-requirement readers show no cip change only because none of the 10 lines has a PO.

**Timings on cip under row security:**

| Statement or reader | D-0057 | D-0065 (round 3) |
|---|---|---|
| Movement shipped-units statement | 0.12 to 0.24 s | 0.35 to 0.58 s |
| Cover `inbound_open` statement | 0.17 to 0.20 s | 0.30 to 0.35 s |
| Whole movement lens | 3.5 s (probe before) | 5.2 to 7.8 s |
| Weekly flow | 0.64 s | 1.0 to 1.4 s |
| Cover distribution | 3.7 s | 4.7 to 4.9 s |
| Net requirement in-transit | 0.25 s | 0.29 to 0.32 s |
| PO auto-link | 6.1 s | 6.0 to 7.1 s |
| PO reconciliation, per case | 2.6 to 5.2 s | 1.8 to 2.8 s |
| 1H hint, 9 calls | 0.09 s | 0.03 s (after the fast path) |

Most of the movement lens time is `latest_woc_observations` (3.0 s), not this rule, and the spread between runs is load noise. Each remainder statement adds 0.15 to 0.35 s.

**No write:** 15,255 rows. `max(updated_at)` = `max(created_at)` = 2026-09-21 18:15:13+02. 0 rows were updated in the last 12 h (database time 2026-10-08 09:36+02).

### R3.4 Quality dimensions

- **data_integrity: pass** (self-verification).
  - Fact rows are not touched. The two no-rewrite tests pass, and cip shows 0 rows updated.
  - The helper's pro-rata values equal an independent computation for all 10 lines.
  - The partial set is still 10 lines, 904 open, remainder 336.
  - No product reader uses the D-0057 helper now, and the cross-screen check holds: supply pipeline +336 = channel ops `inbound_open` +336.
- **backup_recovery: na.** No data write, no schema change. Undo is a code revert.
- **migration_safety: na.** No migration, index or fact rewrite. Pro-rata and "Still to ship" are computed on read.

### R3.5 Open items

1. **Self-verification only.** GOV-008 needs a different run. This handback is blocked by policy; the ledger is at validate.
2. **Not run:**
   - the 33 cip-guarded tests in groups 1 and 2, and the 70 guard errors in the wider run (they need a disposable database);
   - the live screens, including the "Still to ship" column in the grid. No service was restarted.
3. **The 2 `test_lineup_open_channel.py` failures** come from another run's dirty `lineup_open_channel.py` message text, not from N-0071.
4. **The remainder statements add about 0.15 to 0.35 s each** under N-0065 row security. Readers called in a loop must avoid the per-call join. The 1H hint was the only one, and it was fixed with the fast path. No other per-line caller of the helper was found.
5. **The proposed decision "value of a remainder"** (ledger rev 1692) is now decided by Warren (pro-rata). Marking it accepted in the ledger is the orchestrator's step; this run did not change decision records.

### R3.6 Ledger (run RUN-20261007-N0071-IMPL, round 3)

| Event | Ledger rev | Payload (`.eif/audit/PROGRAMME_20261007/`) |
|---|---|---|
| `node.lease.acquire` (node rev 22) | 1708 | `N0071_r3_lease.json` |
| `node.stage` implement (round 3 scope: five readers + pro-rata) | 1709 | `N0071_r3_s_implement.json` |
| `evidence.add`: helper, readers, grid, tests, cip | 1735, 1737, 1738, 1739, 1740 | `N0071_r3_ev_*.json` |
| `node.quality` data_integrity pass / backup_recovery na / migration_safety na | 1741 / 1742 / 1743 | `N0071_r3_q1.json` to `N0071_r3_q3.json` |
| `node.stage` validate | 1744 | `N0071_r3_s_validate.json` |
| `node.lease.release` (node rev 28) | 1746 | `N0071_r3_release.json` |

- The other revisions between 1710 and 1734 are other runs' events.
- The first `evidence.add` (readers) failed with `RUNTIME_INTEGRITY: Permission denied`. It succeeded on one identical retry (rev 1737).
- `node.verification`, `decision.add` and complete were **not** recorded.
- `program.py verify` at rev 1746: integrity_ok true. The only gate issues are acknowledged debt on N-0006, N-0013, N-0014, N-0015 and N-0016; none is on N-0071.

---

## Round 4 (same run, RUN-20261007-N0071-IMPL)

Why round 4: re-verification RUN-20261008-N0071-VER2 failed on **RV4** (`N0071_VERIFY.md`, "Re-verification (rounds 2-3)").
- `lineup_case_suggested_pos.py` (lines ~91 and ~210) summed PO-linked evidence of **every** `line_state` into `total_shipped_units`.
- The distributor list was also ordered by that sum (line ~228).
- The UI shows the value as "Shipped units" (`CurrentLineupSection.tsx`).
- On cip, 404 open rows / 25,509 units were counted as shipped. The PO auto-link "Shipped" counts shipped lines only.

Working tree: dirty, on 1714b78d. Nothing was committed or staged. Lease at ledger rev 1770; stage back to implement at rev 1771.

### R4.1 What changed

One file: `apps/api/app/services/commercial_planner/lineup_case_suggested_pos.py` (+12 / -3; sha256 `a7f200bd...cb50`).

```python
def _shipped_units_sum():
    return func.coalesce(func.sum(EV.quantity).filter(EV.line_state == "shipped"), 0)
```

It is used in three places:
- the `total_shipped_units` column of `suggest_pos_for_case`;
- the `total_shipped_units` column of `suggest_distributors_for_case`;
- the second ordering key of `suggest_distributors_for_case`.

**Design choice: a FILTER on the sum, not a WHERE on the query.** This keeps "no other change":
- An open line still joins its PO, so the same POs and distributors are suggested.
- `matched_product_count` and `po_count` are unchanged. A PO that has only open lines is still suggested, with 0 shipped units.
- A WHERE clause would also have dropped open-only POs from the suggestion list and lowered the matched-product counts. That would change the confirmation workflow, not just the number.

Ordering is unchanged in kind:
- POs: matched products, then PO number. Units were never a key here.
- Distributors: matched products, then shipped units. That key now counts shipped lines only.

`line_state` on the evidence read model is lower-case `shipped` / `open_order` on cip (VER2 probe 3), so a plain `== "shipped"` matches. That is the form the brief asked for.

### R4.2 Tests

`apps/api/tests/test_lineup_case_suggested_pos.py` gets one new test: `test_shipped_units_count_shipped_lines_only_and_order_distributors` (sha256 `4fa4d4fb...eb7c`).
- It runs the real SQL on an in-memory SQLite copy of the evidence read model (`shipment_evidence_current` by default), `purchase_order` and `dim_distributor`. No cip access.
- The case helpers are monkeypatched: products [3, 4], no distributor restriction.

The fixture:

| PO | Distributor | Lines |
|---|---|---|
| PO-A | 1 | shipped 10 (SO-1); **open 10 with a shipped twin** (SO-1); **open 50 with no twin** (SO-2); shipped 5 |
| PO-B | 2 | shipped 40 + 2 |
| PO-C | 1 | open only, 30 |

What it asserts:
- PO-A = **15**, not 75. The open lines are excluded with and without a twin.
- PO-B = 42.
- PO-C = 0, and it is still suggested.
- Matched-product counts are unchanged, and the PO order is A, B, C.
- Distributors are ordered `[(2, 42), (1, 15)]`. Under the all-states sum, Dist One would be 105 and come first. `po_count` is [1, 2].

**Mutation checks.** Each mutant was a source edit followed by a revert, with sha256 `a7f200bd...cb50` identical before and after.

| Mutant | Result |
|---|---|
| Filter removed from `_shipped_units_sum` | **1 failed**: `assert 75.0 == 15.0` |
| Filter removed from the distributor `order_by` only (label still filtered) | **1 failed**: `[(1, 15.0), (2, 42.0)] != [(2, 42.0), (1, 15.0)]`. The ordering assertion catches it on its own. |

The four existing mock tests passed under both mutants, as expected. After the revert, the suggested-PO file and `test_lineup_case_distributor_suggest_assign.py` give **15 passed**.

**N-0071 suites, re-run.** Commands as in section 4 and R2.2, from `apps/api` in a subshell. Output files are in this folder: `n0071_r4_group1_out.txt`, `n0071_r4_group2_out.txt` and `n0071_r4_wider_out.txt`.

| Run | Round 4 | Round 3 |
|---|---|---|
| Group 1 (15 modules) | **222 passed, 13 errors** | 222 + 13 |
| Group 2 (8 modules) | **56 passed, 20 errors** | 56 + 20 |
| Wider: `test_shipping*`, `test_channel_ops*`, `test_lineup*`, `test_supply*`, `test_inbound*`, `test_cover*` | **323 passed, 2 failed, 70 errors** | 322 / 2 / 70; the +1 pass is the new test |

- All 70 errors (and the 13 + 20) are the conftest guard refusing write-capable modules on `cip`. By module: business-unit resolution 20, PO auto-link 18, customer token stamp 13, shipping newly-landed 7, commercial KPIs 6, plus 2 each for bulk-backfill integration, auto-link actions and PO-link carry supersession. They were not run, and `ALLOW_TESTS_ON_DEV_DB` was not set.
- The 2 failures are the same `test_lineup_open_channel.py` message-text tests. They come from another run's edit (VER2 RV5), not from N-0071.
- `compileall` on both changed files passed, and `import app.main` passed. ruff and pyflakes are not installed, so no lint ran.

### R4.3 cip read-only numbers

Script: `N0071_r4_probe2.py`; output in `N0071_r4_probe2_before_out.json` and `N0071_r4_probe2_after_out.json`, logs in `*_log.txt`.
- Each run printed `current_database()` = `cip`, `transaction_read_only` = on (also `default_transaction_read_only=on`), and `row_security` = on, then rolled back.
- It calls the real `suggest_pos_for_case` and `suggest_distributors_for_case` for all 36 lineup cases; 33 have resolved products.
- It checks every returned row against an independent grouped SUM over the evidence read model, both shipped-only and all-states, for the same PO or distributor and the same case products.
- **The before figure** comes from replacing `_shipped_units_sum` in memory with the pre-fix `coalesce(sum(quantity), 0)`. That is the only expression the fix changed, and the service file was not touched. The before run matches the independent all-states SUM on every row, so it reproduces the old reader.

| Reader (all 36 cases, values summed per case) | Before | After | Independent shipped-only |
|---|---|---|---|
| Suggested POs: rows | 2,697 | 2,697 (same membership) | |
| Suggested POs: `total_shipped_units` | 775,204 | **725,145 (-50,059)** | 725,145 |
| Rows equal to shipped-only | 2,441 / 2,697 | **2,697 / 2,697** | |
| Rows now 0 (open-only POs, still suggested) | 0 | 35 | |
| Suggested distributors: rows | 232 | 232 | |
| Suggested distributors: `total_shipped_units` | 1,041,463 | **985,821 (-55,642)** | 985,821 |
| Rows equal to shipped-only | 156 / 232 | **232 / 232** | |
| Rows now 0 | 0 | 5 | |

- **Distributor order.** After the fix, every case is ordered by matched products, then shipped units. In 5 of the 33 cases, the all-states key orders the distributors differently. Those 5 cases are where the fix changes the order Warren sees.
- **Totals are per case.** The same PO appears under several cases, so these totals do not compare with VER2's global PO-linked figure (404 open rows / 25,509 units). After the fix, no open unit counts in either reader.
- Runtime: 168 s for each pass over the 36 cases, with both readers and the independent check under row security.
- **The first probe, `N0071_r4_probe.py`, was too slow.** It ran one independent query per suggestion and was still running after about 50 minutes (started 14:36 local), holding a read-only transaction. I stopped that probe's own two local processes (`Stop-Process`). A read-only `pg_stat_activity` check (`N0071_r4_activity.py`) then showed no non-idle session left on cip. It produced no output file. No service was restarted, and no backend was terminated from the database side.
- **No write.** Every statement was a SELECT inside a read-only transaction. The probe has no DML.

### R4.4 Quality dimensions

- **data_integrity: pass** (self-verification).
  - "Shipped units" in both suggestion readers now equal an independent shipped-only SUM on all 2,697 PO rows and all 232 distributor rows on cip.
  - Suggestion membership, matched-product counts and PO counts are unchanged.
  - The test pins open lines with and without a twin, and both mutants are caught.
  - No fact row is touched.
- **backup_recovery: na.** No data write, no schema change. Undo is a code revert.
- **migration_safety: na.** No migration, index or fact rewrite.

### R4.5 Open items

1. **Self-verification only.** GOV-008 must be a different run. The handback is blocked by policy; the ledger is left at validate.
2. **Not exercised:** the live "Shipped units" column in `CurrentLineupSection.tsx` and the HTTP endpoints. No service was restarted. No frontend file changed.
3. **Still deferred from VER2 RV4** (Low): `cst_sku_twin_disambiguate.py:221` (`InboundWindow.qty`, a steward tie-break). It is outside this round's scope and was not touched.
4. **Process slip:** one shell call began with a bare `cd` to the repo root before a Python edit. It was harmless and read-only in effect, but it broke the no-`cd` rule. The Python in-place edit of the service file later failed twice with Windows `Errno 22` (nothing was written), so the remaining edits were made with the editor tool.

### R4.6 Ledger (run RUN-20261007-N0071-IMPL, round 4)

| Event | Ledger rev | Payload (`.eif/audit/PROGRAMME_20261007/`) |
|---|---|---|
| `node.lease.acquire` (node rev 32) | 1770 | `N0071_r4_lease.json` |
| `node.stage` implement (the stage note cites VER2 RV4) | 1771 | `N0071_r4_s_implement.json` |
| `evidence.add`: service, test, cip probe, this file | 1778, 1779, 1780, 1781 | `N0071_r4_ev_service.json`, `_tests`, `_cip`, `_impl` |
| `node.quality` data_integrity pass / backup_recovery na / migration_safety na | 1782 / 1783 / 1784 | `N0071_r4_q1.json` to `N0071_r4_q3.json` |
| `node.stage` validate | 1785 | `N0071_r4_s_validate.json` |
| `node.lease.release` (node rev 38) | 1786 | `N0071_r4_release.json` |

- Revisions 1772 to 1777 are other runs' events.
- There was no `RUNTIME_INTEGRITY` retry this round.
- `node.verification`, `decision.add`, `finding.defer` and complete were **not** recorded.
- `program.py verify` at rev 1786: integrity_ok true. The only gate issues are acknowledged debt on N-0006, N-0013, N-0014, N-0015 and N-0016; none is on N-0071.
