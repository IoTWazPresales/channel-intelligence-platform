# N-0115 challenge panel: simplicity, cost/scale, security

Reviewed: `docs/DATA_MODEL_SPEC.md` against `N0115_PANEL_BRIEF.md`, `N0115_DISCOVERY.md` and `seats/data-architect.md`.
Timings come from the read-only clone `cip_n0115`, logged in as the owner, which **bypasses row security**. Real scoped timings are UNVERIFIED.

## 1. Simplicity: what to cut for one engineer tonight

| Item | Verdict | Fix |
|---|---|---|
| Fact models | CHANGE | Build only **dsi_sellout, cst_sellthrough, cpor (lines + case grain)** tonight. Those cover parity and all three starter dashboards. Defer shipments (mixed currency), distributor_stock (A3 handler already serves it), returns and lineup_plan (no `tenant_id`, which needs a second tenant pattern) and recorded_prices. recorded_prices is not buildable as written: FACT, `listing_observation` has no `product_id`, no `tenant_id` and no `observed_date` (it has `listing_id` and `fetched_at`), and no row security. |
| Derived breakdowns + walls | KEEP | Simplify W-CUSTOMER-ROLE by allowing **one model per v2 query** (widgets with two measures send two queries). The role wall then holds by construction instead of being checked at run time. Keep every refuse_example verbatim. |
| One compiler | KEEP | It is the core. |
| Calculated measures | CHANGE | Tonight: ratio, difference, prior_period/pct_change (for trend), per_week_rate (for stock cover). Defer prior_year (second shifted query plus week-53 alignment), running_total and share_of_total (GROUPING SETS). |
| Catalog v2 | KEEP, minimal | Measures, breakdowns, derived allowed list and walls. Fold `/semantics/v2/validate` into `/query/v2/explain`, so there is one endpoint fewer. |
| v1 switch (`serve_v1_from`) | CUT | Unit C calls v2, so routing v1 to the compiler gives no user value and adds the parity trap in section 4. Keep parity as a test/script that compares the two; v1 stays on the handler. |
| Spec-key breakdowns | CHANGE (defer to last) | Build only after the rest passes, and only with pre-aggregation (section 2). |
| Day grain | CUT tonight | It waits on proposed decision 1. Today's refusal stays. |
| Per-tenant model overlay | CHANGE | Ship `default.yaml` only. Tenant overlay = labels, hide/show and composed ratios over existing measures. **Never** a tenant-supplied table, column or expression (see section 3). |

Defer order, first deferred first: day grain > recorded_prices > prior_year > spec keys > share_of_total/running_total > returns/lineup > shipments > distributor_stock.

Two gaps in the spec block the starter dashboards:
- **No CPOR `status` breakdown.** FACT: `cpor_case` has both `status` and `workflow_status`. The spec has no "open" definition and no "value" definition. Fix: reuse the portfolio service's open/void rules, and record which status column and which value (support USD, support ZAR or estimate) as a proposed decision.
- **"Stock cover per customer" and "restock flags" are not defined.** `weeks_of_cover` is locked to distributor x product (W-A3-GRAIN-LOCK), and the spec has no restock measure. Fix: if the sell-through overview already computes customer cover or restock in code, reuse it exactly. Otherwise each becomes a proposed decision, and the widget shows reported SOH and per-week sell-through side by side without a derived cover figure.

## 2. Cost and scale

Measured on the clone (owner, no row security):

| Query | Result |
|---|---|
| Sell-out units + value by month x customer, joins to dim_product and dim_customer, top 500 | 165 ms to execute, 206 ms cold planning, 416 ms round trip |
| Same query with the scope predicate emulated (`set_config` + `cip_product_line_visible` subplan) | 47 ms to execute |
| Spec-key discovery: distinct keys under `specs_json.import_staging`, 18,157 products, 58 MB of JSON | **1.86 s, 181 keys** |
| Spec-key breakdown (one key) over all 58k sell-out rows | **1.03 s** (JSON unpacked once per fact row) |
| fact_customer_sellthrough row count | 14,898 |

Findings:
- **Under 2 s is realistic** for base measures at today's volumes. Even at 200k rows a plain grouped sum should stay well under 1 s.
- **The spec-key breakdown will not stay under 2 s.** It grows linearly, to about 3.5 s at 200k rows. Fix: aggregate the fact table by `product_id` first, then join the distinct products to read the spec value. That unpacks about 700 JSON documents instead of 58k.
- **The "full scan > 120 s" did not reproduce for key discovery** (1.86 s here); that figure probably came from a different query shape. Still, never run discovery per request. Cache it per tenant, tied to the catalog version, invalidate it on product import, and build it lazily.
- **12-widget dashboards:**
  - a2_cpor runs a **sync** `SessionLocal()` inside an async handler (`handlers/a2_cpor.py:63`). That blocks the event loop for every other widget on the same worker. Fix: the new CPOR model goes through the async compiler. Leave the a2 handler alone for v1, or run it in `asyncio.to_thread`, which copies contextvars, so the scope survives.
  - The cache is process-local with a 60 s TTL (`cache.py:15`), and Redis is optional, so each worker warms its own cache. That is acceptable.
- **Timeout and limits:** KEEP `SET LOCAL statement_timeout = 10s`, 500 default rows and 5,000 max. Totals must come from SQL, not from summing truncated rows (5,617 customers exist). A limit above the max should be refused, not silently clamped.
- **Re-time every query as a non-owner role with scope bound** before claiming the 2 s target. The emulation above is indicative only.

## 3. Security

**Tenant isolation is the compiler's job alone. CHANGE: make it structural.**
FACT: row security is product-line only. Every policy tests `product_id`/`cip_product_line_visible`, and none tests tenant. `cpor_case`, `dim_customer` and `listing_observation` have no row security at all. `fact_returns`, `fact_lineup_plan_item` and `listing_observation` have no `tenant_id`.

Fix:
- One FROM-builder adds `base.tenant_id = :tid` to every model. A model without `tenant_id` must declare `tenant_via: dim_product`, compiled as an `INNER JOIN dim_product p ON p.id = f.product_id AND p.tenant_id = :tid`. Rows with a null product are then excluded, and explain reports how many.
- The loader refuses a model with neither path.
- Add one test per model that seeds two tenants and asserts zero leakage.

**cpor_case is not scoped by product line. CHANGE.**
Case-grain measures (cases open, by status) read from `cpor_case` alone bypass D-0056. FACT: `cpor_case_line` has forced row security, but its policy passes `product_id IS NULL`.
Fix: compile case-grain measures as `EXISTS (visible line with product_id NOT NULL)`, or record as a proposed decision that line-less cases are visible to every scope. Adding row security to `cpor_case` is a schema change, so it is a decision, not tonight's work.

**Injection. KEEP the design, add these rules:**
- Measure, breakdown and sort ids resolve only by dictionary lookup in the loaded model, to SQLAlchemy column objects. Sort is an enum (`<measure|breakdown> asc|desc`).
- A spec key must be in the tenant's cached discovered list. It is passed as a bound argument to `jsonb_extract_path_text(col, 'import_staging', :k)` with a **fixed alias** (`spec_value`), and is never used as a SQL label.
- Filter lists use expanding bindparams, ids are coerced to int, lists are capped at about 1,000, and dates are parsed server-side.
- Overlay YAML can never carry expressions.

**Product-line scope on every compiled query: holds, as long as the compiler stays on ORM sessions.**
FACT: an `after_begin` listener on the base `Session` binds scope for sync and async sessions alike (`core/product_line_scope.py:128-169`), from contextvars set by the router-level dependency (`api/v1/router.py:49-54`).
Risk: a raw `engine.connect()` or a worker thread without copied context runs open. Fix: the compiler uses only the request `AsyncSession`, and a test asserts that the scope settings are set inside the compiled transaction.

**Cache key: VERIFIED.** `cache.py:62-63` includes `product_lines` and `role`. Fixes:
- v2 needs its own key builder that hashes the whole canonical request (measures, breakdowns, calcs, sort, limit, spec key).
- Unscoped runs (schedules) key as `None`, so they can only collide with other unscoped runs. That is correct.
- UNVERIFIED: whether scheduled reports should run under the recipient's scope.

**Explain:** KEEP "parameter names, no values". Also:
- Data vintage (max date) must be computed in the same scoped session.
- Explain must not reveal row counts for walls or rows outside the caller's scope.

**Auth. CHANGE.**
FACT: `/query/execute` uses `get_optional_current_user`, and `tenant_id_from_user(None)` returns `DEFAULT_TENANT_ID` (`core/tenant_scope.py:27-28`). It is protected only because `api_router` carries a router-level `get_current_user` (`router.py:22`).
Fix: v2 endpoints go on `api_router` (never `public_router`) and depend on `get_current_user` explicitly, not the optional one. Add a test that an anonymous call returns 401.

## 4. Parity and invented-figure risks

1. **The v1 switch combined with the 500-row limit** would truncate `sellout_units` by customer and change `rows`. Cutting the switch removes this.
2. **Attribute joins:** an INNER JOIN to dim_product or dim_customer for `bu`/region drops null-key rows and changes totals. Use a LEFT JOIN plus an "Unassigned" bucket, except for the tenant-via-product path.
3. **CPOR v2 measures are dated by `window_start`.** a2 `support_spend` is all-time (it refuses any period). Give the v2 measure a different label ("Support (window start in period)"); never present it as the same figure.
4. **distributor_stock by period vs `channel_stock`:** two different "stock" numbers. Name them differently.
5. **Customer stock cover, restock flags and the CPOR value/open definitions are new figures** (see section 1). They are proposed decisions and must not be invented.
6. **Period bucketing** must call the same calendar function as `volume_series.py` / `calendar_grain.py`. Parity tests must cover week 53.
7. **CST value:** call the overview's VAT conversion function itself; do not re-implement it.
8. **Region/channel use current assignment.** Label them "current", as the spec already says.
