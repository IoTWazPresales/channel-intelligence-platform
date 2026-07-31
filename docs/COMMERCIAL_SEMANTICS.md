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
| A1-07 | **PM volume bias** | SPEC ONLY | Mean **signed** (shipped − planned) / planned, by **BU** and **PM** across quarters. Exclude planned = 0; report excluded count. Minimum line count per bucket before display (config). Direction is the finding. | BU × PM × multi-quarter | same as fill | Plan vs Executed |
| A1-08 | **Slip** | SPEC ONLY | Lineup quarter vs **actual ship quarter** on linked POs; signed quarter delta. Uses **ship date**, **not** POD. | linked PO / plan line | shipped evidence ship date + lineup `inferred_period_start` | Plan vs Executed |
| A1-09 | **Support bias** | SPEC ONLY · **blocked** | Planned reservation vs actual CPOR spend. **CPOR-owned**, not PvE. Blocked until lineup discovery answers whether reservation is an explicit column or derived (Q-002 / domain Still open #2). | TBD after discovery | lineup reservation + CPOR spend | **CPOR Cases** |

UI label note: scorecard still shows “Deal-stock landing” in code — rename to **Over-plan intake** when the UI is next touched (docs lead).

### 4.2 Shipping — `/shipping`

| ID | Metric | Status | Notes | Owner |
|---|---|---|---|---|
| SH-01 | Lifecycle buckets shipped / pipeline / landed | IMPLEMENTED | Chips + filters on `line_state` / `pod_date` | Shipping |
| SH-02 | Commercial cohorts (arriving / overdue / landed week) | IMPLEMENTED | `shipping_commercial_kpis.py` predicates on **fact** `pod_date` | Shipping |
| SH-03 | POD completeness / awaiting ageing | PARTIAL | UI has `awaiting_pod_days`; truthful completeness blocked by BACKLOG-088 | Shipping |

### 4.3 CPOR intelligence — `/commercial-planner/cpor-cases`

**BU grain:** `dim_product.product_line` (locked).

| ID | Metric | Status | Formula / rule | Owner |
|---|---|---|---|---|
| A2-01 | Support spend by customer / BU / promo type | SPEC ONLY | Portfolio aggregate of support over cases/lines | CPOR |
| A2-02 | **Delivery rate** | SPEC ONLY | `result_qty / estimate_qty` — named apart from claim rate | CPOR |
| A2-03 | **Claim rate** | SPEC ONLY | `claimed / approved` — named apart from delivery rate | CPOR |
| A2-04 | Support norms | SPEC ONLY | Trailing **4** quarters; **%** and **absolute**; window length is **tenant config** | CPOR |
| A2-05 | Comparable-case lookup | SPEC ONLY | **Ranked** (never filtered): customer → BU → promo type → quarter proximity → volume | CPOR |
| A2-06 | **Support cost per unit sold under promo** | SPEC ONLY | `support ÷ result_qty` | CPOR |
| A2-X | Cost per **incremental** unit | **DO NOT BUILD** | No counterfactual/baseline → would fabricate. BACKLOG trigger: validated baseline model exists | — |

### 4.4 Channel Ops — `/sell-out`

**Source module:** `apps/api/app/services/channel_ops_derived_stock.py`

| ID | Metric | Status | Formula / rule | Grain | Owner |
|---|---|---|---|---|---|
| A3-01 | **Derived channel stock** | IMPLEMENTED | latest reported SOH − sell-out since snapshot + POD-landed shipped since (`line_state='shipped'` ∧ `pod_date` > snapshot). Pipeline/`open_order` **never** counts. Latest-per-(distributor, product) only — never sum all snapshots. | distributor × product | Channel Operations |
| A3-02 | **Weeks of cover** | IMPLEMENTED (formula) / SPEC corrected | `derived_stock / velocity` at **distributor × product only**. Customer-grain velocity against distributor stock is a **grain mismatch — not allowed**. Zero / near-zero velocity → **undefined** (never infinity). Code today uses `VELOCITY_NEAR_ZERO≈0.01` → `None`. | distributor × product | Channel Operations |
| A3-03 | **Replenishment flag (v1)** | SPEC ONLY (thin flag exists in API) | Threshold flag vs WoC; **default 4 weeks**; **tenant config**. Not a recommendation engine. | distributor × product | Channel Operations |

CST `/channel-intelligence` remains a **separate** customer×product×site velocity surface — do not conflate with Channel Ops WoC grain.

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
