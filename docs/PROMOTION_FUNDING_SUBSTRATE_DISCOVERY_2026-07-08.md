# CPOR Promotion-Funding Data Substrate — Read-Only Discovery (2026-07-08)

**Audit date:** 2026-07-08  
**Branch:** `feat/unit-6-unified-lineup-import-centre` @ `53996e7`  
**Baseline compared:** `docs/PROMOTION_PLANNING_DATA_SUBSTRATE_AUDIT.md` (2026-06-14 @ `1a7a74d`)  
**Method:** Models / services / endpoints / templates inspected in code. Live population via read-only SELECTs on `cip` after `current_database() = 'cip'`. No writes, migrations, or commits.

**Ops script (disposable):** `apps/api/.tmp/promo_substrate_readonly_audit.py`

---

## Executive answers (8 questions)

| # | Question | Verdict |
|---|----------|---------|
| 1 | DSI SOH / intake unit cost | **No.** DSI inventory facts store units only; no SOH unit cost. Intake sell-in cost is not on DSI — use shipment `unit_price` (OEM sell-in evidence) or planner DAP / PM bottom. |
| 2 | DSI sell-out price | **Yes, populated.** `fact_sales_sellout.unit_sellout_price_ex_tax_amount` (+ `revenue`). Live: 35,582 / 35,583 rows have unit price. |
| 3 | Shipment POD-quarter cost layers | **Yes, feasible.** `fact_inbound_shipment` has `unit_price`, `amount`, `currency_code`, `pod_date`, `distributor_id`, `product_id`. Live: 12,784 layerable rows. |
| 4 | CST promo-window aggregation | **Still week/month start only** (Jun-14 claim holds). Schema supports `period_start_date` + `period_type`; no transaction_date. Live CST rows on cip: **0**. |
| 5 | Customer commercial terms | **Not on `dim_customer`.** Steward pattern: `commercial_customer_term` (margin + rebate). No payment-terms field. |
| 6 | Promo scaffold since Jun-14 | **Unchanged scaffold.** Still seed/read/delete + CPOR export; import still `stub_noop`. cip counts all **0**. |
| 7 | Approval pattern | CPOR `promo_plan_export`: `draft → pending_approval → approved \| rejected` (+ resend → new draft version). |
| 8 | FX beyond SKU assumption | **No rate table.** Planner FX scalar + lineup file ROE evidence only. |

---

## 1. DSI cost availability

### Schema (current HEAD)

| Table | Cost-like columns | Notes |
|-------|-------------------|-------|
| `import_distributor_si_staging_line` | `stock_on_hand`, `unit_sellout_price_ex_tax_amount`, `reported_revenue_amount`, `computed_revenue_amount`, `currency_code` | **No SOH unit cost / MAC / intake cost** — see `apps/api/app/models/import_distributor_si.py` L38–43 |
| `fact_inventory_distributor` | `on_hand_units`, `calculated_soh`, `soh_variance` | Units only — `apps/api/app/models/facts.py` L78–92 |
| `fact_sales_sellout` | sell-out price/revenue (Q2) | Not inventory cost |
| `fact_sales_sellin` | `units`, `revenue` only | Schema scaffold; **no DSI writer** found; cip **0 rows** |

DSI template maps sell-out price and SOH quantity, not inventory cost (`template_definitions.py` L183–210; stock aliases around inventory mapping in `distributor_sales_inventory.py`).

### Live cip

| Metric | Value |
|--------|------:|
| `fact_inventory_distributor` rows | 47,411 (all with `on_hand_units`) |
| `fact_sales_sellin` rows | **0** |
| Staging lines with `stock_on_hand` | 63,697 / 178,067 |

### Implication for CPOR funding

Distributor **SOH unit cost is not in the DSI truth layer**. Intake (OEM→distributor) unit economics live on **inbound shipment** `unit_price` / lineup DAP / `commercial_sku_assumption.controlled_cost_amount` — not DSI inventory.

**Jun-14 alignment:** Jun-14 did not claim DSI SOH cost; this audit makes the gap explicit for funding math.

---

## 2. DSI sell-out price

### Columns

- Staging: `import_distributor_si_staging_line.unit_sellout_price_ex_tax_amount` (`import_distributor_si.py` L40)
- Fact: `fact_sales_sellout.unit_sellout_price_ex_tax_amount`, `revenue`, `reported_revenue_amount`, `computed_revenue_amount` (`facts.py` L27–31)
- Apply path writes unit price on upsert (`distributor_sales_inventory.py` ~L3531–3544)

### Live cip

| Metric | Value |
|--------|------:|
| Sell-out rows | 35,583 |
| With `unit_sellout_price_ex_tax_amount` | **35,582** |
| With non-zero `revenue` | 35,465 |
| With `currency_code` | **0** (column exists; not populated on this corpus) |

**Verdict:** Dealer/customer paid price **is modeled and populated** as ex-tax unit sell-out price. Currency on sell-out facts is currently empty on cip.

---

## 3. Shipment layer costing (POD-quarter)

### Fields (`FactInboundShipment`, `facts.py` L164–175, L182–185)

| Field | Role |
|-------|------|
| `unit_price` | OEM file sell-in evidence (not landed cost / not PM bottom) |
| `amount` | Line commercial amount |
| `currency_code` | Currency |
| `pod_date` | Landing / POD date — **quarter derivation source for landed layers** |
| `distributor_id` / `resolved_distributor_id` | Distributor grain |
| `product_id` | Product grain |

Also available: `ship_confirm_date` (ship quarter), `line_state` (`shipped` / `open_order`). Taxonomy: `docs/PLAN_VS_EXECUTED_SHIPPED_TAXONOMY.md` — landed = `pod_date IS NOT NULL`.

### Live cip

| Metric | Value |
|--------|------:|
| Fact rows | 14,397 |
| With `unit_price` / `amount` / `currency_code` | 14,394 each |
| With `pod_date` | 12,933 |
| Layerable (`distributor_id` + `product_id` + `unit_price` + `pod_date`) | **12,784** |

**Verdict:** Grouping into POD-quarter cost layers per `(distributor, product)` is **possible today** with derived-on-read SQL (no schema change). Caveat: `unit_price` remains OEM sell-in evidence, not true landed cost (Jun-14 §4 still correct).

---

## 4. `fact_customer_sellthrough`

### Grain (unchanged vs Jun-14)

`(customer_id [, customer_location_id], product_id, period_start_date, period_type)`  
`period_type` ∈ `{weekly, monthly}` — `fact_customer_sellthrough.py` L14–49.

| Field | Present |
|-------|---------|
| `units_sold` | Yes |
| `unit_sell_price` | Yes (optional) |
| `unit_cost` | Yes (optional) — retailer inventory cost, not promo spend |
| `reported_soh` | Yes (optional) |
| `transaction_date` / daily grain | **No** |
| `promotion_id` | **No** |

Parsers still collapse to Monday-of-week / sheet period (`customer_sell_through_flat.py` `_monday_of_week`; multi-sheet / MTD parsers set `period_type="weekly"`).

### Arbitrary promo-window aggregation?

**Still no first-class support.** You can only approximate by summing weeks/months whose `period_start_date` falls inside a promo window — not true daily overlap. No CST analytics read API (usage: apply + delete-impact in `customer_usage.py` / `product_usage.py`).

### Live cip

**0 rows** in `fact_customer_sellthrough` (pipeline wired; no applied CST corpus on this DB).

**Jun-14 claim “weekly/monthly start only”:** **Still true.**

---

## 5. Customer master commercial terms

### `dim_customer` (`dimensions.py` L77–94)

Identity / status / region / channel / preferred distributor / merge redirect. **No** margin, rebate, or payment terms.

### Steward-maintained commercial config (existing pattern)

| Table | Fields | Pattern |
|-------|--------|---------|
| `commercial_customer_term` | `customer_id` (unique), `customer_margin_pct`, `customer_rebate_pct` | One row per customer; CRUD via commercial-planner API (`commercial_planner.py` ~L1352+) |
| `commercial_distributor_term` | `distributor_margin_pct` | Same pattern for distributors |
| `commercial_sku_assumption` | cost + FX + reserve splits | Per product |
| Plan-line overrides | `override_customer_margin_pct`, etc. | Per plan line |

`CommercialDataMap.tsx` still lists **payment terms** as deferred.

Related but not commercial terms: `customer_report_config` (sell-through cadence expectations only).

### Live cip

| Table | Rows |
|-------|-----:|
| `commercial_customer_term` | 1 |
| `commercial_distributor_term` | 0 |
| `commercial_sku_assumption` | 0 |

**Verdict:** Follow **`commercial_customer_term`** (and plan-line overrides) for steward-maintained per-customer economics — do not put terms on `dim_customer`.

---

## 6. Promo scaffold — state since 2026-06-14

### Tables (unchanged shape)

| Artifact | Path | Writers since Jun-14? |
|----------|------|------------------------|
| `dim_promotion` | `dimensions.py` L185–192 | Seed only (`seed_demo.py`) |
| `fact_promotion_plan` | `facts.py` L226–234 | Seed + list/delete API |
| `fact_promotion_performance` | `facts.py` L237–244 | **None** (schema only) |
| `promo_readiness` | `derived.py` L67–72 | Seed + list/delete |
| `promo_plan_export` (+ events) | `promo_export.py` | CPOR create/submit/approve/reject |

Import slug `promotion_plan` still `pipeline_handler: "stub_noop"` (`template_definitions.py` ~L589–596).

### Consumers that would break or need migration if `fact_promotion_plan` is deprecated

| Consumer | How it uses the table |
|----------|------------------------|
| `apps/api/app/services/promo_export/cpor_xlsx.py` | Loads plan lines by `promotion_id` to build CPOR workbook |
| `apps/api/app/api/v1/endpoints/promotions.py` | `GET /plans`, delete/clear |
| `apps/web/src/app/(app)/promotions/page.tsx` | Plans tab + CPOR export (needs `promotion_id` + plan lines) |
| `apps/api/app/services/commercial_planner/intelligence/product_rankings.py` | `_promo_product_ids` — presence signal for ranking |
| `apps/api/app/services/product_usage.py` | Delete-impact / cascade delete listing |
| `apps/api/app/services/seed_demo.py` | Demo seed |
| `apps/api/app/services/imports/dsi_import_state_awareness.py` | Documents absence of distributor-scoped CPOR facts |

`FactPromotionPerformance` / `PromoReadiness`: only seed + list/delete + product_usage — no compute writers.

### Live cip

All promo scaffold tables: **0 rows** (empty on this DB; demo seed not applied).

**Verdict vs Jun-14:** Scaffold status **unchanged**. No new writers/readers that make it a working promo planner. Surrounding platform (lineup PO recon, PvE, shipment bitemporal) grew elsewhere — not inside promo facts.

---

## 7. Approval pattern — `promo_plan_export`

**Model:** `apps/api/app/models/promo_export.py`  
**Endpoints:** `apps/api/app/api/v1/endpoints/promo_exports.py` (mounted under `/api/v1/promotions`)

### States (`workflow_status`)

| State | Set by |
|-------|--------|
| `draft` | `POST /{promotion_id}/exports` (create), `POST /exports/{id}/resend` (new version) |
| `pending_approval` | `POST /exports/{id}/submit` |
| `approved` | `POST /exports/{id}/approve` |
| `rejected` | `POST /exports/{id}/reject` (requires `comment`) |

### Transitions (as coded)

```
validate (read-only check)
    → create export (draft, file stored, event "created")
        → submit (pending_approval, submitted_at, email stub event)
            → approve (approved, decided_at/by)
            → reject (rejected, decided_at/by, last_comment)
        → resend (NEW export row, draft, new version; prior unchanged)
```

**Audit:** `promo_plan_export_event` (`created`, `submitted`, `email_stub`, `approved`, `rejected`).  
**Validation:** separate `validation_status` (`passed` on create).  
**Email notify:** stub (`maybe_send_export_email`) — still not a real mailer.

**Candidate reuse:** versioned artifact + explicit submit/approve/reject + event log + actor headers (`X-User-Id`). Does **not** model budget reservation.

---

## 8. FX / ROE beyond SKU assumption

| Mechanism | Location | Nature |
|-----------|----------|--------|
| `commercial_sku_assumption.fx_plan_currency_per_cost_currency` | `commercial_planner.py` L50 | Single scalar: plan currency per 1 cost currency |
| `commercial_plan_line.override_fx_plan_currency_per_cost_currency` | L78 | Line override |
| Lineup file ROE evidence | `lineup_pricing.py` / `lineup_pricing_resolution.py` (`roe_local_per_cost_currency`) | Per-case pricing chain input from workbook / assumption default |
| Template alias `roe_evidence` | `template_definitions.py` L334 | Import mapping only |

**Not found:** FX rate table, spot/hedged/booked basis, dated rate snapshots, USD–ZAR market feed.

Live cip: `commercial_sku_assumption` **0 rows** (FX path unused on this DB until assumptions are stewarded).

**Jun-14 §4 FX claim:** **Still true.**

---

## Stale / drifted claims vs Jun-14 audit

| Jun-14 claim | 2026-07-08 status |
|--------------|-------------------|
| Shipment has `unit_price`/`amount`/`currency_code`; no landed cost/FX on shipment | **Still true** (and now proven populated on cip) |
| CST weekly/monthly `period_start` only; no promo window | **Still true** |
| Promo import `stub_noop`; performance/readiness dead | **Still true** |
| CPOR approval wired | **Still true** |
| No FX rate table beyond planner scalar | **Still true** |
| `fact_customer_sales` missing; truth is `fact_customer_sellthrough` | **Still true** |
| Commercial Planner “partially wired” | **Understates current HEAD** — lineup Units 1–8, PO link/recon, PvE, PO Management, bulk backfill landed since Jun-14 (see `CURRENT.md`). Forecast→promo contract still absent. |
| Branch audited `fix/shipment-steward-performance` | **Stale context** — current work is on `feat/unit-6-unified-lineup-import-centre` |
| “No DB access” population unknown | **Superseded by this audit’s cip SELECTs** |
| Implied CST usable for promo consumption once imported | Soften: pipeline wired but **cip has 0 CST rows**; still no promo attribution |
| Budget reservation absent | **Still true** (out of this 8-question scope; unchanged) |

### New facts Jun-14 did not emphasize (relevant to funding)

1. DSI **sell-out unit price is live and dense** on cip.  
2. DSI **does not carry SOH unit cost**; `fact_sales_sellin` is empty scaffold.  
3. Inbound **POD-quarter cost layers are practically available** (12.7k layerable rows).  
4. Customer terms live in **`commercial_customer_term`**, not `dim_customer`.  
5. Promo scaffold tables are **empty on cip** (not just “dead code”).

---

## Design implications (no schema proposed)

**Can build funding math on today (with caveats):**

- Sell-out price from `fact_sales_sellout.unit_sellout_price_ex_tax_amount`
- Intake / layer cost from `fact_inbound_shipment.unit_price` grouped by `pod_date` quarter × distributor × product
- Channel stack defaults from `commercial_customer_term` / distributor terms / plan overrides
- Approval UX pattern from `promo_plan_export`

**Must still design:**

- Distributor SOH valuation (not in DSI)
- True landed cost / FX basis if OEM `unit_price` is insufficient
- Promo plan grain replacing `fact_promotion_plan` (and migrate CPOR + rankings consumers)
- Promo-window sell-through (CST daily or overlap engine; CST corpus itself)
- Budget reservation/consumption ledger (still absent)

---

*End of read-only discovery. Jun-14 audit file left unmodified.*
