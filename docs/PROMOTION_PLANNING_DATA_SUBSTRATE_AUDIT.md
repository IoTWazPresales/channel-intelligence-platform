# CIP Read-Only Discovery Audit: Promotion-Planning Data Substrate

**Audit date:** 2026-06-14  
**Branch audited:** `fix/shipment-steward-performance` @ `1a7a74d`  
**Method:** Models, migrations, services, endpoints, and UI inspected directly. No DB access. `CONTEXT.md` not used as evidence.

---

## Executive summary

| Area | Exists? | Wired end-to-end? | Promotion-planner readiness |
|------|---------|-------------------|----------------------------|
| 1. Commercial Planner | **Yes** | **Yes** (plan builder + lineup + economics) | Partial — produces `target_units`, does not publish a shared forecast contract |
| 2. Promotion / CPOR | **Partial** | CPOR export wired; plan import dead | Scaffold — not a working promo planner |
| 3. Budget & approvals | **Partial** | Read grids wired; ledger/approval dead | Scaffold — no reservation/reconciliation |
| 4. Landed cost & FX | **Partial** | Shipment pipeline wired; cost/FX not on shipments | Gap — landed cost lives on planner/lineup, not inbound facts |
| 5. Customer sell-through (CST) | **Partial** | Import→steward→fact wired | Gap — no promo attribution or budget consumption |
| 6. Velocity / promo-response | **Partial** | DSI velocity+forecast wired | Baseline demand only — no elasticity/promo response |

---

## 1. Commercial Planner (pipeline / forecast)

### Exists
**Yes** — full module behind feature flag `CIP_COMMERCIAL_PLANNER_ENABLED`.

### Key files

| Layer | Paths |
|-------|-------|
| **Models** | `apps/api/app/models/commercial_planner.py`, `commercial_lineup.py`, `historical_lineup.py` |
| **Services** | `apps/api/app/services/commercial_planner/` (calculator, suggestions, intelligence, lineup parse/sync, readiness) |
| **API** | `apps/api/app/api/v1/endpoints/commercial_planner.py` (+ `commercial_planner_intelligence_routes.py`, `commercial_planner_lineup_routes.py`) |
| **UI** | `apps/web/src/app/(app)/commercial-planner/page.tsx`, `apps/web/src/features/commercial-planner/*` |
| **Migrations** | `20260427_0018`, `20260430_0023`, `20260427_0020`, etc. |

### Tables & forecast grain

| Table | Grain | Forecast-like field |
|-------|-------|---------------------|
| `commercial_plan` | Plan header | `period_start`, `period_end`, `currency_code` |
| `commercial_plan_line` | plan × customer × distributor × product | **`target_units`** (planned units) |
| `commercial_lineup_line` | case × entities × product | `quantity_units`, `month_split_json` |
| `historical_lineup_import_line` | job × customer × product | `quantity_units`, `month_split_json` |

Separate forecast tables (not owned by CP):

- `fact_forecast` — `product_id`, optional `customer_id`, `period_start`, `forecast_units` (`apps/api/app/models/facts.py`)
- `fact_dsi_forecast` — DSI distributor weekly forecasts (`apps/api/app/models/fact_dsi_forecast.py`) — **not read by CP**

### Does it produce a consumable FORECASTED SALES number?

**Partially, but not as a published forecast service.**

- **Output grain:** `commercial_plan_line.target_units` at (plan, customer, distributor, product). No monthly fact decomposition on plan lines (only `month_split_json` on lineup rows).
- **Suggestions** (`suggestions.py`) blend sell-out avg, prior plans, `fact_forecast`, lineup qty → suggested `target_units` (+8%).
- **Intelligence rankings** (`intelligence/product_rankings.py`) return `suggested_target_units` from multi-signal scoring.
- **Economics** (`calculator.py`) derive amounts from `target_units` + pricing/terms — not a demand forecast.
- **CP does not write** `fact_forecast` or any downstream forecast table.
- **No module reads** `commercial_plan_line` for buy-plans, budgets, or promo consumption today.

### Wired vs scaffold

| Flow | Status |
|------|--------|
| Create plan → lines → recalculate economics | **Wired** |
| Suggestions → apply-suggestion | **Wired** |
| Lineup case parse-preview/apply (Celery `commercial_planner.parse_lineup_case`) | **Wired** |
| Entity resolution → sync-to-plan | **Wired** |
| Intelligence product rankings → bulk add | **Wired** |
| Ranking snapshots | **Partial** — in-process only, no UI |
| CP → other modules (budget/promo/buy-plan) | **Not wired** |
| `CommercialDataMap.tsx` | **Static doc table** — not live data |

### Gaps for promotion planner

1. No shared “forecasted sales” API or fact table that promo planning can subscribe to.
2. Two parallel forecast systems (`fact_forecast` vs `fact_dsi_forecast`) — CP reads only `fact_forecast`.
3. Suggestions use **product-level** `fact_forecast` only; rankings prefer customer-scoped rows — inconsistent.
4. No period-aligned monthly plan facts.
5. `fact_dsi_forecast` and `fact_customer_velocity` ignored by CP (CP uses raw `AVG(FactSalesSellout.units)`).

---

## 2. Promotion planner / CPOR scaffolding

### Exists
**Partial** — no module named “promotion planner”. Surface is `/promotions` (“Promo calendar & readiness”) + CPOR export.

**“Promotion planner” as a distinct module:** **not found**.

### Key files

| Layer | Paths |
|-------|-------|
| **Models** | `facts.py` (`FactPromotionPlan`, `FactPromotionPerformance`), `dimensions.py` (`DimPromotion`), `derived.py` (`PromoReadiness`), `promo_export.py` (`PromoPlanExport`, `PromoPlanExportEvent`) |
| **Services** | `apps/api/app/services/promo_export/cpor_xlsx.py`, `notify.py` |
| **API** | `promotions.py`, `promo_exports.py` (both under `/api/v1/promotions`) |
| **Import** | `template_definitions.py` — slug `promotion_plan`, handler **`stub_noop`** |
| **UI** | `apps/web/src/app/(app)/promotions/page.tsx` |

### Tables

| Table | Grain | Key fields |
|-------|-------|------------|
| `dim_promotion` | Promotion header | `code`, `name`, dates |
| `fact_promotion_plan` | promotion × product | `expected_uplift_pct`, `support_needed`, `stock_readiness` — **no customer** |
| `fact_promotion_performance` | promotion × product | `lift_actual_pct` — **schema only** |
| `promo_readiness` | product | explainable recommendations — **no compute service** |
| `promo_plan_export` | export artifact | CPOR workbook + workflow status |

No `source_key` on promo facts. No distributor-scoped CPOR fact table.

### Wired vs dead

| Component | Status |
|-----------|--------|
| CPOR XLSX validate → build → store → download | **Wired** |
| CPOR approval workflow (draft → pending → approved/rejected) | **Wired** |
| `GET /promotions/plans`, `/readiness` | **Wired read-only** |
| Promotions UI (plans, readiness, CPOR tabs) | **Wired** |
| `promotion_plan` import | **Dead** — `pipeline_handler: "stub_noop"` |
| `fact_promotion_performance` | **Dead** — no writers, no API |
| `PromoReadiness` calculator | **Dead** — seed/manual only |
| Plan / `dim_promotion` CRUD | **Dead** — list + delete only |
| CPOR email notify | **Dead stub** |
| DSI `_has_cpor_data()` | **Always `False`** — explicitly no CPOR import evidence |

### Gaps

1. Cannot import promo plans from files.
2. No promotion master UI/API (must know `promotion_id` for CPOR).
3. CPOR export is promotion-level; `Planned_Volume_Units` left blank; optional single `customer_id` default for all lines.
4. No customer/product-period promo plan grain.
5. Not in main sidebar nav — reachable via Getting Started / lineup links only.

---

## 3. Budget & approvals

### Exists
**Partial** — schema + read APIs; no finance ledger engine.

### Key files

| Layer | Paths |
|-------|-------|
| **Models** | `facts.py` (`FactBudgetAllocation`, `FactBudgetCommitment`, `FactBudgetActual`, `FactBudgetRequest`), `dimensions.py` (`DimBudgetOwner`), `derived.py` (`BudgetHealth`, `BudgetJustificationSummary`) |
| **API** | `apps/api/app/api/v1/endpoints/budgets.py` |
| **UI** | `apps/web/src/app/(app)/budgets/page.tsx`, `budget-requests/page.tsx` |

### Reservation vs realization accounting

**Not found** — no `reserved`, `consumed`, or `reconciled` fields, enums, or services anywhere in models.

Closest schema:

| Table | Grain | Role |
|-------|-------|------|
| `fact_budget_allocation` | owner × category × period × envelope_type | Envelope |
| `fact_budget_commitment` | owner × period | Committed amount |
| `fact_budget_actual` | owner × period | Actual spend |
| `fact_budget_request` | owner + optional linked product/customer/promotion/roadmap | Ask / initiative |
| `budget_health` | owner × period | `remaining_amount`, `pressure_state` |

**No linkage keys** between allocation → commitment → actual. **No derivation service** computes `budget_health` from the other tables (UI copy implies derivation; code does not implement it).

### Dimensions

| Dimension | On allocations/commitments/actuals | On requests only |
|-----------|-----------------------------------|------------------|
| Owner (`dim_budget_owner`) | Yes | Yes |
| Pool | **Not found** (`dim_budget_pool` does not exist) | — |
| Customer | No | `linked_customer_id` |
| Product | No | `linked_product_id` |
| Period | `period_start` only | No period on request |
| Promotion | No | `linked_promotion_id` |

**Commercial Planner “promo reserve”** (`reserve_total_pct`, `promo_reserve_split_pct`, `calc_*_reserve_amount` on plan lines) is **separate** — forward-looking economics, not budget ledger.

### Approvals

| Workflow | Status |
|----------|--------|
| Budget request submit/approve/reject | **Scaffold** — `status` field exists; no write API or UI |
| CPOR export approval | **Wired** |
| Lineup item approval | **Wired** (separate module) |

### Wired vs dead

| Component | Status |
|-----------|--------|
| `GET /budgets/allocations`, `/requests`, `/health` | **Wired** |
| Budget pages (read + delete/clear) | **Wired** |
| Dashboard open-budget-requests KPI | **Wired** |
| `fact_budget_commitment`, `fact_budget_actual` | **Dead** (schema + seed only) |
| `budget_justification_summary` | **Dead** |
| Budget import templates | **Not found** |
| Create/update allocation or request | **Dead** |

### Gaps for promotion planner

1. No reservation/consumption/reconciliation model.
2. No pool or promo-budget envelope at product/customer grain.
3. No path from promo spend actuals into `fact_budget_actual`.
4. No budget approval workflow despite status field.

---

## 4. Landed cost & FX

### Exists
**Partial** — shipment commercial amounts wired; landed cost and FX basis not on shipment path.

### Shipment / inbound tables

| Table | Commercial fields | Landed cost / FX |
|-------|-------------------|------------------|
| `shipment_evidence_line` | `quantity`, `unit_price`, `amount`, `currency_code` | **Not found** |
| `fact_inbound_shipment` | Mirror of evidence + `source_key` | **Not found** |

`unit_price` is OEM file sell-in evidence — **not** landed cost and **not** PM `controlled_cost_amount`.

Pipeline: `shipment_evidence_import.py` → `shipment_inbound_facts.py` → `shipment_apply_sync.py` — **wired**.

Shipping API (`shipping.py`) aggregates `amount` by currency for KPIs — not unit cost per product/customer rollup.

### Where landed cost / DAP actually live

| Source | Fields | Wired? |
|--------|--------|--------|
| `historical_lineup_import_line` | `dap_local`, `actual_dap_local`, `disti_cost_local` (+ customer on header) | **Wired** import |
| `commercial_lineup_line` | `dap_evidence_local`, `promo_price_evidence_local` | **Wired** |
| `commercial_sku_assumption` | `controlled_cost_amount`, `controlled_cost_currency_code` | **Wired** — PM bottom |
| `commercial_plan_line` | `override_controlled_cost_*`, `override_fx_plan_currency_per_cost_currency` | **Wired** |

Planner suggestions pull DAP from **latest historical lineup apply job** — explicitly not from shipments (`commercial_planner.py` endpoint logic).

### FX basis (spot / hedged / booked USD↔ZAR)

**Not found** on shipment or inbound tables.

On planner only:

- `commercial_sku_assumption.fx_plan_currency_per_cost_currency` — single scalar (plan currency per 1 cost currency)
- `commercial_plan_line.override_fx_plan_currency_per_cost_currency` — optional line override
- `calculator.py` uses effective FX in economics

No `hedged`, `booked`, `spot_rate`, `fx_basis`, or USD–ZAR rate table anywhere in models/services.

### Gaps for promotion planner

1. Cannot attribute promo margin/cost from shipment evidence.
2. No FX basis for multi-currency promo ROI.
3. Landed cost evidence is planner/lineup-local, not tied to inbound truth layer.
4. Three cost concepts remain separate: OEM `unit_price`, lineup DAP, PM `controlled_cost_amount`.

---

## 5. Customer sell-through (CST)

### Exists
**Partial** — import pipeline wired; no promo-budget consumption path.

### Key files

| Layer | Paths |
|-------|-------|
| **Model** | `apps/api/app/models/fact_customer_sellthrough.py` |
| **Staging** | `import_customer_sellthrough_staging.py` |
| **Services** | `customer_sell_through.py`, `customer_sell_through_apply.py`, `parsers/customer_sell_through_*.py` |
| **Migrations** | `20260518_0044`, `20260518_0045` |

**Note:** Project rules reference `fact_customer_sales` as retailer sell-out truth — **table/model not found** in code. Retailer POS truth is `fact_customer_sellthrough`.

### Fact grain & fields

`(customer_id [, customer_location_id], product_id, period_start_date, period_type)` where `period_type` is `weekly` or `monthly`.

| Field | Present | Promo relevance |
|-------|---------|-----------------|
| `units_sold` | Yes | Units only — no promo flag |
| `unit_sell_price` | Yes | Generic sell price — not promo vs list |
| `unit_cost` | Yes optional | Retailer inventory cost — not promo spend |
| `promotion_id` | **Not found** | — |
| `transaction_date` / daily grain | **Not found** | Template notes daily as future phase |

### Can it source running promo-budget consumption?

**No.**

1. No join to `dim_promotion` or promo windows.
2. No promo price vs list price on CST rows.
3. No service reads CST to compute budget actuals or promo spend.
4. **No read API** for CST facts — usage limited to import apply + delete-impact checks (`product_usage.py`, `customer_usage.py`).
5. Period is week/month **start** only — pivoted parsers collapse daily headers to Monday-of-week; no arbitrary promo window overlap logic.
6. Commercial Planner suggestions use **`fact_sales_sellout`** (DSI distributor sell-out), not CST.

### Wired vs dead

| Component | Status |
|-----------|--------|
| Import → staging → steward → fact apply (`source_key` upsert) | **Wired** |
| CST read/analytics API | **Not found** |
| CST → budget / promo performance | **Not found** |
| Dedicated CST steward UI page | **Deferred** — nav points to generic imports |

---

## 6. Velocity / promo-response

### Exists
**Partial** — DSI baseline velocity wired; promo elasticity/response **not found**.

### DSI velocity (wired)

| Layer | Path |
|-------|------|
| Compute | `dsi_velocity_intelligence.py` |
| Fact | `fact_customer_velocity` — `velocity_4wk/13wk/52wk`, `seasonal_index`, `model_confidence`, `is_promotional_period` |
| Pipeline | DSI apply → Celery `imports.dsi_velocity_compute` → velocity → `fact_dsi_forecast` |
| API/UI | `channel_ops.py`; sell-out Channel Ops tabs (`velocity_52wk`, weeks-of-cover) |

`is_promotional_period` column exists but is **always written `False`** in `dsi_velocity_intelligence.py`.

### DSI forecasting (wired in pipeline; API-only UI)

`dsi_forecasting.py` → `fact_dsi_forecast` (13-week horizon, `velocity_52wk × seasonal_index`).  
`GET /channel-ops/forecasts` exists; **no frontend tab** consumes it.

### Promo elasticity / response

Repo-wide search: **`elasticity`**, **`promo_response`** — **not found**.

| Artifact | Status |
|----------|--------|
| `FactPromotionPlan.expected_uplift_pct` | Stored; no calculator |
| `FactPromotionPerformance.lift_actual_pct` | Schema only |
| `build_promo_mix_suggestion` | Heuristic in `suggestions.py` (forecast vs sell-out ratio) |
| `promotion_plan` import | `stub_noop` |
| `velocity_learning` in `dsi_import_state_awareness.py` | **UX status label** (week-count thresholds) — not ML |

### Run rate

No symbol `run_rate`. Effective implementations:

- DSI: weekly units = sum(units) ÷ weeks in window
- CP suggestions: `AVG(units)` over sell-out rows (not weekly velocity)
- Planning helpers (`wos.py`, `buy.py`): deterministic calculators, not fed from DSI velocity in production paths

### Gaps for promotion planner

1. No promo-period classification or promo vs non-promo velocity split.
2. No price–quantity elasticity math.
3. Two disconnected demand signals: DSI weekly velocity vs CP transaction-level averages.
4. `fact_dsi_forecast` not integrated with CP or promo modules.
5. Cannot measure actual vs expected uplift (`FactPromotionPerformance` empty).

---

## Doc vs code discrepancies

| Document | Claim | Code reality |
|----------|-------|--------------|
| `docs/COMMERCIAL_PLANNER_GAP_ANALYSIS.md` | “No registered Celery task” for lineup parse | **Stale** — `commercial_planner.parse_lineup_case` in `worker/tasks.py` + `celery_app.py` |
| Same doc | “No customer-scoped `FactForecast`” in intelligence | **Stale** — `_forecast_by_product()` prefers customer rows |
| Same doc | “No allocation / buy-plan / budget signals in score” | **Stale** — `FactBudgetRequest`, `FactBuyPlan` in `product_rankings.py` |
| Same doc | `lineup_parse_worker.py` “not wired” | **Partially stale** — task registered; worker module may be thin wrapper |
| `.cursor/rules/Supply-Chain-Intelligence-Project-Rules.mdc` | `fact_customer_sales` is retailer sell-out truth | **Stale** — table does not exist; truth is `fact_customer_sellthrough` |
| Budget UI copy (implied) | `budget_health` derived from allocations/actuals | **No derivation service** in code |
| DSI `velocity_learning` label | Implies learning algorithm | **Week-count status only** in `dsi_import_state_awareness.py` |

---

## Promotion planner design implications

### What you can build on today

- `commercial_plan_line.target_units` + economics calc outputs as forward plan inputs
- `fact_forecast` (manual CRUD) and DSI `fact_customer_velocity` / `fact_dsi_forecast` as parallel demand signals
- CPOR export workflow as an approval artifact pattern (not promo planning logic)
- CST import pipeline for retailer units + sell price at weekly/monthly grain
- Historical/current lineup DAP and promo price evidence

### What does not exist and must be designed

- Promo plan import/apply and customer-level promo grain
- Budget reservation → consumption → reconciliation ledger
- Promo-window attribution on sell-through (daily or arbitrary date range)
- Landed cost + FX basis on shipment truth (or explicit bridge from lineup/planner)
- Promo elasticity / uplift measurement
- Single forecast contract consumable across CP, promo, and budget modules

---

## File path index (quick reference)

### Commercial Planner
- `apps/api/app/models/commercial_planner.py`
- `apps/api/app/models/commercial_lineup.py`
- `apps/api/app/models/historical_lineup.py`
- `apps/api/app/services/commercial_planner/`
- `apps/api/app/api/v1/endpoints/commercial_planner.py`
- `apps/web/src/app/(app)/commercial-planner/page.tsx`

### Promotion / CPOR
- `apps/api/app/models/facts.py` (FactPromotionPlan, FactPromotionPerformance)
- `apps/api/app/models/promo_export.py`
- `apps/api/app/services/promo_export/cpor_xlsx.py`
- `apps/api/app/api/v1/endpoints/promotions.py`
- `apps/api/app/api/v1/endpoints/promo_exports.py`
- `apps/web/src/app/(app)/promotions/page.tsx`

### Budget
- `apps/api/app/models/facts.py` (FactBudget*)
- `apps/api/app/api/v1/endpoints/budgets.py`
- `apps/web/src/app/(app)/budgets/page.tsx`

### Shipment / landed cost
- `apps/api/app/models/shipment_evidence.py`
- `apps/api/app/models/facts.py` (FactInboundShipment)
- `apps/api/app/services/imports/shipment_evidence_import.py`

### Customer sell-through
- `apps/api/app/models/fact_customer_sellthrough.py`
- `apps/api/app/services/imports/customer_sell_through.py`
- `apps/api/app/services/imports/customer_sell_through_apply.py`

### Velocity / forecasting
- `apps/api/app/services/imports/dsi_velocity_intelligence.py`
- `apps/api/app/services/imports/dsi_forecasting.py`
- `apps/api/app/models/fact_customer_velocity.py`
- `apps/api/app/models/fact_dsi_forecast.py`
- `apps/api/app/api/v1/endpoints/channel_ops.py`

---

*End of audit.*
