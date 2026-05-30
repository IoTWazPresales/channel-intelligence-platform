# Channel Intelligence Platform — Current Context

## Branch
`cursor/commercial-planner-program-84b1` (Commercial Planner program phases 1–2 complete)

### May 30, 2026 — Commercial Planner program (phases 2 complete)
- **Celery:** `commercial_planner.parse_lineup_case`; parse-upload/apply returns **202** when file ≥512KB or ≥500 preview rows; activity feed `lineup_parse_task`.
- **Intelligence:** Candidate product union; customer-scoped `FactForecast`; budget request + buy plan signals; ranking snapshots (in-process POST/GET).
- **Steward:** `GET …/lineup-cases/{id}/steward-export`; web **Steward export** download on case workbench.
- **Dashboard:** `kpis.commercial_planner` on `GET /dashboard/summary`; web KPI when flag on.
- **Modularity:** `commercial_planner_auth.py`, `commercial_planner_lineup_routes.py`, `commercial_planner_intelligence_routes.py`, `plan_readiness.py`, `lineup_parse_api.py`.
- **Tests:** API 90 CP tests; web 91 CP tests passing.

### May 30, 2026 — Commercial Planner program (phase 1 finish + QA)
- **Flag:** `CIP_COMMERCIAL_PLANNER_ENABLED` / `NEXT_PUBLIC_CIP_COMMERCIAL_PLANNER_ENABLED` (default on).
- **Lineup:** preview → apply on retry parse and **create-case** dialog; `can_apply` requires ≥1 resolved product.
- **Intelligence:** rankings use sellout, forecast, lineup MSRP, customer net price, promo plan; returns `suggested_srp_local`; intelligent add uses it.
- **Suggestions:** Prefer current `CommercialLineupCase` on plan before historical lineup job.
- **Docs:** `docs/COMMERCIAL_PLANNER_PROGRAM.md`, **`docs/COMMERCIAL_PLANNER_GAP_ANALYSIS.md`** (risks, gaps, test matrix).
- **Tests:** API 13 focused + 74 route tests; web 91 CP tests (page + CurrentLineupSection + autocomplete). DB bootstrap test needs Postgres.
- **Deferred:** Celery parse task (`lineup_parse_worker.py` scaffold only), router split, dashboard widgets, steward mapping bridge.

### May 30, 2026 — Commercial Planner program (phase 1 initial)
- **Flag:** `CIP_COMMERCIAL_PLANNER_ENABLED` / `NEXT_PUBLIC_CIP_COMMERCIAL_PLANNER_ENABLED` (default on).
- **Lineup:** `POST …/parse-preview` + `POST …/parse-apply?confirm=true`; upload dialog uses preview then apply.
- **Intelligence:** `GET …/plans/{id}/intelligence/customer/{cid}/product-rankings`; web **Intelligent add** dialog.
- **Suggestions:** Prefer current `CommercialLineupCase` lines on plan before historical lineup job.
- **Docs:** `docs/COMMERCIAL_PLANNER_PROGRAM.md`
- **Tests:** `test_commercial_planner_intelligence.py`, `test_lineup_parse_preview.py`

### May 30, 2026 — Master bulk delete: complete FK checks, batched preview, 409 on confirm
- **Fix:** Extended `customer_usage` / `product_usage` / `distributor_usage` / `channel_usage` / `region_usage` with staging lines, token aliases, mapping candidates, catalog links, etc.
- **Performance:** `*_hard_reference_breakdown_batch` + `master_usage_batch.py`; preview no longer N×15 queries per id.
- **Confirm:** Body `{ entity_ids, deletable_ids? }`; skips full re-preview when `deletable_ids` sent; batched recheck; `IntegrityError` → 409 with `references` (all-or-nothing).
- **Web:** Confirm passes `deletable_ids`; `MasterBulkDeleteImpactDialog` shows 409 reference detail; `apiPost` raises `HttpConflictError` on 409.
- **Docs:** `docs/MASTER_BULK_DELETE_AUDIT.md`
- **Tests:** `test_master_entity_bulk_delete.py`, `test_customer_bulk_delete_staging_block.py`, `MasterBulkDeleteImpactDialog.test.tsx` (14 API + 3 web passing).

## Branch (prior)
`main` (merged `feat/master-delete-reference-checks-bulk`)

## Head commit
`d004264` on `main` (feature: `448ee1d` — channels/regions admin grids, distributor bulk delete, premium nav)

### May 29, 2026 — Master data admin grids, bulk delete, premium nav
- **Merge:** `feat/master-delete-reference-checks-bulk` → `main` (reference-check delete + customers/products bulk delete).
- **Channels & Regions:** `GET/DELETE` + bulk preview/confirm on `catalog.py`; admin page `/admin/channels-regions` with `CatalogDimensionGridPanel` (row delete 409 alerts, `BulkSelectionToolbar`, `MasterBulkDeleteImpactDialog`).
- **Distributors:** bulk preview/confirm API + `BulkSelectionToolbar` on distributor master grid (mirrors customers/products).
- **Nav (shell only):** `navConfig.ts` + `AppShell.tsx` — grouped IA (Overview → Admin), collapsible groups, icon rail + flyout when collapsed, `cip.shell.nav.collapsed.v1` + `cip.shell.nav.groupExpanded.v1` in localStorage. No route/page file changes except new `channels-regions` page.
- **Tests:** `test_master_entity_bulk_delete.py` extended for channels/regions/distributors bulk preview routes.

### May 30, 2026 — Master delete reference checks + bulk delete
- **Reference-check delete** (mirrors `product_usage.py`): `customer_usage`, `distributor_usage`, `channel_usage`, `region_usage`, `customer_location_usage` + structured 409 + GET refs on API.
- **UI:** Customers + Products admin grids: row-delete conflict alerts; Distributors row-delete alert; customer location delete alert in drawer.
- **Bulk delete:** `BulkSelectionToolbar` + `MasterBulkDeleteImpactDialog` on **Admin → Customers** and **Admin → Products**; `POST …/bulk-delete-preview` and `…/bulk-delete-confirm` (skips blocked rows, deletes deletable only).
- **Catalog API:** `DELETE /catalog/channels/{id}`, `DELETE /catalog/regions/{id}` with reference breakdown (no dedicated channel/region admin grid yet).
- **Tests:** `test_customers_delete.py`, `test_master_entity_bulk_delete.py`, `MasterBulkDeleteImpactDialog.test.tsx` (+ existing `test_products_delete.py`).

## Alembic Head
`20260518_0045` — Customer sell-through Phase 0 (`fact_customer_sellthrough`, staging, `customer_report_config`, template seed). Prior: `0043` `fact_dsi_forecast`, `0042` `fact_customer_velocity`. Smoke: **`cip_alembic_smoke`** at `0045`.

## Current State
- **Local dev:** Windows, **no Docker**; Supabase `cip` via `DATABASE_URL` transaction pooler `:6543` + `NullPool` (`app/db/session.py`).
- **Redis:** Celery requires `127.0.0.1:6379` from Windows; WSL-only ping is not enough. Fallback: `CIP_DEV_CELERY_DISPATCH=in_process_thread` in `apps/api/.env`.
- **`stop-dev.ps1` / `restart-dev.ps1`:** fixed `$pid` bug; restart waits for Redis on Windows.

### May 30, 2026 — Dev reliability + PM imports (local, pending commit)
| Area | Before | After |
|------|--------|--------|
| `stop-dev.ps1` | Crashed on `$pid`; orphans on :8001/:3000 | Kills listeners + repo-scoped processes |
| `restart-dev.ps1` | Windows could not see Redis; windows closed on error | Waits for `:6379`; error + Enter on failure |
| PM `validate_running` stuck | Jobs hung after dead worker (e.g. job #4) | `reconcile_stale_pm_validate_sync` (30 min) on GET `/state`, enqueue, worker |
| PM GET `/state` payload | ~100KB+ inferred samples every poll | `inferred_schema_for_state_payload` trims samples (mapping UI unchanged) |
| Imports jobs grid | Full “Loading data…” on refetch | Spinner only when `jobs == null` |
| New PM wizard | Stale `lastJobId` could confuse steps | Cleared when picking a new import type |

**Tests run:** `test_product_master_workflow.py` 18/18; `test_ai_resolver_integration.py` 16/16; `imports/page.test.tsx` 26/26. Full `pnpm test:web` has unrelated failures/timeouts elsewhere.

**AI:** `AI_ASSIST_ENABLED=false` locally → Anthropic not called; package installed.

---

## Latest work (May 2026) — Product Master validation at scale

### Backend
- **`validate_product_master_sync`**: row-level `ImportRowResult` rows collected in memory, flushed via **`insert(ImportRowResult)` in 2k chunks** (replaces ~14k individual `db.add()` + one flush).
- **Celery task** `imports.product_master_validate` → `product_master_validate_task` / `run_product_master_validate_job` / `run_pm_validate_worker`.
- **POST `/api/v1/imports/product-master/jobs/{id}/validate`**: returns **202** with `pm_validate.outcome=enqueued` when dispatched; polls via existing **GET …/state**.
- **Activity bell**: `staged_metadata.pm_validate_task` slot (`kind: product_master_validate`) in `background_tasks.py`.
- **DB pools** (Supabase): async **`NullPool`** + `statement_cache_size=0` (`c4a8cf9`); sync `prepare_threshold=None`.

### Web
- PM validate mutation accepts **202**; polls state while `validate_queued` / `validate_running`.
- **`?job=N` resume** for PM: steps 3–6 from `stage` / `status` (no read-only stub).
- **Next.js proxy**: `AbortSignal.timeout(600_000)` for validate/commit/apply POST paths.

### Tests
- `tests/test_product_master_workflow.py` — bulk insert assertion (`db.execute`); `from_worker=True` in staged-metadata test.
- `tests/test_async_broker_dispatch.py` — validate job dispatch helper.

### PM mapping (same release train)
- PgBouncer `statement_cache_size=0` on async engine; PM SKU aliases / mapping UI (`4ba9529`, `224e886`, `8868d0b`).
- Imports UI error banners for PM state / jobs list; stale `?job=` redirect on 404.

---

## Latest work (May 2026) — Customer Sell-Through Phase 0

### Foundation
- fact_customer_sellthrough: grain
  (customer_id, customer_location_id nullable,
   product_id, period_start_date)
  period_type: 'daily' | 'weekly' | 'monthly'
  daily supported in schema for future API connectors
  raw_mtd_units + is_mtd_estimate for FNB MTD pattern
  unit_cost and unit_sell_price captured where present
  reported_soh captured from customer files
- import_customer_sellthrough_staging_line: mirrors DSI
  staging pattern, no resolution plan layer
- customer_report_config: per-customer cadence, structure
  type, overdue threshold, last received date
- import_template seeded: slug=customer_sell_through
  column aliases cover all 7 confirmed retailers
- Pipeline handler skeleton: dispatches on 5 structure
  types (flat/pivoted/multi_sheet/mtd_delta/wide_extract)
  All parsers raise NotImplementedError — Phase 1
- Store-level FK: customer_location.id (existing table)
  nullable for chain-level reports
- Migrations: 0044 (fact table), 0045 (staging + config
  + template seed)
- Smoke migration: 0044+0045 applied on cip_alembic_smoke

### Retailers and structure types
- flat:         Evetech, Takealot
- pivoted:      Game, Makro
- multi_sheet:  Computer Mania
- mtd_delta:    FNB (cumulative MTD → weekly delta)
- wide_extract: IC / Incredible Connections (197 cols)

### Phase 1a — Flat parser
- `parsers/customer_sell_through_flat.py` — `parse_flat_report()` →
  `ParseResult` (no DB, isolated)
- No retailer-specific logic — works for any flat source
- Header detection: best-match scan across first 10 rows
- Column mapping: `field_mapping` first, aliases fallback
- Period extraction: date column → filename date range → filename
  date → week number → None + warning
- Formula/apostrophe normalisation on all text fields
- Rows skipped if product token or `units_sold` missing
- `customer_sell_through_apply.py`: upsert resolved staging lines to
  `fact_customer_sellthrough`
- `customer_report_config.last_report_received` updated on flat import
- Fixtures: `tests/fixtures/customer_reports/` (generic synthetic xlsx)

### Phase 1b-1e — All parsers + AI resolver layer

#### Parsers (all generic, no retailer-specific logic)
- `pivoted`: period columns detected by pattern, auto-unpivot, SOH on latest period only
- `multi_sheet`: all data sheets processed, summary sheets excluded, chronological order
- `mtd_delta`: prior week lookup from staging, `derived_units = current - prior`,
  `is_mtd_estimate` flag when no prior exists
- `wide_extract`: header-first streaming, 500-row chunks, falls back to pivoted unpivot
  if period cols found

#### AI resolver layer (`ai_import_resolver.py`)
- Gated behind `AI_ASSIST_ENABLED` env var (default False)
- `suggest_column_mapping`: first-time format classification
- `suggest_token_resolution`: unresolved token matching — auto_resolved ≥ 0.90 confidence,
  `ai_suggested` below
- `detect_format_drift`: set comparison + AI for partial drift
- Generic — works across all import types
- AI failure never breaks import — always falls back

  #### Testing
  - `AI_ASSIST_ENABLED=false`: deterministic only (default)
  - `AI_ASSIST_ENABLED=true`: AI layer active
  - All AI calls mocked in `test_customer_sellthrough_parsers.py`

### AI resolver wired into existing import handlers

Handlers updated (surgical additions only):
- `product_master` (workflow commit): token + description matching fallback
- `customer_master` (pipeline): FK code resolution for region/channel/preferred distributor
- `distributor_master`: no unresolved-token path (direct upsert by code)
- `distributor_sales_inventory`: product/customer/distributor AI after deterministic + format drift
- `shipment_evidence_import`: product/distributor AI + format drift

Pattern: deterministic first, AI only on failure. Confidence >= 0.90 → auto-apply ID.
Below 0.90 → `ai_suggested` diagnostic on staging/shipment payload. AI failure graceful.
`AI_ASSIST_ENABLED=false` → zero AI calls (default). Shared helpers: `ai_resolver_wiring.py`.

### Phase 1 (remaining — non-parser)
- Missing data coverage grid
- Multi-file bulk upload panel (frontend)

### Phase 2 (after Phase 1 validated)
- SOH derivation service (chain level:
  Σ DSI sell-out − Σ sell-through)
- Cost derivation from DSI purchase history
- Sales price fallback chain
- Coverage alerts in Channel Operations
- Customer sell-through velocity

### Phase 3 (future)
- API connectors (Amazon SP-API, distributor APIs)
  daily data slots into fact_customer_sellthrough
  via period_type = 'daily' unchanged
- Inter-customer stock movement tracking
- KPI system

---

## Latest work (May 2026) — Phase 5 Channel Operations page

- Extended existing sell-out page into Channel Operations
- Intelligence depth toggle: Raw|Operational|Strategic|Forecast
  persisted in localStorage `cip_intel_depth`, default Operational
- Four tabs: Overview (charts + KPIs + banners), Sell-out
  (existing page preserved as tab), Inventory, Movements
- Backend: GET `/channel-ops/summary|sell-out|inventory|movements|forecasts`
  registered in router
- Reads: `fact_sales_sellout`, `fact_inventory_distributor`,
  `fact_inventory_reconciliation`, `fact_customer_velocity`,
  `fact_dsi_forecast`, `shipment_evidence_line` (`ShipmentEvidenceLine`)
- `fact_dsi_forecast` only — `fact_forecast` never touched
- All tabs handle empty tables and missing distributor
  gracefully with informative states not blank screens

---

## Latest work (May 2026) — DSI Phase 3 + Phase 4

### Phase 3 — Velocity learning
- Migration 20260518_0042: fact_customer_velocity
  Grain: (distributor_id, product_id, customer_id) —
  one current row per combination, updated each apply.
  computed_through_date = max(transaction_date) from
  fact_sales_sellout — exact source date, no rounding.
  Windows: velocity_4wk (28d), velocity_13wk (91d),
  velocity_52wk (364d). model_confidence: high/medium/low
  based on distinct weeks of history.
  seasonal_index = 1.0 when < 2 calendar years available.
  is_promotional_period always False until CPOR module built.
- dsi_velocity_intelligence.py: compute_distributor_velocity
- dsi_velocity_sync.py: run_dsi_velocity_compute_sync
  chains to dsi_forecasting_enqueue on completion
- dsi_velocity_enqueue.py: mirrors soh enqueue pattern
  Celery task: imports.dsi_velocity_compute
  Activity bell kind: dsi_velocity_compute
  Payload: { distributor_id } — no date, computes from max
- Dispatch: dsi_apply_completion.py dispatches SOH and
  velocity in parallel after apply completion
- dsi_import_state_awareness.py: fixed week_start_date →
  COUNT(DISTINCT DATE_TRUNC('week', computed_through_date))
- Tests: tests/test_dsi_velocity_intelligence.py — 9 passed

### Phase 4 — DSI forecasting
- Migration 20260518_0043: fact_dsi_forecast (new table)
  DO NOT confuse with fact_forecast (Commercial Planner)
  Grain: (distributor_id, product_id, forecast_date)
  forecast_date = future date being forecast, not a period.
  Formula: velocity_52wk * seasonal_index
  Confidence band from 4wk/52wk variance ratio.
  lower_band floored at 0.
  Only medium/high confidence velocity rows feed forecasts.
  Skips products with null or zero velocity_52wk.
- dsi_forecasting.py: generate_distributor_forecasts
  weeks_ahead=13 default
- dsi_forecasting_sync.py: run_dsi_forecasting_sync
- dsi_forecasting_enqueue.py: mirrors soh enqueue pattern
  Celery task: imports.dsi_forecasting
  Activity bell kind: dsi_forecasting
  Payload: { distributor_id }
- Chained from velocity sync after velocity commits
- Tests: tests/test_dsi_forecasting.py — 7 passed

### Migrations applied
- 20260518_0042 + 20260518_0043 applied on cip_alembic_smoke
- NOT yet applied on cip — pending approval

### Task chain (post-apply)
  dsi_apply_completion
    → Task 2: imports.dsi_soh_reconciliation (parallel)
    → Task 3: imports.dsi_velocity_compute (parallel)
      → Task 4: imports.dsi_forecasting (chained from Task 3)

---

## Latest work (May 2026) — DSI Phase 1 + Phase 2 (weekly uploads)

### Phase 1A — import state awareness
- `dsi_import_state_awareness.py`: `check_dsi_import_state(db, job_id, distributor_id)` → `intelligence_state` on `import_job.staged_metadata` (read-only; never blocks validate).
- Layers: `token_auto_resolution`, `soh_reconciliation`, `velocity_learning`, `pricing_intelligence`, `forecasting` with `active` / `degraded` / `initialising` / `inactive`.
- Auto-resolution tier from prior applied DSI jobs on same source: `none` (0) · `supervised` (1) · `automatic` (2+).
- Optional tables: `fact_customer_velocity` — missing → 0 weeks; **CPOR:** `_has_cpor_data` always `False` until a real CPOR import module exists (no proxy).
- Wired at end of validate cache load in `process_distributor_sales_inventory`.
- Tests: `tests/test_dsi_import_state_awareness.py` (14 tests, mocked DB).

### Phase 1B — weekly token auto-resolution
- `dsi_weekly_auto_resolution.py`: validate-time auto-resolve for **automatic** tier; plan-time **supervised** ready rows (`auto_resolved_supervised`).
- `load_historical_customer_resolutions`: steward rows keyed `(distributor_id, normalized_key)` with `(None, key)` fallback.
- Historical workflow unchanged; weekly-only tier logic in `plan_dsi_candidate_sync` and validate row loop.
- Tests: `tests/test_dsi_weekly_auto_resolution.py` (10 tests).

### Phase 1C — frontend
- `DsiIntelligenceStatusPanel.tsx` on validate step (reads `staged_metadata.intelligence_state`).
- Supervised review callout in `DsiImportJobResolutionSection` (`dsi-supervised-auto-resolve-section`).

### Phase 2 — SOH reconciliation
- Migration `20260518_0041`: `fact_inventory_reconciliation` with unique `source_key` (`dsi-recon:{distributor}:{product}:{customer_id|0}:{period_end}`).
- `reconcile_distributor_soh` updates `fact_inventory_distributor` + upserts customer-allocated / open-channel reconciliation rows.
- Post-apply dispatch: `dsi_soh_reconciliation_enqueue.py` → Celery `imports.dsi_soh_reconciliation` (detached thread fallback).
- Activity bell: `dsi_soh_reconcile_task`, kind `dsi_soh_reconciliation`.

### Bug fixes (May 2026)
- **intelligence_state JSONB persistence:** `flag_modified` on `staged_metadata` writes and re-persist at end of validate so Celery validate commits retain `intelligence_state` (`dsi_import_state_awareness.py`, `distributor_sales_inventory.py`).
- **Post-apply loaded + SOH dispatch:** `POST /jobs/{id}/dsi-apply` calls `complete_dsi_import_job_to_loaded` so jobs reach `loaded` and `dsi_soh_reconciliation` dispatches (`imports.py` → `dsi_apply_completion.py`).

### Validation (May 2026)
- `cip_alembic_smoke`: `alembic upgrade head` → `20260518_0041` (clean).
- Pytest (`test_dsi_import_state_awareness`, `test_dsi_soh_reconciliation`): **17 passed** (mocked DB; no `cip` writes).
- Browser/API E2E (`scripts/e2e_dsi_phase1_phase2_validate.py`, job **740** / **741** on `cip`):
  - **S1 pass** — `intelligence_state` panel + API payload; automatic tier (97 prior jobs on source 50).
  - **S2 skipped** — no source with exactly one prior applied job.
  - **S3 pass** — `auto_resolution_tier: automatic`.
  - **S4 pass** — post-apply `dsi_soh_reconcile_task` + `calculated_soh` on `fact_inventory_distributor` (dist **84**).
- **Fixes (May 2026):** JSONB `flag_modified` + end-of-validate re-persist for `intelligence_state`; `POST /dsi-apply` now calls `complete_dsi_import_job_to_loaded` (promotes to `loaded`, dispatches SOH reconcile).

### Next
- Supervised-tier browser check after a controlled “first apply” on a fresh source (or isolated test source).
- Kill stale API on **:8001** if it points at a non-`cip` DB; dev stack used **:8002** + `CIP_API_INTERNAL_URL` for web proxy during validation.
- Phase 3: velocity / forecasting job consumers on `intelligence_state` layers.

---

## Prior work (May 2026) — DSI Phase 0 foundations (shipped on `main`)

### What was built and why

Phase 0 establishes the **fact-layer foundations** for weekly DSI intelligence. Before this work, sell-out upserts used a month-level natural key, negative quantities landed in `fact_sales_sellout`, and inventory had no `source_key`. Returns had no home. Historical imports could not safely auto-apply after validate because `asyncio.run` inside the pipeline Celery task hung on Windows.

| Deliverable | Why |
|-------------|-----|
| **Migrations 0038–0040** | Day-level sell-out grain with `invoice_no` (`''` sentinel, not NULL — stable hash input); new `fact_returns`; inventory `source_key` + reconciliation placeholder columns |
| **Hashed `source_key` builders** (`dsi_fact_source_keys.py`) | Deterministic idempotent upsert: `dsi-sellout:` / `dsi-return:` / `dsi-soh:` prefixes |
| **Quantity routing on apply** | Positive → sell-out; negative → returns (abs qty); zero → skip both — matches commercial semantics |
| **Post-validate historical auto-apply** | Enqueues `dsi_resolution_plan_apply` via Celery or detached daemon thread — never inline `asyncio.run` on the validate thread |
| **Shared enqueue module** (`dsi_resolution_plan_enqueue.py`) | Steward apply-async and post-validate use the same dispatch path |

`period_start` and `transaction_date` are both populated from the staging transaction date on write (sell-out API still reads `period_start`; Phase 1 can unify).

### E2E results (local stack, May 2026)

- Services: `scripts/restart-dev.ps1` — Redis PONG, worker, API `/health`, web `:3000`
- **Scenario 1:** negative qty → `fact_returns` (by `invoice_no`); not in `fact_sales_sellout` — PASS
- **Scenario 2:** re-upload idempotent; qty update on same `source_key` only — PASS
- **Scenario 3:** historical validate enqueues `dsi_post_validate_auto_apply`; weekly does not; activity bell shows `dsi_pipeline` during validate — PASS
- Focused pytest (7 Phase 0 tests): PASS with `ALLOW_TESTS_ON_DEV_DB=1`
- Fixtures: `tests/e2e/fixtures/dsi_e2e_*.csv`

### Architectural decisions locked in Phase 0

1. **Invoice grain:** `distributor_id + product_id + customer_id + transaction_date + invoice_no` (empty string `''` when absent — never NULL in keys).
2. **Returns conflict:** update `return_quantity` and `unit_price` only; `import_job_id` owned by first job (audit record).
3. **Sell-out conflict:** update measures and `source_import_job_id` only — not identity columns.
4. **Inventory:** upsert on `source_key`; drop `uq_fact_inventory_distributor_dsi_v1`; reconciliation columns null until reconciliation jobs run.
5. **Post-validate:** historical workflow only; ready candidates only; excludes `hold_for_manual_review` and `needs_review`.
6. **DSI resolution order / steward governance / corroboration tier order:** unchanged.

---

## Prior work (May 2026) — DSI steward scale + product shipment tie-break

### Shipped on feature branch (`ca4ca57`)
| Area | What changed |
|------|----------------|
| **P0 async apply** | `POST .../dsi-resolution-plan/apply-async` → Celery `imports.dsi_resolution_plan_apply`; poll `.../dsi-steward-bulk-task/{task_id}`; activity bell kind `dsi_resolution_plan_apply` |
| **Apply perf** | Product resolution index loaded **once** per task; chunks of 25 candidates; sync `/apply` capped at 50 ids |
| **409 lock** | `dsi_steward_task_dispatch.py` blocks apply when pipeline or `dsi_bulk_task` active |
| **P1 product tie-break** | `dsi_product_shipment_tiebreak.py` — uses `shipment_distinct_product_ids` + `dominant_evidence_month` on candidate context (set on **next revalidate**) |
| **P1 plan labels** | `suggested_target_label` on plan rows (customer/distributor/product names) |
| **P1/P2 UX** | Single **Review…** row action; plan column shows target label; corroboration chip → **Shipment lines found** vs tie-break; resolution panel **one scroll parent** |

### Not changed
- Shipment evidence import module (read-only corroboration only)
- DSI eligibility / corroboration tier order
- Duplicate detection logic

### Job 733 note
- Existing candidates lack new context fields until **revalidate**. Tie-break at plan time uses stored ids when present; else live `_shipment_disambiguate_product_id`.
- Async apply needs **Redis + worker** (or `CIP_DEV_CELERY_DISPATCH=in_process_thread` when Celery enqueue fails). Stale `dsi_bulk_task` in metadata blocks sync apply until cleared or task completes.

### Validation run
- API: 57 tests (`test_dsi_resolution_plan`, bulk steward, tiebreak)
- Web: 39 tests (`import-steward` features)
- API smoke: `apply-async` 202 + 409 lock; sync apply 1 customer ~5s
- Browser E2E job 733: blocked by Next.js dev overlay on imports grid (manual open job still OK)

### Next
- Merge feature branch after review
- Revalidate job 733 to populate `shipment_distinct_product_ids` / `dominant_evidence_month` on product candidates
- Optional: clear stale `dsi_bulk_task` when Celery task orphaned (PENDING + no worker)

---

## Prior work (on `main`)
- Root-identity duplicate scorer (`0503aaf`)
- Steward same-entity UX, cluster map (`c774616`)

## Next (PM validation)

- Smoke PM validate on Supabase with 14k+ row file (worker + bell + state poll).
- Restart API + worker after deploy.
