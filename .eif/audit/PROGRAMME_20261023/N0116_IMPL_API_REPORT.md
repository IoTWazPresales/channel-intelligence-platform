# N-0116 implementation report, API half

Date: 2026-10-23. Moment (c), implementation of defined work. Lenses: full-stack-product-engineer,
test-engineering-specialist, database-specialist (own knowledge, no skills loaded). Spec:
`.eif/audit/PROGRAMME_20261023/N0116_SPEC_PROPOSAL.md`. Decisions built as proposed: D1 (one
`definition_v2` JSONB), D4 (starter B "Sell-through & stock across customers"), D5 (business unit = `bu`),
D6 (previous year = calendar shift, client side; nothing server side). `cip` was never connected to.
Nothing committed, pushed or restarted.

## 1. Files

New:
- `apps/api/alembic/versions/20261023_0048_dashboard_v2_definitions.py` (S1)
- `apps/api/app/services/dashboard_definitions.py`: `check_definition` (v2 planner check + v1 mirror +
  server-computed `v1_equivalent`), `request_from_definition`, `runs_v1`, `check_dashboard_filters`,
  `definition_from_v1` (migration mapping), `effective_visual_v1` (port of web `effectiveVisual`).
- `apps/api/app/services/dashboard_templates.py` (S14: three starters, `template_list`)
- `apps/api/scripts/n0116_migrate_definitions.py` (S2)
- `apps/api/tests/test_dashboard_v2_definitions.py` (33 tests), `apps/api/tests/test_dashboard_v2_api.py` (7 tests)

Changed:
- `apps/api/app/models/saved_reports.py`: `definition_v2` on SavedReport and DashboardWidget;
  `filters_json`, `template_key` on Dashboard; both visual checks widened.
- `apps/api/app/services/dashboard_widgets.py`: `WIDGET_VISUALS` + combo, dual_axis, scatter, pivot;
  `widget_to_dict` returns `definition_v2`.
- `apps/api/app/services/saved_report_access.py`: report dict returns `definition_v2`; dashboard dict
  returns `filters_json`, `template_key`.
- `apps/api/app/api/v1/endpoints/dashboards.py`: S3 layout route, S4 v2 bodies on POST/PATCH/PUT/create,
  promote copies the definition, dashboard PATCH/POST `filters_json`, S14 routes; `_reload` now uses
  `populate_existing` (finding F-A).
- `apps/api/app/api/v1/endpoints/saved_reports.py`: create/patch accept `definition_v2`; visuals widened.
- `apps/api/app/services/report_delivery.py`: S13 dual path.
- `apps/api/app/query/model/graph.py`: `governed_honours()` and `filter_refusals()` built from the
  existing `_GOVERNED_HANDLER_FILTERS` / `_breakdown_refusal` (table not duplicated); `_GOVERNED_ALL_TIME`
  ({a2_cpor}) for `honours.all_time_only`.
- `apps/api/app/query/model/catalog.py`: `models[].filter_refusals`, governed `measures[].honours`.

(`apps/api/scripts/db_on.py` shows as modified in git; that change predates this run and is not mine.)

## 2. Migration 0048 proof (S1)

No grants or policies needed: none of dashboard / dashboard_widget / saved_report has row security
(relrowsecurity false on the clone), and table-level grants (cip_test: `cip` owns them; cip: `cip` holds
table privileges) cover added columns. Downgrade raises
`Downgrade 20261023_0048 refused: N dashboard_widget and M saved_report rows use a visual added in 0048 ...`
when any row uses a new visual (test-proven), otherwise drops the columns and restores the 0046 checks.

Clone `cip_n0115`, as owner (`db_on.py alembic --db cip_n0115 --owner ...`), counts read with
`db_on.py sql --owner --db cip_n0115` (read-only):

| step | head | dashboard | dashboard_widget | saved_report | report_schedule | new columns | visual checks |
|---|---|---|---|---|---|---|---|
| before | 20261022_0047 | 3 | 6 | 3 | 1 | none | 9 visuals |
| upgrade head | 20261023_0048 | 3 | 6 | 3 | 1 | 4 (filters_json jsonb NOT NULL default '{}'::jsonb; template_key text NULL; 2 x definition_v2 jsonb NULL) | 13 visuals |
| downgrade -1 | 20261022_0047 | 3 | 6 | 3 | 1 | none | 9 visuals |
| upgrade head | 20261023_0048 | 3 | 6 | 3 | 1 | 4 | 13 visuals |

cip_test (`db_on.py alembic --db cip_test upgrade head`, user cip): `Running upgrade 20261022_0047 ->
20261023_0048`; head 20261023_0048; 0 dashboards, 0 widgets, 0 reports, 0 schedules; 4 columns present.

Note: the clone was left at 0048 with the 9 rows migrated (it is disposable; the task allowed writes to it).
The spec's "BEGIN ... ROLLBACK" variant was replaced by the task's real round trip + apply.

## 3. Migration script outputs (S2)

`apps/api/.venv/Scripts/python.exe apps/api/scripts/n0116_migrate_definitions.py --db cip_n0115 --owner --apply`

```
database=cip_n0115 user=postgres mode=apply
counts before: dashboard=3, dashboard_widget=6, saved_report=3, report_schedule=1

| row | v1 metric | grains | period_grain | visual before | kind | v2 measures | v2 breakdowns | grain | visual after | v1_equivalent | result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| W4 | sellout_units | period | week | area | model | dsi_sellout.units | period | week | area | True | written |
| W5 | cst_sellthrough_units | customer,product | - | line | model | cst_sellthrough.units | customer,product | - | hbar | True | written |
| W6 | cst_sellthrough_units | period | week | line | model | cst_sellthrough.units | period | week | line | True | written |
| W11 | sellout_units | distributor,product | - | table | model | dsi_sellout.units | distributor,product | - | table | True | written |
| W19 | pipeline_inbound | period | - | kpi | governed | pipeline_inbound | period | - | kpi | True | written |
| W20 | cst_sellthrough_units | customer,period | week | line | model | cst_sellthrough.units | customer,period | week | line | True | written |
| R1 | weeks_of_cover | distributor,product | - | kpi | governed | weeks_of_cover | distributor,product | - | kpi | True | written |
| R2 | weeks_of_cover | distributor,product | - | kpi | governed | weeks_of_cover | distributor,product | - | kpi | True | written |
| R3 | sellout_units | period | week | line | model | dsi_sellout.units | period | week | line | True | written |

rows with definition_v2 IS NULL: 9; written: 9; unmapped: 0
counts after : dashboard=3, dashboard_widget=6, saved_report=3, report_schedule=1
committed; rows still with definition_v2 IS NULL: 0
```

Second `--apply` on the clone: `rows with definition_v2 IS NULL: 0; written: 0; unmapped: 0`, counts unchanged.
(A `--dry-run` before it printed the same table with "would write" and rolled back.)

`--prove` on the clone (one READ ONLY transaction, rolled back; owner, so row security bypassed):

```
| row | measure | v1 total | v2 total | rows v1 | rows v2 | v2 path | mismatches |
|---|---|---|---|---|---|---|---|
| W4 | dsi_sellout.units | 400,991.8500 | 400,991.8500 | 144 | 144 | run_v2 | 0 |
| W5 | cst_sellthrough.units | 19,361.0000 | 19,361.0000 | 533 | 533 | run_v2 | 0 |
| W6 | cst_sellthrough.units | 19,361.0000 | 19,361.0000 | 95 | 95 | run_v2 | 0 |
| W11 | dsi_sellout.units | 400,991.8500 | 400,991.8500 | 1678 | 1678 | run_v2 | 0 |
| W19 | pipeline_inbound | 3,920.0000 | 3,920.0000 | 1 | 1 | run_v2 | 0 |
| W20 | cst_sellthrough.units | 19,361.0000 | 19,361.0000 | 144 | 144 | run_v2 | 0 |
| R1 | weeks_of_cover | 16.4817 | 16.4817 | 2481 | 2481 | run_v2 | 0 |
| R2 | weeks_of_cover | 16.4817 | 16.4817 | 2481 | 2481 | run_v2 | 0 |
| R3 | dsi_sellout.units | 400,991.8500 | 400,991.8500 | 144 | 144 | run_v2 | 0 |

proved rows: 9; total mismatches: 0
```

cip_test: `--apply` -> `counts before: 0/0/0/0; rows with definition_v2 IS NULL: 0; written: 0; unmapped: 0;
counts after 0/0/0/0; committed`. `--prove` -> `proved rows: 0; total mismatches: 0`. cip_test holds no
dashboards or reports, so the real cip-shaped proof on cip_test is the pytest
`test_migration_script_apply_twice_and_prove_on_cip_test`: it inserts the 9 cip-shaped rows (+ a dashboard and
an R2 schedule) in a rolled-back transaction, applies (exact mapping asserted, v1 columns unchanged, W5 visual
hbar with `migrated_from.visual = line`), applies again (0 written), counts equal, and `--prove` logic gives
`proved rows: 9; total mismatches: 0`.

Script rules as built: only `definition_v2 IS NULL` rows; v1 query columns never changed; `visual` changed only
where the saved one does not fit (the web's `effectiveVisual`, i.e. what users already see: W5 only); every
definition must be planner-clean AND v1-equivalent with exactly the stored v1 columns, otherwise the row is left
alone and reported UNMAPPED (exit 1); counts before = after or rollback + exit 1; prove: v2 run at limit 5,000,
and if truncated the same compiled SQL unlimited for row comparison (not needed on the clone; the column says
which path); governed a2 (CPOR) rows are skipped in prove because the a2 handler reads through the app's own
sync session (its default database), not the script's connection (no such rows exist).

cip: not touched (decision D2).

## 4. API contract for the web engineer

All routes are under `/api/v1`, behind the router's `get_current_user` (session mode: no bearer -> 401).
Errors: refusals of a definition are **400** with
`{"detail": {"message": "<first reason>", "refusals": [{"measure": str|null, "reason": str, "wall": str|null}]}}`
and nothing is written. Other 400s have `detail` as a plain string. Pydantic shape errors are 422.

### 4.1 `definition_v2` (stored on widgets and saved reports)

```json
{
  "v": 1,
  "kind": "model",
  "query": {
    "measures": ["cst_sellthrough.units", "cst_sellthrough.units_per_week"],
    "breakdowns": ["customer", "period"],
    "period": {"grain": "month"},
    "filters": {"bu": ["Notebook"]},
    "sort": {"by": "cst_sellthrough.units", "dir": "desc"},
    "limit": 500
  },
  "display": {"top_n": 15, "series": {"cst_sellthrough.units_per_week": {"kind": "line", "axis": "right"}},
              "kpi": {"compare": true, "sparkline": true},
              "table": {"rules": [{"measure": "cst_sellthrough.units", "op": "<", "value": 1, "tone": "warn"}]}},
  "v1_equivalent": false,
  "migrated_from": {"metric_key": "...", "grains": [], "period_grain": null, "visual": "line", "filters": {}, "at": "2026-10-23", "script": "n0116_migrate_definitions"}
}
```

What the client sends: `{"v": 1, "query": {...}, "display": {...}}` (`kind` optional; `v1_equivalent` is
ignored and recomputed). What the server stores and returns: the normalised form above
(`v`, `kind`, `query`, `display` if sent, `v1_equivalent`, `migrated_from` if present).

Server rules:
- Checked with the v2 planner (`plan_request`, no SQL). Any refusal (even on one of several measures) refuses
  the write. Same texts as `/query/v2/explain`.
- `query.period` may hold only `grain` (week/month/quarter/year). `from`/`to` are refused ("dates come from the
  dashboard"). The request the widget runs = `query` + the dashboard's `period.from` / `period.to`.
- Model definitions are planned with a nominal dashboard window, so `units_per_week` without a period breakdown
  is accepted; it is refused at run time only when the dashboard sends no dates (`all_time`).
- Unknown top-level or query keys refused. `display` is free-form but at most 8 KB; `display.top_n` 1..5000;
  `display.table.rules` at most 3.
- Kind: `governed` when the single measure is a v1 metric (alone), else `model`.
- `v1_equivalent` true when: governed; or one base measure with a `legacy_key`, breakdowns valid in v1, grain in
  week/month/quarter (not year), and filters only customer/product/distributor/site_label with one value each.
- v1 columns mirrored: equivalent -> `metric_key` = v1 key, `grains`, `period_grain`, `filters` = v1 keys
  (`customer_id`, `product_id`, `distributor_id`, `bu`, `site_label`; scalar). Not equivalent ->
  `metric_key` = first measure id, `grains: []`, `period_grain: null`, `filters: {}`.

### 4.2 Widget object (every dashboard response, `widgets[]`)

```json
{"id": 41, "dashboard_id": 7, "tenant_id": "default", "title": "Units and lines by BU", "visual": "combo",
 "metric_key": "dsi_sellout.units", "grains": [], "filters": {}, "period_grain": null,
 "layout_json": {"x": 0, "y": 0, "w": 6, "h": 8}, "saved_report_id": null, "sort_order": 0,
 "definition_v2": {"v": 1, "kind": "model", "query": {"measures": ["dsi_sellout.units", "dsi_sellout.lines"], "breakdowns": ["bu"], "sort": {"by": "dsi_sellout.units", "dir": "desc"}, "limit": 50}, "display": {"top_n": 15}, "v1_equivalent": false},
 "created_at": "...", "updated_at": "..."}
```

`definition_v2: null` = v1 widget (run v1 `POST /query/execute` as today). Non-null = run
`POST /query/v2/execute` with `request = {...definition_v2.query, period: {grain: query.period?.grain, from, to}, filters: AND(dashboard, widget)}`.

Visual values (widgets and reports): `kpi, table, bar, hbar, stacked_bar, line, area, pie, donut, combo,
dual_axis, scatter, pivot`. The server checks membership only; fit rules are client side.

### 4.3 Dashboard object (GET/POST/PATCH responses, list items)

Adds `"filters_json": {...}` (always an object, `{}` by default) and `"template_key": null | "account_overview" | "sellthrough_stock" | "cpor_cases"`.
The `widgets` list in a write response now reflects the write (F-A fix).

### 4.4 Routes

**POST `/dashboards/{id}/widgets`** (owner or admin). v2 body:
```json
{"title": "Sell-through units by week", "visual": "line", "definition_v2": {"v": 1, "query": {"measures": ["cst_sellthrough.units"], "breakdowns": ["period"], "period": {"grain": "week"}}}, "layout_json": {"x": 0, "y": 16, "w": 6, "h": 8}}
```
v1 body unchanged: `{"title", "visual", "metric_key", "grains", "period_grain", "filters", "layout_json"}`.
Neither `metric_key` nor `definition_v2` -> 400. Response: the dashboard object.
Refused example (400):
```json
{"detail": {"message": "Filter 'distributor': Customer sell-through reports do not say which distributor supplied the stock.",
            "refusals": [{"measure": null, "reason": "Filter 'distributor': Customer sell-through reports do not say which distributor supplied the stock.", "wall": "W-CST-NO-DISTRIBUTOR"}]}}
```

**PATCH `/dashboards/{id}/widgets/{wid}`**:
- `definition_v2` sent (object): checked, stored, v1 columns re-mirrored.
- `definition_v2: null` sent: back to the v1 path (the current/sent v1 fields are v1-validated; a v2-only
  widget's mirror is not v1-valid, so this 400s unless v1 fields are sent too).
- not sent, and no v1 query fields (`metric_key`, `grains`, `period_grain`, `filters`) sent: the definition is
  kept untouched (title / visual / layout / sort only; no query re-validation). Use this for rename, visual
  change, etc.
- not sent but v1 query fields sent: the widget becomes v1 again (`definition_v2` cleared), v1-validated.

**PUT `/dashboards/{id}/widgets`** (old full replace; still deletes widgets missing from the body). Each spec
may carry `definition_v2`. A v2 widget sent without `definition_v2` but with its mirrored v1 fields unchanged keeps
its definition. Prefer the layout route below for drag/resize.

**PATCH `/dashboards/{id}/layout`** (S3; owner or admin, 403 otherwise). Body:
```json
[{"id": 41, "x": 0, "y": 0, "w": 6, "h": 8}, {"id": 42, "x": 6, "y": 0, "w": 6, "h": 8}]
```
Writes only `layout_json` (x, y, w, h merged into any existing keys). No query check, no deletes, widgets not
listed are untouched, `updated_at` not touched. Bounds: x 0..1000, y 0..100000, w 1..12, h 1..1000 (422
outside). Unknown or duplicate id -> 400, nothing written. Response: the dashboard object.

**PATCH `/dashboards/{id}`** accepts `"filters_json"` (replaces the saved bar). **POST `/dashboards`** accepts it
too. Shape (validated, 400 on anything else):
```json
{"date": {"preset": "last_52_weeks", "from": null, "to": null},
 "compare": "previous_period",
 "customer": [299], "distributor": [], "product": [], "bu": [], "channel": [], "region": [],
 "required": ["customer"]}
```
- `date.preset`: `last_13_weeks | last_26_weeks | last_52_weeks | this_year | last_quarter | all_time | custom`;
  `from`/`to` ISO dates or null.
- `compare`: `none | previous_period | previous_year`.
- Any other key must be a v2 catalog breakdown id (not `period`) with a list value (at most 1,000 ids or plain
  values; no objects/booleans). So S18 attributes (`category`, `series`, ...) and click keys can be saved.
- `required`: list of breakdown ids.

**POST `/dashboards/{id}/widgets/{wid}/promote`**: a v2 widget's report gets the same (re-checked)
`definition_v2` and v1 mirror; response `{dashboard, saved_report}` (report includes `definition_v2`).

**GET `/dashboards/templates`** (signed in):
```json
{"count": 3, "items": [
  {"key": "account_overview", "title": "Account overview",
   "description": "One retailer's own sell-through: ... Pick a customer above.",
   "widget_count": 8, "required_filters": ["customer"],
   "filters_json": {"date": {"preset": "last_52_weeks", "from": null, "to": null}, "compare": "previous_period", "customer": [], "distributor": [], "product": [], "bu": [], "channel": [], "region": [], "required": ["customer"]},
   "left_out": [
     {"what": "Stock cover", "reason": "Customer stock cover is not defined for the builder; show reported stock beside units per week (no derived cover).", "pending_id": "cst_sellthrough.stock_cover"},
     {"what": "Restock flags", "reason": "Restock flags live in the sell-through overview's SKU problem rules (per-customer config, forward cover); not a compiler measure tonight.", "pending_id": "cst_sellthrough.restock_flag"},
     {"what": "Sales value", "reason": "Proposed decision 3: CST sales value and its VAT basis conversion is not picked.", "pending_id": "cst_sellthrough.value"},
     {"what": "DSI sell-out to this customer as a dealer", "reason": "A distributor's dealer is a different customer role ...; add a DSI widget by hand.", "pending_id": null},
     {"what": "Colour rules on the stock table", "reason": "No agreed threshold, so no colour rule is set.", "pending_id": null}]},
  {"key": "sellthrough_stock", "title": "Sell-through & stock across customers", "widget_count": 6, "required_filters": [], "left_out": ["Stock cover in weeks", "Restock flags", "Sales value"]},
  {"key": "cpor_cases", "title": "CPOR cases", "widget_count": 8, "required_filters": [], "filters_json": {"date": {"preset": "all_time"}, "compare": "none", "...": []}, "left_out": ["Open cases", "Case value", "A list of cases", "Cases as a pie"]}]}
```
(abridged; `left_out` items are always `{what, reason, pending_id}`; pending reasons come live from the catalog.)

**POST `/dashboards/from-template`** body `{"key": "account_overview", "name": "optional override"}`. Creates a
**personal** dashboard owned by the caller (`owner_user_id` = caller; a caller with no app_user id -> 401) with
`template_key`, the starter's `filters_json`, `description`, and its widgets (each `definition_v2` planner-checked
before anything is written). Unknown key -> 404. Response: the dashboard object. The UI should show the
"Template — editable" chip when `template_key` is set, and the `left_out` list from `/templates`.

Starter widgets (visual, measures, breakdowns, grain, layout x,y,w,h, display):
- account_overview: kpi units (0,0,3,5; kpi compare+sparkline) | kpi units_per_week (3,0,3,5; compare) | kpi
  reported_soh (6,0,3,5; `display.caption` "as of latest report on or before {to}") | kpi stores_reporting
  (9,0,3,5) | line units [period] week (0,5,8,8) | hbar units [product] (8,5,4,8; top_n 15) | table units,
  units_per_week, reported_soh [product] sort units desc (0,13,12,10) | hbar units [site_label] (0,23,12,8; top_n 15).
  All `cst_sellthrough.*`.
- sellthrough_stock: kpi units (0,0,4,5; compare+sparkline) | kpi units_per_week (4,0,4,5) | kpi reported_soh
  (8,0,4,5) | hbar units [customer] (0,5,6,8; top_n 15) | line units [customer, period] month (6,5,6,8) | table
  units, units_per_week, reported_soh, stores_reporting [customer] sort units desc (0,13,12,8).
- cpor_cases: kpi cases | kpi support_usd | kpi support_zar | kpi delivery_rate (row 0, w 3 each) | hbar cases
  [status] (0,5,4,8) | table cases, support_usd, support_zar, estimate_units, result_units, delivery_rate
  [status, workflow_status] (4,5,8,8) | bar support_usd [period] quarter (0,13,6,8) | hbar support_usd [customer]
  (6,13,6,8; top_n 15). All `cpor.*`.
`display.kpi` = `{"compare": bool, "sparkline": bool}` on every KPI.

**Saved reports** `POST /saved-reports`: `metric` now optional when `definition_v2` is given; same check/mirror;
`PATCH /saved-reports/{id}`: same rules as the widget PATCH (v1 query fields there are `metric`, `grains`,
`period_grain`, `filters`). Report dicts include `definition_v2`.

### 4.5 Catalog v2 additions (`GET /semantics/v2/catalog`)

- `models[].filter_refusals`: `{breakdown_id: reason}` for every catalog breakdown a filter on that model is
  refused for (never `period`, never an allowed one). The planner refusal reads exactly
  `Filter '<id>': <reason>`. On today's model:
  - `cst_sellthrough`: distributor = "Customer sell-through reports do not say which distributor supplied the
    stock." (W-CST-NO-DISTRIBUTOR); promo_type / status / workflow_status = "<label> is not a breakdown of
    Customer sell-through (CST)."
  - `dsi_sellout`: site_label = "Store / site comes only from customer sell-through reports. Distributor
    sell-out has no store." (W-SITE-CST-ONLY); promo_type / status / workflow_status.
  - `cpor`: site_label (same W-SITE-CST-ONLY text, see F-C).
- Governed measures (`kind: "governed"`) get `honours`:
  `{"handler": "a3_stock", "filters": ["distributor", "product"], "dates": false, "all_time_only": false, "one_value_per_filter": true}`.
  - a1_pve (fill_rate, pipeline_inbound, ...): filters ["bu"], dates true.
  - a2_cpor (support_spend, delivery_rate, support_cost_per_unit_sold): filters ["bu", "customer"], dates true,
    **all_time_only true** (the handler refuses any period: do not send dates; show "Not filtered by date").
  - a3_stock (channel_stock, weeks_of_cover, replenishment_flag): ["distributor", "product"], dates false.
  - not handler-backed: handler null, filters [], dates false.
  Client rule: send a dashboard filter to a governed measure only if its id is in `honours.filters` and it has
  exactly one value; send dates only if `dates && !all_time_only`. Anything else is refused by the planner
  (never silently ignored).

### 4.6 Delivery (S13, no client change)

`deliver_saved_report` runs the v1 path when `definition_v2` is null or `v1_equivalent` is true (schedule 1 /
R2 is unchanged). A v2-only report runs `run_v2(query, no dates)` on the same session: `value_preview` =
`totals[first measure]`, status delivered/failed from `ok`, `error_message` = first refusal reason,
`data_vintage` = `{"engine": "v2", "min", "max", "as_of_utc"}`. A v2-only report whose measure needs a date range
(units_per_week without period) fails with the planner's text (no dates are stored).

## 5. Tests

Command: `apps/api/.venv/Scripts/python.exe apps/api/scripts/db_on.py pytest <files>` (cip_test).

New (40, all pass): `test_dashboard_v2_definitions.py` (33) and `test_dashboard_v2_api.py` (7):
spec s.8 API items:
1. 0048 downgrade + upgrade in a rolled-back transaction (columns, default, checks); downgrade refuses with a
   `combo` widget present.
2. 9 cip-shaped rows -> exact definitions (parametrised pure test + DB test; W5 -> hbar, `migrated_from.visual =
   line`); second apply writes 0; counts before = after; v1 columns unchanged.
3. `--prove` logic on cip_test with those rows: 9 proved, 0 mismatches.
4. Widget POST/PATCH with definition_v2: valid 200 (mirror asserted), refused cross-model / wall / limit 5,001 ->
   400 with the text and widget count unchanged; v1 body accepted; refused PATCH leaves the stored definition;
   title-only PATCH keeps it; `definition_v2: null` goes back to v1.
5. PATCH /layout: only layout_json changes (definition, title, visual, v1 columns, updated_at equal), nothing
   deleted, unknown/duplicate ids 400 with nothing written, w 13 -> 422, other user 403; old PUT with mirrored
   fields keeps the definition.
6. filters_json round trip + 400 on a bad value; from-template makes all 3 (8/6/8 widgets) personal to the
   creator (another user gets 403), every widget plans with no refusals (account overview with a customer);
   unknown key 404; anonymous 401 on /templates, /from-template, /layout (session mode).
7. Catalog filter_refusals: CST + distributor and DSI + site_label equal the planner's reason.
8. honours: weeks_of_cover + customer refused (text), pipeline_inbound + customer refused, + bu applied (planner
   passes `{"bu": ...}`; on cip_test an unknown bu gives 0/None vs the unfiltered total, asserted), support_spend
   + dates refused with the a2 handler's text; weeks_of_cover + dates refused.
9. Delivery: R2-shaped report gives the same status / value_preview / metric_key before and after migration with
   run_v2 never called; a v2-only report (units + lines) delivers through run_v2 with the v1 engine patched to
   fail if called; a refused v2-only report fails with the planner's reason.
10. Regression set below.

Run of the relevant set (23 files: the 2 new + test_dashboard_widgets, test_dashboard_widget_persist,
test_dashboard_freshness, test_report_export, test_report_delivery_alert, test_saved_report_access,
test_query_model_graph, test_query_model_db, test_query_model_rules, test_query_v2_api,
test_query_v1_callers_n0115, test_query_engine, test_query_compose, test_query_labels, test_semantic_layer,
test_semantic_overlay_api, test_semantic_overlay_governed, test_a1_handler_grains, test_volume_series,
test_cst_period_grain, test_product_line_scope_n0065): **222 passed, 1 skipped** (pre-existing skip:
test_dashboard_widget_persist needs ALLOW_TESTS_ON_DEV_DB), 1 pre-existing RuntimeWarning (test_query_engine
AsyncMock). The last new test (governed execute) was added after that run and passes with the two new files
(40 passed). The full suite was not run (orchestrator).

Test harness note: the API tests bind every request session to one connection inside an outer transaction
(`join_transaction_mode="create_savepoint"`, httpx `ASGITransport`), so app commits are savepoints and all is
rolled back.

## 6. Not done / deferred

- Web half (S6-S12, S15-S17 client work): not in this run.
- `docs/DATA_MODEL_SPEC.md` "as built" bullets: out of my change scope (apps/api only).
- cip: 0048 and the script not run (D2, Warren's go; restart the worker after, per standing rule).
- Report builder `/reports` editing on v2, S19 case breakdown, server-side value search: per spec, deferred.
- Visual fit is not checked server-side (only membership); fit stays a client rule (spec s.4).

## 7. Findings

- **F-A (FACT, fixed)**: every dashboard write route returned the dashboard's widget list as it was BEFORE the
  write (`_reload` hit the identity map with `expire_on_commit=False`), e.g. POST /widgets answered without the
  new widget. The web hid it by refetching. `_reload` now uses `populate_existing`; tests assert the response.
- **F-B (OBSERVATION)**: a governed a2 (CPOR) metric reads through the app's own sync `SessionLocal`, not the
  request session, so a migration `--prove` on a clone cannot exercise it (skipped by design; none exist).
- **F-C (OBSERVATION)**: the W-SITE-CST-ONLY reason ("... Distributor sell-out has no store.") is also the CPOR
  site_label refusal text, which mentions DSI. Wording only; owner: model file.
- **F-D**: honours.dates for a2 is true (dates reach the handler, which refuses); exposed `all_time_only` so the
  client does not send a range it knows will be refused. Without that, any a2 widget on a dated dashboard would
  always show a refusal.
- **F-E**: an old-client PATCH of a v2-only widget with v1 query fields 400s (v1 validation of a v2 id). Expected
  until the web switches to definition_v2; title/visual/layout-only PATCHes and PUTs with unchanged mirrored
  fields are safe.
- **F-F**: `cst_sellthrough.units` with no breakdown (KPI) is not v1-equivalent (v1 has no empty grain set for
  it), so starter KPIs mirror `metric_key = cst_sellthrough.units` with empty grains; old v1 readers cannot run
  them (they are v2-only by design).
- Clone `cip_n0115` now sits at 0048 with the 9 rows migrated (allowed; disposable).
