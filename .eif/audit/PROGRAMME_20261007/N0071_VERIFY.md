# N-0071 GOV-008 verification (RUN-20261007-N0071-VER)

Node: N-0071, open->shipped double-count. Accepted decision D-0057: totals skip an open line when its strict shipped twin exists, and fact rows are never rewritten. Risk R2, facet data_migration.
Implementation run: RUN-20261007-N0071-IMPL. Verification run: RUN-20261007-N0071-VER.

**Independence rung: R2.** This was a fresh-context subagent session of the same model family, not a different model. Every result below was re-run in this session. N0071_IMPL.md was used only to find the file list (its section 3) and the claimed numbers to compare against.

Lenses: verification-controller, database-specialist, implementation-reviewer.

## Overall verdict: FAILED (narrow)

- **What holds:** the helper and every changed reader are correct. The tests pass, the mutation tests catch the bugs I planted, cip agrees with my own independent SQL (552 ids, same md5), and no fact row was written.
- **What fails:** the node claims, in the helper docstring and in IMPL section 1, that the supply overview was already wired. That is only partly true. Two user-visible counts on the Supply overview still add an open row and its shipped twin together:
  - "Unreceived past ETA" includes 532 of the 552 open twins.
  - `overdue_commercial_lines` includes 11 of them, so it disagrees with the shipping overdue KPI: 375 against 364.

  This breaks D-0057 ("no two screens disagree") on cip today.
- **Fix:** small. Add the existing `NOT (lower(line_state)='open_order' AND {_OPEN_HAS_SHIPPED_TWIN})` guard to those FILTER clauses in `apps/api/app/services/supply_overview.py`. The alternative is for Warren to accept those two tiles as out of scope.

| # | Check | Verdict |
|---|---|---|
| 1 | Code review: helper and changed readers | VERIFIED |
| 2 | Tests re-run and own mutation tests | VERIFIED_WITH_LIMITATIONS (33 cip-guarded tests not run) |
| 3 | cip read-only: independent twin set, no fact rewrite | VERIFIED |
| 4 | Readers that disagreed now agree | VERIFIED |
| 5 | Readers that still total open plus shipped without the rule | FAILED: 2 supply overview counts (and `oldest_eta_past`) |

## 1. Code review: VERIFIED

Files reviewed:
- `apps/api/app/services/shipment_strict_pair.py`: untracked, sha256 `84f8b020...a462`.
- The `git diff` of `brief_signals.py`, `dashboard.py`, `inbound_lineup_quarter.py`, `shipping.py` and `intake_weighted_mac.py`.

**Rule and key match D-0057.**
- The key is tenant (when the model has `tenant_id`), `lower(trim(coalesce(operating_unit,'')))`, `lower(trim(order_no))` and `lower(trim(item_code))`.
- The ORM form (`open_has_shipped_twin`) and the raw SQL form (`OPEN_HAS_SHIPPED_TWIN_SQL`) build the same key.

**Only open_order rows are dropped.**
- `exclude_open_when_shipped_twin` is `lower(line_state) != 'open_order' OR NOT twin(...)`, so any row that is not open is kept.
- `twin(...)` also requires `line_state <> 'shipped'`.
- On cip, the dropped rows are open_order only (552 of 552).

**A NULL or blank order or item never pairs.**
- On the outer row: `trim(coalesce(order_no,'')) <> ''` and the same for `item_code`.
- On the shipped side: `order_no IS NOT NULL AND item_code IS NOT NULL`.
- A blank (non-NULL) shipped key can sit in the shipped set, but it can only match an outer row that has a blank key, and the outer guard rejects those. Mutation M1 below proves the guard is load-bearing.

**NOT IN cannot go NULL.**
- Every element of the outer tuple is non-NULL whenever the IN is evaluated:
  - `tenant_id` and `line_state` are NOT NULL in the model (`facts.py`), and cip has 0 NULLs in either.
  - `operating_unit` is coalesced.
  - `order_no` and `item_code` are guarded non-blank in the same AND.
- The subquery filters out NULL `order_no` and `item_code`. Its tenant comes from a NOT NULL column, and its operating unit is coalesced. So every subquery key is non-NULL.
- Result: the IN is strictly true or false, and `NOT (...)` cannot drop a row as NULL. The test `test_shipped_row_with_null_key_does_not_hide_unrelated_open` covers this.

**The ORM subquery does not correlate.**
- The twin is an `aliased(model)`, so SQLAlchemy does not auto-correlate it with the outer table.
- Confirmed on cip: the set the exclude filter drops equals my independent self-join set.

**Readers:**
- **Brief and dashboard:** one shared `inbound_not_received_count_stmt` (status != received, tenant scope, plus the rule). Correct.
- **`lineup_quarter_summary`:** reads facts with the rule. Correct.
- **Shipping:**
  - `_apply_fact_where_clause` applies the rule, which covers the grid, KPI tiles, cohorts, commercial summary and newly-landed.
  - ETA-shift applies it on every path. It is applied twice on the filtered path (harmless).
  - `/summary` applies it to every count, and the additive `open_lines_skipped_shipped_twin` uses the FILTER form.
- **CPOR intake MAC:** both queries apply the rule. Correct.

**Observations for implementation review (not failures):**
- **Slow positive form.** The positive WHERE form, `WHERE open_order AND open_has_shipped_twin(F)`, took **35.8 s** on cip under RLS. The negated filter form took **0.57 s**. No product reader uses the positive WHERE form today (`/summary` uses FILTER, which takes 2.07 s end to end). The helper docstring does not warn against the positive form. A one-line warning would stop a future reader from paying 35 s.
- **Unrelated changes in the same diffs.** Some of the diffs in these files belong to other dirty-tree work, not to N-0071:
  - brief card detail copy strings;
  - the lineup `arrived` lifecycle bucket.

  Attribution rests on the IMPL table because nothing is committed.

## 2. Tests and mutation tests: VERIFIED_WITH_LIMITATIONS

Commands were run from `apps/api` in a subshell, as `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider ...`.

**Test results:**
- `tests/test_shipment_strict_pair.py`: **19 passed**.
- All 23 suites from IMPL section 4 in one run: **242 passed, 33 errors**. This equals the IMPL figures: 186+56 passed, 13+20 errors.
- All 33 errors are the conftest cip guard ("Refusing write-capable test module ... database name is 'cip'") in:
  - `test_shipping_commercial_kpis.py`
  - `test_shipping_newly_landed.py`
  - `test_lineup_po_auto_link.py`
  - `test_lineup_po_auto_link_actions.py`

  These modules were **not run**, and `ALLOW_TESTS_ON_DEV_DB` was not set. **This is the limitation:** they need a disposable database.

**My own mutation tests** (temporary edits to the helper, then restored):

- **M1: blank order can pair.**
  - Change: removed `trim(coalesce(order_no,'')) != ''` from `open_has_shipped_twin`.
  - Result: **2 failed**, `test_open_without_order_or_item_is_never_paired[]` and `[   ]`.
  - The `[None]` case still passes, which is correct: NULL keys are filtered from the shipped set and never compare equal.
- **M2: any non-shipped row can be dropped, not only open_order.**
  - Change: `!= "open_order"` became `== "__mutant__"` in `exclude_open_when_shipped_twin`.
  - Result: **1 failed**, `test_only_open_rows_are_dropped`.
- **Restored.**
  - The sha256 after the restore is identical to the original: `84f8b0201f1f4e10867cf4808e7c3b477aec033eed1a813b2f537e36454ba462`.
  - The file is untracked (`git status` shows `??`), so `git diff` cannot show it clean. The hash is the proof instead.
  - The suite after the restore: 19 passed.
  - The backup copy was deleted.

## 3. cip read-only: VERIFIED

- **Scripts:** `.eif/audit/PROGRAMME_20261007/N0071_ver_probe.py` and `N0071_ver_probe2.py`.
- **Outputs:** `N0071_ver_probe_out.json` and `N0071_ver_probe2_out.json`.
- **Connection:** psycopg driver from `get_settings().database_url_sync`; no secret was printed.
- **Read-only proof:** both scripts printed `current_database() = cip` and `transaction_read_only = on`, and rolled back.
- **RLS:** `cip.product_lines` was unset, so the RLS function lets every row through.

**Table state:**
- 15,255 fact rows: open_order 1,775 and shipped 13,480.
- One tenant (`default`).
- 0 NULL tenants, 0 NULL line_state, 0 open rows with a blank order or item.

**My independent SQL:** a plain `SELECT DISTINCT o.id ... JOIN ... s` self-join on the strict key with its own `btrim` guards. It does not import the helper's SQL.

| Measure | Result |
|---|---|
| Independent join | **552** ids, md5 `4a4aef0453e6f1ad4c6e78d3e4df2a57` |
| Helper ORM set | **552** ids, same md5; 0 ids on either side only |
| Rows the exclude filter drops | 552, equal to the independent set; all open_order |
| Units / amount of the 552 | 42,956 / 27,833,737.92, matching IMPL |

**No fact row was rewritten:**
- `max(updated_at)` = `max(created_at)` = 2026-09-21 18:15:13+02.
- Rows updated since 2026-10-07 00:00 SAST: **0**. Since 13:00 SAST: **0**. Twin rows updated today: **0**.
- The database clock read 2026-10-07 16:35+02 at the time.
- `pg_stat_user_tables` counters are cumulative (n_tup_upd 609, n_tup_del 6337, n_tup_ins 6563). I had no snapshot from before the run, so they are context, not proof.

**No write in the code:**
- The diffs of the changed readers contain no added insert, update, delete, commit, flush or `.add(`. The only "insert" in the helper is `list.insert`.
- No migration touches this; there is no alembic commit since 2026-10-06 for it.
- Nothing is committed, so git history has no fact rewrite.

## 4. Consistency: VERIFIED

These are the real code paths, called directly on an async psycopg session in a READ ONLY transaction on cip.

**Shipping `/summary` and the lines grid now agree:**

| Measure | `/summary` | Grid (`shipping_evidence_lines`) |
|---|---|---|
| Total lines | 14,703 | 14,703 |
| open_order | 1,223 | 1,223 |
| shipped | 13,480 | 13,480 |

- `open_lines_skipped_shipped_twin` = 552.
- 14,703 + 552 = 15,255, the stored total.

**Brief and dashboard against the supply overview:**
- `inbound_not_received_count_stmt` = **1,561**.
- `supply_overview.open_lines` = **1,561**, which is pipeline 1,223 + shipped-not-landed 338.
- They agree, because cip has 0 NULL statuses, so `!=` and `IS DISTINCT FROM` give the same count.

## 5. Readers that still total open plus shipped without the rule: FAILED

In `apps/api/app/services/supply_overview.py` (the raw SQL aggregate), `open_lines`, `open_units`, `pipeline_lines` and `pipeline_units` apply the rule. These columns do not:

| Column (UI) | cip now | Twin opens inside | With the rule |
|---|---|---|---|
| `eta_past_no_pod_lines` ("Unreceived past ETA" tile, `SupplyOverview.tsx`) | 1,218 | **532** | 686 |
| `overdue_commercial_lines` | 375 | **11** | 364 (= the shipping overdue KPI through `predicate_overdue` + rule) |
| `oldest_eta_past`, `oldest_days_past_eta` | n/a | can be driven by a stale open twin | not measured |

The landed columns (`pod_date IS NOT NULL`) are unaffected today, because no open row has a pod_date.

**Lower severity, by design or out of rule scope:**
- **`GET /inbound`** (`inbound_shipments.py` `list_inbound`): returns every stored row, twins included. It is a list, not a total.
- **Shipment evidence grid count** (`shipment_evidence.py` ~1438): counts staging and evidence lines, not facts. This is the steward path.
- **Distributor and product usage, and `distributors.py` `linked_inbound_rows`:** reference counts for delete and merge safety. These must see stored rows.
- **`data_integrity_audit.py`:** an audit path.
- **Already wired, checked:** `channel_ops.py` (3 call sites), `lineup_bulk_rederivation`, `lineup_po_auto_link`, `lineup_po_reconciliation` (on the evidence read model) and `net_requirement`.
- **Shipped-only readers, nothing to drop:** `channel_ops_derived_stock` and `woc_observation` filter `line_state='shipped'`.

## Ledger (run RUN-20261007-N0071-VER)

| Event | State | Ledger rev | Node rev before |
|---|---|---|---|
| `node.verification` behavioral | fail | 1658 | 12 |
| `node.verification` referent | pass (path `apps/api/app/services/shipment_strict_pair.py`) | 1659 | 13 |
| `node.stage` verify | stage note gives the verdict | 1660 | 14 |

- Payloads: `N0071_ver_behavioral.json`, `N0071_ver_referent.json`, `N0071_ver_stage_verify.json`.
- `complete` was not set.

## Limitations

- R2, same model family. No independent model was used.
- 33 cip-guarded tests were not run; they need a disposable database.
- Live screens and HTTP endpoints were not exercised through the running services. Reader functions were called directly; no service was restarted.
- `pg_stat` had no snapshot from before the run.
- Unrelated changes in the same dirty files cannot be separated by commit.
- Partial-ship decision (10 pairs, 904 units) is still pending with Warren; it was not judged here.

---

## Re-verification (rounds 2-3) (RUN-20261008-N0071-VER2)

Scope: IMPL rounds 2-3 (`N0071_IMPL.md`), against D-0057 (strict-pair skip, never rewrite facts), D-0065 (partial lines count the remainder) and the pro-rata value decision (`amount x remainder / open qty`).
Implementation run: RUN-20261007-N0071-IMPL. Verification run: RUN-20261008-N0071-VER2. Lenses: verification-controller, database-specialist, implementation-reviewer.

**Independence rung: R2.** Fresh-context subagent, same model family, not a different model. This run continues a session that was cut off by a usage limit; that session left no files and no partial section, so every result below was produced in this session. IMPL was used only for the file list and the claimed numbers.

### Overall verdict: FAILED (narrow), one reader outside the implemented set

- **What holds (VERIFIED):**
  - The round-1 failure is fixed. On cip, "Unreceived past ETA" is 696, and supply overdue = shipping overdue KPI = 364. My own SQL gives the same numbers.
  - The helper and every reader changed in rounds 2-3 are correct.
  - 55/55 strict-pair tests pass. My 4 in-memory mutants were all caught. The 10 partial lines, the remainder of 336 and the pro-rata total (USD 291,836) equal my independent SQL.
  - Channel ops and supply agree to the unit.
  - No fact row was written.
- **What fails:** one user-visible total still adds open lines, covered twins included, to a "Shipped" figure:
  - The reader is `lineup_case_suggested_pos.py` (lines 91 and 210, `func.sum(EV.quantity)` with no `line_state` filter and no rule). The UI shows it as the "Shipped units" column of the suggested POs in `CurrentLineupSection.tsx`.
  - On cip the PO-linked evidence (`shipment_evidence_current`) holds 404 open_order rows (25,509 units). 110 of those rows (6,810 units) are covered strict twins.
  - The PO auto-link proposals' `total_shipped_units` counts shipped rows only. So two screens that both say "Shipped" for POs count differently, which breaks D-0057 ("no two screens disagree").
  - This reader is not new and N-0071 did not touch it (the file is clean at `6de21b8d`). Discovery and the round-1 verification (my section 5 above) both missed it.
- **Fix (small):** add `EV.line_state == 'shipped'` to both queries.
  - This matches the column label and `PLAN_VS_EXECUTED_SHIPPED_TAXONOMY`, and it makes the twin rule irrelevant for this reader.
  - The alternative is for the orchestrator or Warren to record this reader as out of N-0071's scope (`finding.defer`, follow-up node). With that exclusion recorded, the verdict becomes VERIFIED_WITH_LIMITATIONS. The choice is theirs, not mine.

| # | Check | Verdict |
|---|---|---|
| 1 | Code review: helper and readers changed in rounds 2-3 | VERIFIED (3 minor observations) |
| 2 | Tests, round 1-3 suites, own mutants | VERIFIED_WITH_LIMITATIONS (33 cip-guarded tests not run) |
| 3 | cip read-only: partial lines, remainder, pro-rata, supply tiles, overdue, channel ops vs supply, no write | VERIFIED |
| 4 | Readers still totalling open + shipped without the rule | FAILED: suggested POs "Shipped units" (1 reader) |
| 5 | The 2 `test_lineup_open_channel.py` failures | Not caused by N-0071 (from another run's edit to the message text) |

### RV1. Code review: VERIFIED

**Files and state.**
- `apps/api/app/services/shipment_strict_pair.py`: untracked, sha256 `f7c217a64800c8d58a50668bf770e6b27a51abff006751154a7e72000d8eb561`, 311 lines.
- `tests/test_shipment_strict_pair.py`: untracked, sha256 `692328ff...8a97`.
- Readers reviewed through `git diff`: `supply_overview.py`, `channel_ops.py`, `lineup/net_requirement.py`, `lineup_po_auto_link.py`, `lineup_po_reconciliation.py`, `lineup_bulk_rederivation.py`, `shipping.py` and `grid_fields.py`. I also looked at the round-2 readers `brief_signals.py`, `inbound_lineup_quarter.py` and `intake_weighted_mac.py`.

**Helper (D-0065 and pro-rata).**
- **Key.** Tenant (when the model has `tenant_id`), `lower(trim(coalesce(operating_unit,'')))`, `lower(trim(order_no))` and `lower(trim(item_code))`. The ORM window and the SQL text both partition by this same key.
- **Unusable keys and states.** NULL or blank order or item is filtered out before the window, so it never pairs. Only `shipped` and `open_order` rows enter the window.
- **Shipped total.** The shipped quantity is summed per key, not taken from the first twin. The mutant that switched to the largest twin only failed 3 tests.
- **Remainder and skip.**
  - The remainder is `open - shipped` when `open > shipped`, else 0.
  - `keep_counted_line` drops exactly the ids with `n_shipped > 0 AND open_qty <= shipped_qty`. It uses `id NOT IN (...)` on the primary key, so it cannot go NULL.
  - `twin.kept` (`fact_id IS NULL OR counted_qty > 0`) selects the same set. On cip: 542 ids not kept, equal to my independent covered set.
- **`counted_amount`.** No twin gives the stored amount. A partial line gives `amount * counted_qty / nullif(quantity, 0)`. A covered line gives 0.
  - `amount` and `quantity` are `Numeric(18,4)`, so there is no integer truncation.
  - `counted_qty > 0` implies `quantity > 0`, because shipped quantities are never negative on cip (0 rows below 0), so the `nullif` never fires on a partial line.
  - The SQL text form has the same precedence: `(amount * counted_qty) / quantity`.
- **Shipped and arrived rows are never adjusted.** `counted_quantity = coalesce(counted_qty, quantity)`, and only open_order rows are in the CTE.

**Readers.**
- **`supply_overview._headline_sql`.**
  - Every column now goes through `LEFT JOIN twin_rem` + `WHERE ... AND {_KEPT}`. That covers "Unreceived past ETA", oldest past ETA, overdue, open, pipeline and the landed counts.
  - Units use the counted quantity. `shipped_*` and `arrived_*` keep the stored quantity, which is correct because the rule never adjusts them.
  - The CTE window spans all tenants but is partitioned by tenant, so the result is correct.
- **`channel_ops.py`.** All three readers (movement shipped units, weekly flow, cover `inbound_open`) use `twin_remainder` + `twin.kept` + `sum(counted_quantity)`. Correct.
- **`net_requirement._in_transit_by_dist_product`.** Same pattern. Its shipped-not-landed rows are untouched. Correct.
- **`lineup_po_auto_link`.** `outerjoin_twin_remainder(select(FactInboundShipment))` + `add_columns(counted_quantity)`; `ship_qty` comes from the counted quantity. For shipped rows the counted quantity equals the stored one. Correct.
- **`lineup_po_reconciliation` (pipeline).**
  - It uses `twin_remainder(EV, row_filter=active_evidence_line_predicate)`, and the predicate works on the alias.
  - **Observation O1:** `shipment_evidence_current`, the default read model, has no `tenant_id`, so the evidence key is tenant-less. That is harmless with one tenant (cip has one), but it would pair across tenants if a second tenant ever shares an order and item. The D-0057 helper behaved the same way.
- **`lineup_bulk_rederivation._shipment_q1_hint`.** Non-open rows are summed directly, which is valid because the rule never adjusts them. Open ids in the window go through the remainder join with `kept`. The totals are equivalent to the full join.
  - The same diff also contains unrelated `refused_no_month_columns` work from another run. Because nothing is committed, attribution rests on the IMPL table.
- **`shipping.py`.**
  - `_apply_fact_where_clause` adds `keep_counted_line`. This covers the grid, KPI tiles, cohorts and newly-landed.
  - ETA-shift scope adds `keep_counted_line` on every path.
  - `/summary` uses `keep_counted_line`, plus a FILTER count of `skipped_open_twin_line`.
  - `_aggregate_currency_qty_lines` joins `twin_remainder` and sums `counted_quantity` and `counted_amount`. These are the pro-rata KPI values for current incoming, overdue and landed.
  - The arriving-by-distributor totals sum `counted_quantity` and pass through `_apply_fact_where_clause`, so a covered line is neither counted as a line nor summed.
  - `_still_to_ship_by_id` has no `kept` filter, so a covered line would return 0. This is unreachable from `/lines`, which already filters covered lines out.
- **`grid_fields.py`.** `still_to_ship` is a static key with the label "Still to ship". `test_grid_fields` parity passes.

**Observations (not failures).**
- **O1.** The tenant-less evidence key (above).
- **O2.** D-0065 compares each open line with the key's whole shipped total. Two open lines on one key with a single shipped total would each subtract the full total. On cip, no key has more than one open twin line (0), so this does not occur today. If it ever appears, it is a question for Warren.
- **O3. IMPL R2.3 is worded too strongly.** It says "no key has more than one shipped twin on cip today". In fact, 46 keys have 2 shipped twins each (92 shipped rows). All 46 of their open lines are covered by the sum, and they are also covered by the largest single twin (`N0071_ver2_probe2_out.json`). The conclusion IMPL drew (summing changes nothing on cip today) still holds; the wording is wrong. The implementer's check counted only partial lines.

### RV2. Tests and mutants: VERIFIED_WITH_LIMITATIONS

Run from `apps/api` in a subshell: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider ...`.

| Run | Result | IMPL claim |
|---|---|---|
| `tests/test_shipment_strict_pair.py` | **55 passed** | 55 |
| Group 1 (15 modules, IMPL section 4 item 3) | **222 passed, 13 errors** | 222 + 13 |
| Group 2 (8 modules, item 4) | **56 passed, 20 errors** | 56 + 20 |
| Wider: `test_shipping*`, `test_channel_ops*`, `test_lineup*`, `test_supply*`, `test_inbound*`, `test_cover*` | **322 passed, 2 failed, 70 errors** | same |

- All 33 group errors are the conftest cip guard ("Refusing write-capable test module ..."). By module: `test_lineup_po_auto_link.py` 18, `_actions` 2, `test_shipping_commercial_kpis.py` 6, `test_shipping_newly_landed.py` 7.
- All 70 errors in the wider run are the same guard (I counted 70 "Refusing" lines).
- Those modules were **not run**, and `ALLOW_TESTS_ON_DEV_DB` was not set. **Limitation:** they need a disposable database.

**Own mutants.**
- **Method.** In memory: the pytest plugin `.eif/audit/PROGRAMME_20261007/n0071_ver2_mutant_plugin.py` reads the helper source, applies the text mutation and registers the module in `sys.modules` before the tests import it.
- **The product file was never written.** sha256 before and after = `f7c217a6...d8eb561`. `git status` still shows `??` (the file is untracked, so `git diff` cannot show it; the hash is the proof).
- **Output:** `n0071_ver2_mutant_out.txt`.

| Mutant | Result |
|---|---|
| `first_twin_only`: shipped total = the largest twin, not the sum (ORM and SQL) | **3 failed**: `two_twins_summed`, `three_twins_cover`, pro-rata `two_twins_summed_counts300` |
| `pro_rata_to_full`: partial line value = full stored amount (ORM and SQL) | **4 failed**: both KPI tests, pro-rata `open10..400` and `two_twins..300` (USD 2,600 vs 2,000) |
| `equal_not_covered`: `open <= shipped` became `<` (exact cover no longer skipped) | **11 failed** (line-rule, brief, ETA-shift, `/summary`, KPI tests) |
| `covered_amount_full`: covered line `counted_amount` = stored amount | **1 failed**: `test_covered_line_counted_amount_is_zero_without_kept_filter` |

### RV3. cip read-only: VERIFIED

- **Scripts:** `N0071_ver2_probe.py`, `N0071_ver2_probe2.py` and `N0071_ver2_probe3.py`.
- **Outputs:** `N0071_ver2_probe_out.json`, `N0071_ver2_probe2_out.json` and `N0071_ver2_probe3_out.json`.
- **Connection:** psycopg from `get_settings().database_url_sync`; no secret was printed.
- **Every connection was opened read-only:** `options=-c default_transaction_read_only=on`, plus `SET TRANSACTION READ ONLY`. Each script printed `current_database() = cip` and `transaction_read_only = on`. The main probe printed both again at the end, after the reader calls. `row_security` was on.
- **Probe time:** 2026-10-08 14:05+02. SAST date = UTC date = 2026-10-08.

**My independent SQL.** Shipped totals are computed per strict key with `GROUP BY`, then joined to open rows, with `btrim` guards. This is not the helper's window form.

| Measure | Independent | Code under test | IMPL |
|---|---|---|---|
| Twin pairs: covered / partial | 542 / 10 | helper not-kept 542, same ids | 542 / 10 |
| Partial lines: open / shipped / remainder | 904 / 568 / **336** | helper `counted_quantity` equals mine on all 10 | 336 |
| Partial lines: stored amount / pro-rata | USD 880,304 / **291,836** | helper `counted_amount` equals mine line by line | 291,836 |
| Grid "Still to ship" for the 10 | = remainder | `_still_to_ship_by_id` equals mine | equal |
| "Unreceived past ETA": raw / with rule | 1,218 / **696** | `supply_overview.eta_past_no_pod_lines` = 696 | 696 |
| Oldest past ETA with the rule | 2026-05-08 | supply 2026-05-08, 153 days (152 on 10-07) | 2026-05-08 |
| Overdue: raw / with rule (SAST and UTC today) | 375 / **364** / 364 | supply `overdue_commercial_lines` 364; shipping KPI overdue 364 lines, 25,271 units, USD 53,240,831 | 364 |
| Open lines / open units | 1,571 / 114,832 | supply 1,571 / 114,832 | same |
| Pipeline lines / units (raw units 127,870) | 1,233 / 85,250 | supply 1,233 / 85,250 | same |

- The per-line table of the 10 matches IMPL R3.3: ids 299, 300, 302, 308, 100351, 100374, 100797, 100962, 100963 and 107364. All are USD and scheduled, with no POD, no ship_confirm_date and no PO; all have a distributor and a product.

**Channel ops against the supply pipeline.**
- My independent `inbound_open` per (distributor, product) totals **86,818** over all pairs, the same as IMPL.
- The real `channel_ops_cover_distribution` returned 2,481 items totalling 15,634. **0 items** differ from my per-pair value.
- **Reconciliation:** the open_order part of my channel-ops pairs (66,025) plus the open units with no distributor or product, which channel ops excludes by design (19,225), equals **85,250**, the supply `pipeline_units`. So both screens count the same open units, remainder included.

**Edge checks on cip.**
- Line states: only `open_order` (1,775) and `shipped` (13,480).
- 0 negative quantities.
- 0 twin open lines with a NULL or 0 quantity.
- 0 keys with more than one open twin line.

**No fact row written.**
- 15,255 rows. `max(updated_at)` = `max(created_at)` = 2026-09-21 18:15:13+02. 0 rows were created or updated in the last 36 h.
- `pg_stat_user_tables` for `fact_inbound_shipment`: n_tup_ins 6,563, n_tup_upd 609, n_tup_del 6,337. These are **identical** to my 2026-10-07 16:35 reading, so there has been no insert, update or delete on the table since then (unless stats were reset, which there is no sign of).
- The round 2-3 diffs add no insert, update, delete, commit, flush or `.add(`.

### RV4. Readers still totalling open + shipped without the rule: FAILED (1)

**Search.** In `apps/api/app`, I grepped for:
- `func.sum(...quantity|amount)` and `FactInboundShipment.quantity|amount`;
- raw `FROM|JOIN fact_inbound_shipment`;
- `func.sum(EV|ShipmentEvidence*.quantity)`.

Results by classification:

| Site | Classification |
|---|---|
| `lineup_case_suggested_pos.py:91, :210` (`total_shipped_units`, also used to order the list at :228) | **FAILED.** Sums PO-linked evidence of every line_state. Shown as "Shipped units" in `CurrentLineupSection.tsx`. cip population: 404 open rows / 25,509 units counted as shipped; 110 rows / 6,810 units are covered twins. The PO auto-link "Shipped" counts shipped only. Fix: `EV.line_state == 'shipped'` (see verdict). |
| `cst_sku_twin_disambiguate.py:221` (`InboundWindow.qty`) | **Low.** Import-steward heuristic. Sums every state per product, but the qty is only a second tie-break key after last date, and it appears in the steward evidence. Not a screen total. Defer. |
| `lineup_distributor_attribution.py:139` | Matches rows by quantity, not a total. Out of scope, as in IMPL. |
| `channel_ops_derived_stock.py`, `woc_observation.py:157`, `po_management.py`, `lineup_po_gap.py`, PO reconciliation shipped | Shipped-only (or landed with `line_state='shipped'`). The rule has nothing to drop. |
| `dsi_soh_reconciliation.py` | Write path at import, landed rows. No-op today (no open row has a POD). Already deferred by IMPL. |
| `shipment_shipped_fact_identity_twin_merge.py`, `shipment_plan_d_cutover.py`, `cst_alias_era_derive.py` (min dates), `product_master_gap_worklist.py` (unresolved tokens), `distributors.py` counts, `amount_scale.py` (per-row clause), `observation_transitions.attach_fact_line_columns` (per-row display) | Import, merge or audit paths, reference counts or per-row values. Not totals. |
| `shipping.py:407` `_count_shipment_facts` and the cohort id statements | Go through `_apply_fact_where_clause`, so they are on the rule. |

The D-0057 helpers (`exclude_open_when_shipped_twin`, `open_has_shipped_twin`) are referenced only inside the helper module, which confirms the docstring claim.

### RV5. The 2 failures in `tests/test_lineup_open_channel.py`: not caused by N-0071

- **Failing tests:** `test_sync_eligibility_open_channel_missing_account` and `test_sync_skip_detail_unassigned_placeholder_reference_data`. Both assert that the skip message contains `OPEN_CHANNEL` or `UNASSIGNED`.
- **Cause:** the `git diff` of `lineup_open_channel.py` (8+/8-) rewrites only the message copy in `sync_skip_detail_message`. The new text ("The Open Channel account is missing ...") drops those codes. The HEAD text contained them.
- **Not from N-0071:**
  - The file's mtime is 2026-10-07 09:01:58+02, before N-0071's implementation started (lease 15:24).
  - The test file is unmodified against HEAD.
  - Neither file references shipments or `shipment_strict_pair`.
- **Status:** these 2 failures predate N-0071 (they come from another run's edit to the message text). The tests or the copy need reconciling in that run. No stash was used.

### Ledger (run RUN-20261008-N0071-VER2)

| Event | State | Ledger rev | Node rev before |
|---|---|---|---|
| `node.verification` behavioral | fail | 1766 | 29 |
| `node.verification` referent | pass (path `apps/api/app/services/shipment_strict_pair.py`) | 1767 | 30 |
| `node.stage` verify | the stage note gives the verdict | 1768 | 31 |

- Payloads (in `.eif/audit/PROGRAMME_20261007/`): `N0071_ver2_behavioral.json`, `N0071_ver2_referent.json`, `N0071_ver2_stage_verify.json`.
- **`--run` placement:** the first attempt placed `--run` after the subcommand. It was rejected by argparse before anything was written. The retry with `--run` before `event` succeeded.
- There was no `RUNTIME_INTEGRITY` retry.
- `program.py verify` at rev 1768: integrity_ok true. The only gate issues are acknowledged debt on N-0006, N-0013, N-0014, N-0015 and N-0016; none is on N-0071.
- `complete` was not set.

### Limitations

- R2, same model family. No independent model was used.
- 33 cip-guarded tests (70 in the wider run) were not run; they need a disposable database.
- Live screens and HTTP endpoints were not exercised. Reader functions were called directly; no service was restarted.
- The suggested-PO figures are for the whole PO-linked population, not for one case.
- Unrelated dirty-tree changes in the same files cannot be separated by commit.
- **Process slip:** one shell call in this session started with a bare `cd` to the repo root, before a `git diff --stat`, instead of using a subshell. It was harmless (read-only, repo root) but against the run's no-`cd` rule.

---

## Re-verification (round 4) (RUN-20261008-N0071-VER3)

Scope: IMPL round 4 (`N0071_IMPL.md`, "Round 4"), which answers RV4 above. I also spot-checked that rounds 1-3 still hold. The checks were made against D-0057 (no two screens disagree; facts are never rewritten), D-0065 and the PO auto-link "Shipped" figure, which counts shipped lines only.
Implementation run: RUN-20261007-N0071-IMPL. Verification run: RUN-20261008-N0071-VER3. Lenses: verification-controller, implementation-reviewer.

**Independence rung: R2.** This was a fresh-context subagent of the same model family, not a different model. IMPL was used only for the file list and the numbers it claimed. Every result below was produced in this session (2026-10-08, about 20:40-21:05 +02).

### Overall verdict for N-0071 (rounds 1-4): VERIFIED_WITH_LIMITATIONS

- **RV4 is closed.** In both suggestion readers, "Shipped units" now counts shipped evidence lines only:
  - On cip, the readers' values equal my independent raw-SQL shipped-only SUM on every sampled row: 881/881 PO rows and 73/73 distributor rows over 8 cases.
  - Suggestion membership, `matched_product_count` and `po_count` are unchanged.
  - My 4 in-memory mutants are each caught by the new test.
- **Rounds 1-3 still hold.** The helper and its test file are byte-identical to the VER2 hashes. No round 1-3 reader file has changed since VER2. The suites give the same counts as VER2, plus the one new test. The fact table has had no insert, update or delete.
- **Limitations** are listed at the end of this section. None of them is a failure.

| # | Check | Verdict |
|---|---|---|
| 1 | Code review of the round-4 diff; FILTER on the sum vs D-0057, D-0065 and PO auto-link "Shipped" | VERIFIED (2 minor observations) |
| 2 | New test, round 1-4 suites, own mutants, file unchanged | VERIFIED_WITH_LIMITATIONS (cip-guarded modules not run) |
| 3 | cip read-only: independent shipped-only SUM vs reader output, sample of 8 cases | VERIFIED |
| 4 | RV4 closed; earlier VERIFIED items still hold | VERIFIED |

### RV4-1. Code review: VERIFIED

**File state.**
- `apps/api/app/services/commercial_planner/lineup_case_suggested_pos.py`: tracked, `M`, +12 / -3, sha256 `a7f200bdbb115a891c1d02e6867d05c9b13217b2fcf315cbcf20a711cd673b50`. This equals the IMPL hash.
- `apps/api/tests/test_lineup_case_suggested_pos.py`: `M`, +115, sha256 `4fa4d4fb7408e72c39d62d33391ed81fff802b8c6139ab373545a30a69c7eb7c`. This equals the IMPL hash.

**The diff.** `_shipped_units_sum()` returns `coalesce(sum(EV.quantity) FILTER (WHERE EV.line_state = 'shipped'), 0)`. It replaces the unfiltered sum in exactly three places:
- `suggest_pos_for_case`, the `total_shipped_units` column;
- `suggest_distributors_for_case`, the `total_shipped_units` column;
- `suggest_distributors_for_case`, the second `order_by` key.

Nothing else in the file changed. I checked the following:
- Joins, `WHERE`, `GROUP BY`, `apply_active_evidence_filter`, the distributor post-filter and the PO ordering (matched products, then PO number) are all untouched.
- The column is computed in SQL and passed through `float(shipped_units or 0)`. The `coalesce` returns 0 when a group has no shipped line. Without it, a FILTER over zero rows would return NULL.
- In the distributor query, the `order_by` key is the same expression as the select column, so the order and the displayed value cannot drift apart.

**Why a FILTER on the sum and not a WHERE.** A WHERE clause would have changed the suggestions, not just the number:
- An open-only PO would drop out of the list.
- `matched_product_count` would fall for POs whose case products are only on open lines.

With the FILTER, an open line still corroborates the PO's product match, which is what "matched products" means. It just is not counted as a shipped unit. The new test pins this: PO-C is open-only and is still suggested with 0. My mutant `where_not_filter` (below) confirms that the alternative would change membership.

**Consistency with the decisions.**
- **D-0057** governs how an open line is counted in open and pipeline totals, where it is skipped when a strict shipped twin exists. A "Shipped units" figure should contain no open line at all, with or without a twin.
  - Counting shipped lines only makes the strict-pair rule moot for this reader. No open unit is in the figure, so a covered twin cannot be double-counted.
  - This is the fix proposed in VER2, and it matches `PLAN_VS_EXECUTED_SHIPPED_TAXONOMY`.
- **D-0065** (a partial line counts its remainder) applies to open totals only. The remainder is open quantity, so it rightly does not appear in a shipped figure.
- **PO auto-link "Shipped".** `lineup_po_auto_link.py:596-597` adds `ship_qty` to `shipped_units` only when `line_state == "shipped"`. `ship_qty` is the counted quantity, which equals the stored quantity for shipped rows. The proposal's `total_shipped_units` (`:719`) is the sum of those. Both "Shipped" figures are now shipped-only, so the D-0057 "no two screens disagree" breach from RV4 is gone.

**Observations (not failures).**
- **O4. Case normalisation.**
  - PO auto-link normalises with `(line_state or "").strip().lower()`. The reader compares exactly (`== "shipped"`).
  - On cip the evidence relation has only `open_order` and `shipped`, both lower case, so the two are equivalent today. My independent SQL uses `lower(btrim(line_state))` and still equals the reader on every row.
  - The exact form is the codebase norm (23 other `line_state == "shipped"` sites). It would matter only if an import ever wrote a variant spelling.
- **O5. The two "Shipped" figures still read different sources.**
  - Auto-link reads `fact_inbound_shipment`. The suggestion readers read the evidence relation (`shipment_evidence_current`).
  - Both are shipped-only now. The source split is older than N-0071 and outside its scope.
- **Test hygiene (minor).** The new test registers `@compiles(JSONB, "sqlite")` process-wide when it runs. That affects only SQLite DDL rendering, and the other 4 tests in the file and both full suites pass with it in place.

### RV4-2. Tests and mutants: VERIFIED_WITH_LIMITATIONS

Tests were run from `apps/api` in a subshell with `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`.

| Run | Result | IMPL claim |
|---|---|---|
| `test_lineup_case_suggested_pos.py` + `test_lineup_case_distributor_suggest_assign.py` | **15 passed** | 15 |
| Group 1 (15 modules, IMPL section 4 item 3), `n0071_ver3_group1_out.txt` | **222 passed, 13 errors** | 222 + 13 |
| Group 2 (8 modules, item 4), `n0071_ver3_group2_out.txt` | **56 passed, 20 errors** | 56 + 20 |
| Wider (`test_shipping*`, `test_channel_ops*`, `test_lineup*`, `test_supply*`, `test_inbound*`, `test_cover*`), `n0071_ver3_wider_out.txt` | **323 passed, 2 failed, 70 errors** | 323 / 2 / 70 |

- **The 70 errors.** All 70 `E` lines in the wider run are "Refusing write-capable test module" (the conftest guard for cip). By module:
  - business-unit resolution 20;
  - PO auto-link 18;
  - customer token stamp 13;
  - newly-landed 7;
  - commercial KPIs 6;
  - bulk-backfill integration, auto-link actions and PO-link carry supersession, 2 each.
- **They were not run.** `ALLOW_TESTS_ON_DEV_DB` was not set.
- **The 2 failures** are the same two `test_lineup_open_channel.py` message-text assertions as VER2 RV5 ("OPEN_CHANNEL" / "UNASSIGNED" missing from the new copy). They come from another run, not from N-0071.

**Own mutants.**
- **Method.** The mutants ran in memory through the pytest plugin `.eif/audit/PROGRAMME_20261007/n0071_ver3_mutant_plugin.py`. It reads the service source, applies the text mutation and registers the module in `sys.modules` and on the parent package before the test imports it.
- **The product file was never written.** sha256 was `a7f200bd...3b50` before and after. `git diff --stat` on the file still shows +12 / -3, identical to IMPL.
- **Control.** With the plugin loaded and no mutant selected: 5 passed.
- **Output:** `n0071_ver3_mutant_out.txt`.

| Mutant | Result |
|---|---|
| `twin_open_counted`: an open line that has a strict shipped twin (same OU + order + item) also counts as shipped (correlated EXISTS in the FILTER) | **1 failed**: `assert 25.0 == 15.0` (PO-A) |
| `where_not_filter`: the filter moves from the SUM to the WHERE of both queries | **1 failed**: `['PO-A', 'PO-B'] == ['PO-A', 'PO-B', 'PO-C']` (the open-only PO is dropped) |
| `order_asc`: distributor tie-break ascending | **1 failed**: `[(1, 15.0), (2, 42.0)] != [(2, 42.0), (1, 15.0)]` |
| `all_states`: the pre-fix unfiltered sum | **1 failed**: `assert 75.0 == 15.0` |

In every mutant, the 4 older mock tests passed and the new test failed, as expected.

### RV4-3. cip read-only: VERIFIED

- **Scripts:** `N0071_ver3_probe.py` and `N0071_ver3_probe2.py`.
- **Outputs:** `N0071_ver3_probe_out.json` and `N0071_ver3_probe2_out.json`.
- **Connection.** The URL comes from `get_settings().database_url_sync` as `postgresql+psycopg`; no secret was printed. Each connection was opened with `options=-c default_transaction_read_only=on -c statement_timeout=60000`, plus `SET TRANSACTION READ ONLY`.
- **Session checks.** Each script printed `current_database() = cip` first, then `transaction_read_only = on` (and on again at the end), `statement_timeout = 1min` and `row_security = on`. Each rolled back.
- **Probe time:** 2026-10-08 18:59 UTC.
- **No per-row queries.** The independent side was 2 grouped queries in 4.6 s. The real readers ran for 8 sample cases only, in 24.3 s.

**Independent formulation.**
- One raw-SQL query covers every lineup case. Distinct `(case_id, product_id)` from `commercial_lineup_line` are joined to `shipment_evidence_current` (the read relation the code selects) on the product, for PO-linked rows, and grouped by case and PO. A second query groups by case and distributor through `purchase_order` and `dim_distributor`.
- Shipped-only is `sum(quantity) FILTER (WHERE lower(btrim(line_state)) = 'shipped')`. This is the auto-link normalisation, written as SQL text rather than the ORM expression under test.
- **Population:** 3,763 (case, PO) pairs, of which 304 carry open units.
- **The sample** (`sample_cases`) is the 6 cases with the most open units on PO-linked evidence (123, 9, 122, 119, 144 and 120, with 13,650 down to 4,083 open units) plus the two lowest-id cases with products (7 and 90).

| Reader (8 sample cases) | Rows | Reader = independent shipped-only | Reader = all-states | Reader total | Independent shipped-only | Independent all-states |
|---|---|---|---|---|---|---|
| `suggest_pos_for_case` | 881 | **881 / 881** | 725 | 285,433 | **285,433** | 324,975 |
| `suggest_distributors_for_case` | 73 | **73 / 73** | 36 | 413,664 | **413,664** | 458,356 |

- **Counts.** `matched_product_count` equals the independent `count(DISTINCT product)` on 881/881 PO rows and 73/73 distributor rows. `po_count` equals it on 73/73.
- **Zero rows still listed.** 17 PO rows and 1 distributor row have 0 shipped units and are still listed, which confirms that membership is unchanged.
- **Distributor order.** In 8 of 8 cases the readers order distributors by matched products, then independent shipped-only units. In 2 of the 8 cases the all-states key would have produced a different order. Those are cases where the fix changes what Warren sees.
- **Mismatches:** none.

**Population note.**
- PO-linked rows of every product in `shipment_evidence_current`: open_order 528 rows / 34,571 units, shipped 14,382 rows / 1,324,451 units. Line states present: only `open_order` and `shipped`.
- VER2's 404 / 25,509 also required `product_id IS NOT NULL`, so the two figures are not comparable.
- Probe 2 shows the evidence did not change: `shipment_evidence_observation` max `created_at` / `updated_at` / `observed_at` is 2026-09-21 18:32+02, with 0 rows since VER2. There were 0 import jobs today.

**No write.**
- `fact_inbound_shipment`: 15,255 rows, max `created_at` = max `updated_at` = 2026-09-21 18:15:13+02.
- `pg_stat_user_tables` for it: n_tup_ins 6,563, n_tup_upd 609, n_tup_del 6,337. These are **identical** to VER2 and to the 2026-10-07 reading.
- The round-4 diff adds no DML, commit, flush or `.add(`.
- My probes are SELECT-only inside read-only transactions.

### RV4-4. RV4 closed; earlier VERIFIED items still hold: VERIFIED

- **RV4.** The FAILED reader (`lineup_case_suggested_pos.py`, both queries and the sort key) now counts shipped lines only (RV4-1 to RV4-3).
  - The PO-linked open units that VER2 found counted as shipped, covered twins included, are no longer in either figure. On the sample, the reader equals shipped-only, not all-states (725 of 881 PO rows happen to be equal under both, because they have no open line).
  - The Low item `cst_sku_twin_disambiguate.py:221` stays deferred, as VER2 classified it (a steward tie-break, not a screen total).
- **Rounds 1-3 spot-check.**
  - `apps/api/app/services/shipment_strict_pair.py`: sha256 `f7c217a6...d8eb561` and `tests/test_shipment_strict_pair.py`: sha256 `692328ff...8a97`. Both are byte-identical to VER2 and both still untracked (`??`).
  - Group 1 includes `test_shipment_strict_pair.py`, and its 222 passes equal VER2.
  - **Files changed since VER2.** Searching `apps/api/app` and `apps/api/tests` for `.py` files newer than VER2's `N0071_ver2_probe3_out.json` (14:09+02) finds:
    - the two round-4 files;
    - listing-capture files (`registry.py`, `snapshot_retention.py`, their tests);
    - `worker/celery_app.py` and `worker/tasks.py`.

    None of the round 1-3 readers is on that list. The listing-capture and worker changes come from another run. `tasks.py` mentions shipments only in pre-existing code; its diff lines contain no shipment or inbound text.
  - The VER2 RV3 cip figures depend only on unchanged facts and unchanged evidence (no write since then), so I did not re-run them.

### Ledger (run RUN-20261008-N0071-VER3)

| Event | State | Ledger rev | Node rev before | Result |
|---|---|---|---|---|
| `node.verification` behavioral | pass | 1788 | 39 | recorded (`pass_run` RUN-20261008-N0071-VER3) |
| `node.verification` referent (path `apps/api/app/services/commercial_planner/lineup_case_suggested_pos.py`) | pass | - | 40 | **NOT recorded**: `RUNTIME_INTEGRITY: [Errno 13] Permission denied` on the first attempt and again on the one permitted retry |
| `node.stage` verify (the stage note gives the verdict) | - | - | - | **NOT attempted**: the ledger part stopped after the failed retry |

- **Payloads** (in `.eif/audit/PROGRAMME_20261007/`): `N0071_ver3_behavioral.json`, `N0071_ver3_referent.json` and `N0071_ver3_stage_verify.json`.
  - The stage payload carries `expected_revision` 41, which assumes the referent event lands first.
  - Re-read the node revision before replaying either one.
- **State after the failures.** `status --node N-0071` still shows node rev 40 and stage validate. The referent is still the VER2 pass on `shipment_strict_pair.py`. Ledger revs 1789-1790 were other runs' events written in the same minutes, which suggests contention for the ledger file.
- **`program.py verify` at rev 1790:** integrity_ok true. The only gate issues are acknowledged debt on N-0006, N-0013, N-0014, N-0015 and N-0016; none is on N-0071.
- **Still to do.** The orchestrator must replay the referent event and then the stage event, both with `--run RUN-20261008-N0071-VER3` placed before `event`.
- `complete` was not set.

### Limitations

- **Independence.** R2, same model family; no independent model was used.
- **Tests not run.** 70 cip-guarded test errors (13 + 20 in the groups) were not run; they need a disposable database.
- **No live check.** The live "Shipped units" column in `CurrentLineupSection.tsx` and the HTTP endpoints were not exercised. The readers were called directly, and no service was restarted.
- **Sample only.** The cip comparison covers 8 of 36 cases, chosen to include the cases with the most open units. IMPL's 36-case pass reported the same equality, but its "independent" side reused the ORM FILTER expression; mine is raw SQL with a normalised `line_state`.
- **Deferred items.** VER2 observations O1 (tenant-less evidence key), O2 (several open lines per key) and the deferred `cst_sku_twin_disambiguate.py` heuristic remain as recorded; none applies to this reader.
- **Uncommitted tree.** Nothing is committed, so the file state is proved by hashes, not by a commit.
