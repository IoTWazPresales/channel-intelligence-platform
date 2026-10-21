# N-0071 discovery and baseline (RUN-20261007-N0071-IMPL)

Node N-0071, R2, facet data_migration, touches existing code. Decision D-0057 (Warren 2026-10-07): accept as built. An open line is skipped in totals when its strict shipped twin exists. Fact rows are not rewritten.

## Rule as built (before this run)

`apps/api/app/services/shipment_strict_pair.py` (untracked, dirty tree) had two forms:
- `OPEN_HAS_SHIPPED_TWIN_SQL`: a correlated `EXISTS` over `fact_inbound_shipment` (same tenant, other id, `line_state = 'shipped'`, the same trimmed lower-case operating unit + order number + item code, with order number and item code not blank).
- `exclude_open_when_shipped_twin(model)`: `line_state <> 'open_order' OR NOT EXISTS(the same twin)`. Tenant is part of the key only when the model has `tenant_id`; the evidence view does not have it.

Quantity is not compared. Order line is not part of the key.

## cip observations (read-only; every script prints `current_database()` first and runs `SET TRANSACTION READ ONLY`)

Scripts: `N0071_probe.py` (output `N0071_probe_out.json`, old predicate), `N0071_probe_new.py` (outputs `N0071_probe_new_out_run1.txt` and `N0071_probe_new_out.json`), `N0071_probe_old_orm.py`, `N0071_probe_size.py`, `N0071_probe_activity.py`. Database printed: `cip`.

| Measure | Value |
|---|---|
| fact_inbound_shipment rows | 15,255 (open_order 1,775 scheduled; shipped 13,142 received + 338 scheduled) |
| open rows with a strict shipped twin | **552** rows, **42,956** units, amount 27,833,737.92, all one tenant |
| their status | 552 scheduled, 0 received; 0 have a pod_date; 552 have an ETA or promise date; 410 have a PO link; 440 have distributor+product; 513 have a customer |
| open qty vs strict-twin shipped qty | 471 equal, 71 open < shipped, **10 open > shipped (904 open units)**, 46 opens have more than one shipped twin |
| order line | in all 552 pairs at least one twin has the same order_line, so the key never joins different order lines in today's data |
| open rows with any pod_date | 0 |
| open rows with an `arrived` twin | 0 |

Per-reader double count today, if a reader does not skip the twin (units = the open twin's quantity):

| Reader slice | Lines | Units |
|---|---|---|
| not-received line count (brief card, dashboard tile) | 552 | - |
| lineup quarter, no pod (pipeline) | 552 | 42,956 (32,591 PO-linked) |
| current incoming (scheduled, no pod) | 552 | 42,956 |
| ETA-shift scope (scheduled, no pod, has evidence line) | 552 | - |
| landed readers (pod_date not null) | 0 | 0 |
| CPOR MAC (PO-linked, price > 0, qty > 0) | 410 | 32,591 |
| distributor attribution pool (resolved distributor + product) | 468 | 32,548 |
| cover in-transit (distributor+product, no pod) | - | 31,560 |

## Performance (material, new)

On cip under the configured sync role, row-level security from N-0065 (`cip_product_id_visible`, a SECURITY DEFINER SQL function, so it is not inlined) runs for every row scanned. The correlated `EXISTS` re-scans the table for every open row, so the RLS function runs about 1,775 x 15,255 times.
- Old ORM helper, `WHERE exclude_open_when_shipped_twin(F)`: **statement_timeout at 120 s**.
- Old raw SQL in the FILTER form used by supply overview (15 aggregates): **statement_timeout at 240 s**. The top-level `AND EXISTS` count took about 40 s to 2 min.
- Every screen wired in the dirty tree (shipping grid, KPIs, supply overview, channel ops, net requirement) carries this cost.

## Readers (AS-IS before this run)

| Reader | Totals open+shipped for the same line? | Strict-pair exclusion? | Evidence |
|---|---|---|---|
| Supply overview open/pipeline counts and units | yes | yes (raw SQL) | `app/services/supply_overview.py:94-137` |
| Shipping grid, KPI tiles, cohorts, commercial summary, arriving-by-distributor, newly-landed scoping (all via `_apply_fact_where_clause`) | yes | yes | `app/api/v1/endpoints/shipping.py:168` |
| Shipping ETA-shift scope, no-filter path | yes (counts open + shipped lines) | **no**; only the filtered path got it | `shipping.py:_eta_shift_metrics` (fact_scope before the change) |
| Shipping `/summary` (by_line_state, total_lines) | yes | **no**; disagreed with the grid | `shipping.py:shipping_evidence_summary` |
| Brief card "inbound shipments not received" | yes | **no** | `app/services/brief_signals.py:177-186` (before) |
| Dashboard `late_risk` | yes (same count) | **no** | `app/api/v1/endpoints/dashboard.py:36-41` (before) |
| Lineup quarter summary (pipeline/shipped/unattributed units) | yes | **no**; the grid with lineup filters already skipped | `app/services/commercial_planner/inbound_lineup_quarter.py:499` (before) |
| CPOR intake MAC qty and disti cost proxy | yes (any state with landing date / PO) | **no** | `app/services/cpor/intake_weighted_mac.py:109-127, 240-252` |
| Channel ops movement lens, cover weekly flow, cover distribution | yes | yes | `app/api/v1/endpoints/channel_ops.py:251,1015,1137` |
| Lineup net requirement in-transit | yes | yes | `app/services/lineup/net_requirement.py:210` |
| Lineup PO auto-link proposals | yes (shipped and open kept separate) | yes | `lineup_po_auto_link.py:479` |
| Lineup PO reconciliation pipeline (evidence view) | open only, shown next to shipped | yes | `lineup_po_reconciliation.py:232` |
| 1H rederivation Q1 hint | yes | yes | `lineup_bulk_rederivation.py:150` |
| Channel ops derived stock (landed) | no, `line_state = 'shipped'` only | not needed (rule only drops open rows) | `channel_ops_derived_stock.py:272,381,492` |
| PO management, PO gap | no, shipped-only CASE | not needed | `po_management.py:144,149`; `lineup_po_gap.py:79` |
| WOC observation | no, shipped only | not needed | `imports/woc_observation.py:163` |
| DSI SOH reconciliation (writes `fact_inventory_reconciliation`) | any state with pod_date | no; no-op today (0 open rows have a pod_date) | `imports/dsi_soh_reconciliation.py:138,209,346` |
| Distributor attribution pool | matches by distributor set, not a total | no; the twin has the same distributor, so the set is unchanged | `lineup_distributor_attribution.py:125-169` |
| Shipping commercial KPI predicates | predicates only; applied through `_apply_fact_where_clause` | inherited | `shipping_commercial_kpis.py` |
| stock_leaves_honesty | does not read shipment facts | - | `stock_leaves_honesty.py` |
| Import, steward, merge and audit paths (shipment_inbound_facts, twin merge, data_integrity_audit, cst_*) | write or audit stored rows, not totals | must not exclude: they own the stored rows | n/a |

## Baseline: behaviour to keep

- Stored fact rows are untouched. Nothing in this node writes `fact_inbound_shipment`.
- Readers already wired keep the same result. The new predicate drops the same 552 ids: the md5 of the sorted ids from the new predicate equals the md5 from an independent key-join formulation (`4a4aef0453e6f1ad4c6e78d3e4df2a57`), and the count, units and amount equal the old predicate's (552 / 42,956 / 27,833,737.92).
- Shipped rows are never dropped. Arrived rows are never dropped.
- The shipment sheet picker default (Shipped + Unship) belongs to N-0072 and is unchanged.
- Latent capabilities: the stored open twins can be listed again by dropping the filter (reversible), and the `/summary` endpoint now reports how many were skipped.
