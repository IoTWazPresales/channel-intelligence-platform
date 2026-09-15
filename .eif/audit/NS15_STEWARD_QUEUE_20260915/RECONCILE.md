# NODE A recon — steward queue by failure type

**Run:** `NS15_STEWARD_QUEUE_20260915`  
**Branch:** `feat/ns-2-brief-nav-collapse` @ `6684ab87` (git, this session)  
**DB:** `current_database()='cip'` printed first; SELECT only.

This note is source recon. The operator brief is observation, not acceptance.

## Decisions cited

- **D-0008** (accepted): Data & Stewardship owns Import Center, Steward queue, Master data, Steward audit. Mapping/resolution stays reachable per-job **and** as a cross-job Steward queue leaf.
- **D-0006** defers **D-0002** (restore vs retire `entity_mapping_queue` UI). Out of scope. Do not restore or retire the legacy table.
- **N-0011** `finding.defer` `STEWARD_QUEUE_APPROVE_REJECT`: CONSULT named approve/reject **on** the queue; unresolved until Design Language v2. Do not build a parallel resolver.
- Lab `DataSurface` StewardTab hardcodes customer/product/distributor and accept/reject on the leaf. That is **not** the production contract for this node: grouping must follow the failure taxonomy in data; resolution stays in existing engines.

## Candidate writers (VERIFIED from constructors)

Only three writers insert `import_entity_mapping_candidate`:

| Writer | Template slug | `entity_type` values |
|---|---|---|
| `distributor_sales_inventory.py` | `distributor_inventory` | `distributor_token`, `product_identifier`, `customer_dealer_token` |
| `cst_mapping_candidates.py` | `customer_sell_through` | `cst_product_token`, `cst_location_token` |
| `shipment_evidence_import.py` | `inbound_shipments` | `shipment_distributor`, `shipment_customer_token` |

No other importer writes this table (VERIFIED by `ImportEntityMappingCandidate(` grep).

## Live taxonomy on cip (VERIFIED)

`entity_type` × `status` (candidate count, distinct jobs):

| entity_type | needs_review | other statuses present |
|---|---|---|
| `cst_location_token` | 790 / 9 jobs | ignored 725 |
| `cst_product_token` | 407 / 21 jobs | ignored 412 |
| `customer_dealer_token` | 413 / 6 jobs | ignored 2, resolved 10, waived_open_channel 1 |
| `product_identifier` | 989 / 4 jobs | ignored 20 |
| `shipment_customer_token` | 163 / 6 jobs | ignored 8, resolved 1243 |
| `shipment_distributor` | 52 / 2 jobs | resolved 55 |
| `distributor_token` | 0 | resolved 1 |

Every `needs_review` row sits on `import_job.status` in `{completed, completed_with_errors}` — not on pending/validated. Completing a job does **not** mean tokens were resolved (FLAG ≠ BLOCK). A queue that drops “dead” jobs hides the work.

`entity_mapping_queue`: **empty** (no rows).

Unarchived `import_job` statuses: completed 210, completed_with_errors 46, **failed 47**, pending 64, validated 6, validation_failed 1.

## Existing resolution paths (job-scoped unless noted)

| Failure type (code name) | Importer(s) | Resolution path today | Scope | Re-resolution |
|---|---|---|---|---|
| `product_identifier` | DSI | `DsiImportJobResolutionSection` on `/admin/imports?job=` when `dsiJobHasValidationComplete` (includes completed / completed_with_errors) | job | Cross-job scan/preview/apply: `product_master_gap_worklist` + `product_master_gap_resolve` (BACKLOG-072). DSI **facts** FLAG only — `source_key` includes product_id (STOP). |
| `customer_dealer_token` | DSI | same DSI steward (map / provisional / open-channel waive / ignore) | job | Alias tables; no automatic replay of other jobs |
| `distributor_token` | DSI | same DSI steward | job | `distributor_source_token_alias` |
| DSI channel/region geo (`no_catalog_match`, `conflicting_*_token_aliases`) | DSI | `collect_dsi_job_unresolved_geo_tokens_sync` + steward geo UI | job, **derived** from customer candidate context — **not** an `entity_type` | Alias tables |
| `cst_product_token` | CST | `CstImportJobResolutionSection` on `/admin/imports?job=` | job | Gap worklist merge (`_merge_cst_tokens`) |
| `cst_location_token` | CST | same CST steward → `CustomerLocation` | job | none cross-job |
| CST article aliases / key accounts | CST | `/admin/cst-steward` (different object) | cross-job | n/a |
| `shipment_distributor` | inbound | `ShipmentImportJobResolutionSection` `/admin/shipment-evidence?importJobId=` | job | none |
| `shipment_customer_token` | inbound | same shipment steward | job | none |
| Shipment / inbound **product** `product_resolution_status` ∈ {no_match, inactive_only, ambiguous, no_identifier, unresolved} | inbound | Evidence workspace product filter; facts filter; catalogue-gaps worklist | job + cross-job worklist | BACKLOG-072 apply (evidence + staging; DSI facts FLAG) |
| Live on cip: evidence `no_match` 472, `inactive_only` 24; facts `no_match` 513, `unresolved` 6, `inactive_only` 21 | | | | |
| Product master upsert | `product_master` | no entity steward; validate/commit | n/a | Catalogue gaps is the gap surface |
| Distributor/customer master | `distributor_master`, `customer_master` | upsert; unverified status on dims | master grids | n/a |
| Lineup `unknown_customer` / `unknown_product` / `unknown_distributor` | historical/unified/current lineup | FLAG on lines (unknown_customer does not block apply); chips on Import Center + Commercial Planner | job / planner | `lineup_customer_token_stamp` etc. — not mapping candidates |
| Lineup distributor attribution | lineup | `/lineup` attribution status on lines | line | n/a |
| Payment evidence `customer_unresolved` / `distributor_unresolved` / unmatched Case IDs | `cpor_payment_evidence` | payment-evidence import overlay + Payments lens | job / overlay | not mapping candidates |
| CPOR claim product gaps | `cpor_claim_evidence` | catalogue-gaps worklist | cross-job derived | BACKLOG-072 |
| Historical unmatched Case IDs | `cpor_historical_cases` | Case book (Node C) | case book | n/a |
| Import **job** `status=failed` | any | Import Center `/admin/imports?jobStatus=failed` (already filters) | jobs | n/a |
| Job `pending` / `validation_failed` | any | Import Center chips | jobs | n/a |
| Stubs | `customer_channel_mapping`, `pricing_support`, `lineup_plan`, `promotion_plan`, `customer_inventory_sales` | no loader | UNCOVERED | n/a |

## Failed-imports brief signal (VERIFIED)

`brief_signals.build_brief_payload` counts unarchived `import_job.status='failed'` then sets `action_href="/admin/mappings"` and `action_label="Open steward queue"`. Lab fixture already points at Import Center failed filter (`/design-lab/data?tab=imports&status=failed`). Production filter is `jobStatus=failed`. N-0024’s change conflated job failure with steward tokens. **Wrong destination.** Steward queue leaf stays `/admin/mappings` for token work.

## Re-resolution after master import (CANDIDATE, not this node)

Exists: `/admin/product-master-gaps`, scan/preview/confirm-apply, exact-tier only, no auto-create. DSI fact repoint explicitly STOP’d. Lifecycle/idempotency/provenance are not a queue-listing problem. **Do not implement in this node.** BACKLOG with trigger: operator asks to replay unresolved facts after a catalogue apply, or DSI `source_key` product_id redesign is accepted.

## Coherent subset for this node (implement)

1. Cross-job **list** of `needs_review` candidates grouped by `entity_type` from SQL (not hardcoded Customer/Product/Distributor sections). Job id + template + file are provenance. Click routes into the existing job steward (`/admin/imports?job=` or `/admin/shipment-evidence?importJobId=`). Unknown `entity_type` still appears; no registry href ⇒ UNCOVERED, not invented.
2. Registry is **config** for labels/hrefs of known types; tenant conventions (OPEN_CHANNEL, ignore reasons, `DEFAULT_TENANT_ID`) stay existing config — not queue constants.
3. Point `failed_imports` at `/admin/imports?jobStatus=failed`.
4. Leave `entity_mapping_queue` UI in place, secondary; D-0002 untouched. No accept/reject on the new list.

## Routed out (enumerate, do not implement)

- D-0002 restore/retire
- Cross-job accept/reject on the queue
- Geo tokens as first-class `entity_type`
- Shipment product_resolution_status as a synthetic candidate type (catalogue gaps already lists it)
- Lineup unknown_* , payment unmatched, historical Case IDs, master unverified, TMP codes
- Re-resolution / DSI fact repoint
- N-0025 remediation, Start work card chrome (Node B)
