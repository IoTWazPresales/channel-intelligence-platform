# N-0116 feature definition (proposal): the dashboard builder on the new data model

Date: 2026-10-23. Moment (b), feature definition. Lenses applied from the agent's own knowledge (no skills
loaded): product-manager, product-interaction-designer, ui-visual-design-specialist, premium-benchmark-reviewer
(bar: Power BI / Looker / Datadog, without copying them blindly). This is a proposal. No product files edited.
The only file written is this one. Database reads: the read-only clone `cip_n0115`, as owner (no row
security). `cip` was not touched.

Builds on N-0115 (`docs/DATA_MODEL_SPEC.md` s.10, `.eif/audit/PROGRAMME_20261023/N0115_IMPL_REPORT.md`):
`GET /api/v1/semantics/v2/catalog`, `POST /api/v1/query/v2/execute|explain`. Constraints held: no new
UI or chart library (MUI, AG Grid Community 33, Recharts 2.15, react-grid-layout 2.2, dnd-kit; reuse
`features/workbench-ui/charts.tsx`, `ChartControls.tsx`, `HeadlineFigure.tsx`). Customer and Distributor
columns show names only. No figure is invented. Commercial definitions that are not in code stay as
proposed decisions.

---

## 0. Scope cut (one full-stack engineer, one long session)

| # | Item | Rank |
|---|---|---|
| S1 | Alembic 0048: `definition_v2` on widget and report, `filters_json` + `template_key` on dashboard, wider visual check | MUST |
| S2 | Migration script: 6 widgets and 3 reports to v2, parity-checked on the clone in a rolled-back transaction, applied to cip_test | MUST |
| S3 | Layout-only PATCH, so dragging no longer re-saves (and re-validates against v1) every widget | MUST |
| S4 | Widget card runs v2 execute (`definition_v2` set) or the v1 path (null), keeping the existing per-widget loading | MUST |
| S5 | Catalog v2 additions: `filter_refusals` per model; `honours` per governed measure. Governed planner refuses a filter its handler ignores | MUST |
| S6 | Dashboard filter bar: date range + compare, customer, distributor, product, business unit, channel, region. Plain-words "not filtered by" line on each widget | MUST |
| S7 | Per-widget filters in the editor (AND with the dashboard's) | MUST |
| S8 | Editor on catalog v2: measures (one model), breakdowns (up to 3), period grain, filters, top N / sort, visual, display options | MUST |
| S9 | Visuals: KPI + compare + sparkline, columns, ranked bars, stacked, line, area, bar + line, pie, donut, table + conditional colour | MUST |
| S10 | Click a bar, slice, point or legend item to filter the dashboard (chip clears it); click a period to narrow the date range | MUST |
| S11 | "View rows" drawer: v2 execute at the finest allowed breakdown in AG Grid, labelled honestly as grouped rows | MUST |
| S12 | Widget menu: duplicate, full screen, export CSV, export PNG (Recharts SVG to canvas), skeleton, empty, refused, error and truncated states | MUST |
| S13 | Report delivery: unchanged v1 path for v1-expressible reports; `run_v2` only for v2-only reports | MUST |
| S14 | Three starter templates, created on demand, marked "Template — editable" | MUST |
| S15 | Dual axis, scatter, pivot table | SHOULD |
| S16 | Compare series on line, area and columns ("Previous period", muted and dashed); compare column in tables | SHOULD |
| S17 | Per-widget "ignore this dashboard filter"; per-widget fixed date window | SHOULD |
| S18 | More attribute filters in the bar (category, series, form factor, price band, sales model, lifecycle, partner tier) | SHOULD |
| S19 | CPOR `case` breakdown (id + `cpor_case.case_name`), so "view rows" can list cases | SHOULD |
| S20 | Report builder (`/reports`) editing on v2; source-line drill (single transactions); colour scale on tables; text/note widget; cross-model widgets | LATER |

---

## 1. AS-IS (observed in code and on the clone)

**Canvas**
- `apps/web/src/features/dashboards/DashboardWorkspace.tsx:61-64` fetches the **v1** catalog `/api/v1/semantics/catalog`. The left list keeps only implemented, handler-backed metrics (`:76-83`).
- Adding a widget: click or drag a metric (`:162-189`) opens the editor. A metric dropped on `dashboard-canvas` sets `metric_key` and the first allowed grain set.
- Saving a layout (`:135-160`) PUTs **every widget's full spec** to `PUT /dashboards/{id}/widgets`. That endpoint (`apps/api/app/api/v1/endpoints/dashboards.py:371-420`) re-runs the v1 `validate_widget_query` on each one through `_apply_widget_fields` (`:122-151`) and **deletes any widget missing from the body**. A v2-only widget would fail v1 validation, so dragging would return 400. A field the client does not send would be overwritten.
- Page copy says "Governed metric canvas — one widget is one metric" (`:207`). This is out of date once v2 lands.
- Grid: `DashboardGrid.tsx:56-62` uses react-grid-layout, 12 columns, rowHeight 36, drag handle `.dashboard-widget-drag`, resize on. Below 720 px the widgets stack full width and the saved layout is not rewritten (`:20-30`). Default size 6x8 (`:32-43`). Saves are debounced 400 ms (`:63-78`).
- "Grafana-style loading" means each card runs its own React Query request (`DashboardWidgetCard.tsx:36-52`, v1 `POST /query/execute`), and the grid itself loads with `dynamic(..., {ssr:false})` showing "Loading canvas…" (`DashboardWorkspace.tsx:49-52`). **Keep both.**
- Card header actions: drag, Edit, Promote to saved report, Remove (`DashboardWidgetCard.tsx:63-91`). Below them, "About this figure" shows the formula and coverage (`:93-117`).
- Body: plain "Loading…" text (`WidgetBody.tsx:44`), a refusal Alert (`:47-53`), KPI through `HeadlineFigure` (`:54-56`), table through `EnterpriseDataGrid` (`:57-59`), otherwise `WidgetChart`.
- `WidgetChart.tsx` draws the N-0114 shared charts: empty state (`:38-44`), `ShareChart` (`:53-66`), `RankedBars` / `CategoryBars` (`:69-98`), `TrendChart` period x category (`:101-116`), single series (`:119-131`).
- `widgetModel.ts`: 9 visuals (`:16-26`); fit rules (`visualsFor`, `:35-46`). `categoryPoints` **merges rows by label** (`:113-120`), so two products with the same name collapse into one bar. The v2 work must key by id.
- `HeadlineFigure.tsx:17-38` already accepts `delta`, `sparkline` and `state` (loading/empty/stale). The dashboard KPI uses none of them.
- Charts: `TrendChart` (`charts.tsx:946-985`) already mixes `line | area | bar` series on **one** axis, so bar + line needs no new chart. There is no second axis, no scatter and no click callback.

**Editor** (`WidgetEditorDialog.tsx`)
- Picks one v1 metric (`MetricBrowser`), a governed grain set from chips (`:219-233`), a period grain week/month/quarter (`:236-256`) and a visual (`:272-305`). Title is automatic.
- The live preview is v1 execute with `filters: {}` always (`:148-158`). **There is no filter UI anywhere in the builder.** Saved value: `{title, metric_key, grains, period_grain, visual}` (`:58-64`).

**Storage** (`apps/api/app/models/saved_reports.py`)
- `saved_report` (`:14-49`): `metric_key` NOT NULL, `grains`, `filters`, `visual` (check `:18-21`: kpi, table, bar, hbar, stacked_bar, line, area, pie, donut), `period_grain` (check `:22-25`: week, month, quarter).
- `dashboard` (`:52-80`): name, visibility, shared_roles. **No filters column.**
- `dashboard_widget` (`:83-122`): the same query columns, plus `layout_json` and `saved_report_id` (FK, SET NULL).
- Visual list is duplicated in `services/dashboard_widgets.py:12`. v1 validation: `:39-58`.
- Promote (`dashboards.py:509-551`) copies a widget onto a saved report and links them, so schedules live on the report.
- Overview pins (`overview_report_pin`; `OverviewHub.tsx:97-105, 266`) list report **names only** and run no query, so the migration does not affect them. There are 0 pin rows on the clone.

**Saved reports and schedules**
- `report_delivery.deliver_saved_report` (`apps/api/app/services/report_delivery.py:43-95`) runs v1 `execute_query(metric, grains, filters)`. **It does not pass `period_grain`** (`:54-61`). See finding F3.
- `report_schedule_runner._deliver_schedule_async` calls it (`report_schedule_runner.py:173-200`).

**Saved state on the clone `cip_n0115` (= cip)**
- Dashboards: 1 "Channel stock board" (published), 2 "test" (published), 4 "Unit 14 canvas" (personal). All 6 widgets are on dashboard 4.
- Alembic head: `20261022_0047`.
- Schedule 1: saved report 2, `weekly_monday_0700`, xlsx, enabled. Last run 2026-10-19, next 2026-10-26.

| row | title | visual | metric | grains | period_grain | link |
|---|---|---|---|---|---|---|
| W4 | Sell-out units (period by week) | area | sellout_units | [period] | week | saved_report 3 |
| W5 | CST sell-through units (customer) | line | cst_sellthrough_units | [customer, product] | - | - |
| W6 | CST sell-through units (period by week) | line | cst_sellthrough_units | [period] | week | - |
| W11 | Sell-out units (distributor x product) | table | sellout_units | [distributor, product] | - | - |
| W19 | Pipeline (inbound) (period) | kpi | pipeline_inbound | [period] | null | - |
| W20 | CST sell-through units by customer and week | line | cst_sellthrough_units | [customer, period] | week | - |
| R1 | Weeks of cover | kpi | weeks_of_cover | [distributor, product] | - | - |
| R2 | WoC smoke | kpi | weeks_of_cover | [distributor, product] | - | schedule 1 |
| R3 | Sell-out units (period by week) | line | sellout_units | [period] | week | - |

**v2 API facts the builder depends on** (`apps/api/app/query/model/`)
- Request: `{measures, breakdowns, filters:{id: value|[values]}, period:{grain, from, to}, sort:{by, dir}, limit}`.
- Limits (`graph.py:23-28`): 3 breakdowns, 20 measures, default 500 rows, max 5,000 rows (a higher limit is refused, not clamped), 1,000 filter values.
- One model per query (`graph.py:292-301`). A governed metric must be queried alone (`:278-287`). `sellout_units` and `cst_sellthrough_units` are refused in v2 with "Use dsi_sellout.units …" (`:270-273`).
- A filter on a breakdown the model does not allow refuses the **whole query** (`graph.py:385-402`). The builder therefore has to drop such a filter before sending, and say so.
- Response rows: entity columns arrive as `{e}_id` + `{e}_name`, with NULL shown as "Unassigned". Period fields: `bucket_key`, `bucket_start`, `bucket_end`. Measures are keyed by measure id. `totals` come from SQL; `truncated`; `explain.data_vintage` {min, max}; `explain.row_count` (`execute.py:64-189`).
- Governed measures: the v1 engine runs and v2 reshapes the result (`execute.py:192-237`). Filters map through `_GOVERNED_FILTER_MAP` (`graph.py:457-464`), one value per filter.

---

## 2. Storage design

### 2.1 Columns (Alembic `20261023_0048_dashboard_v2_definitions.py`, additive and reversible)

| table | column | type | meaning |
|---|---|---|---|
| dashboard_widget | `definition_v2` | JSONB NULL | the v2 definition. When NULL, the widget runs the v1 path as today |
| saved_report | `definition_v2` | JSONB NULL | same |
| dashboard | `filters_json` | JSONB NOT NULL DEFAULT '{}' | saved dashboard filters (2.3) |
| dashboard | `template_key` | TEXT NULL | `account_overview`, `sellthrough_stock` or `cpor_cases` when created from a starter |

- Both visual checks (`ck_dashboard_widget_visual`, `ck_saved_report_visual`) and `WIDGET_VISUALS` gain `combo`, `dual_axis`, `scatter` and `pivot`. Add all four now, even though three of them are SHOULD visuals, so there is only one constraint migration.
- `period_grain` and its check stay as they are. The v2 grain (which may be `year`) lives inside `definition_v2`.
- Downgrade drops the columns and restores the checks. It **fails loudly** if any row uses a new visual, rather than rewriting data.
- The v1 columns stay populated (`metric_key` is NOT NULL). For a v2 definition, `metric_key` is set to the v1 key when the definition can be expressed in v1 (the measure's `legacy_key`, or the governed key), otherwise to the first measure id. `grains` and `period_grain` are mirrored only when v1-expressible, otherwise `[]` and NULL. Old readers (report builder, exports) keep working on v1-expressible rows.

Why one `definition_v2` column rather than `query_v2` + a version field: the query and its display options (combo series roles, conditional colour, compare, top N) change together and are validated together. One nullable column is the version switch (`NULL` = v1). This is proposed decision D1.

### 2.2 `definition_v2` shape (version 1)

```json
{
  "v": 1,
  "kind": "model",
  "query": {
    "measures": ["dsi_sellout.units"],
    "breakdowns": ["period"],
    "period": {"grain": "week"},
    "filters": {"bu": ["Notebook"]},
    "sort": {"by": "dsi_sellout.units", "dir": "desc"},
    "limit": 500
  },
  "display": {
    "top_n": 15,
    "series": {"dsi_sellout.units": {"kind": "bar", "axis": "left"}},
    "kpi": {"compare": true, "sparkline": true},
    "table": {"rules": [{"measure": "cst_sellthrough.units_per_week", "op": "<", "value": 1, "tone": "warn"}]}
  },
  "v1_equivalent": true,
  "migrated_from": {"metric_key": "sellout_units", "grains": ["period"], "period_grain": "week", "visual": "area", "filters": {}, "at": "2026-10-23", "script": "n0116_migrate_definitions"}
}
```

- `kind` is `model` or `governed`.
- `query.period` never stores `from` or `to`. Dates come from the dashboard, or from a fixed widget window (S17).
- `display` is optional, and every key in it is optional.
- `migrated_from` is present only on migrated rows. It is the audit trail.

Writes:
- `POST/PATCH /dashboards/{id}/widgets` accept `definition_v2`. They validate it with `plan_request` (no SQL), the same code explain uses. Any refusal returns 400 with the refusal texts and nothing is written. v1 bodies are still accepted unchanged.
- Promote copies `definition_v2` onto the saved report.

**S3, new route:** `PATCH /dashboards/{id}/layout` with body `[{id, x, y, w, h}]`. It writes `layout_json` only: no validation, no deletes. `persistLayoutMut` (`DashboardWorkspace.tsx:135-160`) switches to it. The existing PUT keeps working for v1 callers.

### 2.3 `dashboard.filters_json`

```json
{
  "date": {"preset": "last_52_weeks", "from": null, "to": null},
  "compare": "previous_period",
  "customer": [299],
  "distributor": [],
  "product": [],
  "bu": [],
  "channel": [],
  "region": [],
  "required": ["customer"]
}
```

- Date presets: `last_13_weeks`, `last_26_weeks`, `last_52_weeks`, `this_year`, `last_quarter`, `all_time`, `custom`. They resolve on the client to `from`/`to` (ISO dates; `to` = today). `all_time` sends neither.
- `compare`: `none`, `previous_period` (same length, immediately before) or `previous_year` (both dates minus one calendar year).
- `required` is used by templates: until the listed filter has a value, widgets show "Pick a customer above to see this account" and **run no query**.
- Click chips (S10) are session state and are **not** saved. Clicking "Save filters" writes the bar's current state.

### 2.4 Migration of the 6 widgets and 3 reports

Script: `apps/api/scripts/n0116_migrate_definitions.py --db <name> [--owner] (--dry-run | --apply | --prove)`.

| row | definition_v2.query | kind | visual after | note |
|---|---|---|---|---|
| W4 | measures [dsi_sellout.units], breakdowns [period], grain week | model | area | parity case "sellout_units / period / week" proven in N-0115 |
| W5 | [cst_sellthrough.units], [customer, product] | model | **hbar** | the saved `line` does not fit a breakdown with no period. Today it already renders as `hbar` through `effectiveVisual`, so the migration writes what users see and records `line` in `migrated_from` |
| W6 | [cst_sellthrough.units], [period], week | model | line | coarsest stored type is weekly (Amazon holds daily + weekly), so week is allowed |
| W11 | [dsi_sellout.units], [distributor, product] | model | table | rows with no distributor are left out when grouped, as in v1 |
| W19 | [pipeline_inbound], [period], grain null | governed | kpi | v1 handler, unchanged |
| W20 | [cst_sellthrough.units], [customer, period], week | model | line | |
| R1, R2 | [weeks_of_cover], [distributor, product] | governed | kpi | R2 keeps schedule 1 on the v1 path (2.5) |
| R3 | [dsi_sellout.units], [period], week | model | line | |

Rules:
- `legacy_key` maps v1 to model measures (`sellout_units` → `dsi_sellout.units`, `cst_sellthrough_units` → `cst_sellthrough.units`). Every other v1 key becomes governed with the same grains.
- v1 filter keys map `customer_id` → `customer`, `product_id` → `product`, `distributor_id` → `distributor`. All 9 rows have `{}`.
- Only rows with `definition_v2 IS NULL` are written, so a second run writes 0. v1 columns are never changed.
- **Nothing is lost:** the script counts widgets and reports before and after, and exits non-zero if a row is left unmapped or the counts differ.
- `--prove` runs v1 `execute_query` and v2 `run_v2` for every mapped row in one transaction. It compares the total and every row (rounded to 6 dp; rows matched on ids + bucket_key) and prints a table (row, v1 total, v2 total, rows v1, rows v2, mismatches). Any mismatch exits non-zero. It reuses the comparison in `scripts/n0115_parity.py`.

Where each step runs:
- **Clone:** `BEGIN; alembic 0048 DDL; --apply; --prove; ROLLBACK` as owner, so the clone stays read-only. DDL is transactional in Postgres. Row security is bypassed as owner (same caveat as N-0115). The output table goes into the implementation report.
- **cip_test:** `alembic upgrade head` + `--apply` + `--prove` over whatever cip_test holds (report the count; it may be 0). A pytest also inserts the 9 cip-shaped rows in a rolled-back transaction and asserts the exact mapping.
- **cip:** not touched. Running 0048 and the script there is decision D2 (Warren's go, with the worker restarted, per standing rule).

### 2.5 Scheduled delivery keeps sending

- `deliver_saved_report` stays on v1 whenever `definition_v2` is NULL **or** `definition_v2.v1_equivalent` is true. That covers R1, R2 and R3 after migration, so schedule 1 (R2) runs exactly the code it runs today.
- Only a report whose definition has no v1 equivalent (for example `cpor.support_usd` by status, promoted from a v2 widget) goes through `run_v2` on the same session. For those, `value_preview` = `totals[first measure]`, `status` follows `ok`, and the failure message is the first refusal reason.
- The schedule runner is unchanged.
- Tests: R2-shaped report delivered before and after migration gives the same `value_preview` and status (rolled back). A v2-only report delivers through `run_v2`. The existing `test_report_export.py` schedule runner tests pass. `test_v1_report_delivery_unchanged` passes.

---

## 3. Dashboard filter bar and per-widget filters

**Bar** (sticky, above the grid; Power BI filter pane / Looker filter bar pattern)
- Controls in order: Date range, Compare, Customer, Distributor, Product, Business unit, Channel, Region. "More filters" (S18) adds the other attributes.
- Each value filter is an MUI `Autocomplete` (multi, chips, search). **Names only**, never codes.
- Values come from v2 execute itself, so no new endpoint is needed: `{measures:[<model>.lines], breakdowns:[<filter id>], period:<dashboard window>, sort:{by:<model>.lines, dir:desc}, limit:5000}` for each model used on the dashboard, combined by id. The list then holds only values that have data in that window. Each option shows its model ("Dealer (DSI)", "Retailer (CST)", "CPOR account"), because the same customer id can be a DSI dealer and a CST retailer (for example Computer Mania, id 18).
- Fewer than 5,000 options are fetched once and searched on the client. DSI has 4,822 customers. Above that, show "Type to search" and filter client-side on the first 5,000 (finding F7).
- Business unit = the `bu` attribute ("Business unit (product line)"), which is what v1 widgets already use. See F6 for the near-duplicate `business_unit` attribute.
- 390 px: the bar collapses into a "Filters (n)" button that opens a bottom drawer. Active chips stay visible in one scrolling row.

**Per widget (request builder `requestFor(widget, dashboardFilters, catalog)`)**
1. For each dashboard filter `k` with a value, and the widget's model `M`:
   - **Model measures:** applies if `k` is in the catalog's `models[M].breakdowns`. Otherwise it is **not sent**, and the widget shows the reason from the new catalog field `models[M].filter_refusals[k]`. The server builds that field with the planner's own `_breakdown_refusal` (`graph.py:224-232`), so the wording always matches a refusal.
   - **Governed measures:** applies only if `k` is in the measure's new `honours` list (S5) **and** has exactly one value.
2. Per-widget filters (stored in `definition_v2.query.filters`) are combined with dashboard filters by AND. On the same key, the request carries the **intersection**. If the intersection is empty, the widget shows "This widget is limited to Makro, which the dashboard filter leaves out." and does not query.
3. Date: `period.from` / `period.to` from the dashboard, for every model measure (all three models are dated). `reported_soh` reads it as "latest report on or before `to`", and its caption says "as of {to}". Governed: only if `honours` includes `date`.

**Plain-words "not filtered by" line** (always visible under the widget title, not only a tooltip; a figure that looks filtered but is not is the risk). Examples:
- CST widget, distributor filter: "Not filtered by distributor: customer sell-through reports do not say which distributor supplied the stock." (W-CST-NO-DISTRIBUTOR reason)
- DSI widget, store filter (click chip): "Not filtered by store / site: store / site comes only from customer sell-through reports. Distributor sell-out has no store." (W-SITE-CST-ONLY)
- Weeks of cover, customer filter: "Not filtered by customer: channel stock and weeks of cover are worked out per distributor and product only." (W-A3-GRAIN-LOCK reason)
- Weeks of cover, date range: "Not filtered by date: stock is the latest count, so the date range does not change it."
- Governed metric with two customers picked: "Not filtered by customer: this metric takes one customer at a time."
- Several at once: "Not filtered by distributor, store / site", followed by the reasons in a popover.
- Wall ids are never shown to users. They stay in `data-wall` for tests.

**S5, API (MUST, small).** Today `_plan_governed` passes filters the handler then ignores:
- `a3_stock` reads only `distributor_id` and `product_id` (`handlers/a3_stock.py:166-167`).
- `a1_pve` reads only period and `bu` (`handlers/a1_pve.py:65-67`).
- `a2_cpor` reads `customer_id` and `bu`, and **refuses any period** (`handlers/a2_cpor.py:44,105,113`).

So a customer filter on `weeks_of_cover` or `pipeline_inbound` is accepted in v2 and silently not applied (finding F1). Fix:
- A server table, keyed by handler, of the filter ids each handler reads (plus `date`), exposed as `honours` on governed catalog measures.
- `_plan_governed` refuses any other filter with a plain reason, instead of passing it through.
- Test each handler family.

---

## 4. Widget editor on `/semantics/v2/catalog`

The three-column layout stays (`WidgetEditorDialog.tsx`): list on the left, live preview and controls in the middle, visual and title on the right. It is full screen at xs.

1. **Measure list** (left), grouped by the catalog's models: "Distributor sell-out (DSI)", "Customer sell-through (CST)", "CPOR promotion lines", then "Other governed metrics" (v1 metrics, `handler_backed` only, not `refuse_all`).
   - Searchable. Each row shows the label and its unit.
   - Pick one or more measures **from one model**. A measure from another model is disabled, with the W-CUSTOMER-ROLE reason as the tooltip and inline note. A governed metric is picked on its own.
   - **Pending items** (`catalog.pending`) appear greyed under "Not available yet", with their reason. For example: "Customer stock cover is not defined for the builder; show reported stock beside units per week (no derived cover)." The catalog is honest about gaps.
2. **Breakdowns:** chips of the breakdowns all chosen measures allow, grouped by group (Time, Product, Customer, Distributor, Store, Promotion), at most 3, in order (first = category or x axis, second = series).
   - Governed: the old grain-set chips (`grain_sets`).
   - A blocked chip is disabled with its refusal reason.
3. **Period grain:** week, month, quarter or year, shown when period is chosen.
4. **Filters (this widget only):** the same pickers as the bar, limited to the model's breakdowns. Shown as a summary row "Filters: Business unit = Notebook".
5. **Rows:** sort (a measure or breakdown, asc/desc) and row limit (default 500, max 5,000). "Top N" on charts uses the existing `ChartControls` viewer control.
6. **Visual** (right): tiles as today. Tiles that do not fit are disabled with the reason ("Pie needs one category and a measure that adds up").
7. **Display options** for the chosen visual: KPI compare and sparkline toggles; bar + line (which measure is bars); dual axis (right-axis measure); table conditional colour rules.
8. **Preview:** live v2 execute **with the current dashboard filters** (switch: "Preview with dashboard filters", on by default), debounced 300 ms. A refusal shows next to the control that caused it (the refusal names its measure or filter). The "not filtered by" line shows in the preview too.
9. **Title:** automatic ("Sell-through units by customer and week"), editable.

**Visual fit rules (`visualsFor(measures, breakdowns, catalog)`):**

| visual | fits when | rank |
|---|---|---|
| KPI | any; shows `totals[first measure]`. Compare = a second request with the compare window; delta % = (a-b)/b, "—" when b is 0 or null (same null rule as `calc.py` pct_change); ratio measures show the change in points. Sparkline = a third request with `period` at auto grain (up to 26 weeks: week; up to 2 years: month; else quarter). No sparkline for `reported_soh` (W-SNAPSHOT-NOT-SUMMED) or for governed measures without a period grain set | MUST |
| Table | any; AG Grid; names only; units in headers | MUST |
| Conditional colour (table) | rules on a measure column: `< <= > >= between`, tone good/warn/bad, at most 3. Cell tint from theme tones **plus** a text marker in the cell's aria-label and a small dot glyph, so colour is not the only signal; 4.5:1 contrast in both themes. **No default thresholds**; the user sets them | MUST |
| Columns (`bar`) | one category or period; 1-2 measures (grouped) | MUST |
| Ranked bars (`hbar`) | one category; 1 measure | MUST |
| Stacked | period + one category, **additive** measure only (stacking distinct counts or ratios misleads) | MUST |
| Line / area | period required; one category or 2+ measures as series; area stacked only for additive measures | MUST |
| Bar + line (`combo`) | period or one category; exactly 2 measures; same unit (different units: suggest dual axis). `TrendChart` mixed kinds, no new component | MUST |
| Pie / donut | one category, one **additive** measure, all values ≥ 0 (not `dealers`, `stores_reporting`, `cases` or ratios) | MUST |
| Dual axis | 2 measures with different units; add `axis: 'left' \| 'right'` per series to `TrendChart` (second Recharts `YAxis`), both axes titled with units | SHOULD |
| Scatter | one category, 2 measures (x, y); new `ScatterPlot` in `charts.tsx` on Recharts `ScatterChart`; names in tooltips | SHOULD |
| Pivot | 2 breakdowns; rows = first, columns = second (at most 24 columns, rest refused with "Too many columns; filter or swap"); AG Grid Community has no pivot mode, so the client reshapes. Row and column totals only for **additive** measures; otherwise only the grand total from `totals` | SHOULD |

`effectiveVisual` stays the fallback for a saved visual that no longer fits.

---

## 5. Click to filter, and "view rows"

**Click to filter (S10).** Add an optional `onSelect(datum)` to `RankedBars`, `CategoryBars`, `ShareChart`, `TrendChart` (series legend and x point) and to table rows. Points carry `key` = `{breakdown}:{id or value}` (`RankedBarDatum.key` already exists), so equal names no longer merge (fixes the `categoryPoints` label merge).
- Click → the value is added to the dashboard filter for that breakdown, shown as a chip in the bar with a "from chart" style (outlined, cursor icon) and ×. Ctrl/Cmd-click adds several. Clicking the same mark again, or Esc, removes it. "Clear" removes all click chips.
- Period click (line point, column) → date range set to that bucket, shown as a chip "Week 2026-W14 ×". Clearing restores the previous range.
- Keys the bar does not have (`site_label`, `promo_type`, `status`, `workflow_status`) still become chips. Widgets whose model lacks them show the "not filtered by" line.
- "Unassigned" for an **entity** (id null) is not clickable, with tooltip "Not filterable: no id". The v2 filter takes ids. "Unassigned" for an attribute is clickable (it matches NULL; N-0115 F4).
- Keyboard: marks are focusable and Enter applies, which `ChartFigure`'s hidden data table already supports for screen readers.

**View rows (S11), honest version.** v2 has **no row-level endpoint**. Every v2 answer is aggregated. "View rows" therefore opens a right-hand drawer (full screen at xs). It runs v2 execute with:
- the widget's measures and filters, plus the clicked value (if opened from a mark's context menu), plus the dashboard filters;
- breakdowns = the widget's own, filled to 3 with the model's finest: DSI customer, product, then period week; CST customer, product, site_label (period week if the widget has period); CPOR customer, product, status (case once S19 lands);
- `limit` 5,000.

The drawer shows:
- Title: "Rows behind this figure — grouped by customer, product and week (not single transactions)".
- AG Grid table: names only, units in headers.
- Footer: "Totals match the widget: 10,133 units" from `totals`, and the row count from `explain.row_count`, with "Showing 5,000 of 16,241; narrow the filters" when `truncated`.
- Export CSV.

Governed metrics: the handler's own rows at its grain lock, captioned "Channel Ops figures are worked out per distributor and product; these are those rows." Single source lines (transaction, import batch) are LATER: a new endpoint with tenant + row-security proof.

---

## 6. Widget tools

- **Menu** (the header's three-dot icon, replacing the three loose icons; Edit stays visible): Edit, Duplicate, Full screen, View rows, Export CSV, Export image, Promote to report, Remove (with confirm). Every action has a `data-testid`.
- **Resize / drag:** the existing grid, unchanged, saved through `PATCH /layout` (S3).
- **Duplicate:** POST a new widget with the same `definition_v2`, title "… (copy)", layout `{x: same, y: max y + h, w, h}`. The new card scrolls into view.
- **Full screen:** MUI `Dialog fullScreen`, the same `WidgetBody` with `chartHeight = viewport − 160`, the filter chips and the "not filtered by" line. Esc closes.
- **Export CSV** (client side, from the rows already fetched):
  - Columns from `response.columns`: entity → name only, period → `bucket_key`, measures as raw numbers.
  - Header labels with units ("Sell-out units (units)").
  - UTF-8 BOM, RFC 4180 quoting, and a **formula-injection guard**: prefix `'` to cells starting with `= + - @`, tab or CR.
  - File name `{dashboard}-{widget}-{yyyy-mm-dd}.csv`.
  - A toast says "Exported 500 rows (first 500 of 1,678)" when truncated.
- **Export image (PNG, no library):**
  - Find the widget's single `svg.recharts-surface`, clone it, inline the computed `font-family`, `font-size` and `fill` on text nodes, and set explicit width and height.
  - `XMLSerializer` → Blob URL → `Image` → `<canvas>` at devicePixelRatio 2.
  - On the canvas: theme paper background, the title, a caption line (dashboard filters, date range, "Data to {vintage max}"), the plot, and the legend from the series model (HTML legends do not serialise). Then `toBlob` → download.
  - Enabled only when the body has exactly one Recharts SVG. KPI, table and pivot show "Image export is for charts; use CSV". Check whether `RankedBars` (`charts.tsx:1150`) is SVG or HTML; if HTML, it falls under the same rule. Exports follow the current theme.
- **States** (each card independent, Grafana style):
  - Loading: MUI `Skeleton` shaped like the visual (KPI block, bars, line), not "Loading…".
  - Refetch: a thin `LinearProgress` on the card's top edge **while keeping the previous result** (`placeholderData: keepPreviousData`).
  - Empty: "No sell-out units for Makro in the last 13 weeks.", plus "Clear filters" when filters are active.
  - Refused: amber panel with the refusal reason(s).
  - Error: red panel with "Retry".
  - Truncated: caption "First 500 rows".
  - Footer: "Data to 2026-10-09" (from `explain.data_vintage.max`), the Datadog-style freshness cue.
  - Required filter missing: "Pick a customer above to see this account."

---

## 7. Starter templates (S14)

- Defined in code (`apps/api/app/services/dashboard_templates.py`). `POST /api/v1/dashboards/from-template {key}` creates a **personal** dashboard for the caller with `template_key` set, every widget's `definition_v2` validated by `plan_request` first. Nothing is seeded into `cip`.
- UI: "New ▸ From a starter" and the empty-dashboard state list the three starters.
- Marking: a "Template — editable" chip beside the name, and a one-line description card that can be dismissed per dashboard.
- Only existing v2 measures and breakdowns are used. Grid positions are given as x, y, w, h on 12 columns.
- Data checked on the clone: DSI 2024-01-02 to 2026-10-09 (58,128 rows); CST 8 retailers (Amazon 11,732 lines, to 2026-10-12; others end between June and July 2026; Incredible Connection and Hifi only 2025-06-09); CPOR case window starts 2024-01-01 to 2026-08-03.

### A. Account overview (`account_overview`)
Filters: customer **required**, single; date Last 52 weeks; compare previous period. Model: CST (a retailer reporting its own sales).

| # | title | visual | measures | breakdowns / period | layout |
|---|---|---|---|---|---|
| 1 | Sell-through units | KPI, compare + sparkline | cst_sellthrough.units | - | 0,0,3,5 |
| 2 | Units per week | KPI, compare | cst_sellthrough.units_per_week | - (uses from + to) | 3,0,3,5 |
| 3 | Reported stock on hand (latest report) | KPI, no sparkline | cst_sellthrough.reported_soh | - ; caption "as of latest report on or before {to}" | 6,0,3,5 |
| 4 | Stores / sites reporting | KPI | cst_sellthrough.stores_reporting | - | 9,0,3,5 |
| 5 | Sell-through units by week | line | cst_sellthrough.units | [period] week | 0,5,8,8 |
| 6 | Top products | ranked bars, top 15 | cst_sellthrough.units | [product] | 8,5,4,8 |
| 7 | Stock beside sell-through, by product | table, sort units desc | units, units_per_week, reported_soh | [product] | 0,13,12,10 |
| 8 | Sell-through by store / site | ranked bars, top 15 | cst_sellthrough.units | [site_label] | 0,23,12,8 |

Shows: what this retailer sold, its weekly rate, its latest reported stock, which products and stores sell, and stock beside rate for each product.

Left out, and why:
- **Stock cover and restock flags.** They are proposed decision 5. The catalog's pending texts are shown in the description: "Customer stock cover is not defined for the builder …", "Restock flags live in the sell-through overview's SKU problem rules …".
- **Sales value.** Decision 3.
- **DSI sell-out to this customer as a dealer.** A different customer role (W-CUSTOMER-ROLE). It can be added by hand as a DSI widget.

No conditional colour on widget 7, because there is no agreed threshold.

### B. Sell-through & stock across customers (`sellthrough_stock`)
Filters: date Last 52 weeks; compare previous period; all customers. Model: CST.

| # | title | visual | measures | breakdowns / period | layout |
|---|---|---|---|---|---|
| 1 | Sell-through units | KPI, compare + sparkline | cst_sellthrough.units | - | 0,0,4,5 |
| 2 | Units per week | KPI, compare | cst_sellthrough.units_per_week | - | 4,0,4,5 |
| 3 | Reported stock on hand (latest report) | KPI | cst_sellthrough.reported_soh | - | 8,0,4,5 |
| 4 | Sell-through by customer | ranked bars (click to filter) | cst_sellthrough.units | [customer] | 0,5,6,8 |
| 5 | Sell-through by customer, monthly | line (7 series + Other) | cst_sellthrough.units | [customer, period] month | 6,5,6,8 |
| 6 | Stock beside sell-through, by customer | table | units, units_per_week, reported_soh, stores_reporting | [customer] | 0,13,12,8 |

Shows: sell-through and latest reported stock for each retailer, side by side, and the monthly trend.

Left out: stock cover in weeks and restock flags (decision 5), and value (decision 3). **Naming:** the mandate calls this "Sell-through & stock cover across customers". This proposal titles it "… stock across customers" because no cover figure exists yet. Decision D4.

### C. CPOR cases (`cpor_cases`)
Filters: date **All time** (CPOR dates by case window start; labels say "(window start in period)"); customer and distributor apply. Model: CPOR.

| # | title | visual | measures | breakdowns / period | layout |
|---|---|---|---|---|---|
| 1 | Promotion cases | KPI | cpor.cases | - | 0,0,3,5 |
| 2 | Support USD | KPI | cpor.support_usd | - | 3,0,3,5 |
| 3 | Support ZAR | KPI | cpor.support_zar | - | 6,0,3,5 |
| 4 | Delivery rate | KPI | cpor.delivery_rate | - | 9,0,3,5 |
| 5 | Cases by status | ranked bars | cpor.cases | [status] | 0,5,4,8 |
| 6 | Status and approval status | table | cases, support_usd, support_zar, estimate_units, result_units, delivery_rate | [status, workflow_status] | 4,5,8,8 |
| 7 | Support USD by quarter (window start) | columns | cpor.support_usd | [period] quarter | 0,13,6,8 |
| 8 | Support USD by customer | ranked bars, top 15 | cpor.support_usd | [customer] | 6,13,6,8 |

Shows: how many cases there are, what support they carry, how well they delivered, and how they split by status, quarter and account.

Left out:
- **"Open" cases and case "value".** Proposed decision 4; the pending texts are shown.
- On the clone, the 304 non-excluded cases by `status` are settled 210, ended 74 and cancelled 20. By `workflow_status` they are settled 208, ended 77 and cancelled 19. No status in either field reads as open today, so an "open" widget would show nothing whichever set is picked. This is a raw count of `cpor_case` rows; the model's distinct-case figure applies the line rules and may differ.
- **A list of cases.** There is no case breakdown yet (S19, using `cpor_case.case_name`).
- Cases by status uses bars, not a pie, because `cases` is a distinct count.

---

## 8. Tests and render checklist

**API (pytest via `db_on.py pytest` on cip_test, rolled back)**
1. 0048 upgrade and downgrade (columns, checks; downgrade refuses when new visuals are in use).
2. Migration mapping: 9 cip-shaped rows → the exact definitions above (W5 → hbar with `migrated_from.visual = line`). A second run writes 0. Counts before = after.
3. Migration `--prove` on cip_test data: v1 total = v2 total, rows equal.
4. Widget POST/PATCH with `definition_v2`: valid → 200. Refused (cross-model, wall, limit 5,001) → 400 with the refusal text, nothing written. A v1 body is still accepted.
5. `PATCH /layout` writes only `layout_json`, deletes nothing, and keeps `definition_v2` (regression for `DashboardWorkspace.tsx:135-160`).
6. `filters_json` round-trip. `from-template` makes 3 dashboards whose widgets all pass `plan_request` with no refusals (A with a customer set). Personal to the creator. Anonymous → 401.
7. Catalog `filter_refusals`: CST + distributor = W-CST-NO-DISTRIBUTOR reason; DSI + site_label = W-SITE-CST-ONLY reason. Texts are equal to the planner's.
8. Governed `honours`: weeks_of_cover + customer → refused (not ignored); pipeline_inbound + customer → refused; + bu → applied (value differs from unfiltered on cip_test, or both are 0, documented); support_spend + date → refused with the a2 text.
9. Delivery: R2-shaped report before and after migration gives the same status and `value_preview`. A v2-only report delivers through `run_v2`. Existing schedule runner tests pass.
10. The N-0115 suite (the 25 files) still passes.

**Web (vitest)**
- `visualsFor` v2 rules: pie off for non-additive, stacked off for non-additive, combo needs 2 measures, line needs period.
- `requestFor`: applied vs not applied, with reasons; intersection; governed one value; required filter blocks the query.
- Compare windows (previous period, previous year, leap day) and the delta null rule.
- CSV: names not ids, BOM, quoting, injection guard, unit headers.
- Click reducer: add, toggle, Ctrl add, period set and restore, entity Unassigned not clickable.
- Conditional colour evaluation and aria text.
- Editor: cross-model measure disabled with reason, pending shown, preview refusal placement.
- Card: not-filtered line, skeleton, empty with Clear filters, refused, truncated caption.
- Update `WidgetEditorDialog.test.tsx`, `WidgetChart.test.tsx`, `DashboardWidgetCard.test.tsx`, `widgetModel.test.ts`.
- `tsc`: no **new** errors (standing gate).

**Render checklist** (light and dark, 1280x800 and 390x844; screenshots into the run folder). Data: the visuals on a "Visual check" dashboard on cip_test, plus extended design-lab fixtures (recorded v2 responses) for the visuals cip_test cannot fill (CST, CPOR). Starters need real data: see F8.

- [ ] Each visual: KPI (delta up, down, none; sparkline), columns, ranked bars, stacked, line, area, bar + line, pie, donut, table with 3 conditional-colour rules (+ dual axis, scatter, pivot if built). Names only, axis titles with units, a legend when there is more than one series, nothing clipped.
- [ ] Filter bar: each control, chips, "Filters (n)" drawer at 390, required-filter empty state.
- [ ] "Not filtered by" line on a CST widget with a distributor filter and on weeks_of_cover with a customer filter.
- [ ] Click a bar, a slice and a line point; the chip appears and clears; the period range restores.
- [ ] View rows drawer: totals line, truncation line, CSV.
- [ ] Full screen; duplicate places the copy below; resize and drag persist after reload.
- [ ] CSV opens in Excel with names and units; PNG legible in both themes, with legend and caption.
- [ ] Each state: skeleton, refetch bar, empty, refused, error and Retry, truncated, "Data to".
- [ ] The three starters: "Template — editable" chip, description with what is left out, every widget rendered with real figures.
- [ ] 390 px: grid stacks (`DASHBOARD_STACK_BELOW` 720), no horizontal page scroll, editor full screen, widget menu reachable.
- [ ] Keyboard: menu, chips, chart marks (Enter applies); focus is visible.

---

## 9. Findings, decisions for the operator, deferred

**Findings (FACT unless marked)**
- **F1** (N-0115 v2 governed path): filters a governed handler never reads are accepted and silently ignored.
  - `_GOVERNED_FILTER_MAP` (`graph.py:457-464`) passes `customer_id` to `a3_stock` (reads only distributor and product, `a3_stock.py:166-167`) and to `a1_pve` (reads only period and bu, `a1_pve.py:65-67`).
  - `a2_cpor` refuses any period (`a2_cpor.py:44`).
  - Fixed in S5 by refusing such filters, not ignoring them.
- **F2:** saving a layout re-saves and re-validates every widget against v1 and deletes any widget missing from the body (`dashboards.py:371-420`, `DashboardWorkspace.tsx:135-160`). After migration that would break dragging, or drop `definition_v2`. Fixed in S3.
- **F3:** `deliver_saved_report` does not pass `period_grain` (`report_delivery.py:54-61`). A weekly report (R3) is delivered at the v1 handler's default grain. `value_preview` is the total, so it is not affected; any rows or attachment built from it would be. Left as is (v1 path kept on purpose); flagged.
- **F4:** `categoryPoints` merges rows by label (`widgetModel.ts:113-120`), so equal names collapse into one bar. The v2 path keys by id.
- **F5:** W5 is saved as `line` over [customer, product] and has always rendered as ranked bars. The migration writes `hbar` and keeps `line` in `migrated_from`.
- **F6:** the catalog has two near-identical labels, "Business unit (product line)" (`bu`) and "Business unit (product master)" (`business_unit`). The filter bar uses `bu`. Naming decision D5.
- **F7:** DSI has 4,822 customers, close to the 5,000 limit on the values query. Over 5,000 needs server-side search (LATER).
- **F8:** starters "on real data" can only be rendered against the clone or cip. The app user has no grants on the clone (N-0115 deferred item), and cip_test has 146 DSI rows and no CST or CPOR. To render them: grant the app role on `cip_n0115`, or run the API locally against the clone as owner for screenshots only, labelled as bypassing row security. Decision D3.
- **F9:** on the clone no CPOR case has a status that reads as open, so the "open cases" question is moot on today's data.
- **F10:** CPOR has no case breakdown, so it cannot list cases (S19).

**Decisions for Warren (proposed; options laid out, not picked)**
- **D1, storage shape:** one `definition_v2` JSONB (query + display; NULL = v1) [proposed] vs `query_v2` + `display_v2` vs a `version` int. Easy to change before 0048 ships, costly after.
- **D2, apply to cip:** run 0048 + the migration script on cip after the clone proof and cip_test (with the worker restarted), or keep cip on v1 until GOV-008 verifies N-0115/N-0116. The dual path means not migrating is safe.
- **D3, real-data render:** grant the app role on `cip_n0115` [proposed; also unblocks the scoped timings] vs owner-mode API for screenshots only.
- **D4, starter B title:** "Sell-through & stock across customers" [proposed, no cover figure] vs the mandate's "… stock cover …", which would then need decision 5.
- **D5:** which "business unit" the filter bar means (product line `bu` [proposed, what v1 widgets use] vs product master `business_unit`), and whether to rename one label.
- **D6, compare "previous year":** shift by calendar year [proposed] vs 52 weeks (keeps Monday weeks aligned; differs at 53-week years).
- Already open (from N-0115, not re-decided here): decision 4 (CPOR open / value), decision 5 (customer stock cover / restock), decisions 2 and 3 (sales value), day grain (decision 1).

**Deferred (record as `finding.defer` on N-0116)**
- Report builder `/reports` editing on v2 (it keeps reading the v1 columns, which stay populated for v1-expressible reports).
- Single source-line drill endpoint.
- Server-side value search over 5,000.
- Text/note widget.
- Colour-scale tables.
- Cross-model widgets (two queries, one visual; W-CUSTOMER-ROLE rules apply).
- `prior_year` / `share_of_total` calculated measures (N-0115 deferred).
- GOV-008 independent verification of N-0115 (still open) and of N-0116 (a different run from the implementation run).
