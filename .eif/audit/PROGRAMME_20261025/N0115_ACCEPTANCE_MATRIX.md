# N-0115 original acceptance matrix — 25 October 2026

Primary reviewer supplement to `N0115_REVIEW.md`. The specialist turn stopped at a usage limit after persisting its initial findings; this matrix and the independently rerun probes are the coordinating reviewer's work, not a completed specialist gate. Source checkpoint: `d069f86c9232a735b87c64bb8f3fe3c7b5916b08`. No product implementation or acceptance.

Scope anchors: original operator mandate in `PROGRAMME_20261023/N0115_PANEL_BRIEF.md:25`, original node-add event 2681, and accepted D-0131. `DATA_MODEL_SPEC.md` section 10 is a reduced implementation plan, not authority to retire original requirements.

Categories: **1 implemented and independently verified**, **2 implemented with verification limitations**, **3 partially implemented**, **4 not implemented**, **5 blocked by a genuine operator/business decision**, **6 explicitly excluded**. No category grants operator acceptance. Category 1 below applies only to the stated bounded contract, not the whole query system.

| Original requirement | Category | Evidence and remaining boundary |
|---|---:|---|
| Discovery of catalog, handlers, facts and every caller | 2 | `PROGRAMME_20261023/N0115_DISCOVERY.md`, current registry/handlers/endpoints and caller map below. Existing inventory largely resolves; recorded-price source claim requires correction before implementation. |
| DSI sell-out fact model | 3 | `semantics/models/default.yaml`, `query/model/loader.py`, DB tests: units/priced units/lines/distinct dealers exist. Original sales-value requirement remains absent and pricing/currency interpretation is proposed. |
| CST sell-through fact model | 3 | Same YAML; units/priced units/lines/distinct stores/latest reported SOH exist. Sales value, cover and restock outcomes missing. |
| CPOR cases and lines | 3 | Case-line model with case join, current named-case breakdown, estimate/result/support measures and ratios. Cases are counted over included lines; this is not a general case register/open-case/value model. Preserve portfolio exclusions and case-window dating until resolved. |
| Shipment/sell-in model | 4 | Actual `FactInboundShipment` and `FactSalesSellin` exist in `models/facts.py`; no corresponding model in the v2 registry. Source/date semantics need reconciliation; mixed currencies do not block unit measures. D-0120 governs an unresolved date choice. |
| Distributor inventory model | 4 | `FactInventoryDistributor` exists; no model declaration. Existing governed channel stock is not a declared reported-inventory model. Latest-per-bucket/carry-forward policy remains D-0119, not permission to sum snapshots. |
| Returns model | 4 | `FactReturns` exists; tenant-via-product path is supported and tested using a test-only returns model. Absence of a tenant_id column is not a general compiler blocker. No production model declaration. |
| Lineup-plan model | 4 | Existing commercial lineup case/line sources; no declared model. Confirm current commercial lineup as canonical, keep lineage/period/approved-state rules. No need to build a second plan writer. |
| Recorded-price model | 4 | `FactPricing` (`models/facts.py:207`) is read by `/pricing/facts` (`endpoints/pricing.py:56`) and the pricing page. YAML pending message instead names `listing_observation` and says unbuildable. This is a doc/source conflict, not proof the original feature is impossible. Confirm intended price family before implementation; do not invent a currency aggregate. |
| Sum, count and distinct count | 2 | Real loader/compiler support; final-source capability probe confirms registered operators. Historical DB parity covers existing examples, not every future model. |
| Average, min and max measures | 4 | Loader `AGGS` is only sum/count/count_distinct/latest_sum. Internal vintage min/max are not public aggregate-measure support. |
| Sales-value measures | 5 | D-0117/0118 are proposed; current YAML explicitly pending. DSI has a currency_code column but historical coverage was null, so “no currency” must not mean no column. Recheck approved-clone coverage, reuse known VAT conversion, show priced coverage, never estimate unpriced units or mix currencies to force parity. |
| Shared customer/distributor/product breakdowns | 2 | Graph derives joins and named identities for current models; CST/DSI customer roles are walled. Non-owner runtime proof outstanding. |
| Product attributes | 3 | bu/business_unit/category/series/form_factor/price_band/sales_model/lifecycle are declared; original “every attribute” is not demonstrated. Adding models inherits reachable attributes, not new entity writers. |
| Product specs_json breakdowns | 4 | No model spec-key metadata/compiler expression/typed safe catalog support. Original requirement remains open. |
| BU, channel, region, site and promotion type | 2 | Current model joins/references/local dimensions; site is CST-only, promo/status/case CPOR-only. BU vs product.business_unit label is D-0128; do not collapse them. |
| Week/month/quarter/year grouping | 2 | Compiler uses Gregorian `date_trunc`; existing DB examples prove these grains with limits. This is not tenant business-calendar support. |
| Day grouping | 4 | `graph.DAILY_REFUSAL`, period registry excludes day; D-0116 remains proposed. Preserve v1 refusal while resolving the requested v2 native-day behavior; never split weekly/monthly CST into fictitious daily observations. |
| Tenant business-calendar grouping | 4 | `services/business_calendar.py::BusinessCalendar` already provides configured calendar buckets, including fiscal/retail/custom behavior. Compiler calls `calendar_grain.date_trunc_expr` instead. Reuse canonical calendar service/configuration; implementation is not a new commercial calendar policy. |
| Allowed combinations derived from joins/walls | 2 | `graph.derived_breakdowns`/`measure_breakdowns`, loader metadata validation. Governed legacy handlers intentionally retain their grain contract; do not force them into arbitrary model joins. |
| Walls declared once, plain reasons, all original refusal examples | 1 (bounded) | Primary reviewer executed `n0115_readonly_probes.py`: all 11 v1 examples remain verbatim across 9 walls; DSI lacks site_label, CST permits it. Broader runtime enforcement still needs DB tests for new paths. |
| Ratio | 2 | `calc.py` + CPOR delivery/support-per-unit definitions; historical DB null/zero denominator coverage. No sum of displayed ratios for totals. |
| Difference | 2 | Current calculated kind, DSI/CST prior difference definitions; historical focused DB evidence. |
| Percentage change | 2 | Current kind, DSI/CST definitions; previous zero yields null. |
| Prior period | 2 | Compiler prior join, known missing/partial-bucket behavior; business-calendar alignment remains absent. |
| Prior year | 4 | Not in CALC_KINDS. Unit C browser-side comparison is not a compiler calculated measure. |
| Running total | 4 | Not in CALC_KINDS; not implemented in compiler. |
| Share of total | 4 | Not in CALC_KINDS. Pie display share does not satisfy the reusable measure contract. |
| Per-week rates | 2 | Existing kind, DSI/CST definitions and partial-period tests. Saved report requires execution dates or period breakdown; current promotion can lose required dates. |
| Re-express or retain existing governed metrics | 3 | 16 platform keys are handler-backed: eight PvE, three CPOR, three stock, two volume. Other catalog keys remain honestly unimplemented/refused; no requirement to fabricate them. Existing handlers retained, but CPOR filter totals and background scope are material gaps. |
| Old/new parity on cip_test and read-only cip clone | 3 | Historical 52/66 comparisons with zero mismatches cover two volume metrics/grains. cip_test CST was empty in that script, supplemented by seeded DB tests. CPOR rule/portfolio tests exist; not a complete per-metric/caller parity matrix. No numerical repair just to match. |
| Keep old handler and list unmatched metrics | 2 | v1 handlers retained and v2 delegates governed keys; no silent mass switch. Finish per-metric inventory including unbacked/refuse_all and filter/period semantics. |
| One compiler: measures × breakdowns × filters | 3 | Model path is SQLAlchemy Core and shared request session. Governed path delegates v1 and CPOR opens a separate sync session; `support_spend` accepts filters it cannot consistently apply. Reproduced with real planner/handler and mocked portfolio I/O. |
| Tenant isolation | 3 | Model structural tenant predicates plus authenticated ORM request scope. Authenticated DSI proof exists. Background governed CPOR ignores request tenant and relies on unset request ContextVar: source-supported risk requiring a two-tenant schedule regression, not an asserted authenticated data leak. |
| Product-line scope | 2 | Transaction-local role/scope binding and forced RLS on facts; empty/scoped/admin authenticated DSI checks exist. No non-owner PostgreSQL role proof, cross-model schedule proof or comprehensive direct SQL checks. |
| Cache security | 2 | v1/v2 keys include tenant, role, product-line scope, request and catalog version. Historical authenticated cache-order test is useful. It does not repair a query that was already incorrectly scoped; tenant semantic overlay remains bypassed for model counterparts. |
| Row limits and explain | 2 | 500 default/5,000 maximum, invalid larger request refused, SQL totals/count independent of display limit, bound SQL/explain. Saved-export v1-equivalence drops explicit sort/limit and remains a defect outside the compiler core. |
| Under-two-second widget target | 2, proof incomplete | Eight historical owner/bypass clone queries 63–292 ms, cache off. No non-owner representative cardinality, cold/warm, concurrency or supported-maximum query proof. A 10-second statement timeout is not a 2-second performance result. |
| Tenant-specific semantic configuration | 3 overall; model configuration 4 | Legacy overlay/config exists. `default_model()` is a single global cached YAML. Fresh in-memory probe: hide/narrow/relabel sellout_units -> v1 refuses, v2 dsi_sellout.units still accepted/exposed. This is semantic governance bypass, not proof of row leakage. |
| Catalog API returns measures/breakdowns/allowed combinations | 2 | Real v2 catalog route, metadata, conditions and refusals. Missing models/specs/calendar/tenant configuration remain missing, despite API shape existing. |
| Every existing caller keeps working, test per caller | 3 | Caller inventory below. Saved report sort/limit/period/date/export gaps and schedule-scope risk preclude blanket parity. |
| No invented rules/figures/new libraries | 2 | Current implementation retains handlers and explicit pending entries; the audit changes no amounts. Proposed definitions remain unaccepted. No new libraries needed for the next bounded fixes. |

## Caller-by-caller coverage

Paths below are relative to `apps/api/app/` unless frontend. Existing test references were inspected; full suites were not repeated. Newly reproduced defects are in the two audit probe scripts/JSON.

| Caller | Route/path and test evidence | Status |
|---|---|---|
| v1 query execute/explain | `api/v1/endpoints/query.py`, `test_query_engine.py`, `test_query_v1_callers_n0115.py` | Retained; CPOR accepted-filter defect applies. |
| v2 query execute/explain | Same endpoint + `query/model/execute.py`; `test_query_v2_api.py`, model DB/graph tests | Implemented for subset; original security/calendar/model coverage incomplete. |
| v1 semantics/catalog/validation | `endpoints/semantics.py`, `semantics/registry.py`; semantic layer/overlay API tests | Legacy path retained. |
| v2 catalog | Same endpoint + model catalog; definitions/graph tests | Model counterparts bypass legacy hide/narrow/label; no tenant model overlay. |
| Tenant semantic settings | `services/commercial_tenant_profile.py`, frontend `SemanticCatalogOverlayPanel.tsx` | Existing editor configures v1 overlay, not current model definitions. |
| Widget validation/save | `services/dashboard_widgets.py`, `dashboard_definitions.py`, dashboards endpoints; definitions/auth tests | Current validation/writers retained; v1-equivalence and ordinary promote context defects. |
| Legacy widget rendering | `DashboardWidgetCard.tsx`, `WidgetChart.tsx`, widget tests | v1 fallback retained with not-filtered notice. |
| v2 editor/card/workspace | builder components, integration tests, final fixture6/auth1 | Current functions substantial; chart config/keyboard gaps; missing model catalog. |
| Saved reports CRUD | saved_reports endpoint + definition validation tests | Dual storage exists, ordinary report context/grain parity incomplete. |
| Ad-hoc PDF/XLSX | `endpoints/report_exports.py` -> v1 engine -> `services/report_export.py` | Existing path; report UI cannot safely reinterpret saved v2. XLSX text formula reproduction. |
| Saved PDF/XLSX | same endpoint -> runs_v1 or shared v2 payload | Fixed-window case works historically; sort/limit equivalence and period-grain defects. |
| Manual delivery | `services/report_delivery.py`, auth/export tests | Authenticated fixed-window admin case proven historically; not scheduler proof. |
| Scheduled/import-triggered delivery | `report_schedule_runner.py` -> `deliver_saved_report(user=None)`; schedule tests | Runs with absent request identity. Need report-tenant binding, authorized recipient scope and pooled-transaction tests. |
| Overview | frontend `OverviewHub.tsx` links/names saved reports | No query translation needed for pins; names-only behavior is not report execution parity. |
| `/reports` frontend | `ReportBuilderView.tsx` v1 fields/run/ad-hoc export | v2 editor excluded by S20, but safe saved definition download/preservation is required and incomplete. |

## Do not convert implementation gaps into blanket business blocks

Existing reusable cover/restock logic is in `services/channel_intelligence/sell_through_overview.py:592` and `:844`: own latest-report anchor, recent sales rate, per-customer settings, freshness and forward cover. Establish original starter meaning against these methods, then add a governed adapter if it matches. Do not invent a generic stock / arbitrary-window sales ratio. `BusinessCalendar` and tenant-via-product support already exist. Missing returns/model aggregates/calculation infrastructure are engineering work. Recorded-price identity and amount/date/status decisions require explicit reconciliation, not a new duplicate source.

The principal first unit is the existing governed CPOR filter contract: reproduce filter/grain/zero-match failures, wire filtering before aggregation or refuse unsupported combinations, preserve formulas, and check v1/v2/export/delivery. Background scope verification is a separate immediate security unit. Neither requires production access or changing business amounts.
