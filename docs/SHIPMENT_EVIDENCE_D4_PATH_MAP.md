# Shipment evidence D4 — path map (node N-0098, BACKLOG-057-D4)

**Scope:** stop writing the `shipment_evidence_line` columns that mirror the observation payload, and move every reader of
them onto `shipment_evidence_observation`. The columns stay (no drop). D5 (BACKLOG-058-D5, dropping them) is not in scope.
**Branch:** `feat/shipment-single-write`. **Fix protocol:** this is the interconnection audit (AGENTS.md) written before code.

## 1. What the two tables hold today

`shipment_evidence_line` (one row per job and `source_key`) and `shipment_evidence_observation` (append-only, one row per
job and payload hash) are filled from the same parsed row. Observations are built **from the line** after the line is final
(`append_observations_for_job_lines` copies `_LINE_TO_OBSERVATION_COLS` out of the line). So every payload value is stored twice.

| Group | Columns | After D4 |
|-------|---------|----------|
| **Job scope** (identity of the staging row) | `id`, `import_job_id`, `source_key`, `source_sheet`, `source_row_number`, `created_at`, `updated_at` | still written on the line |
| **Steward state** (changes after validate; the line is the authority and the current view reads it over the observation) | `product_id`, `product_resolution_status/_token/_detail`, `distributor_id`, `distributor_resolution_status/_token`, `customer_id`, `customer_resolution_status`, `resolved_customer_id`, `resolved_distributor_id`, `purchase_order_id`, `crad_date`, `corpus_superseded_at` | still written on the line |
| **Payload mirror** (read from the observation after D4) | `report_type`, `line_state`, `raw_source_row`, `operating_unit`, `bill_to_raw`, `ship_to_raw`, `order_no`, `customer_po`, `order_line`, `delivery_no`, `invoice_line`, `item_code`, `sales_model_name`, `customer_item`, `ean_code`, `upc_code`, `mpor_item_no`, `quantity`, `unit_price`, `amount`, `currency_code`, `ship_confirm_date`, `schedule_ship_date`, `promise_date`, `exwork_date`, `erd_date`, `est_pod_date`, `pod_date`, `customer_dealer_token`, and the voyage fields (`WATER_FIELDS`) | **no longer written**; columns kept, rows already on cip keep their old values |

`report_type`, `line_state` and `raw_source_row` were `NOT NULL` on the line. D4 adds one migration (section 6) so an insert can
leave them out. On `cip` they are nullable (read-only check 2026-11-10). `crad_date`, `resolved_*` and the steward columns have no
observation twin, which is why they stay.

## 2. Writers of the payload mirror columns

| Writer | Where | D4 change |
|--------|-------|-----------|
| Validate loader | `shipment_evidence_import.process_shipment_evidence_import` → `_flush_shipment_line_batch` → `_shipment_line_conflict_set` | line upsert carries job scope + steward state only; the parsed payload is held for the job and written once, to the observation |
| Observation writer | `shipment_evidence_observations.append_observations_for_job_lines`, `sync_job_observations_after_validate` | takes the payload from the parsed row (or, on a re-observe, from the line's latest observation) plus the line's steward state; no longer reads payload from the line; no dual-write flag |
| Re-validate steps that fill steward state | `_resolve_unresolved_shipment_lines_for_job`, `populate_resolved_entities_for_job`, `materialize_purchase_orders_for_shipment_job` | read payload from the parsed row (or the observation), write steward state to the line only |
| One-off customer PO backfill | `scripts/backfill_shipment_customer_po.py` (writes `customer_po`) | retired: observations are append-only and the loader extracts the PO |
| One-off voyage backfill | `scripts/ops/backfill_shipment_water_fields.py` (writes voyage fields on the line) | already run on cip on 1 Nov; not re-run; line table dropped from its targets |

Writers that only touch steward state and do not change: `shipment_evidence_steward_ops` (map/ignore/duplicate ops),
`product_master_gap_resolve._repoint_shipment`, `shipment_null_distributor_po_merge`, `shipment_null_distributor_sibling_po_merge`,
`distributor_merge_po_consolidation`, `provisional_entity_consolidation`, `distributor_duplicate_groups` (merge repoint),
`shipment_invoice_graduation._mark_evidence_lines_superseded`, `shipment_plan_d_cutover.soft_supersede_legacy_duplicate_evidence`.

## 3. Readers of the payload mirror columns (and their new source)

| Reader | Reads | New source |
|--------|-------|-----------|
| `shipment_inbound_facts._row_values_from_evidence`, `upsert_inbound_shipment_facts_for_job` (apply) | every payload column | `EvidenceRow` = line (job scope + steward state) + the line's latest observation (payload). A line with no observation fails the apply loudly |
| `shipment_evidence_import._rebuild_shipment_distributor_candidates` / `_rebuild_shipment_customer_candidates` | `bill_to_raw`, `ship_to_raw`, `customer_dealer_token`, `quantity`, `amount` | `EvidenceRow` (runs after the observation append) |
| `shipment_evidence_import._resolve_unresolved_shipment_lines_for_job` | dates, `item_code`, `ean_code`, `upc_code`, `sales_model_name`, `bill_to_raw`, `ship_to_raw` | the parsed row of this job, else the latest observation |
| `shipment_resolved_entities.apply_resolved_entities_to_line` / `populate_resolved_entities_for_job` | `bill_to_raw`, `ship_to_raw`, `customer_dealer_token`, `raw_source_row` (CRAD) | `EvidenceRow` |
| `shipment_purchase_order_materialize.materialize_purchase_orders_for_shipment_job` | `customer_po` | `EvidenceRow` / parsed row |
| `shipment_evidence_steward_ops._remember_special_case_clear` | `item_code` | the latest observation of each line |
| `product_master_gap_resolve` (`_count_shipment`, `_repoint_shipment`, `scan_open_gaps_for_matches`) | `item_code`, `ean_code`, `upc_code`, `sales_model_name`, `customer_item`, `mpor_item_no` | `EvidenceRow` (steward state filters stay on the line) |
| `shipment_open_book` (scopes of a job, newest scope, older-book guard, BOM-moved test) — raw SQL | `report_type`, `operating_unit`, `customer_po`, `item_code` | the line joined to its latest observation (`LATERAL`) |
| `shipment_shipped_fact_identity_twin_merge` PO-less twin query — raw SQL | `quantity`, `line_state`, `delivery_no`, `item_code` | same lateral join |
| `dsi_temporal_supersession.ProductShipmentWindowIndex.load` — raw SQL | dates, `line_state`, `quantity`, `sales_model_name` | same lateral join |
| `import_job_delete_figures._shipments` (restore from the newest other load) | `delivery_no`, `item_code` + every column via `_row_values_from_evidence` | same lateral join / `EvidenceRow` |
| `shipment_evidence_read` (`read_relation`, `read_model`, active filter), `data_integrity_audit`, `endpoints/shipment_evidence` | legacy branch when `CIP_SHIPMENT_BITEMPORAL_READ=0` read the line payload | the legacy branch is removed; the flag is gone |
| `shipment_plan_d_cutover` (`remigrate_observation_line_identity_keys`, `count_shipped_corpus_groups_in_evidence`) | payload fallback to the line | observation / lateral join |
| view `shipment_evidence_current` | `sel.pod_date` inside the `pod_date` COALESCE | migration re-issues the view without it (the sticky-pod subquery already covers it) |
| one-off scripts: `backfill_sticky_pod_facts`, `resync_shipment_facts_customer_po`, `backfill_shipment_resolved_entities` | `pod_date`, `customer_po`, line rows | `EvidenceRow` / lateral join |

Readers that **already** read observations or the current view and do not change: `dsi_shipment_corroboration`,
`dsi_product_shipment_tiebreak`, `dsi_distributor_receipt_disambiguation`, `shipment_change_events`, `shipping/observation_transitions`,
`shipping/newly_landed`, `shipping_water`, `endpoints/shipping`, `endpoints/shipment_evidence` (list, detail, steward preview),
`lineup_*`, `plan_vs_executed`, `product_master_gap_worklist`, `customer_usage`, `distributor_usage`, `product_usage`.

Readers of steward state only (unchanged): `shipment_apply_sync` (unresolved product count), RLS policies on the three tables
(`product_id`), `import_job_bulk_delete` (deletes by job).

## 4. Where the fact is written (unchanged semantics)

`UI Apply → POST apply → shipment_apply (Celery or dev thread) → run_shipment_apply_sync → write_shipment_facts_and_close_book →
upsert_inbound_shipment_facts_for_job → _upsert_evidence_chunk → _upsert_shipped_chunk / _upsert_open_order_chunk`.
The conflict key (`fact_upsert_key`, per tenant), the latest-job-wins replace, sticky POD, the closed-fact guard and the
open-book close are not touched. Only the source of the payload fed to `_row_values_from_evidence` changes.

## 5. Behaviour differences a reviewer should know

1. **Sticky POD.** The observation carries the sticky POD (a null POD in the file is filled from the identity's earlier
   observation). The apply used to read the file's POD from the line and rely on the fact's own sticky rule. A fact is only
   different when an identity was observed with a POD, never applied, and the fact for the key no longer exists.
2. **Graduation flags.** Invoice graduation writes steward flags into the observation's `raw_source_row`. A fact written after a
   flagged graduation now carries that key in its `raw_source_row` too.
3. **Lines without an observation.** The apply and the steward readers no longer fall back to the line's own payload. The clone
   script counts these lines before anything else (they should be 0).
4. **Old rows keep their old payload.** The loader stops writing the columns; it does not clear them. D5 drops them.
5. **Same-hash refresh.** `customer_po`, `raw_source_row`, `purchase_order_id`, `evidence_line_id` and the voyage fields are stored on the observation but are not part of `source_row_hash` (so a re-validate of rows already on cip does not mint a second observation). The observation insert updates those columns in place when the hash matches. A change to a hashed column still appends.

## 6. Migration

`20261103_0056` (down_revision `20261103_0055`). It drops `NOT NULL` from `report_type`, `line_state` and `raw_source_row` on
`shipment_evidence_line`; adds index `ix_shipment_ev_obs_evidence_line (evidence_line_id, id DESC)` on
`shipment_evidence_observation`; re-issues `shipment_evidence_current` without the line `pod_date` term. An earlier draft of this
section called the revision `20261103_0052` and said it was not run on `cip`. That text was stale. Read-only on `cip` 2026-11-10
(`current_database() cip`, alembic `20261110_0061`): those three columns are nullable, the index is present, and the view does not
reference `sel.pod_date` (it still mentions `pod_date` from the observation). This check wrote nothing. Apply the migration before
deploying the loader that inserts lines without those three columns; on `cip` that order already happened. The clone proof
`apps/api/scripts/ops/prove_shipment_single_write_clone.py` was not run in this pass. D5 is not done.

## 7. Out of scope

D5 (drop the columns), the DSI resolution order, steward governance, `fact_upsert_key` and latest-job-wins, the open-book rules.
