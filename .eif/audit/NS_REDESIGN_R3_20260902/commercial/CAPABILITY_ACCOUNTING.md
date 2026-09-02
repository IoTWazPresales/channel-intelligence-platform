# Commercial capability accounting — source evidence (N-0013 r3 amendment, 2026-09-02)

Scope: Promotion Planner (N-0010), website / listing intelligence, product competition. Read-only
discovery against the working tree on `feat/ns-2-brief-nav-collapse`; row counts quoted from
`docs/design/PROMO_PLANNER_CAPABILITY.md` (measured 2026-08-30 on `cip`) and are not re-measured here.

## 0. Status vocabulary used below

| State | Meaning | Evidence bar |
|---|---|---|
| **IMPLEMENTED** | Endpoint + service + UI exist and are exercised in the shipped app | code path + shipped page |
| **PARTIAL** | Real code path exists but a required step is missing, manual, or hard-coded | code path + named gap |
| **SUBSTRATE** | Tables / models / pure functions exist; no UI, no writer, or no caller | model/service file, no route or no writer |
| **PLANNED** | Roadmap / spec / backlog entry with a stated trigger; no code | doc pointer |
| **NOT SUPPORTED** | Explicitly excluded by spec or not derivable from stored data | spec pointer |

## 1. Correction to r3

r3 `DIRECTION.md` §3 listed the Commercial domain as owning "promotion_plan lines, price_observations"
and hid Competition as "computes nothing". Both are wrong against source:

- `promotion_plan` is `enabled: False, hidden: True` in `template_definitions.py` (legacy scaffold, H-10).
  The real promotion object is `cpor_case` / `cpor_case_line` — which r3 placed under *Funding &
  Settlement* as if it were only a money record. The planner (B4, VERIFY PASS 2026-08-14) authors that
  same object.
- "price_observations" is not a table; the real tables are `customer_listing` + `listing_observation`
  with an activation check against CPOR line SRP and an intelligence roll-up already shipped.
- Competition has a working mapping approve/reject workflow and stored competitor prices; it "derives
  nothing" only because nothing calls the scorer and nothing imports prices. Hiding it applied the
  rule the operator has now withdrawn (truth 4).

## 2. Promotion Planner

The promotion plan **is** a CPOR case (customer × window × promotion type) with lines (product ×
distributor × POD-quarter layer). Lifecycle `draft → proposed → approved | rejected → active → ended →
settled | cancelled` (`docs/SPEC_CPOR_V1_AND_LISTING_CAPTURE_V0.md` §2.3; `cpor_cases.py` `/transition`).

| Operator requirement | State | Evidence | Gap |
|---|---|---|---|
| CIP proposes a plan | **PARTIAL** | `promo_plan_builder.py` GET `/cpor/intelligence/promo-plan-draft` — per-line history units, intake-weighted MAC (explain-only legs), cover weeks, SRP, 13-wk forecast volume, comparable cases, budget check vs lineup-derived reservation | Requires a **seed case id** typed by hand; no proposal from customer + period + product family; no seasonal/analogue reasoning exposed beyond comparables count |
| Create a plan manually | **PARTIAL** | POST `/cpor/cases`, POST `/cases/{id}/lines` (case UI at `/commercial-planner/cpor-cases`); B4 "Add line" by product id | Two separate entry points (B4 panel vs case page); ids typed, no entity pickers on B4 |
| Edit proposed / existing plan | **IMPLEMENTED** | B4 per-cell edit (estimate_qty, cost_basis, srp, cover_weeks, distributor_id, pod_quarter), dirty survives refresh, reset-to-suggested; PATCH case/line, void, split-layers, recompute | — |
| Review evidence behind the plan | **PARTIAL** | cost-suggest (CST cost → DSI sell-out weighted avg → manual, with `cost_evidence_json`), MAC bucket popover, comparables, norms, support-bias, forecast volume | Evidence is scattered across popovers/endpoints; no single "why this line" view; competitor and listing evidence not joined into the draft |
| Validate customer / product / period / pricing / support | **IMPLEMENTED** | waterfall recompute server-side (`dealer_price = SRP/(1+vat)×(1−margin)`, `support_unit = max(0, cost − dealer_price)`), flags (`cost_basis_drift`, `no_cost_evidence`, missing SKU assumptions), budget warn/hard-enforce, lifecycle transitions with events | — |
| Export to the external promotion-plan format | **PARTIAL** | POST `/cpor/cases/{id}/export` → versioned XLSX (Reseller sheet + USD pivot); `export_xlsx.py` | Layout is a **frozen 32-column tuple in code** (H-01); import maps 39 fields (H-02/H-03); legacy second export path (H-08); no round-trip; one tenant's layout only |
| Map a new customer's template once, export in it later | **SUBSTRATE → PLANNED** | Import side exists: `CporHistoricalMappingProfile` (DB: header_row_index, sheet_roles_json, column_map_json, value_maps_json, is_default); generic mapping step `CanonicalColumnMappingPanel`; export sibling pattern `lineup_export_columns [{field, header}]` (D-056) | No export-side profile for CPOR; no "learn template from example workbook" UI; `PROMO_PLANNER_CAPABILITY.md` P3 + round-trip test are the roadmap items |
| Historical plans as data + as template examples | **IMPLEMENTED (data)** / **PARTIAL (template)** | 26,313 staged lines via profile `asus_consumer_cpor_tracking_v1`; profiles listed at `/cpor/historical-import/profiles` | Profile is import-only; sheet/value maps not reused for export |
| Uplift, elasticity, effectiveness | **NOT SUPPORTED** | Spec §1 out of scope; BACKLOG §9.8 trigger "5–10 settled cases with claim evidence across ≥3 customers"; `fact_promotion_performance` has no writer | Do not show as figures |
| Delivery rate (result ÷ estimate) | **IMPLEMENTED** | 386 lines with both qty; portfolio/norms endpoints; settlement rollup | Descriptive, per case — not causal |
| Budget envelope | **PARTIAL** | Budget check uses lineup-derived reservation / tenant profile; `fact_budget_*` 0 rows | Show as "reservation check", never as a ledger |

## 3. Website / listing intelligence

| Job (operator truth 2) | State | Evidence | Gap |
|---|---|---|---|
| Monitored listings + URLs per customer × product | **IMPLEMENTED** | `customer_listing` registry (status active/out_of_stock/delisted/dead_link, never deleted); manual, CSV import, feed proposals (`cst_listing_seed` from retailer sell-through feeds), auto-finder (Amazon/Takealot/Evetech) with confirm | Registry is customer-scoped; no competitor listings (BACKLOG §9.9) |
| Price monitoring + history | **IMPLEMENTED** | `listing_observation` (fetched_at, extracted_price, availability, promo_badge, parse flags, raw snapshot retained); scheduled poll (`CIP_LISTING_CAPTURE_SCHEDULE`) + manual `/poll`; `/reparse` without refetch | Takealot needs REST path; span accumulating (<14 d) on live listings |
| Detect customer price changes | **PARTIAL** | `intelligence_v1.py` first→last `price_drift_pct` per listing | No per-observation change events, no threshold alert, no attention signal |
| Is the planned promo live at planned price/time | **IMPLEMENTED** | `cpor_activation.py`: observation price vs covering CPOR **line** SRP (promo line first; sell-out bar only when no promo line) → `not_activated / price_consistent / no_case_detected / no_product_link / no_price`, explainable message, persisted on the observation | Point-in-time per observation |
| Late activation / early deactivation / unexpected movement | **SUBSTRATE** | Derivable from the observation timeline + line window (first `price_consistent` date vs `window_start`; first post-consistent `not_activated` before `window_end`) | Not computed; no worklist |
| SEO / listing-quality monitoring | **PLANNED** | Spec §8 non-goal v0; roadmap P5 lists "SEO/listing-content auditing" as future | No parser, no schema |
| Product content / spec evidence | **SUBSTRATE** | `raw_snapshot` bytes retained per observation, `parser_version` supports re-parse | Nothing extracted beyond price/availability/badge |
| Worklist / attention | **PARTIAL** | `/listing-capture/intelligence` returns `not_activated` worklist (≥14 d ready) | Not a Brief signal; not on any dashboard |

Shipped UI: `/listing-capture` — Registry · Feed proposals · Observations · Intelligence (four tabs).

## 4. Product competition

| Job (operator truth 3) | State | Evidence | Gap |
|---|---|---|---|
| Our SKU ↔ competitor SKU mapping | **IMPLEMENTED (workflow)** / **SEED-ONLY (data)** | `fact_competitor_mapping` (score, explanation, approval_status); `/competition/mappings` approve / reject / delete; page `/competition` Mappings tab | Only `seed_demo.py` writes rows; no import template; no UI to create a mapping by hand |
| System-proposed candidates | **SUBSTRATE** | `services/competition/matching.py` `score_competitor_candidate` — deterministic weighted blend (category .25, form .15, spec Jaccard .25, title tokens .25, price proximity .10) with factor breakdown + explanation | **No caller**; never runs |
| Competitor product master | **SUBSTRATE** | `dim_competitor_brand`, `dim_competitor_product` (sku, name, category, specs_json) | No import, no steward surface |
| Competitor prices | **SUBSTRATE** | `fact_competitor_price` (observed_at, price, channel, source_job_id) + `/competition/prices` list; page tab | 0 rows; `market.py` placeholder falsely reports `competitor_price_import: ready` (doc/code contradiction — record) |
| Competitor listings monitored | **PLANNED** | Spec §9.9 "extend `customer_listing` registry with competitor/marketplace listings … trigger: LC v0 stable + first competitive-pricing decision" | Registry FK is `customer_id`/`product_id`; would need a competitor_product_id seam |
| Reuse by Planning / Planner | **SUBSTRATE** | `planning/pricing.py` rule `comp_gap > 8% → consider_reduction` (feeds seed-only PricingRecommendation) | Not surfaced anywhere live |
| Competitor impact / share | **NOT SUPPORTED** | No data; `market.py` "Foundation only" | Do not show |

## 5. Cross-domain connections already present in code (to make visible in the IA)

| From | To | Mechanism |
|---|---|---|
| Promotion Planner draft | Planning | budget check reads lineup-derived reservation (`profit_reservation`), `pod_quarter` layer |
| Promotion Planner draft | Stock & Sell-through | 13-week `fact_demand_forecast` volume; on-hand / intake buckets for MAC; cover weeks policy |
| Promotion Planner draft | Funding history | comparable cases, trailing support norms, support bias |
| Promotion Planner draft | Data & Stewardship | `commercial_customer_term` (margin/rebate defaults), `commercial_sku_assumption`, provisional masters |
| Listing activation | Promotion Planner / Funding | CPOR **line** SRP is the bar; result persisted on the observation |
| Promo-load recon | Stock & Sell-through | retailer sell-through vs case window/price (`/cases/{id}/promo-load-recon`) |
| Settlement | Funding | claim-evidence import → `result_qty` → payable; payment recon |
| Listing registry | Data & Stewardship | proposals from CST feeds need steward confirm; unmatched products go to catalogue gaps (never auto-create) |
| Competition mapping | Data & Stewardship | approve/reject is a steward act; product master is the anchor |
| Overview | all | Brief signals: `settlement_blocked` exists; `promo_not_activated`, `listing_price_change`, `competitor_mapping_pending` are computable from shipped read models but not wired |

## 6. Doc/code contradictions recorded

1. `market.py` `competitor_price_import: ready` vs no such template in `template_definitions.py`.
2. `/promotions` page text "Scaffold plans/readiness are parked" coexists with the live B4 builder on
   the same page — the shipped page mixes a dead scaffold with the real planner.
3. `PROGRAM.yaml` N-0010 acceptance criteria cite `CIP_DESIGN_LANGUAGE.md FROZEN v1.1 … container
   Response` — a rejected design input.
4. r3 `DIRECTION.md` §3 "promotion_plan lines" / "price_observations" — fixture names that do not exist
   as tables (corrected by this amendment).
