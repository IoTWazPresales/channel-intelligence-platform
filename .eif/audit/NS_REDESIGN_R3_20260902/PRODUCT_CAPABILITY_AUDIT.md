# CIP product capability audit — from source, not route names

Run `NS_REDESIGN_R3_20260902`. Sources: `apps/web/src/app/(app)/**/page.tsx` (47 routes),
`apps/web/src/middleware.ts` (retired-route redirects), `apps/api/app/api/v1/endpoints/*.py`
(sizes as rough complexity proxy), `apps/api/app/services/**`, `apps/api/app/semantics/catalog/default.yaml`
(governed metric registry), rendered surfaces in `renders/current/` (1280px unless stated).
"Derives" = computed from the data layer today; "Stores" = imported/entered fact or master;
"Latent" = API/service exists, no UI; "Scaffold" = route exists, thin/parked behaviour.

## 1. Data layer the product stands on

| Layer | Truth object | Fed by (template slug) | Notes |
|---|---|---|---|
| Masters | `dim_product` (~18k rows in dev), `dim_customer`, `dim_distributor`, stores, dealer groups | `product_master`, `customer_master`, `distributor_master`, `customer_channel_mapping` | Steward-gated; provisional records; duplicates detection; commercial terms attached to customer/distributor |
| Inbound | `fact_inbound_shipment` (latest-job-wins) | `inbound_shipments` | Lifecycle states, ETA, receipt/POD evidence, cohorts |
| Distributor sell-out + SOH | `fact_sales_sellout`, DSI vintages | `distributor_inventory` | Tiered product resolution (item_code→EAN→model→alias), corroboration, historical vs weekly mode |
| Retailer sell-through | `fact_customer_sales`, customer inventory | `customer_sell_through`, `customer_inventory_sales` | Transaction-immutable |
| Lineup / plan | `CommercialLineupCase`, plan lines, SKU assumptions, PO links | `historical_lineup`, `current_lineup`, `unified_lineup`, `bulk_lineup_backfill`, `lineup_plan` | 195KB endpoint module — the largest in the API |
| Funding / settlement | CPOR cases, claim evidence, payment evidence, pricing support | `cpor_historical_cases`, `cpor_claim_evidence`, `cpor_payment_evidence`, `pricing_support` | 311 cases / R6.0m outstanding in dev (`settlement-1280.png`) |
| Promotions | promotion plan lines | `promotion_plan` | Import exists; analysis surface is a scaffold |
| Market | listing observations (price capture polling) | listing-capture service | Small endpoint (`market.py` thin) |
| Semantic layer | ~30 governed metrics × grains | — | Drives Reports + Dashboards; statuses `implemented / spec_only / do_not_build` |

19 import templates share one pipeline `upload → parse → map → validate → steward → apply → derive`
(`.cursor/rules/import-parity.mdc`).

## 2. Capability inventory (what each really does)

### 2.1 Attention / landing — **Brief** (`/brief`, `brief_signals.py`)
Derives 8 signal families from live facts: `failed_imports`, `soh_recon_not_run`, `dsi_vintage_stale`,
`sell_out_gap`, `cover_breach`, `inbound_open`, `settlement_blocked`, `missing_assumptions`. Each
signal carries a count and a deep link into the owning workflow. OBS: currently four rows and no
figures (`brief-1280.png`). It is an *attention* surface, not a business overview.

### 2.2 Business overview — **Dashboards** (`/dashboards`, `dashboards.py`, `dashboard_widgets.py`)
Stores dashboard definitions with `layout_json` (12-col grid), widgets = one governed metric each
(`WidgetSpec.metric_key`, `validate_widget_query`, visuals `kpi | table | bar | line | area`), grain
and filter per widget, publish/draft. Metrics available = the same ~30 governed metrics the report
builder exposes (plan-vs-executed, shipping lifecycle, CPOR, channel ops, channel intelligence,
forecast families). OBS: shipped as an empty state described as "governed metric canvas"
(`dashboards-1280.png`) — the configurable business view exists in API + editor but is invisible at
first sight. This is the operator's "strategically important customisable view of the business": it
is real, it is governed (cannot fabricate metrics), and it is currently hidden under a utility group.

### 2.3 Reporting — **Reports** (`/reports`, `reports.py`, `ReportBuilderView.tsx`)
Governed report builder: pick metric(s), valid grain chips, dimensions, filters, formula display;
run, save, export (CSV/XLSX), schedule, inbox of runs. OBS strong (`reports-1280.png`). Shares the
semantic registry with Dashboards — Reports = ad-hoc/scheduled tables; Dashboards = persistent
visual monitoring of the same metrics.

### 2.4 Stock & channel movement — **Stock** (`/stock` lenses; `channel_ops.py`, `sell_out`)
Derives: SOH (calculated, never stored), weeks-of-cover per distributor×product, cover breaches
(119 pairs <4w in dev), sell-out velocity, DSI vintage staleness, SOH reconciliation vs reported SOH
(validation checkpoint only), execution vs plan (`/stock?lens=execution` absorbs legacy
plan-vs-executed). Lenses: cover, movement, execution, sell-through. Weakness OBS: raw IDs
("Dist # 9 / Product # 61") in grid at 390px and 1280px (`stock-cover-390.png`).

### 2.5 Inbound & shipping — **Shipping / inbound** (`shipping.py` 40–60KB, `shipment_evidence.py` 60–90KB)
Stores shipments; derives lifecycle (open/in-transit/received/unreceived — 1714 unreceived in dev),
cohort ageing, receipt/POD evidence status, commercial summary (Recharts in
`ShippingCommercialSummary.tsx`), PO coverage/backlog (`po_management`). Steward surface for shipment
entity resolution (`ShipmentEntityStewardPanel`, `ShipmentImportJobResolutionSection`).

### 2.6 Lineup / planning — **Lineup** (`/lineup`, `commercial_planner.py` 195KB)
Stores lineup cases and plan lines per customer×product×period; derives readiness checks, plan vs
shipped, line economics (`recalculate` → `calc_*` fields with `calc_explanation`/`calc_flags`),
customer/distributor terms, SKU assumptions, PO reconciliation and auto-link, product rankings,
distributor attribution, customer-token minting. OBS `lineup-1280.png`: scope bar, read strip,
plan-vs-shipped bars, customer grid — genuinely rich.

### 2.7 Funding & settlement — **Settlement / CPOR** (`/commercial-planner/cpor-cases`, `cpor_cases.py`, `services/cpor/*`)
Stores cases, claim and payment evidence; derives book total / settled / outstanding, blocked reasons,
delivery rate, comparables, support per unit sold, and `cost_per_incremental_unit` with a sell-through
baseline and weak-baseline flag (`incremental_unit_cost.py`, BACKLOG-089: "8 ok / 192 flagged").
**Doc/code contradiction (recorded, not fixed):** `semantics/catalog/default.yaml` still lists
`cost_per_incremental_unit` as `do_not_build` while the service computes it with an honesty flag.

### 2.8 Forecasts (`/forecasts`, `forecasts.py`)
Derives velocity-based and analogue projections from sell-out history with explicit method labels;
no ML claims. Registry marks some forecast metrics `spec_only`.

### 2.9 Pricing / promotions / competition / roadmap / budgets / market (scaffolds)
Routes exist; endpoints small (`market.py` thin; `pricing.py`, `promotions.py` mostly CRUD + import).
Pricing support is real as *funding evidence* (feeds CPOR); price observation capture exists as a
service (listing capture polling). Promotion plan import exists; no promotion effectiveness
calculation exists in the data layer. **Do not present these as analytical capabilities**; present as
"plan inputs & evidence" until derived metrics exist.

### 2.10 Imports — **Import Center** (`/admin/imports`, `imports.py` 60–90KB, `import-steward/` engine)
19 templates; guided 8-step wizard with typed import cards (`imports-1280.png`); async
validate/apply with progress polling; job list; per-job resolution workspace (entity tabs, candidate
grid, plan/bulk apply, drawer, progress). Benchmark-grade UI (`steward-dsi-job-1280.png`).

### 2.11 Stewarding & mapping/resolution (`mappings.py` 60–90KB, `steward_ops.py`, `/admin/mappings`, `/admin/steward-audit`)
Token→dimension mappings (distributor/customer/product), corroboration signals, provisional record
creation (steward-initiated only), duplicate review, steward audit trail. The **mapping queue UI**
(D-0002 subject) is the cross-job view of unresolved tokens; the per-job workspace in 2.10 covers
job-scoped resolution. Both are the same governance boundary seen from two angles.

### 2.12 Master data (`/admin/products`, `/admin/customers`, `/admin/distributors`, `/admin/stores`, dealer groups)
Master grids with search, column selector, drawers, commercial terms, duplicate detection, provisional
enrichment. Strong grid shell (`EnterpriseDataGrid` + `ColumnSelectorModal`).

### 2.13 Operational tooling, audit, SQL (`/admin/ops`, `/admin/sql`, `/admin/audit`, activity feed)
Failed/queued job control (retry/cancel), background task activity feed (bell), read-only audited SQL
viewer, audit log. Real and used; admin/steward roles.

### 2.14 Users, roles, settings (`/admin/users`, `/admin/settings`)
Four roles: admin / steward / planner / viewer (`navConfig.ts` ALL/STEWARD_PLUS/PLANNER_PLUS/ADMIN_ONLY).
Settings: tenant, period, dev-only wipe/seed (destructive; guarded).

## 3. What is genuinely derivable today (the "no fabricated intelligence" fence)

Allowed to show as computed: counts and totals of facts; SOH; weeks of cover; sell-out velocity;
plan vs shipped variance; readiness flags; line economics `calc_*` with explanation/flags; CPOR book/
settled/outstanding/blocked; delivery rate; support per unit; cost per incremental unit **with its
baseline flag**; shipment lifecycle/ageing; DSI vintage age; import/job/steward queue counts; forecast
projections **labelled by method**; governed metrics per registry status `implemented`.
Not derivable (must not appear): confidence percentages outside resolver candidate scores, financial
impact estimates of recommendations, causal attributions, promotion uplift, competitor price impact,
`do_not_build` metrics (claim rate etc.).

## 4. API-without-UI gaps carried from reconciliation (still true from source)
Recommendation/explanation fields (`RecommendationMixin`) on derived entities have no dedicated
surface; PO auto-link results; product rankings; distributor attribution; price observation history;
steward audit detail. These are candidates for *context panels* in the new IA, not new top-level areas.

## 5. Capability → workflow clusters (input to architecture, not labels)

| Cluster | Capabilities | Frequency / who |
|---|---|---|
| Monitor the business | Dashboards, Brief signals, Reports | daily · every role; dashboards config = planner/admin |
| Stock & sell-through | Stock lenses, Forecasts, sell-through, SOH recon | daily/weekly · planners, account managers |
| Supply & inbound | Shipping lifecycle, PO coverage, receipts/POD | daily · planners, ops |
| Plan & commit | Lineup cases, plan lines, economics, PO reconciliation | weekly cycle · buyers/planners, brand managers |
| Fund & settle | CPOR cases, claims, payments, pricing support | weekly/monthly · account/brand managers, finance-adjacent |
| Commercial inputs (latent) | Promotions, pricing, competition, roadmap, budgets, market | periodic · brand managers |
| Data & governance | Import Center, steward/mapping queue, masters, audit, ops, SQL | daily for stewards · steward/admin |
| Administration | Users, roles, settings | rare · admin |

Role evidence: the role model materially affects **visibility** (steward/admin gets Data & governance;
viewer sees monitor + read-only workflows) and **defaults** (steward lands on queue; planner on stock/
lineup), not separate persona UIs. Mobile evidence: away-from-desk needs are *attention + approve +
look-up*: Brief signals, dashboard read, settlement case approve/reject with evidence, shipment
receipt status, stock cover for a product/customer, import job status. Dense grids (lineup, masters,
steward candidates) remain desktop-first with intentional 390px behaviour (summary cards + drill list).
