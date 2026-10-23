# N-0115 discovery: what the query engine and catalog are today (2026-10-23)

Read from code at `af707758` and read-only on `cip_n0115` (pg_dump of cip taken 2026-10-23 01:05 as the
postgres owner; queried as owner, which bypasses row security; tenant `default` only on the facts checked).

## Catalog (`apps/api/app/semantics/catalog/default.yaml`, version 2)

- 10 dimensions: period, customer, distributor, product, bu (dim_product.product_line), sales_model, channel,
  region, site_label (CST only), promo_type (CPOR). Plus `lineup_quarter` accepted by the validator only.
- 28 metrics, each with a hand-written `allowed_grains` list. No unit field on any metric (the web infers).
- `refuse_examples` (kept verbatim as walls): fill_rate {lineup_quarter}, {distributor, product};
  pipeline_inbound {distributor, product}; channel_stock {period}, {lineup_quarter}, {customer, product};
  weeks_of_cover {period, bu}, {customer, product, site_label}; sellout_units {site_label},
  {customer, product, site_label}; cst_sellthrough_units {distributor, product}.
- `refuse_all`: claim_rate (A2-03), cost_per_incremental_unit (A2-X). `spec_only`: support_bias (A1-09).
- Tenant overlay (`commercial_tenant_profile.semantic_overlay`, plus back-compat `catalog/tenants/*.yaml`):
  label, hidden, narrowed allowed_grains; composed metrics (ratio or alias, one fact family). Overlay folds
  into `catalog.version`, which is part of the cache key.

## Handlers (`apps/api/app/query/handlers/`)

| Handler | Keys | How it computes | Grains it really serves |
|---|---|---|---|
| a1_pve | fill_rate, line_hit_rate, over_plan_intake_rate, short_exposure, unplanned_intake, no_po_blind_spot, pipeline_inbound, volume_bias | wraps `plan_vs_executed_read_model` (Python), picks scorecard / trend / by-BU values | period (lineup quarter trend), bu |
| a2_cpor | support_spend, delivery_rate, support_cost_per_unit_sold | wraps `build_portfolio_intelligence` (sync session, all-time, non-superseded cases); refuses any period filter | customer, bu, promo_type (one at a time) |
| a3_stock | channel_stock, weeks_of_cover, replenishment_flag | latest `weeks_of_cover_observation` per distributor x product; live calculator on `woc_source=live` | distributor x product |
| volume_series | sellout_units (fact_sales_sellout.units), cst_sellthrough_units (fact_customer_sellthrough.units_sold) | the only SQL GROUP BY; `date_trunc` week/month/quarter | listed grains; CST refuses a period finer than stored |
| composed | tenant ratio / alias | evaluates inputs through dispatch_handler | its one declared grain |

Catalog metrics with no handler answer `not_implemented`: slip, lifecycle_buckets, commercial_cohorts,
pod_completeness, support_norms, comparable_cases, forecast_* (B1-01..05).

## Engine (`apps/api/app/query/engine.py`)

validate (`registry.validate_metric_grain`) -> in-process TTL cache (`query/cache.py`, key = tenant, metric,
grains, filters, catalog version, period grain) -> composed or handler -> `labels.attach_names`.
Product-line scope (D-0056) is not in the engine: it is row security bound per transaction by
`core/product_line_scope.py` on the request session (forced RLS on every fact table below except
`cpor_case` and `listing_observation`). The a2 handler opens its own `SessionLocal()`; scope reaches it only
through the request contextvars (`db/session_sync.py`).

## Every caller found (search: execute_query, catalog_for_tenant, validate_metric_grain, load_catalog,
`/api/v1/query`, `/api/v1/semantics` over apps/api/app and apps/web/src)

API: `endpoints/query.py` (POST /query/execute, /query/explain); `endpoints/report_exports.py` (POST /export,
GET /saved/{id}/export, POST /saved/{id}/deliver); `services/report_delivery.py` (scheduled and manual
sends, run by `services/report_schedule_runner.py`); `endpoints/saved_reports.py` (create, patch validate);
`services/dashboard_widgets.py` (widget validate); `endpoints/semantics.py` (catalog, metrics, dimensions,
overlay GET/PUT, validate); `services/commercial_tenant_profile.py` (overlay editor, composed validation,
cache clear). Not found in `services/brief_signals.py` (brief signals do not use the engine).
Web: `features/dashboards/DashboardWidgetCard.tsx`, `WidgetEditorDialog.tsx`, `DashboardWorkspace.tsx`;
`features/overview/OverviewHub.tsx` (pins); `features/reports/ReportBuilderView.tsx`;
`features/settings/SemanticCatalogOverlayPanel.tsx`.

## Saved state on cip (clone)

- dashboard 3, dashboard_widget 6 (all on dashboard 4): sellout_units [period] week area; cst [customer,
  product] line; cst [period] week line; sellout_units [distributor, product] table; pipeline_inbound
  [period] kpi; cst [customer, period] week line. All filters `{}`.
- saved_report 3: weeks_of_cover [distributor, product] kpi (x2); sellout_units [period] line.
- report_schedule 1: "WoC Mon smoke", saved report 2, weekly Monday 07:00, xlsx, enabled, no subscribers.

## Fact tables (rows on the clone)

| Table | Rows | Measures available | Keys / breakdowns | Notes |
|---|---|---|---|---|
| fact_sales_sellout (DSI sell-out) | 58,128 (2024-01-02..2026-10-09; 4,822 customers, 10 distributors) | units, revenue, computed/reported revenue, unit price ex tax | product, customer (dealer), channel_id, distributor, transaction_date, invoice_no | customer is the DSI dealer, not the CST retailer |
| fact_customer_sellthrough (CST) | 14,898 (2024-03-25..2026-10-12) | units_sold, reported_soh, in_transit, on_order, unit_sell_price, unit_cost, unit_mac | customer, customer_location_id, site_label, product, period_start_date + period_type/grain | vat_basis per row |
| fact_inbound_shipment (shipments / sell-in) | 15,246 | quantity, unit_price, amount (currency_code) | product, distributor, customer, resolved ids, line_state, pod/ship dates | fact_sales_sellin has 0 rows |
| fact_inventory_distributor (stock) | 47,411 | on_hand_units, calculated_soh, soh_variance | product, distributor, as_of_date | snapshot: never sum across dates |
| fact_returns | 6,793 | return_quantity, unit_price | distributor, product, customer, transaction_date | no tenant_id column |
| fact_lineup_plan_item / commercial_lineup_line (lineup plan) | 1,647 / 3,446 | planned/current volume; quantity_units, msrp, dap, profit | customer, channel, product, period | lineup plan item has no tenant_id |
| cpor_case / cpor_case_line | 310 / 657 | estimate/result qty, ttl_support (ZAR), ttl_support_usd, srp, dealer price | case customer, promotion_type, channel, status, window; line product, distributor | cpor_case has no RLS |
| weeks_of_cover_observation | 197,259 | derived_stock, weekly_velocity, weeks_of_cover, flag | distributor, product, cover_as_of_date | governed A3 tape |
| listing_observation (recorded prices) | 76,844 | observed prices | listing / product | fact_pricing has 0 rows |
| fact_demand_forecast | 66,627 | forecast units, bands | distributor, product, customer, period | |

Dimensions: dim_product 18,157 (product_line, business_unit, category, series, form_factor, price_band,
specs_json, ...), dim_customer 5,617 (region_id, channel_id, is_key_account), dim_distributor 24,
dim_region, dim_channel. Business calendar: `services/business_calendar.py` `tenant_calendar(tenant_id)`.
