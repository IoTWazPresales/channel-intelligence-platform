# Current state

**Last updated:** 2026-07-09 (CPOR v1 Unit 2 waterfall + cost service)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-unit-2-waterfall-cost-service` |
| **HEAD** | `e26c4bd` ? tip (Unit 2 feature `44fedba`) |
| **PR** | None open |
| **Alembic (code)** | `20260708_0067` (unchanged ? U2 no migration) |
| **Alembic (DB)** | **`20260708_0067`** on local `cip` |

---

## CPOR v1 Unit 2 ? DONE (waterfall + cost; no schema)

| Item | Status |
|------|--------|
| Waterfall | `services/cpor/waterfall.py` ? reseller `vat_divide`?`margin_deduct`; Decimal; clamp; full-precision fixtures |
| Cost suggestion | `cost_suggestion.py` ? CST ? sell-out WAVG ? manual; drift detect-only; FLAG?BLOCK |
| Recompute | `recompute.py` ? writes computed columns; optional `recomputed` event; no API (U3) |
| Tests | 19 green; `ALLOW_TESTS_ON_DEV_DB` unset |
| Next | Feed Fable U2 report ? U3 case UI prompt |

---

## CPOR v1 Unit 1 ? DONE (code + cip)

| Item | Status |
|------|--------|
| Models | `cpor_case`, `cpor_case_line`, `cpor_case_event`, `cpor_claim_evidence_line` |
| Migration | `20260708_0067` ? applied to cip |
| Terms | `commercial_customer_term` reused as-is |
| Steward UI | `/admin/customer-commercial-terms` |

---

## Database and environment

| Field | Value |
|-------|--------|
| **Active DB** | Local Postgres `cip` @ `127.0.0.1:5432` (topology B) |
| **Bitemporal flags** | `CIP_SHIPMENT_BITEMPORAL_DUAL_WRITE` / `_READ` ? **default ON** |
| **Observation store** | View `shipment_evidence_current` **14,673** rows (post graduation repair; was 14,847) |
| **Invoice-line graduation** | **174** lineages quantity-graduated on cip; **432** blank observation versions superseded; audit `invoice_line_graduation_gap` = **0** |
| **Legacy supersede** | 35,134 + graduated blank corpus lines `corpus_superseded_at` |
| **Celery dispatch** | `broker` (apps/api/.env) |

---

## PO Management rollup attribution ? CLOSED (2026-07-06, `1586f1e`)

| Item | Status |
|------|--------|
| `backlog()` BU-true projection | **Done** ? product rows filtered by group `product_line` (product-first, `business_unit` fallback) |
| Customer chip re-summarization | From projected rows only |
| `po_no_match` | Deduped per linked PO in group |
| Formerly-identical BU pairs on cip | **Diverge** ? 26Q2 NV/NR, 26Q1 NX/NV, 25Q1 NR/NB, 24Q4 PF/NR |
| `linked_po_count` / coverage counting | Unchanged |

**Projection flag-note (intelligence view):** `unplanned` / `amended` stay as computed per product row. A BU group may show `unplanned` where the case has planned lines in **other** BUs ? correct per `product_line` filter; Plan vs Executed drill adds BU context in-UI.

---

---

## Inbound shipments by lineup plan quarter ? DONE (2026-07-08)

| Item | Status |
|------|--------|
| Read model | `inbound_lineup_quarter.py` ? PO-only attribution via `commercial_lineup_case_po`; plan_quarter from case `inferred_period_start`; disambiguate multi-case PO by (customer×product) lineup line ? single-case ? BU match |
| API | `GET /shipping/lines` enriched fields + filters (`plan_quarter`, `plan_business_unit`, `lineup_attribution=unattributed`, `lifecycle_bucket`, `slip_direction`); `GET /shipping/lineup-plan-periods`; `GET /shipping/lineup-quarter-summary` |
| UI | `/shipping` ? plan-quarter select (PvE period enumeration), BU filter, summary strip, bucket/slip chips, columns (plan/landing quarter, slip, awaiting POD days); PvE drill ? inbound deep-link |
| Taxonomy | shipped / pipeline / landed per `PLAN_VS_EXECUTED_SHIPPED_TAXONOMY.md`; awaiting_pod_days on shipped+pod_date NULL only |
| cip 26Q2 validation (read-only) | planned **27,218** · shipped **967** · landed **17,890** · pipeline **5,224** · slipped_in **111** · slipped_out **204**; **4** ambiguous multi-quarter POs; slipped sample id 106449 (plan 26Q2 ? land 26Q3); awaiting-POD sample 57 days |
| Tests | 11 API unit tests (`test_inbound_lineup_quarter.py`); web `buildShippingLinesUrl.test.ts` green |

Closes the "filter inbound by lineup quarter" ask. No schema change.

---

## Plan vs Executed intelligence view ? DONE (2026-07-06)

| Item | Status |
|------|--------|
| Spec | `docs/PLAN_VS_EXECUTED_SPEC.md` |
| Read model | `plan_vs_executed.py` ? `reconcile_case` product rows + `product_line` projection filter |
| API | `GET /api/v1/plan-vs-executed` (commercial-planner gated) |
| UI | `/plan-vs-executed` ? scorecard, 3-bucket + 6-flag, 3-lens exceptions, trend, drill grid |
| Nav | Commercial Planning group ? "Plan vs Executed" (top-level route, not under `/admin`) |
| Deep-links | Commercial Planner guide + PO Management alert |
| 26Q2 KPI tie-out (cip read-only) | **PASS (shipped-only, 2026-07-07)** ? fill **41.80%**, line-hit **30.42%**, shipped_units_in_plan **12,648**; over-ship does not reduce fill rate. (Was 45.96% / 35.36% / 16,751 pre-fix when open_order leaked into shipped ? 4,103 open_order units removed; see shipped/pipeline taxonomy block below.) |
| BACKLOG-066 UI flag | Warning when range includes 25Q1 / 24Q4 |
| Period enumeration fix (2026-07-06) | `available_periods` from `coverage()` groups ? independent of active filter; default latest |
| Round-2 hardening (2026-07-06) | Exception AG grids, product lens SKU/sales-model/description toggle, cross-drill, PO Mgmt deep-link params, loading-state fix, golden tie-out tests all clean periods |
| UX repair + PO slim (2026-07-06) | One full-width exception category grid (tabs inside lens); human-readable product labels (description?sales_model?SKU) in exceptions + drill + chip; product selector drives drill column; PO Management linked cards ? compact status + PvE deep-link only (recon chips removed; APIs unchanged) |
| Grid + value honesty (2026-07-06) | Fixed-height paginated exception/drill grids; exception value columns return `null` when FX/plan bridge absent (no units-as-value); value-rank disables when category has no value coverage; PO Management "What needs action" worklist summary + visible PvE outcomes button on linked groups |
| Single-line entity + default period (2026-07-06) | One value per exception column (customer name only ? no BU stack); product/BU single Entity column; `resolve_default_period` = latest quarter with linked PO reconciliation (not empty 26Q3) |
| Intake vs fill clarity (2026-07-08) | **Total shipped (in scope)** KPI tile (`shipped_units_total` = in-plan + unplanned); tooltips on headline tiles; scope alert explains fill vs intake vs workbook POD. Fix: Recharts `Tooltip` was shadowing MUI ? KPI section failed to render. Web test green. |

---

## PvE NB 26Q2 shipped discrepancy ? READ-ONLY AUDIT CLOSED (2026-07-08)

| Metric | Value (cip, NB filter 26Q2) |
|--------|----------------------------|
| Planned | 22,375 |
| Shipped in-plan | 11,465 |
| Unplanned intake | 5,197 |
| **Total shipped in scope** | **16,662** |
| Evidence / workbook POD Q2 2026 NB | **16,493** (exact match) |
| POD Q2 NB not on 26Q2-linked POs | 927 (outside PvE reconcile scope) |

**User confusion root cause:** compared **in-plan shipped** tile to workbook POD total. Correct intake comparison: **total shipped in scope** or evidence POD-quarter filter. Fill rate correctly uses in-plan only. POD-landed quarter KPI deferred ? BACKLOG-068.

---

## PvE shipped/pipeline/landed taxonomy ? fill-rate leak corrected ? DONE (2026-07-07)

| Item | Status |
|------|--------|
| Root cause | `reconcile_case` summed **all** `shipment_evidence_current` quantity on linked POs (no `line_state` filter) ? `open_order` (pipeline) credited as shipped, inflating fill rate. Only leak surface. |
| Fix (`lineup_po_reconciliation.py`) | Shipped aggregation now gated `line_state='shipped'` (explicit ? bitemporal read ON makes `apply_active_evidence_filter` a no-op); `open_order` aggregated separately as `pipeline_units`; units flags recompute off shipped-only. Domain confirmed `{shipped, open_order}` only ? no third state. |
| Consumers swept | `plan_vs_executed` scorecard/exceptions/drill/`_compute_trend` (all inherit shipped-only + new `pipeline_units_in_plan` tile + `pending_split`); `po_management` backlog projection re-summarizes flags only (inherits) and coverage meter already `line_state='shipped'`; reconcile endpoint pass-through. |
| Pipeline surfaced (UI) | New "Pipeline (inbound)" KPI tile (open_order on in-plan rows) + Pipeline drill column; pending bucket splits inbound/pipeline vs cold. Never enters fill. |
| Corrected 26Q2 (cip read-only) | fill **45.96%?41.80%**, shipped_units_in_plan **16,751?12,648** (4,103 open_order removed), line-hit 35.36%?30.42%. Full range 62.43%?61.10% (?5,853 units). |
| Doc | `docs/PLAN_VS_EXECUTED_SHIPPED_TAXONOMY.md` (addendum to spec) |
| Tests | New anti-leak tests: reconcile excludes open_order + surfaces pipeline; scorecard excludes pipeline from fill + splits pending. Golden + web tests green. |
| Landed gap | `pod_date` exists on shipping evidence only; recon has **no landed gate** (~3% shipped-not-landed counted as executed). Deferred ? BACKLOG-068. `cargo_status` does not exist. |
| Out of scope (unchanged) | `lineup_case_suggested_pos.total_shipped_units` still sums all evidence for PO-suggestion **ranking** (not a reported PvE metric) ? sibling surface, left as-is. |

---

## Lineup PO lifecycle + Open Channel plan ? DONE (2026-07-05, `88f8db4`)

| Item | Status |
|------|--------|
| PO link ? `po_pending` (not `po_issued`); steward open through `in_fulfillment` | Wired + unit-tested |
| Explicit `POST ?/close-work` ? `work_closed`; list hides work-closed by default | Wired + unit-tested |
| Open Channel plan parity | TMP provisional dim **#19** aliased to system **OPEN_CHANNEL #1** for plan/reconcile/auto-link; `effective_lineup_customer_id` on staging |
| PO auto-link proposals | `group_planned_units` = full customer-period plan (not PO-matched SKUs only) |
| Bulk link UX | Chunked apply (100/request), top progress bar, success counts |
| Bulk link on cip | **191** new `commercial_lineup_case_po` rows proven live (~2026-07-05) |

**Mental model:** PO linked (`po_pending`) ? work closed (`work_closed`) ? archive. Restart API + hard-refresh web after pull.

**Data hygiene (optional):** merge/remap TMP Open Channel customer **#19** ? **OPEN_CHANNEL #1** ? reads already alias.

---

## Invoice-line mint graduation ? DONE (2026-07-04)

| Step | Status |
|------|--------|
| Write path (dual-write hook) | Quantity-gated supersede / `invoice_partial_graduation` flag |
| One-time repair | Preview 174 full / 0 partial; **13,685** double-count units; clone + cip green |
| Integrity audit | `invoice_line_graduation_gap` check added |
| Change events | `graduated` + `graduation_kind: invoice_mint` on lineage thread |

**Preview impact (pre-repair):** 174 lineages · top double-count 26Q2 Open Channel 5,581 units.

**Sample invoice_mint event:** order `151126051002768` line `1.1` item `90NR0NG1-M00C30` ? `ship:15260187716|?|8883|1`.

---

## Plan D cutover ? DONE (2026-07-02)

| Phase | Commit | Gate |
|-------|--------|------|
| 1 Identity + clone proof | `9109664` | `cip_planD_smoke` green; 0 split collapse |
| 2 cip cutover | `1b77efc` | Migration 0066; jobs 153/154 backfilled; dual-write ON |
| 3 Consumers + supersede | `6de21b8` | Audit **5b=0**; 35,134 superseded; parity worklist measured post-cutover |
| 4 Change events v1 | `91f227e` | API + CLI; unit tests green; real chain spot-check jobs 32/40 |

**Integrity audit (cip):** `evidence_true_dupes` (5b) = **0** · `evidence_fact_parity` = **10** on cip today (2026-07 audit; **184** was the pre-audit Plan-D cutover figure ? steward worklist shrank after graduation/supersede) · `duplicate_qty_inflation_groups` = **0**.

**Open?shipped fact double-count (diagnostic only, BACKLOG-062):** 104 matching pairs; open qty 5,752 / shipped qty 7,224 ? remediation deferred.

**Sample change event (jobs 32?40):** `order:151126031011047|1.1|90NR0KS1-M00EW0` ? `est_pod` slip ?1 day, `erd` slip ?1 day.

---

## Consumer read sources (after Plan D)

| Consumer | Read source |
|----------|-------------|
| DSI corroboration (cache + per-row) | `shipment_evidence_current` |
| DSI receipt disambiguation | `shipment_evidence_current` |
| DSI product tiebreak | via corroboration (current view) |
| Lineup PO reconciliation / suggested POs / BU resolution | `shipment_evidence_current` |
| Shipment evidence API list/get | `shipment_evidence_current` |
| Shipping ETA LAG metrics | `shipment_evidence_observation` partitioned by `line_identity_key` |
| Channel ops, usage counters | `shipment_evidence_current` |
| Steward writes / import apply | `shipment_evidence_line` (unchanged) |

---

## Shipment apply hardening ? DONE (2026-07-08)

| Item | Status |
|------|--------|
| Open-order fact upsert | Uses `uq_fact_inbound_shipment_fact_upsert_key` (was stale `source_key` constraint name ? job 310 apply blocker) |
| Unresolved product write-through | All evidence lines upsert; `product_id=NULL` + existing `no_match` / `inactive_only` status carried on facts |
| Failure writeback | `record_shipment_apply_failure` ? fresh session + `ImportRowResult` + terminal `failed` (mirrors PM worker pattern) |
| Terminal status | **`completed` + `loaded`** on successful apply (mirrors DSI `complete_dsi_import_job_to_loaded`; unresolved count in return payload only) |
| **REAL clone gate** (pg_dump 227.9 MB ? `cip_clone_310`) | 7,080 evidence ? **6,649** facts (shipped `fact_upsert_key` dedupe); **140** null-product facts; `dim_product` **18,158?18,158**; session hardening proven |
| **cip job 310** | **Proven applied** on `cip` 2026-07-08 ~15:04 ? `stage=loaded`, `status=completed`; **6,649** fact rows (matches clone gate); `imports.shipment_apply` succeeded after earlier failed attempts |
| purmidr test | **(a) STALE ASSERTION** fixed ? PO now linked to case 9; test guards fact shipped sum ? 7000 |

---

## Dev topology

Local desktop (no Docker): `pnpm dev:api` :8001 · `pnpm dev:web` :3000 · `pnpm dev:worker` (Redis :6379) or `CIP_DEV_CELERY_DISPATCH=in_process_thread`.

---

## CPOR promotion funding ? discovery + draft spec (2026-07-08)

| Item | Status |
|------|--------|
| Substrate discovery | `docs/PROMOTION_FUNDING_SUBSTRATE_DISCOVERY_2026-07-08.md` ? read-only; cip SELECTs after `current_database()=cip` |
| Draft spec | `docs/SPEC_CPOR_V1_AND_LISTING_CAPTURE_V0.md` ? Warren review; not implementation |
| Jun-14 baseline | `docs/PROMOTION_PLANNING_DATA_SUBSTRATE_AUDIT.md` left unmodified |

---

## Next

- **Warren review** ? `SPEC_CPOR_V1_AND_LISTING_CAPTURE_V0.md` before any CPOR schema/implementation.
- **Browser soak** ? inbound `/shipping` plan-quarter filter + PvE drill deep-link; summary strip vs grid row counts for 26Q2.
- **W2 on cip (Warren)** ? PO Management ? Duplicate ingestion panel ? Preview partition ? Apply (cases #39/#40); clone already proven (`cip_clone_dup066`).
- **Unit 6 browser soak** ? PvE total-shipped tile vs workbook POD; paginated exception grid; PO worklist summary chips.
- **BACKLOG-066** ? partition repair wired; **cip apply pending** Warren (UI panel above).
- **BACKLOG-067** ? backfill file-provenance gap (unified_lineup / bulk_backfill paths retain no original bytes).
- **Spec C Step C:** archive lineup backfill + link-apply.
- **BACKLOG-062:** Warren decision on open?shipped fact remediation (104 pairs measured).
- **BACKLOG-057/058:** D4/D5 legacy column deprecation after soak.
- **Perf (defer):** bulk PO apply still one DB commit per item ? batched writer if volume grows.

---

## Discovery hints (for next agent ? verify in code + cip)

| Surface | Grain / trigger (code truth ? re-verify) |
|---------|------------------------------------------|
| `po_management.backlog` | Groups: `(year, quarter, product_line)` from `fact_inbound_shipment`; linked groups **project** `reconcile_case` product rows matching group `product_line` ? `reconciliation_summary` + `reconciliation_customers` |
| `plan_vs_executed` | Period options from `po_management.coverage` observed groups (full history); scorecard/trend filtered by From..To range; default latest quarter |
| `reconcile_case` | `(case × customer × product)`; product rows carry `product_line` + `business_unit` |
| Current Lineup recon UI | `CaseReconciliationInline` = case-level (out of scope for BU projection) |
| Assign distributor button | `RESOLUTION_UI_STATUSES` && `!superseded` ? no unassigned-line gate in UI |

---

## Prior session context (abbreviated)

Unified lineup import Units 1?8 backend done; Unit 6 frontend wired. Spec C Step A/B done (`20260701_0064`/`0065`). Distributor full merge on `cip`. PO rollup attribution fixed `1586f1e`. Data integrity audit tool (`10fd3ea`).
