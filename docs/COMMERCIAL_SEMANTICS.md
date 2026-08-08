# Commercial Semantics

**Owner:** Warren · **Version:** 1.0 · 2026-08-01  
**Status:** authoritative. Metric definitions, lifecycle states, grains, source facts, and
owning surfaces live **here**. If a metric is not defined in this file, it is not built.

**Supersedes / absorbs:** `docs/SURFACE_OWNERSHIP.md` · `docs/PLAN_VS_EXECUTED_SHIPPED_TAXONOMY.md`
(those paths are stubs pointing here). Extends the shipped/pipeline/landed taxonomy rather
than replacing it.

**Nav labels/hrefs:** `apps/web/src/features/shell/navConfig.ts` (tree evidence for routes).

**Code is evidence; this doc is a claim until grepped against the tree.** Implemented metrics
cite their source module. Defined-but-not-built metrics are marked **SPEC ONLY**.

---

## 1. Ownership rule

1. **One concept, one owning surface.** Every metric, filter and lifecycle state has exactly
   one screen that owns it. Other surfaces may *read* or *link*, never re-implement.
2. **Extend, never parallel-build.**
3. **Declare the owner before building** (unit prompt). No owner → halt and ask.
4. **Read across, don't rebuild across.**

A metric mattering to a **phase** means that phase may **consume** it. It does not mean the
phase's screen owns or renders it.

### Pre-build existence audit (mandatory)

```
grep -rn "<concept>" apps/web/src
grep -rn "<concept>" apps/api/app/services
```

Hit → STOP, report, extend that surface. No hit → consult this map; no owner → halt and ask.
Print audit output in the unit report.

---

## 2. Ownership map (routes from tree)

| Concept | Owning surface | Route |
|---|---|---|
| Inbound lifecycle — shipped / pipeline / **landed**; smart cohorts | Shipping | `/shipping` |
| **POD** — `pod_date`, awaiting-POD ageing, landed-week | Shipping | `/shipping` |
| Inbound commercial KPIs (pipeline / arriving / landed / overdue) | Shipping | `/shipping` |
| **Plan vs fill** — fill, line-hit, short, **over-plan intake**, unplanned, no-PO, pipeline tile | Plan vs Executed | `/plan-vs-executed` |
| PO ↔ lineup linking, coverage, auto-link | PO Management | `/admin/po-management` |
| Support economics, settlement, support bias (when unblocked) | CPOR Cases | `/commercial-planner/cpor-cases` (+ `[id]`) |
| CPOR historical import + steward | CPOR Historical Import | `/commercial-planner/cpor-cases/historical-import` |
| DSI ingest + steward | Import Center (`distributor_inventory`) | `/admin/imports` |
| Shipment ingest | Import Center (`inbound_shipments`) | `/admin/imports?template=inbound_shipments` |
| Shipment browse / steward / apply | Shipment Evidence | `/admin/shipment-evidence` |
| CST ingest | Import Center (`customer_sell_through`) | `/admin/imports?template=customer_sell_through` |
| CST ops (key accounts / slots / aliases) | CST steward | `/admin/cst-steward` |
| Channel Ops read (sell-out, **derived stock**, WoC) | Channel Operations | `/sell-out` |
| CST velocity / WoC / aged (customer×product×site) | CST channel intelligence | `/channel-intelligence` |
| Listing registry | Listing Capture | `/listing-capture` |
| Confirmed lineups / plan economics | Commercial Planner | `/commercial-planner` |
| Line-up planning items CRUD | Line-up Planning | `/lineup` |
| **Demand forecast** (units, confidence, bands, method, analogue) | Demand Forecast | `/forecasts` |
| Masters / merges / gaps / channels | Admin masters | `/admin/customers` · `/products` · `/distributors` · … |

### Split surfaces (same domain, different job)

| Domain | Ingest / steward | Ops / analytics read |
|---|---|---|
| Inbound | Import Center + Shipment Evidence | **Shipping** |
| DSI | Import Center | **Channel Operations** (`/sell-out`) |
| CST | Import Center | CST steward · CST channel intelligence |
| Lineups | Commercial Planner · Line-up Planning · PO Management | **Plan vs Executed** (outcomes only) |

---

## 3. Canonical inbound lifecycle (taxonomy)

One lifecycle; every surface maps to it. Source of truth for state: `shipment_evidence_line` /
`fact_inbound_shipment` (`line_state`, `pod_date`).

| State | Rule | Executed for fill? |
|---|---|---|
| Unshipped | planned on linked PO, no shipped evidence qty | No — not cancelled (cancelled = BACKLOG-063) |
| Pipeline | `line_state = 'open_order'` | No — never in fill |
| Shipped | `line_state = 'shipped'` | **Yes** — fill-rate bar |
| Landed | shipped ∧ `pod_date IS NOT NULL` | No for fill; Shipping owns measurement |

### Two time axes (never conflated)

| Axis | Meaning | Used for | Owner |
|---|---|---|---|
| **Shipped** | left the factory (`line_state='shipped'`) | fill, plan execution | Plan vs Executed (consumes) |
| **Landed** | arrived (`pod_date`) | budget consumption, Shipping landed KPIs | **Shipping** (measurement) · budget layer later |

**P1-D004 / BACKLOG-088:** evidence often has `pod_date` while current view / some facts under-count — Shipping KPIs that read fact/current can understate landed until fixed.

---

## 4. Metric catalogue

Status values: **IMPLEMENTED** (transcribed from tree) · **SPEC ONLY** (defined; not built) · **DO NOT BUILD**.

### 4.1 Plan vs Executed — `/plan-vs-executed`

**Source module:** `apps/api/app/services/commercial_planner/plan_vs_executed.py`  
(`compute_scorecard_from_execution_rows`). Spec cross-ref: `docs/PLAN_VS_EXECUTED_SPEC.md`.

| ID | Metric | Status | Formula / rule | Grain | Source facts | Owner |
|---|---|---|---|---|---|---|
| A1-01 | **Fill rate** | IMPLEMENTED | Σ min(shipped, planned) / Σ planned on **in-plan** rows (planned > 0). Shipped = reconcile shipped units only (`line_state='shipped'`). Over-ship capped (met plan). Pipeline/unshipped never in numerator. | period × BU filter (optional); line-level then sum | lineup plan qty + linked-PO shipped qty via reconcile | Plan vs Executed |
| A1-01b | **Line-hit rate** | IMPLEMENTED | Share of in-plan lines with shipped ≥ planned | same | same | Plan vs Executed |
| A1-02 | **Over-plan intake rate** (formerly “deal-stock landing”) | IMPLEMENTED | Σ max(shipped − planned, 0) on in-plan rows — **overship vs plan, not POD** | same | same | Plan vs Executed |
| A1-03 | **Short exposure** | IMPLEMENTED | Σ max(planned − shipped, 0) on in-plan rows | same | same | Plan vs Executed |
| A1-04 | **Unplanned intake** | IMPLEMENTED | Σ shipped on rows with planned = 0 and shipped > 0 | same | same | Plan vs Executed |
| A1-05 | **No-PO blind spot** | IMPLEMENTED | In-plan lines with `awaiting_po`; count + Σ planned units | same | lineup without linked PO | Plan vs Executed |
| A1-06 | **Pipeline (inbound)** | IMPLEMENTED | Σ `pipeline_units` (open_order) on in-plan rows; pending split = inbound vs cold | same | open_order evidence on linked POs | Plan vs Executed |
| A1-07 | **Volume bias (BU / PM)** | IMPLEMENTED | Mean **signed** (shipped − planned) / planned by **BU** (`product_line` / business line). Exclude planned = 0; report excluded count. Min lines per bucket (`VOLUME_BIAS_MIN_LINES`). Direction is the finding. **PM (Q-009):** tenant `pm_attribution_mode=business_line` → PM grain = same business-line buckets (NB/NR/NV/NX); `by_pm` mirrors `by_bu`. Other tenants may use `person_field` / `none` via commercial profile. | BU + business-line PM | same as fill | Plan vs Executed |
| A1-08 | **Slip** | IMPLEMENTED | Lineup quarter vs **actual ship quarter** on linked POs; signed quarter delta. Uses **ship_confirm_date** then **schedule_ship_date** — **not** POD. | linked PO / plan line × product | shipped evidence ship date + lineup period | Plan vs Executed |
| A1-09 | **Support bias** | IMPLEMENTED | Planned reservation vs actual CPOR spend. **CPOR-owned**, not PvE. Planned reservation = **derived from profit** (Q-002; `reservation_source=derived_from_profit`) via SKU `reserve_total_pct` × case `estimate_qty` economics (`GET /cpor/intelligence/support-bias`). Missing `commercial_sku_assumption` → `missing_sku_assumption` (never fabricate 0). Actual = Σ non-voided `ttl_support_usd`. Bias = (actual − planned) / planned when planned > 0. | case / portfolio | derived reservation + CPOR spend | **CPOR Cases** |

UI label: scorecard shows **Over-plan intake** (A1-02; BACKLOG-091 resolved 2026-08-01). API keeps `deal_stock_*` keys with `over_plan_intake_*` aliases.

### 4.2 Shipping — `/shipping`

| ID | Metric | Status | Notes | Owner |
|---|---|---|---|---|
| SH-01 | Lifecycle buckets shipped / pipeline / landed | IMPLEMENTED | Chips + filters on `line_state` / `pod_date` | Shipping |
| SH-02 | Commercial cohorts (arriving / overdue / landed week) | IMPLEMENTED | `shipping_commercial_kpis.py` predicates on **fact** `pod_date` | Shipping |
| SH-03 | POD completeness / awaiting ageing | PARTIAL | UI has `awaiting_pod_days`; truthful completeness blocked by BACKLOG-088 | Shipping |

### 4.3 CPOR intelligence — `/commercial-planner/cpor-cases`

**BU grain:** `dim_product.product_line` (locked).

**Currency (locked 2026-08-01):** compute and aggregate in **USD**. Always **display ZAR alongside**.
Aggregate ZAR by summing each line/case’s own ZAR totals (each case’s booked or floating FX —
domain §1.5). **Never** convert a USD portfolio total through one period FX rate into ZAR.

| ID | Metric | Status | Formula / rule | Owner |
|---|---|---|---|---|
| A2-01 | Support spend by customer / BU / promo type | IMPLEMENTED (A2-U1) | Σ `ttl_support_usd` (compute) + Σ `ttl_support` ZAR (display); voided excluded | CPOR |
| A2-02 | **Delivery rate** | IMPLEMENTED (A2-U1) | Σ `result_qty` / Σ `estimate_qty` (voided / zero-estimate excluded) | CPOR |
| A2-04 | Support norms | IMPLEMENTED (A2-U2) | Trailing **4** quarters (tenant config `SUPPORT_NORMS_TRAILING_QUARTERS`); **absolute** support USD+ZAR; **%** = mean(`support_unit / srp`) | CPOR |
| A2-05 | Comparable-case lookup | IMPLEMENTED (A2-U2) | **Ranked** (never filtered): customer → BU → promo type → quarter proximity → volume | CPOR |
| A2-06 | **Support cost per unit sold under promo** | IMPLEMENTED (A2-U1) | Σ `ttl_support_usd` / Σ `result_qty` (result > 0); ZAR companion = Σ `ttl_support` / Σ `result_qty` | CPOR |
| A2-07 | **Promo load recon** (BACKLOG-093) | IMPLEMENTED | Case-scoped CST (`fact_customer_sellthrough`) vs approved case terms: buckets `ok` / `missing_load` / `wrong_window` / `wrong_price` / `price_unknown` / `no_cst`. Strict window overlap; price tol 2%. Never DSI sell-out. Separate from Settlement claim-vs-CST. `GET /cpor/cases/{id}/promo-load-recon` · UI tab **Promo load**. | CPOR |
| A2-X | Cost per **incremental** unit | **DO NOT BUILD** | No counterfactual/baseline → would fabricate. BACKLOG trigger: validated baseline model exists | — |

#### Non-computable register

| Former ID | Name | Reason | TRIGGER to reconsider |
|---|---|---|---|
| A2-03 | Claim rate (`owed ÷ approved`) | Settlement does **not** capture an **owed** amount independent of `support_unit × result_qty`. Claim evidence is units (+ optional `unit_price`); rollup writes `result_qty`; `ttl_result` is recomputed from the **same** `support_unit` as approved estimate. Owed÷approved money collapses to delivery rate (`result/estimate`). Building both would be two names for one number. **Not “paid”:** paid = distributor payment reconciliation (Ken / admin) — a separate future input, not U5 settlement. | Settlement captures an **owed** amount **distinct from computed support** (and/or support-per-unit can differ between approval and settlement). |

### 4.4 Channel Ops — `/sell-out`

**Source module:** `apps/api/app/services/channel_ops_derived_stock.py`

| ID | Metric | Status | Formula / rule | Grain | Owner |
|---|---|---|---|---|---|
| A3-01 | **Derived channel stock** | IMPLEMENTED | latest reported SOH − sell-out since snapshot + POD-landed shipped since (`line_state='shipped'` ∧ `pod_date` > snapshot). Pipeline/`open_order` **never** counts. Latest-per-(distributor, product) only — never sum all snapshots. | distributor × product | Channel Operations |
| A3-02 | **Weeks of cover** | IMPLEMENTED | `derived_stock / velocity` at **distributor × product only**. Velocity = sell-out units over 364d ÷ 52 from `fact_sales_sellout` (same grain). Portfolio = Σstock / Σvelocity. Zero / near-zero velocity → **undefined**. | distributor × product | Channel Operations |
| A3-03 | **Replenishment flag (v1)** | IMPLEMENTED | Threshold flag when `0 < weeks_of_cover < REPLENISHMENT_WOC_THRESHOLD_WEEKS` (tenant config default **4**). Not a recommendation engine. Portfolio summary reports pair count below threshold + portfolio flag. Row field `replenishment_flag` (`reorder_signal` alias). | distributor × product | Channel Operations |
| A3-04 | **Sell-out YoY / coverage** | IMPLEMENTED | YoY = (current − prior) / prior only when **current calendar quarter has ≥1 sell-out row**. Empty current quarter → `has_data=false`, `sell_out_yoy_pct=null` (never −100%), declare `sell_out_data_vintage.max_transaction_date`. True zero with rows is distinct from no coverage. | portfolio (optional distributor filter) | Channel Operations |

CST `/channel-intelligence` remains a **separate** customer×product×site velocity surface — do not conflate with Channel Ops WoC grain.

### 4.5 Demand forecast — `/forecasts`

**Source of truth table:** `fact_demand_forecast` (sole B2/B4 consumable contract).  
**Upstream signal (not the contract):** `fact_dsi_forecast` — DSI velocity projection cache; Channel Ops may label it “DSI velocity projection.”  
**Legacy:** `fact_forecast` — superseded; rows migrate as `method=manual`. Do not write new business logic against it.

**Atomic grain:** distributor × product × customer × period. Roll up by **SUM** on any axis (no double-count). Quarter totals are a **comparison re-derivation** only — never the primary stored grain.

**B2 net-requirement note:** A3 channel stock is distributor × product. Subtract forecast from stock at the **distributor × product rollup**, not at customer-atomic grain.

| ID | Metric / concept | Status | Formula / rule | Grain | Owner |
|---|---|---|---|---|---|
| B1-01 | **forecast_units** | IMPLEMENTED (B1-01/02) | Stored at atomic grain; rollup = Σ across any axis (`GET /forecasts/rollups`) | distributor × product × customer × period | Demand Forecast |
| B1-02 | **confidence_level** | IMPLEMENTED (velocity) | Ordinal `{low, medium, high, override}`. Velocity: from `fact_customer_velocity.model_confidence`. Analogue: capped `low` (B1-03). Manual override: `override`. | same | Demand Forecast |
| B1-03 | **Forecast band** | IMPLEMENTED (velocity) | `lower_band` / `upper_band`. Velocity: 4wk-vs-52wk variance. Analogue: widened + confidence capped low (B1-03). Override: band = point. | same | Demand Forecast |
| B1-04 | **Forecast method** | IMPLEMENTED (velocity + analogue + manual) | Taxonomy `{velocity, analogue, manual}` live; `blend` deferred. Precedence: override/manual > analogue > velocity. | same | Demand Forecast |
| B1-05 | **Analogue provenance** | IMPLEMENTED (B1-03) | Required when `method=analogue`: `analogue_product_id` + `analogue_basis` JSON `{matched[], scale}` from product_line / series / form_factor / price_band / gpu / predecessor. | same | Demand Forecast |
| B1-06 | **Channel pseudo-customer** | SPEC (schema B1-01) | `customer_id` is **NOT NULL**. Channel-only / missing-customer demand uses controlled `dim_customer.code = OPEN_CHANNEL`. Missing distributor on manual override uses `dim_distributor.code = UNASSIGNED`. | — | Demand Forecast |
| B1-07 | **Forecast layer invariant** | SPEC (schema B1-01) | Forecast is **never merged into actuals**. Separate table, separate labelled surface. Missing actual ≠ gap-filled with prediction. | — | Demand Forecast |

### 4.6 Buy plan / budget — B2 (IMPLEMENTED — Unit 1 author loop)

**Consumes:** B1 `fact_demand_forecast` (rollup), A3 derived stock, inbound `fact_inbound_shipment`
(`line_state='shipped'` ∧ `pod_date` for landed; `open_order` + shipped-not-landed for in-transit).
**SKU economics:** steward-seeded `commercial_sku_assumption` only (never backfilled from
assumptions). SRP inputs come from plan/lineup authoring evidence (`dap_evidence_local` /
`msrp_local` or operator-entered SRP) — never a silent SKU backfill (`CommercialSkuAssumption`
has cost + reserve % only).

**Caveats (Unit 1–3):** tenant Excel workbook = **XLSX on-ramp** (`GET …/net-requirement/export.xlsx`
with NetRequirement + DraftLineup sheets) plus CSV; full ASUS reseller workbook format still later if
tenant demands column parity beyond on-ramp. `/lineup` owns the author loop; nav merge into
commercial-planner deferred. Hard budget enforce stays off until reapproval workflow.
Apply can also write `commercial_lineup_case` + lines (`write_commercial_case`, default true).

| ID | Metric / concept | Status | Formula / rule | Grain | Owner |
|---|---|---|---|---|---|
| B2-01 | **Net requirement** | IMPLEMENTED | `forecast_units` (dist×product rollup) − derived channel stock − in-transit (`open_order` + shipped∧`pod_date IS NULL`) + cover policy units. Pipeline never counts as stock. Optional A1 bias (UI toggle). `GET /api/v1/lineup/net-requirement`; apply → `POST /apply-net-requirement` → `fact_lineup_plan_item` (+ optional commercial case). Half-year period slots via `GET /half-year-periods`. | distributor × product × period | Line-up Planning (`/lineup`) |
| B2-02 | **Profit with reservation** | IMPLEMENTED | Line economics via commercial calculator; reservation = `reserve_total_pct` × sell-in (derived, not workbook column). `POST /api/v1/lineup/builder-economics` (requires SKU + target SRP). Hard money ceiling deferred. | plan line / SKU | Line-up Planning |
| B2-03 | **Budget position (money)** | IMPLEMENTED | Planned reservation (B2-02) derived from draft/commercial lineup × SKU × SRP evidence vs drawn CPOR `ttl_support_usd` by `pod_quarter`≈period_label (string join). Missing SKU → `missing_sku_economics`; missing SRP → skip + `missing_srp` — never fabricate. | period × (optional BU) | Line-up Planning / CPOR |
| B2-04 | **Budget position (support %)** | IMPLEMENTED | Planned support % = reservation÷sell-in companion track on same payload as B2-03. Informational when money-binding. | period | Line-up Planning / CPOR |

### 4.7 Promo draft — B4 (IMPLEMENTED — compose + draft create)

| ID | Metric / concept | Status | Formula / rule | Grain | Owner |
|---|---|---|---|---|---|
| B4-01 | **Promo draft composition** | IMPLEMENTED | Compose A2 comps + B1 volume + B2 budget check into a draft case. `GET /cpor/intelligence/promo-plan-draft` (budget from lineup-derived reservation when `planned_support_usd` omitted). `POST …/promo-plan-draft/create-case` writes a **draft** CPOR case via existing case/line path. Draft may warn on over-budget; hard enforce follows tenant profile (`confirm_over_budget`). Do not invent parallel economics. UI: `/promotions` B4 panel. | case / line | Promotions |

---

## 5. Related specs (not absorbed)

| Doc | Role |
|---|---|
| `docs/PLAN_VS_EXECUTED_SPEC.md` | **Stub** → this file (no parallel metric copy) |
| `docs/COMMERCIAL_DOMAIN_RULES.md` | Domain ground truth — never overridden; corrected when it conflicts with this file |
| `docs/STEWARD_EXPERIENCE_CONTRACT.md` | Steward UX contract rows |
| `docs/BACKLOG.md` | Deferred work + TRIGGER (incl. incremental-unit cost, POD propagation, WoC grain) |

---

## 6. Document discipline

Factual claims about ownership, routes, and metric formulas are generated from the tree and
Warren decisions, then reviewed. Do not draft ownership maps from memory
(2026-08-01 incident). Full-file rewrites must diff section lists before/after.
