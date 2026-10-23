# N-0115 implementation report: data model and one query compiler under the dashboard builder

Date: 2026-10-23. Lenses applied (no skills loaded): backend-engineer, test-engineering-specialist,
database-specialist. Built to `docs/DATA_MODEL_SPEC.md` section 10 (overrides earlier sections).
Change scope: `apps/api` only, plus four "as built" correction bullets in `docs/DATA_MODEL_SPEC.md`
section 10. No migration. No connection to `cip`. Nothing committed, pushed or restarted.
Verification rung: self-verification only (same session that built it); GOV-008 independent run still to do.

## 1. Files

New:
- `apps/api/app/semantics/models/default.yaml`: the model file (dimensions, 3 models, 15 base measures,
  10 calculated measures, 9 walls, 11 pending items).
- `apps/api/app/query/model/__init__.py`
- `apps/api/app/query/model/loader.py`: parses and validates the file against the ORM metadata;
  `ModelLoadError` on any unknown table, column, rule, id, cycle or missing tenant path; checks each wall's
  kept text against the v1 catalog verbatim.
- `apps/api/app/query/model/rules.py`: the only SQL not named by a column: CPOR portfolio line/case rules
  and support USD per line, mirroring `services/cpor/pivot.py` and `portfolio_intelligence.py`
  (case filter reuses `where_commercial_intelligence()`'s column).
- `apps/api/app/query/model/graph.py`: derived breakdowns, walls, request validation into a plan.
- `apps/api/app/query/model/compiler.py`: SQLAlchemy Core (agg CTE, optional prev self-join, totals,
  count, stored-period check).
- `apps/api/app/query/model/calc.py`: calculated-measure null rules and totals.
- `apps/api/app/query/model/execute.py`: runs on the request `AsyncSession`; `SET LOCAL statement_timeout
  = '10s'`; reads the bound scope in the same transaction; names via `labels.attach_names`; cache v2.
- `apps/api/app/query/model/explain.py`, `apps/api/app/query/model/catalog.py`
- `apps/api/scripts/n0115_parity.py`
- Tests: `apps/api/tests/test_query_model_graph.py`, `test_query_model_db.py`, `test_query_model_rules.py`,
  `test_query_v2_api.py`, `test_query_v1_callers_n0115.py`.

Changed:
- `apps/api/app/query/cache.py`: added `cache_key_v2(tenant_id, request, catalog_version)` (prefix
  `cip:query:model:v1:`; hashes the whole canonical request + tenant + catalog version + product-line
  scope + role). v1 `cache_key` untouched.
- `apps/api/app/api/v1/endpoints/query.py`: `POST /v2/execute`, `POST /v2/explain` (v1 routes untouched).
- `apps/api/app/api/v1/endpoints/semantics.py`: `GET /v2/catalog` (v1 routes untouched).
- `docs/DATA_MODEL_SPEC.md`: "As built" bullets in section 10 (see section 8 below).

## 2. Endpoints (all on `api_router`, each with `Depends(get_current_user)` explicitly)

- `GET /api/v1/semantics/v2/catalog`: version (`model version.file digest.v1 catalog version`), groups,
  breakdowns (id, label, group, kind; period with grains), models (customer role, derived breakdowns),
  measures (id, label, unit, model, kind base/calculated/governed, additivity, breakdowns allowed,
  period_grains, requires, legacy_key; governed: grain_sets = old allowed_grains, handler_backed,
  refuse_all/reason, hidden for admins only), walls (reason + kept v1 texts), combination rule, limits,
  pending.
- `POST /api/v1/query/v2/execute` and `POST /api/v1/query/v2/explain`. Request
  `{measures, breakdowns, filters:{breakdown: value|[values]}, period:{grain, from, to}, sort:{by, dir}, limit}`.
  Response `{ok, columns, rows, totals, truncated, refusals:[{measure, reason, wall}], explain, cache}`.
  Explain validates and compiles; it runs no SQL (the CST stored-period check is noted as execute-time).
- Governed measures (v1 metrics with no model counterpart, e.g. `weeks_of_cover`, `fill_rate`,
  `support_spend`, tenant composed metrics) are accepted alone in a v2 request: v1 validation and the v1
  engine run unchanged; v2 only reshapes rows/columns. `sellout_units` / `cst_sellthrough_units` in v2 are
  refused with "Use dsi_sellout.units / cst_sellthrough.units".

## 3. Measures built

| Model | Base measures | Calculated |
|---|---|---|
| dsi_sellout (fact_sales_sellout, tenant_id; time transaction_date) | units (legacy sellout_units), priced_units, lines, dealers (distinct) | units_prior_period, units_change (difference), units_pct_change, units_per_week |
| cst_sellthrough (fact_customer_sellthrough, tenant_id; time period_start_date, never finer than stored period_type) | units (legacy cst_sellthrough_units), priced_units, lines, stores_reporting (distinct), reported_soh (semi-additive, latest report per customer on or before period.to; same rule as `sell_through_overview.load_stock_positions`, test-proven) | units_prior_period, units_change, units_pct_change, units_per_week |
| cpor (cpor_case_line + inner cpor_case; tenant via case; time case window_start) | estimate_units, result_units, support_usd, support_zar, lines, cases (distinct case over visible lines). Labels say "(window start in period)". | delivery_rate (ratio result/estimate), support_per_unit_usd (ratio) |

Breakdowns derived: period (week/month/quarter/year; day refused with the v1 text), product + bu,
business_unit, category, series, form_factor, price_band, sales_model, lifecycle; customer + partner_tier,
region (current), channel (current); distributor (DSI, CPOR); site_label "Store / site" (CST); promo_type,
status, workflow_status (CPOR). Up to 3 at once; one model per query.

## 4. Deferred / not built, and why

- Value measures: DSI sales value (proposed decision 2), CST sales value + VAT conversion (decision 3).
  The CST VAT conversion is inline in `sell_through_overview.load_observations` (not a callable function)
  and the overview adds listing-price estimates; building it in SQL would be a re-implementation of an
  unpicked definition. Listed under `pending:`.
- Customer stock cover and restock flags: the overview computes them in Python with per-customer config
  and forward cover; not a compiler measure. Widgets can show `reported_soh` beside `units_per_week` (no
  derived cover), as section 10 says.
- CPOR "open" and CPOR "value": proposed decisions; break down by status / workflow_status instead.
- prior_year, running_total, share_of_total; spec-key breakdowns; day grain (decision 1); models shipments,
  distributor_stock, returns, lineup_plan, recorded_prices (not buildable as written); per-tenant model
  overlay (only `default.yaml` ships). The tenant_via dim_product path is built and tested with a test-only
  returns model.

## 5. Tests

Run: `apps/api/.venv/Scripts/python.exe apps/api/scripts/db_on.py pytest <files>` on cip_test.
Final run of the relevant set (25 files): **320 passed, 2 skipped** (skips pre-existing: dashboard_widget
INSERT needs ALLOW_TESTS_ON_DEV_DB; R1d e2e needs CIP_AUTH_MODE=session in the environment). One
pre-existing RuntimeWarning in `test_query_engine.py` (AsyncMock in labels).

New tests (49):
- `test_query_model_graph.py` (27, no DB): model loads with tenant paths; loader refuses missing tenant
  path, unknown table/column/rule, wall text drift; tenant_via dim_product accepted; all 11 v1
  refuse_examples kept verbatim; each refused with its exact text in v2 (model measure or governed) AND in
  v1 `validate_metric_grain`; wall reasons for other measures/filters; one model per query
  (W-CUSTOMER-ROLE); stock never summed by period; refuse_all reason; governed alone; day refused with v1
  text; calculated needs; injection (5 bad measure ids, bad breakdown/sort/filter ids, non-int ids, 1,001
  values, empty list; compiled SQL has no values, only parameter names); limit 5,001 refused not clamped;
  CPOR rules + case tenant in SQL; LEFT JOIN + 'Unassigned'; v2 cache key separates request, tenant,
  version, scope, role.
- `test_query_model_db.py` (10, cip_test, rolled back): parity compiler == volume_series at every v1
  grain x week/month/quarter x (no filter, one customer) for both metrics, incl. ISO week 2026-W53 across
  the year end; two tenants zero leakage (facts, region via customer, CST); tenant_via dim_product path;
  Unassigned keeps totals + names beside ids; limit truncates rows but totals from SQL (row_count from
  SQL); calculated null rules (prior null on gap, pct null on previous 0, difference, per-week with
  partial bucket); CST week refused with the v1 handler's exact message; reported_soh == overview
  `load_stock_positions` (also with a site filter); CPOR measures == portfolio service by customer
  (superseded, intelligence_exclude, voided, zero-estimate excluded; ratio null at 0); scope and
  `statement_timeout=10s` bound inside the compiled transaction, timeout gone in the next one.
- `test_query_model_rules.py` (2, cip_test, VALUES only): SQL line rules and support USD equal
  `is_voided_line` / `_line_ttl_support_usd` on 11 edge rows; case rule equals the portfolio case filter.
- `test_query_v2_api.py` (5): anonymous 401 on all three v2 routes in session mode (and forged headers);
  each v2 route carries `get_current_user` itself; catalog shape; explain shows `%(period_from)s` not values;
  execute through the real app (scope source "this transaction", cache miss then hit, same total and
  buckets as v1 `/query/execute`).
- `test_query_v1_callers_n0115.py` (5): v1 `/query/explain`, `/semantics/validate`, `/saved-reports`
  create validation (400, v1 text, no write), `/reports/export` (xlsx), `report_delivery.deliver_saved_report`
  (value equals v1 engine; rolled back).

v1 callers and the test that proves each still works:
| Caller | Test |
|---|---|
| POST /query/execute | test_query_compose.py::test_query_execute_endpoint_returns_composed_ratio; test_query_v2_api.py::test_execute_runs_on_the_request_session |
| POST /query/explain | test_query_v1_callers_n0115.py::test_v1_query_explain_endpoint_unchanged; test_query_engine.py::test_explain_a3_no_db |
| report export (POST /reports/export) | test_query_v1_callers_n0115.py::test_v1_report_export_unchanged |
| saved report validate (create) | test_query_v1_callers_n0115.py::test_v1_saved_report_create_validates_with_v1_text |
| dashboard widget validate | test_dashboard_widgets.py::test_validate_widget_* (5) |
| report delivery | test_query_v1_callers_n0115.py::test_v1_report_delivery_unchanged; test_report_export.py schedule runner tests |
| semantics catalog / overlay | test_semantic_overlay_api.py (catalog GET, overlay GET/PUT, composed execute) |
| semantics validate | test_query_v1_callers_n0115.py::test_v1_semantics_validate_endpoint_unchanged; test_semantic_layer.py |

## 6. Parity (`apps/api/scripts/n0115_parity.py`, one READ ONLY transaction, rolled back)

Every v1 allowed grain + no grain, x week/month/quarter where period is a grain, x (no filter, customer
with most rows). Compiler run with no row limit so every row is compared; values rounded to 6 dp.

### cip_test (`--db cip_test`, user cip): 52 cases, 0 mismatches
cip_test holds 146 DSI rows and no CST rows (CST cases compare empty results). Full table:

| metric | grains | period | filter | old total | new total | rows old | rows new | rows compared | mismatches | v1 ms | compiler ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sellout_units | distributor,product | - | none | 310.0000 | 310.0000 | 2 | 2 | 2 | 0 | 5 | 6 |
| sellout_units | distributor,product | - | customer=20 | 74.0000 | 74.0000 | 1 | 1 | 1 | 0 | 3 | 4 |
| sellout_units | period | week | none | 310.0000 | 310.0000 | 11 | 11 | 11 | 0 | 4 | 4 |
| sellout_units | period | week | customer=20 | 74.0000 | 74.0000 | 9 | 9 | 9 | 0 | 3 | 5 |
| sellout_units | period | month | none | 310.0000 | 310.0000 | 9 | 9 | 9 | 0 | 2 | 3 |
| sellout_units | period | month | customer=20 | 74.0000 | 74.0000 | 7 | 7 | 7 | 0 | 2 | 3 |
| sellout_units | period | quarter | none | 310.0000 | 310.0000 | 4 | 4 | 4 | 0 | 2 | 3 |
| sellout_units | period | quarter | customer=20 | 74.0000 | 74.0000 | 4 | 4 | 4 | 0 | 2 | 3 |
| sellout_units | period,product | week | none | 310.0000 | 310.0000 | 13 | 13 | 13 | 0 | 4 | 6 |
| sellout_units | period,product | week | customer=20 | 74.0000 | 74.0000 | 9 | 9 | 9 | 0 | 4 | 5 |
| sellout_units | period,product | month | none | 310.0000 | 310.0000 | 11 | 11 | 11 | 0 | 2 | 3 |
| sellout_units | period,product | month | customer=20 | 74.0000 | 74.0000 | 7 | 7 | 7 | 0 | 2 | 3 |
| sellout_units | period,product | quarter | none | 310.0000 | 310.0000 | 5 | 5 | 5 | 0 | 2 | 3 |
| sellout_units | period,product | quarter | customer=20 | 74.0000 | 74.0000 | 4 | 4 | 4 | 0 | 2 | 3 |
| sellout_units | distributor,period | week | none | 310.0000 | 310.0000 | 13 | 13 | 13 | 0 | 4 | 4 |
| sellout_units | distributor,period | week | customer=20 | 74.0000 | 74.0000 | 9 | 9 | 9 | 0 | 4 | 5 |
| sellout_units | distributor,period | month | none | 310.0000 | 310.0000 | 11 | 11 | 11 | 0 | 3 | 3 |
| sellout_units | distributor,period | month | customer=20 | 74.0000 | 74.0000 | 7 | 7 | 7 | 0 | 2 | 3 |
| sellout_units | distributor,period | quarter | none | 310.0000 | 310.0000 | 5 | 5 | 5 | 0 | 2 | 3 |
| sellout_units | distributor,period | quarter | customer=20 | 74.0000 | 74.0000 | 4 | 4 | 4 | 0 | 2 | 3 |
| sellout_units | distributor,period,product | week | none | 310.0000 | 310.0000 | 13 | 13 | 13 | 0 | 3 | 4 |
| sellout_units | distributor,period,product | week | customer=20 | 74.0000 | 74.0000 | 9 | 9 | 9 | 0 | 3 | 4 |
| sellout_units | distributor,period,product | month | none | 310.0000 | 310.0000 | 11 | 11 | 11 | 0 | 2 | 4 |
| sellout_units | distributor,period,product | month | customer=20 | 74.0000 | 74.0000 | 7 | 7 | 7 | 0 | 2 | 3 |
| sellout_units | distributor,period,product | quarter | none | 310.0000 | 310.0000 | 5 | 5 | 5 | 0 | 2 | 3 |
| sellout_units | distributor,period,product | quarter | customer=20 | 74.0000 | 74.0000 | 4 | 4 | 4 | 0 | 2 | 4 |
| sellout_units | customer | - | none | 310.0000 | 310.0000 | 119 | 119 | 119 | 0 | 3 | 4 |
| sellout_units | customer | - | customer=20 | 74.0000 | 74.0000 | 1 | 1 | 1 | 0 | 3 | 4 |
| sellout_units | customer,period | week | none | 310.0000 | 310.0000 | 127 | 127 | 127 | 0 | 5 | 5 |
| sellout_units | customer,period | week | customer=20 | 74.0000 | 74.0000 | 9 | 9 | 9 | 0 | 3 | 4 |
| sellout_units | customer,period | month | none | 310.0000 | 310.0000 | 125 | 125 | 125 | 0 | 3 | 3 |
| sellout_units | customer,period | month | customer=20 | 74.0000 | 74.0000 | 7 | 7 | 7 | 0 | 2 | 3 |
| sellout_units | customer,period | quarter | none | 310.0000 | 310.0000 | 122 | 122 | 122 | 0 | 7 | 4 |
| sellout_units | customer,period | quarter | customer=20 | 74.0000 | 74.0000 | 4 | 4 | 4 | 0 | 2 | 3 |
| sellout_units | product | - | none | 310.0000 | 310.0000 | 2 | 2 | 2 | 0 | 3 | 4 |
| sellout_units | product | - | customer=20 | 74.0000 | 74.0000 | 1 | 1 | 1 | 0 | 3 | 5 |
| sellout_units | - | - | none | 310.0000 | 310.0000 | 1 | 1 | 1 | 0 | 3 | 4 |
| sellout_units | - | - | customer=20 | 74.0000 | 74.0000 | 1 | 1 | 1 | 0 | 3 | 4 |
| cst_sellthrough_units | customer | - | none | 0.0000 | 0.0000 | 0 | 0 | 0 | 0 | 3 | 5 |
| cst_sellthrough_units | product | - | none | 0.0000 | 0.0000 | 0 | 0 | 0 | 0 | 3 | 4 |
| cst_sellthrough_units | customer,product | - | none | 0.0000 | 0.0000 | 0 | 0 | 0 | 0 | 2 | 4 |
| cst_sellthrough_units | customer,product,site_label | - | none | 0.0000 | 0.0000 | 0 | 0 | 0 | 0 | 3 | 4 |
| cst_sellthrough_units | period | week | none | 0.0000 | 0.0000 | 0 | 0 | 0 | 0 | 5 | 6 |
| cst_sellthrough_units | period | month | none | 0.0000 | 0.0000 | 0 | 0 | 0 | 0 | 3 | 4 |
| cst_sellthrough_units | period | quarter | none | 0.0000 | 0.0000 | 0 | 0 | 0 | 0 | 4 | 4 |
| cst_sellthrough_units | customer,period | week | none | 0.0000 | 0.0000 | 0 | 0 | 0 | 0 | 7 | 6 |
| cst_sellthrough_units | customer,period | month | none | 0.0000 | 0.0000 | 0 | 0 | 0 | 0 | 3 | 5 |
| cst_sellthrough_units | customer,period | quarter | none | 0.0000 | 0.0000 | 0 | 0 | 0 | 0 | 4 | 5 |
| cst_sellthrough_units | period,product | week | none | 0.0000 | 0.0000 | 0 | 0 | 0 | 0 | 4 | 5 |
| cst_sellthrough_units | period,product | month | none | 0.0000 | 0.0000 | 0 | 0 | 0 | 0 | 3 | 4 |
| cst_sellthrough_units | period,product | quarter | none | 0.0000 | 0.0000 | 0 | 0 | 0 | 0 | 3 | 4 |
| cst_sellthrough_units | - | - | none | 0.0000 | 0.0000 | 1 | 1 | 1 | 0 | 2 | 3 |

| widget-shaped v2 query, cip_test (run_v2, cache off) | rows | ms |
|---|---|---|
| DSI units by month, 2025-11..2026-10 | 1 | 60 |
| DSI top 10 dealers, units + lines, 2026 | 1 | 23 |
| DSI units + % change by week, 2026 | 2 | 11 |
| DSI units by month x region x bu | 1 | 25 |
| CST units by customer x product (top 500) | 0 | 6 |
| CST stock beside units/week by customer, last 8 weeks | 0 | 12 |
| CST units by month x store | 0 | 7 |
| CPOR support USD + delivery rate by status x promo type | 0 | 33 |

### Clone (`--db cip_n0115 --owner`, user postgres, read only): 66 cases, 0 mismatches
The app user has no grants on the clone, so this ran as the owner, which BYPASSES row security.

| metric | grains | period | filter | old total | new total | rows old | rows new | rows compared | mismatches | v1 ms | compiler ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sellout_units | distributor,product | - | none | 400,991.8500 | 400,991.8500 | 1678 | 1678 | 1678 | 0 | 37 | 61 |
| sellout_units | distributor,product | - | customer=18 | 10,133.0000 | 10,133.0000 | 249 | 249 | 249 | 0 | 10 | 13 |
| sellout_units | period | week | none | 400,991.8500 | 400,991.8500 | 144 | 144 | 144 | 0 | 53 | 57 |
| sellout_units | period | week | customer=18 | 10,133.0000 | 10,133.0000 | 115 | 115 | 115 | 0 | 9 | 12 |
| sellout_units | period | month | none | 400,991.8500 | 400,991.8500 | 34 | 34 | 34 | 0 | 41 | 67 |
| sellout_units | period | month | customer=18 | 10,133.0000 | 10,133.0000 | 33 | 33 | 33 | 0 | 8 | 13 |
| sellout_units | period | quarter | none | 400,991.8500 | 400,991.8500 | 12 | 12 | 12 | 0 | 60 | 80 |
| sellout_units | period | quarter | customer=18 | 10,133.0000 | 10,133.0000 | 12 | 12 | 12 | 0 | 8 | 18 |
| sellout_units | period,product | week | none | 400,991.8500 | 400,991.8500 | 13525 | 13525 | 13525 | 0 | 267 | 110 |
| sellout_units | period,product | week | customer=18 | 10,133.0000 | 10,133.0000 | 1580 | 1580 | 1580 | 0 | 26 | 19 |
| sellout_units | period,product | month | none | 400,991.8500 | 400,991.8500 | 6135 | 6135 | 6135 | 0 | 105 | 73 |
| sellout_units | period,product | month | customer=18 | 10,133.0000 | 10,133.0000 | 845 | 845 | 845 | 0 | 95 | 14 |
| sellout_units | period,product | quarter | none | 400,991.8500 | 400,991.8500 | 3218 | 3218 | 3218 | 0 | 93 | 80 |
| sellout_units | period,product | quarter | customer=18 | 10,133.0000 | 10,133.0000 | 470 | 470 | 470 | 0 | 14 | 15 |
| sellout_units | distributor,period | week | none | 400,991.8500 | 400,991.8500 | 505 | 505 | 505 | 0 | 58 | 76 |
| sellout_units | distributor,period | week | customer=18 | 10,133.0000 | 10,133.0000 | 174 | 174 | 174 | 0 | 11 | 13 |
| sellout_units | distributor,period | month | none | 400,991.8500 | 400,991.8500 | 136 | 136 | 136 | 0 | 49 | 66 |
| sellout_units | distributor,period | month | customer=18 | 10,133.0000 | 10,133.0000 | 62 | 62 | 62 | 0 | 9 | 12 |
| sellout_units | distributor,period | quarter | none | 400,991.8500 | 400,991.8500 | 51 | 51 | 51 | 0 | 49 | 70 |
| sellout_units | distributor,period | quarter | customer=18 | 10,133.0000 | 10,133.0000 | 25 | 25 | 25 | 0 | 9 | 13 |
| sellout_units | distributor,period,product | week | none | 400,991.8500 | 400,991.8500 | 16241 | 16241 | 16241 | 0 | 230 | 236 |
| sellout_units | distributor,period,product | week | customer=18 | 10,133.0000 | 10,133.0000 | 1593 | 1593 | 1593 | 0 | 33 | 20 |
| sellout_units | distributor,period,product | month | none | 400,991.8500 | 400,991.8500 | 7737 | 7737 | 7737 | 0 | 168 | 118 |
| sellout_units | distributor,period,product | month | customer=18 | 10,133.0000 | 10,133.0000 | 872 | 872 | 872 | 0 | 24 | 18 |
| sellout_units | distributor,period,product | quarter | none | 400,991.8500 | 400,991.8500 | 4176 | 4176 | 4176 | 0 | 122 | 91 |
| sellout_units | distributor,period,product | quarter | customer=18 | 10,133.0000 | 10,133.0000 | 500 | 500 | 500 | 0 | 14 | 13 |
| sellout_units | customer | - | none | 400,991.8500 | 400,991.8500 | 4822 | 4822 | 4822 | 0 | 129 | 67 |
| sellout_units | customer | - | customer=18 | 10,133.0000 | 10,133.0000 | 1 | 1 | 1 | 0 | 7 | 11 |
| sellout_units | customer,period | week | none | 400,991.8500 | 400,991.8500 | 25488 | 25488 | 25488 | 0 | 392 | 637 |
| sellout_units | customer,period | week | customer=18 | 10,133.0000 | 10,133.0000 | 115 | 115 | 115 | 0 | 16 | 18 |
| sellout_units | customer,period | month | none | 400,991.8500 | 400,991.8500 | 17720 | 17720 | 17720 | 0 | 395 | 179 |
| sellout_units | customer,period | month | customer=18 | 10,133.0000 | 10,133.0000 | 33 | 33 | 33 | 0 | 12 | 15 |
| sellout_units | customer,period | quarter | none | 400,991.8500 | 400,991.8500 | 12006 | 12006 | 12006 | 0 | 347 | 151 |
| sellout_units | customer,period | quarter | customer=18 | 10,133.0000 | 10,133.0000 | 12 | 12 | 12 | 0 | 13 | 15 |
| sellout_units | product | - | none | 400,991.8500 | 400,991.8500 | 1130 | 1130 | 1130 | 0 | 44 | 79 |
| sellout_units | product | - | customer=18 | 10,133.0000 | 10,133.0000 | 218 | 218 | 218 | 0 | 12 | 18 |
| sellout_units | - | - | none | 400,991.8500 | 400,991.8500 | 1 | 1 | 1 | 0 | 29 | 57 |
| sellout_units | - | - | customer=18 | 10,133.0000 | 10,133.0000 | 1 | 1 | 1 | 0 | 7 | 14 |
| cst_sellthrough_units | customer | - | none | 19,361.0000 | 19,361.0000 | 8 | 8 | 8 | 0 | 18 | 35 |
| cst_sellthrough_units | customer | - | customer=299 | 7,382.0000 | 7,382.0000 | 1 | 1 | 1 | 0 | 18 | 31 |
| cst_sellthrough_units | product | - | none | 19,361.0000 | 19,361.0000 | 333 | 333 | 333 | 0 | 20 | 31 |
| cst_sellthrough_units | product | - | customer=299 | 7,382.0000 | 7,382.0000 | 119 | 119 | 119 | 0 | 17 | 26 |
| cst_sellthrough_units | customer,product | - | none | 19,361.0000 | 19,361.0000 | 533 | 533 | 533 | 0 | 20 | 35 |
| cst_sellthrough_units | customer,product | - | customer=299 | 7,382.0000 | 7,382.0000 | 119 | 119 | 119 | 0 | 18 | 32 |
| cst_sellthrough_units | customer,product,site_label | - | none | 19,361.0000 | 19,361.0000 | 1392 | 1392 | 1392 | 0 | 37 | 42 |
| cst_sellthrough_units | customer,product,site_label | - | customer=299 | 7,382.0000 | 7,382.0000 | 119 | 119 | 119 | 0 | 18 | 35 |
| cst_sellthrough_units | period | week | none | 19,361.0000 | 19,361.0000 | 95 | 95 | 95 | 0 | 41 | 55 |
| cst_sellthrough_units | period | week | customer=299 | 7,382.0000 | 7,382.0000 | 88 | 88 | 88 | 0 | 40 | 52 |
| cst_sellthrough_units | period | month | none | 19,361.0000 | 19,361.0000 | 24 | 24 | 24 | 0 | 43 | 53 |
| cst_sellthrough_units | period | month | customer=299 | 7,382.0000 | 7,382.0000 | 21 | 21 | 21 | 0 | 35 | 47 |
| cst_sellthrough_units | period | quarter | none | 19,361.0000 | 19,361.0000 | 10 | 10 | 10 | 0 | 41 | 49 |
| cst_sellthrough_units | period | quarter | customer=299 | 7,382.0000 | 7,382.0000 | 8 | 8 | 8 | 0 | 36 | 45 |
| cst_sellthrough_units | customer,period | week | none | 19,361.0000 | 19,361.0000 | 144 | 144 | 144 | 0 | 43 | 54 |
| cst_sellthrough_units | customer,period | week | customer=299 | 7,382.0000 | 7,382.0000 | 88 | 88 | 88 | 0 | 41 | 52 |
| cst_sellthrough_units | customer,period | month | none | 19,361.0000 | 19,361.0000 | 54 | 54 | 54 | 0 | 41 | 51 |
| cst_sellthrough_units | customer,period | month | customer=299 | 7,382.0000 | 7,382.0000 | 21 | 21 | 21 | 0 | 36 | 43 |
| cst_sellthrough_units | customer,period | quarter | none | 19,361.0000 | 19,361.0000 | 35 | 35 | 35 | 0 | 38 | 47 |
| cst_sellthrough_units | customer,period | quarter | customer=299 | 7,382.0000 | 7,382.0000 | 8 | 8 | 8 | 0 | 32 | 41 |
| cst_sellthrough_units | period,product | week | none | 19,361.0000 | 19,361.0000 | 2757 | 2757 | 2757 | 0 | 75 | 60 |
| cst_sellthrough_units | period,product | week | customer=299 | 7,382.0000 | 7,382.0000 | 1932 | 1932 | 1932 | 0 | 43 | 39 |
| cst_sellthrough_units | period,product | month | none | 19,361.0000 | 19,361.0000 | 1271 | 1271 | 1271 | 0 | 51 | 55 |
| cst_sellthrough_units | period,product | month | customer=299 | 7,382.0000 | 7,382.0000 | 622 | 622 | 622 | 0 | 42 | 48 |
| cst_sellthrough_units | period,product | quarter | none | 19,361.0000 | 19,361.0000 | 868 | 868 | 868 | 0 | 50 | 56 |
| cst_sellthrough_units | period,product | quarter | customer=299 | 7,382.0000 | 7,382.0000 | 314 | 314 | 314 | 0 | 40 | 48 |
| cst_sellthrough_units | - | - | none | 19,361.0000 | 19,361.0000 | 1 | 1 | 1 | 0 | 14 | 26 |
| cst_sellthrough_units | - | - | customer=299 | 7,382.0000 | 7,382.0000 | 1 | 1 | 1 | 0 | 14 | 26 |

### Timings: 8 widget-shaped v2 queries on the clone (owner, cache off, end to end incl. totals, names)

| widget-shaped v2 query | rows | ms |
|---|---|---|
| DSI units by month, 2025-11..2026-10 | 12 | 182 |
| DSI top 10 dealers, units + lines, 2026 | 10 | 130 |
| DSI units + % change by week, 2026 | 41 | 63 |
| DSI units by month x region x bu | 133 | 292 |
| CST units by customer x product (top 500) | 500 | 83 |
| CST stock beside units/week by customer, last 8 weeks | 8 | 65 |
| CST units by month x store | 500 | 89 |
| CPOR support USD + delivery rate by status x promo type | 13 | 118 |

All under 300 ms as owner. Scoped (row security on, non-owner) timings: UNVERIFIED (the app user has no
grants on the clone; cip_test is too small to be indicative).

## 7. Findings

- F1 (spec correction): the spec said CPOR "voided status excluded". The portfolio service excludes voided
  LINES (remark markers) and zero-estimate lines; it never filters `cpor_case.status`. Built as the service does.
- F2: `cpor_case_line` has no `tenant_id`; tenant comes from the inner join to `cpor_case` (third
  structural tenant path). `cpor_case_line` also carries its own `window_start` (N-0050 line windows);
  the model dates CPOR by the CASE window start as section 10 says. A line-window dating would differ.
- F3: the YAML key `on:` parses as boolean True in PyYAML; the file uses `via:` for "column on a base join".
- F4: v1 CST groups `site_label` raw; v2 shows NULL as "Unassigned" (filter value "Unassigned" matches
  NULL). Row counts and totals identical (parity proven). Attribute strings are not trimmed (portfolio
  trims promotion_type; whitespace variants would split into separate rows in v2).
- F5: `reported_soh` latest date is computed under row security on the same session: a scoped user whose
  lines are absent from a customer's latest report sees an older "latest" date for that customer. Same
  behaviour the overview would have on a scoped session; worth a decision if it matters.
- F6: sort by an entity breakdown sorts by id, not by name (names are attached after SQL).
- F7: period buckets use `date_trunc` exactly as v1 (Gregorian, Monday weeks); non-Gregorian tenant
  calendars are not honoured by v1 or v2 yet.
- F8: the first bucket is partial when `period.from` falls mid-bucket; its prior bucket is whole (noted in explain).
- F9: governed measures in v2 delegate to the v1 engine; `a2_cpor` still opens a sync `SessionLocal()`
  inside the async handler (challenge 2): unchanged, v1 behaviour.
- F10: prior_period / pct_change / difference over a prior have no total (null) by design.

## 8. Decisions needed (proposed, not picked)

1. Day grain (spec decision 1): still refused in v2 with the v1 text.
2. DSI sales value (decision 2) and 3. CST sales value / VAT conversion (decision 3): not built; also
   whether the CST VAT conversion should become a shared function the overview and the compiler both call.
4. CPOR "open" status set and CPOR "value" definition.
5. Customer stock cover / restock flags in the builder: reuse the overview's Python (governed handler) or
   leave as reported stock beside units per week.
6. Whether `reported_soh`'s latest report date should be computed scope-blind (F5).
7. CPOR period date: case window start (built) vs line window start (F2).

## 9. Deferred findings for the programme

- GOV-008 independent verification of this node (different run).
- Scoped (non-owner) timing of the 8 widget queries on a clone with app-role grants.
