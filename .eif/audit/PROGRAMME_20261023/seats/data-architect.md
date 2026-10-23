# N-0115 seat: data-architect (first-round run, report delivered in the agent's final message)

Recorded by the orchestrator from the seat's final message, 2026-10-23 06:05. The seat ran read-only on
`cip_n0115` as owner (row security bypassed). The `data-architect` skill load was refused by the guard
(SHIM_TOOL_UNMAPPED); the lens was applied without it.

## Findings (FACT from code or the clone)
- F1 (security): the query cache key had no product-line scope or role (`query/cache.py:51-58`,
  `engine.py:98-105`); an unscoped schedule run or an admin could cache a result a scoped user then reads
  (process and Redis). Orchestrator verified and fixed it in N-0115 (scope and role in the key, key v2).
- F2: the CST/DSI customer wall is a role wall, not a table wall: 7 of 8 CST customers are the same
  dim_customer rows DSI uses.
- F3: dim_customer.preferred_distributor_id would open CST x distributor if allowed breakdowns were
  inferred from foreign keys (refused today). Joins must be declared, never inferred.
- F4: fact_sales_sellout.channel_id is NULL on all 58,128 rows; DSI channel comes only via
  dim_customer.channel_id; dim_customer.region_id is NULL on 21,610 DSI rows (37%).
- F5: DSI currency_code NULL on every row; revenue = 0 on 22,664 rows (0 means not reported);
  unit_sellout_price_ex_tax_amount NULL on 22,546.
- F6: CST mixes 11,710 daily rows (all customer 299) and 3,188 weekly; 96 rows inc VAT; some weekly rows
  start on a Tuesday.
- F7: specs_json has one top-level key `import_staging` with 178 distinct keys on sold products;
  multi-line text values; a key scan over all products ran past 120 s (1.4 s over sold products only).
- F8: fact_inventory_distributor: 91 snapshot dates over 2,481 pairs; calculated_soh filled on 545 of
  47,411 rows.
- F9: DSI by month x spec.os x region with product+customer joins: 966 ms as owner (RLS cost unmeasured).
- F10: the default business calendar is Gregorian, January start, Monday weeks
  (`services/business_calendar.py:28-35`), so it gives today's date_trunc buckets; keep `bucket_key`
  formats (`2026-W05`, `2026-03`, `2026-Q1`) and add `bucket_label`.

## Proposal (format rules)
1. Joins declared, never inferred; many-to-one only, with a key-uniqueness test.
2. A model joins `customer` under a role (dsi_dealer, cst_retailer, cpor_account); the public breakdown
   id stays `customer`; walls compare roles.
3. Allowed breakdowns derived: period (if the model has a time column) + each join + joined dimension
   attributes and declared sub-dimensions + local breakdowns, minus walls; any subset up to 3 allowed
   unless it contains a wall trigger. The catalog API returns the rule (breakdowns, walls, period floor),
   not an enumeration. Governed handlers keep an explicit `serves:` list (today's allowed_grains).
4. Each measure declares additivity (additive, semi-additive latest-per-key over time, non-additive).
   Totals for non-additive measures via GROUPING SETS, never by adding rows; averages are weighted ratios.

## YAML sketch (catalog v3: default.yaml keeps `metrics:` and adds `dimensions`, `models`, `walls`, `calculated`)
- dimensions: product (dim_product; attributes bu=product_line, business_unit, category, series_name,
  form_factor, price_band, sales_model_name, lifecycle_status; json attributes spec from
  specs_json.import_staging, discovered keys, first line trimmed), customer (dim_customer; key_account,
  partner_tier; joins region, channel with nulls -> 'Unassigned'; preferred_distributor deliberately
  absent), distributor, region, channel, period (tenant calendar; day..year).
- dsi_sellout: fact_sales_sellout, tenant_id, time transaction_date (floor day); joins product, customer
  role dsi_dealer, distributor (nulls exclude, parity with volume_series.py:138); measures units
  (legacy sellout_units), priced_units, value_ex_tax = units x unit_sellout_price_ex_tax_amount where
  price not null (currency 'not recorded', coverage priced_units; never SUM(revenue)), lines, dealers
  (distinct), avg/min price ex tax.
- cst_sellthrough: fact_customer_sellthrough; time period_start_date with floor from stored period_type;
  joins product, customer role cst_retailer; local breakdown site_label 'Store / site'; measures units
  (legacy cst_sellthrough_units), priced_units, value (units_sold x unit_sell_price, per-row vat_basis
  converted to the tenant sales-value VAT basis as sell_through_overview.py:244-258 does; no listing
  estimate), reported_soh (semi-additive, latest per customer, site, product), stores_reporting.
- distributor_stock: fact_inventory_distributor; time as_of_date snapshot; measures reported_soh_units
  (semi-additive latest per distributor x product, no carry-forward), calculated_soh_units,
  pairs_reporting. Latest-per-key SQL: inner DISTINCT ON (bucket, key) ORDER BY as_of_date DESC, outer SUM.
- Others same shape: shipments (quantity; amount summed only within one currency_code; time role pod_date
  or ship_confirm_date), returns, lineup_plan, cpor_lines (support_usd compute, support_zar display, never
  converted), recorded_prices (listing_observation: min, max, latest only).
- calculated: pct_change, prior_year (BusinessCalendar.same_day_last_year), per_week_rate (bucket days / 7,
  refused without a period); allowed breakdowns = intersection of inputs with the same roles; tenant
  composed ratio/alias translate one to one.

## Walls (declared once; exact refuse_example text wins, then the wall reason; order as registry.py:550-583)
W-SITE-CST-ONLY, W-CUSTOMER-ROLE, W-CST-NO-DISTRIBUTOR, W-SNAPSHOT-NOT-SUMMED, W-LINEUP-QUARTER,
W-PVE-GRAIN, W-A3-GRAIN-LOCK. Mapping: fill_rate {lineup_quarter} -> LINEUP-QUARTER; fill_rate
{distributor, product} -> PVE-GRAIN; pipeline_inbound {distributor, product} -> PVE-GRAIN; channel_stock
{period} -> SNAPSHOT-NOT-SUMMED; channel_stock {lineup_quarter} -> LINEUP-QUARTER; channel_stock
{customer, product} -> A3-GRAIN-LOCK; weeks_of_cover {period, bu} -> A3-GRAIN-LOCK; weeks_of_cover
{customer, product, site_label} -> SITE-CST-ONLY + CUSTOMER-ROLE; sellout_units {site_label} ->
SITE-CST-ONLY; sellout_units {customer, product, site_label} -> CUSTOMER-ROLE; cst_sellthrough_units
{distributor, product} -> CST-NO-DISTRIBUTOR. Also: one query is one measure (registry.py:473-483); no
period finer than stored; claim_rate / cost_per_incremental_unit refuse_all and support_bias spec_only kept.

## Per-tenant configuration
Extend the tenant profile `semantic_overlay` (services/commercial_tenant_profile.py:610-620), no new
table (BACKLOG-096 said no new table; the overlay already folds into the catalog version in the cache
key). A tenant may rename or hide measures and breakdowns, choose exposed spec keys, add calculated
measures, add walls, set the default period grain; may not add models, change table/column/aggregation
or remove a wall. Deferred risk: the profile is a file per API instance and the catalog is cached per
process.

## Metric mapping
Model measures (parity tested): sellout_units -> dsi_sellout.units; cst_sellthrough_units ->
cst_sellthrough.units; tenant composed -> calculated. Old keys stay as aliases with the same response
shape. Governed handlers kept: all A1 plan-vs-executed; A2 support_spend, delivery_rate,
support_cost_per_unit_sold (new cpor_lines measures beside them under their own ids); A3 channel_stock,
weeks_of_cover, replenishment_flag (observation tape; reported stock is a different, differently labelled
number); refused, spec_only and not_implemented entries.

## Risks
Cache leak (fixed); FK inference reopening walls; one-to-many double counting; channel/region/BU are
current values (label 'current'); 37% DSI rows with no region -> 'Unassigned'; spec keys must be bound
parameters checked against a cached discovered list; stock with no carry-forward under-reports gaps
(show pairs_reporting); non-Gregorian tenants get different buckets; fact_returns and
fact_lineup_plan_item have no tenant_id (tenant via product); cpor_case has no row security; scheduled
delivery runs unscoped; under 2 s not measured under a scoped role.

## Decisions for the operator (proposed)
- Day grain: the mandate asks for it; today it is refused on purpose (registry.py:638-639). Allow, or keep
  week as the lowest?
- May reported distributor stock be broken down by period (latest snapshot per bucket)? It would sit beside
  the Channel Ops wall that refuses stock by period.
- Carry stock forward into a period with no snapshot? Seat default: no.
