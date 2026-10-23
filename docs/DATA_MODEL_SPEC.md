# Data model under the builder (N-0115)

Status: proposed design, 2026-10-23 overnight run. Sources: `.eif/audit/PROGRAMME_20261023/N0115_DISCOVERY.md`
(what exists), `.eif/audit/PROGRAMME_20261023/seats/data-architect.md` (the one panel seat that
delivered), the orchestrator's reading of `app/query/` and `app/semantics/`. Commercial definitions follow
what the code already does; open questions are listed at the end as proposed decisions for Warren.

## 1. What changes and what does not

Today every catalog metric is answered by a hand-written handler; only `sellout_units` and
`cst_sellthrough_units` are a real SQL GROUP BY, and each metric's breakdowns are a hand-typed
`allowed_grains` list. After this change:

- **Fact models** declare a table, its time column, its joins to shared dimensions and its measures.
- **Breakdowns are derived** from those joins minus declared **walls**.
- **One compiler** turns measures x breakdowns x filters x period into one SQL statement.
- The 28 catalog metrics keep their keys and answers. Two become model measures (parity proven); the rest
  stay **governed handlers** behind the same interface, at the grains they serve today.
- `/api/v1/query/execute`, `/query/explain`, `/semantics/catalog` and stored widgets, saved reports and
  schedules keep working unchanged (v1). New callers use `/api/v1/query/v2/execute` and
  `/api/v1/semantics/v2/catalog`.

## 2. Shared dimensions

| Breakdown id | Source | Notes |
|---|---|---|
| period | the fact model's time column, bucketed on the tenant business calendar | grains week, month, quarter, year; day where the fact is dated by day (see D-proposed 1) |
| product | dim_product (name) | attributes: bu (product_line), business_unit, category, series, form_factor, price_band, sales_model, lifecycle |
| product spec | dim_product.specs_json -> import_staging -> key | key checked against a cached discovered list, bound as a parameter, first line trimmed |
| customer | dim_customer (name) under a **role** per model | dsi_dealer, cst_retailer, shipment_customer, cpor_account, lineup_customer |
| region, channel | via dim_customer.region_id / channel_id | NULL -> "Unassigned"; current values (labelled "current") |
| distributor | dim_distributor (name) | |
| site | model-local (CST site_label) | "Store / site" |
| promo_type | model-local (cpor_case.promotion_type) | |

Joins are declared, many-to-one only, never inferred from foreign keys (`preferred_distributor_id` must
not link CST to distributor).

## 3. Fact models (v1 of the model file: `apps/api/app/semantics/models/default.yaml`)

| Model | Table | Time column (floor) | Joins (role) | Base measures (unit, additivity) |
|---|---|---|---|---|
| dsi_sellout | fact_sales_sellout | transaction_date (day) | product, customer (dsi_dealer), distributor (rows with no distributor excluded, as today) | units (units, additive; = sellout_units), value_ex_vat = units x unit_sellout_price_ex_tax_amount on priced rows (money, currency not recorded), priced_units, lines (count), dealers (distinct count) |
| cst_sellthrough | fact_customer_sellthrough | period_start_date (floor = coarsest stored period_type in scope) | product, customer (cst_retailer), site | units (= cst_sellthrough_units), value (units_sold x unit_sell_price on priced rows, ex/inc VAT as each row's vat_basis says; see D-proposed 3), priced_units, reported_soh (semi-additive: latest per customer, site, product), stores_reporting (distinct) |
| shipments | fact_inbound_shipment | ship_confirm_date (day) | product, distributor, customer (shipment_customer) | quantity (units), amount (money in currency_code; summed only within one currency, mixed currencies refused), lines |
| distributor_stock | fact_inventory_distributor | as_of_date (snapshot) | product, distributor | reported_soh_units (semi-additive latest per distributor x product, no carry-forward), pairs_reporting |
| returns | fact_returns | transaction_date (day) | product, customer (dsi_dealer), distributor | return_units, lines. No tenant_id column: tenant comes through dim_product |
| cpor_lines | cpor_case_line join cpor_case | cpor_case.window_start (day) | product, distributor, customer (cpor_account via case), promo_type | estimate_units, result_units, support_usd (ttl_support_usd), support_zar (ttl_support), lines, cases (distinct case). Superseded cases excluded (superseded_by_case_id IS NULL), voided status excluded, as the portfolio service does |
| lineup_plan | fact_lineup_plan_item | period_start (day) | product, customer (lineup_customer) | planned_units, current_units. No tenant_id: tenant via dim_product |
| recorded_prices | listing_observation | observed date | product | min, max, latest price only (never summed) |

Measures: sum, count, distinct count, weighted average (sum / sum, never AVG over rows), min, max. A
non-additive measure's total comes from the database (GROUPING SETS), never by adding the rows.

## 4. Walls (declared once; `walls:` in the model file)

Each wall has an id, a plain-words reason, and a trigger. When a request hits a wall the answer is a
refusal carrying the reason. Today's refuse_example text is kept verbatim: an exact match on an old
example returns its own text (same order as `registry.validate_metric_grain`).

| Wall | Plain-words reason | Blocks | Keeps refuse_example |
|---|---|---|---|
| W-SITE-CST-ONLY | Store / site comes only from customer sell-through reports. Distributor sell-out has no store. | site with any model but cst_sellthrough | sellout_units {site_label}; weeks_of_cover {customer, product, site_label} |
| W-CUSTOMER-ROLE | A distributor's dealer and a retailer reporting its own sales are different customers and are never combined. | one request mixing customer roles | sellout_units {customer, product, site_label}; weeks_of_cover {customer, product, site_label} |
| W-CST-NO-DISTRIBUTOR | Customer sell-through reports do not say which distributor supplied the stock. | cst_sellthrough x distributor | cst_sellthrough_units {distributor, product} |
| W-SNAPSHOT-NOT-SUMMED | Stock is a count on a day. It is shown as the latest count, never added up across dates. | summing a semi-additive measure across time | channel_stock {period} |
| W-A3-GRAIN-LOCK | Channel stock and weeks of cover are worked out per distributor and product only. | A3 governed measures at any other grain | channel_stock {customer, product}; weeks_of_cover {period, bu} |
| W-LINEUP-QUARTER | Lineup quarter belongs to the plan, not to the calendar. | lineup_quarter outside A1 | fill_rate {lineup_quarter}; channel_stock {lineup_quarter} |
| W-PVE-GRAIN | Plan vs executed is measured by period and business unit, not by distributor stock. | A1 governed measures at distributor x product | fill_rate {distributor, product}; pipeline_inbound {distributor, product} |
| W-ONE-STORED-PERIOD | Sell-through reported weekly or monthly cannot be split into smaller periods. | period grain finer than stored | (handler rule, kept) |
| W-NOT-COMPUTABLE | (existing refuse_reason text) | claim_rate, cost_per_incremental_unit | refuse_all kept |

Derived rule: a model measure allows period (if the model has a time column), every declared join, every
attribute of a joined dimension and every local breakdown, in any combination of up to 3, unless a wall
triggers. A governed handler measure allows exactly its old `allowed_grains` (`serves:`).

## 5. Calculated measures

| Kind | Meaning | Rules |
|---|---|---|
| ratio | a / b of two measures of the same model | null when b is 0 or null |
| difference | a - b | same units only |
| pct_change | (this period - previous bucket) / previous bucket | needs period breakdown; null when previous is 0/null |
| prior_period | the measure for the previous bucket of the same grain | computed by a window over the bucketed result; first bucket fetched by widening the range by one bucket |
| prior_year | the measure for the same bucket one year earlier on the business calendar | second query on the shifted range, joined on bucket position |
| running_total | cumulative sum ordered by period | additive measures only |
| share_of_total | measure / total over the same filters across the other breakdown | total from GROUPING SETS |
| per_week_rate | measure / number of business weeks in the bucket (or the filter window) | needs a period or a date window |

Inputs must share a model (or be the same measure); breakdowns allowed = intersection of the inputs.
Tenant composed metrics (ratio / alias) map one to one.

## 6. The compiler (`apps/api/app/query/model/`)

- `loader.py` reads `semantics/models/default.yaml` plus the tenant overlay; `graph.py` derives breakdowns
  and checks walls; `compiler.py` builds SQLAlchemy Core (identifiers only from the model file, values
  only as bound parameters); `calc.py` applies calculated measures; `execute.py` runs on the request
  `AsyncSession` so row security (D-0056 product-line scope) applies on every statement.
- Always applied: tenant (`tenant_id` column, or via dim_product where the table has none), the filters,
  a row limit (default 500, max 5,000; top-N pushed into SQL with ORDER BY), `SET LOCAL statement_timeout`
  of 10 s per query.
- Explain output: models, measures, joins, walls checked, filters, scope applied, SQL text with bound
  parameter names (no values), row count, ms, data vintage.
- Cache: the existing `query/cache.py`, key = tenant, full request, catalog version, product-line scope,
  role (scope and role added 2026-10-23; before that a scoped user could read a result cached under
  another scope).

## 7. v1 compatibility

`execute_query(metric, grains, filters, period_grain)` stays. A per-metric switch in the model file
(`legacy_key:` on a measure plus `serve_v1_from: compiler|handler`, default `handler`) lets a v1 request
for `sellout_units` / `cst_sellthrough_units` be answered by the compiler only after parity is proven;
the v1 response shape is unchanged (`value`, `rows` with `{g}_id`, `series` with `bucket_key`). Stored
widgets, saved reports and the schedule need no data migration for Unit B.

## 8. Catalog API v2 (`GET /api/v1/semantics/v2/catalog`)

```json
{
  "version": 3,
  "breakdowns": [{"id": "customer", "label": "Customer", "group": "Customer"}, {"id": "period", "label": "Period", "grains": ["week", "month", "quarter", "year"]}],
  "measures": [{"id": "dsi_sellout.units", "label": "Sell-out units", "unit": "units", "model": "dsi_sellout", "kind": "base", "additivity": "additive", "breakdowns": ["period", "product", "customer", "distributor", "region", "channel", "bu"], "period_grains": ["week", "month", "quarter", "year"], "legacy_key": "sellout_units"}],
  "walls": [{"id": "W-SITE-CST-ONLY", "reason": "Store / site comes only from customer sell-through reports. Distributor sell-out has no store."}],
  "combination_rule": "any up to 3 of a measure's breakdowns unless a wall applies; POST /semantics/v2/validate checks one"
}
```

Governed handler metrics appear as measures with `kind: governed` and their old grains.

## 9. Parity proof

For `sellout_units` and `cst_sellthrough_units`, every stored grain in the catalog x period grains week,
month, quarter x no filter and one customer / product filter: old handler value and rows vs compiler,
exact equality on Decimal-summed values (float rounding to 6 dp allowed). Run on cip_test and read-only
on a pg_dump clone of cip; print old vs new per metric. A metric that differs keeps `serve_v1_from:
handler` and is listed.

## 10. Proposed decisions for Warren (not picked)

1. Day grain: the mandate asks for day; today day is refused on purpose ("no daily widget grain"). Proposed
   default tonight: allow day only on models dated by day (DSI, shipments, returns, CPOR) and only from the
   v2 endpoint; v1 keeps refusing day.
2. DSI sales value: DSI has no currency and price is missing on 22,546 of 58,128 rows. Proposed: value =
   units x price ex VAT on priced rows only, shown with "priced units" coverage, currency "not recorded",
   never SUM(revenue).
3. CST sales value: rows carry their own vat_basis (96 inc VAT). Proposed: convert to the tenant
   sales-value VAT setting exactly as the sell-through overview does; no listing-price estimate for
   unpriced units.
4. Distributor stock by period: latest reported count per distributor and product in each bucket, with
   no carry-forward into a bucket with no report (shows "pairs reporting" beside it). Channel Ops derived
   stock (channel_stock, weeks of cover) stays a governed handler and keeps refusing period.
5. Shipment date for the period: ship confirm date (what the A1 slip formula names first). Alternative:
   POD date (landed).
