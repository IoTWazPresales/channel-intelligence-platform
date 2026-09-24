# N-0034 — implementation pass 1 of 2 (ORM-fact Tier A grids)

**Node:** N-0034 "Stage 2.4 + grid parity" (R2, ui) · **Design:** `n0034/DESIGN.md` (D-0030) · **Date:** 2026-09-24 · **Branch:** `feat/ns-2-brief-nav-collapse`
**Lenses applied:** frontend-engineer, backend-engineer, test-engineering-specialist, accessibility-specialist. Skill tool unavailable; lenses applied by name.
**Commits:** `11f7765b` (API registry and serializers), `08e5f974` (web hook, picker, hosts, BACKLOG-201). Not pushed.
**Verification rung:** self-check only (same session). GOV-008 verification still has to run separately.

## What was built

### API (`11f7765b`)
- `apps/api/app/services/grid_fields.py`: `GRID_FIELDS` registry (`GridFieldSpec`: model, default_keys, joined_extras, hidden_internal, label_overrides, static_keys, auto_hide); `grid_field_items` (picker list: fact fields sorted by key, then reference fields; every item `default_hidden: true`); `fact_row_dict(row, grid_id, exclude=)` (json-safe mapper values, merged **under** each endpoint's own dict so existing keys win); `customer_labels` / `distributor_labels` (one `IN (...)` query per list, no per-row lookups); `reference_fields`.
- `apps/api/app/api/v1/endpoints/grid_fields.py` + `router.py`: `GET /api/v1/grid-fields/{grid_id}` returns `{grid_id, items:[{field,label,group,default_hidden}]}`, or 404 `unknown_grid`.
- `shipping.py`: `INBOUND_GRID_DEFAULT_FACT_KEYS` and the label override moved into the registry. `/shipping/inbound-optional-columns` is now an alias that returns the registry's inbound fact group in the old `{field,label}` shape. `_fact_to_dict` gets `fact_row_dict` merged under it (`raw_source_row` stays opt-in).
- Row serializers were pulled out as pure functions and now merge the registry fields: `commercial_line_row_dict` (sellout.py), `inventory_customer_row_dict` (inventory.py, **adds `customer_name`**), `pricing_fact_row_dict` / `pricing_recommendation_row_dict` (pricing.py), `buy_plan_row_dict` (buy_plans.py), `roadmap_row_dict` (roadmap.py), `forecast_row_dict` (forecasts.py; wraps the existing `_serialize`).

Grids registered: `inbound-shipments`, `sellout.commercial-lines`, `inventory.customer`, `pricing.facts`, `pricing.recommendations`, `buy-plans`, `roadmap`, `forecasts`.

**Hidden columns, checked fact by fact.** On all new grids: `tenant_id`, `raw_source_row`, anything ending `_token`, and any JSON/JSONB column (`explanation_factors`, `analogue_basis` as an *optional* field; `analogue_basis` is already a default forecasts column). `pricing.recommendations` also hides `reviewed_by`, because it identifies a person (a [PII]-like user id or email). No other fact in scope has person-identifying columns: I checked `FactSalesSellout`, `FactInventoryCustomer`, `FactPricing`, `PricingRecommendation` (+ RecommendationMixin), `FactBuyPlan`, `FactProductRoadmap` and `FactDemandForecast`. Inbound keeps its historic list (`auto_hide=False`): `raw_source_row`, the resolver tokens and "Customer remarks (source)" are still offered, as before.

**Reference fields (D7), all default-hidden.** Sell-out: customer code and distributor code. Inventory: customer code. Pricing facts: customer name and customer code. Buy-plans: distributor name and distributor code. Forecasts: customer name and code, distributor name and code. Inbound: customer code and distributor code.

### Web (`08e5f974`)
- `features/workbench-ui/useFactColumns.ts`: fetches `['grid-fields', gridId]` (5 min staleTime). It keeps the layout under `cip.grid.<gridId>.optional.v1` (or a `storageKey` override), reading on mount, **merge-writing** (other keys in the stored object survive) and pruning unknown fields once the list has loaded. Storage failures are caught, so the layout just doesn't persist. The default formatter is `fmtCellForKey` (dates, JSON), reused from the shipping helpers; `formatters` / `colDefFor` hooks are available. Returns `{optionalColDefs, optionalFields, pickerProps, openPicker, loading}`.
- `features/workbench-ui/FactColumnPicker.tsx`: wraps `ColumnPickerDialog size="md"` with groups "Fact fields" then "Reference", search, and Reset all, which sets `[]`, the default (codes hidden). `FactColumnsButton` is the toolbar opener. It uses `aria-haspopup="dialog"`, a visible text label, and shows "Columns (n)" when optional columns are on. No second dialog implementation.
- Inbound (`InboundShipmentsWorkspace.tsx`): moved onto the hook with `storageKey: 'cip.commercial.inbound-shipments.grid.optional.v1'`, so existing layouts keep working. pageSize still persists in the same object (merge-write on both sides). Its title, description, testids and raw-row width/wrap are kept. It now also offers the Reference group.
- Hosts adopted (DESIGN.md rows 1, 6, 7, 8, 9, 10, 14): `sell-out/SellOutTab.tsx` (commercial lines only; the channel-ops branch is pass 2), `inventory/page.tsx`, `pricing/page.tsx` (both tabs, one hook each), `buy-plans/page.tsx`, `roadmap/page.tsx`, `features/stock/ForecastsWorkspace.tsx`. Optional ColDefs come before the delete column. The button sits in `ModuleGridToolbar`'s `leading` slot; `ModuleGridToolbar` itself is unchanged.
- D7 name-only sweep (DESIGN.md section 5):
  - SellOutTab: Customer = `customer_name` (was `name (code)`), Distributor = `distributor_name` (was `distributor_code`).
  - Inventory: Customer = `customer_name` (was `customer_code`).
  - ChannelIntelligenceWorkspace: `customerLabel` = name only, falling back to `Customer <id>`.
- SellOutTab's lines `ModuleDataSection` now has `onRetry` (criterion 3; it had no Retry before).
- `docs/BACKLOG.md` BACKLOG-201: a pass-1 progress row plus the criterion-4 per-host toolbar table (search → N-0041, saved views → N-0042, export → N-0043).

## Criteria (whole node; pass-1 share)

| # | Criterion | Pass 1 status | Evidence |
|---|---|---|---|
| 1 | One generic picker on Tier A grids, via registry + layout key, through ColumnPickerDialog | **PASS for 8 grids** (7 new + inbound); PARTIAL for the node (7 grids are pass 2) | `useFactColumns.ts`, `FactColumnPicker.tsx`; every host renders `<FactColumnPicker {...pickerProps}/>`; `grep ColumnPickerDialog` shows no new direct callers outside the wrapper |
| 2 | Codes are their own pickable columns; identity cells name-only | **PASS** on the pass-1 hosts plus ChannelIntelligence | registry `joined_extras`; SellOutTab/inventory/CI diffs; pytest `test_codes_are_reference_fields` |
| 3 | Loading / error+Retry / empty kept | **PASS** | every adopted host still wraps the grid in `ModuleDataSection` with isLoading/isError/onRetry/isEmpty; SellOutTab gained onRetry |
| 4 | Toolbar parity table recorded under BACKLOG-201 | **PASS** | `docs/BACKLOG.md` BACKLOG-201 "Toolbar parity per host" |
| 5 | Tier B / C fixed | **PASS** (untouched) | no Tier B/C file in the diff |
| 6 | BACKLOG-200 held; no Enterprise | **PASS** | `MasterColumnPickerDialog` / `ColumnSelectorModal` untouched; no new deps; AgGridReact only in `EnterpriseDataGrid` |
| 7 | Mechanism carries Stage 2.5 | **PASS (by construction)** | any registry field (e.g. `sku`, `sales_model_name`) becomes a column with no web change; not exercised |
| 8 | No density change, no migration, read-only on cip | **PASS** | no DDL/Alembic; the smoke below is GET-only |
| 9 | tests / tsc 0 / eslint clean / API registry guard | **PASS** | see Commands |
| 10 | Browser smoke 1280x800 on 3 Tier A grids | **UNABLE (not mine)**: the orchestrator runs it after a rebuild; covered by the roadmap host test (open, add, remount, persists) | `roadmap/page.test.tsx` |
| 11 | BACKLOG 201 and 140-display stamps on completion | **PARTIAL**: 201 progress recorded; the 140 display-half stamp and the 201 close wait for pass 2 | `docs/BACKLOG.md` |

## Commands and results
- `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_grid_fields.py -q`: **38 passed**. The parity guard runs per grid: catalog fields ⊆ keys of a row built by the endpoint's own serializer from transient ORM rows (no DB). Other checks: codes are reference + default_hidden; internal columns are never offered or merged; JSON and `reviewed_by` are hidden; `fact_row_dict` is json-safe; existing keys win; `customer_labels` is 1 query; the route returns 200 or 404; the inbound alias equals the registry fact group.
  - The guard caught a real gap on its first run: 4 inbound columns (`crad_date`, `fact_upsert_key`, `resolved_customer_id`, `resolved_distributor_id`) had always been offered but never serialized, so they showed blank. Fixed by merging `fact_row_dict` under `_fact_to_dict`.
- Related API tests: `test_shipping_amount_scale`, `test_shipping_commercial_kpis`, `test_shipping_distributor_display`, `test_demand_forecast_compute`, `test_rbac_r1c_admin_gates`, `test_cpor_rbac_r1_auth` passed. `test_shipping_newly_landed.py` ERRORs at setup: the conftest write-guard refuses it on `cip` (pre-existing, environmental, not run).
- Read-only in-process smoke `n0034/ro_smoke_pass1.py` (prints `current_database: cip`; GET only). All 8 list endpoints return HTTP 200 with **no offered field missing** from any row. The one exception is inbound `raw_source_row`, which is opt-in via `include_raw_row` and requested by the web only when selected. Rows returned: forecasts 50, sell-out 20, inbound 20; roadmap, buy-plans, pricing ×2 and inventory are **0 rows on cip**, so for those only the unit parity test proves the payload. Reference keys are populated on the first forecasts and sell-out rows. All 8 `grid-fields/*` return 200.
- `pnpm --filter @cip/web exec tsc --noEmit`: **exit 0**.
- `pnpm --filter @cip/web exec vitest run src/features/workbench-ui src/app/(app)/{roadmap,forecasts,channel-intelligence,sell-out,shipping,supply}`: **10 files, 25 tests passed**. New tests: `useFactColumns.test.tsx` (7: fetch + default empty, toggle → labelled ColDef + persist, reset → `[]`, restore + prune, storageKey override keeps pageSize, localStorage throws, formatter/colDefFor, FactColumnPicker groups/toggle/reset/search) and `roadmap/page.test.tsx` (host: open picker → add column → grid shows it → "Columns (1)" → localStorage → remount restores). `ColumnPickerDialog.test.tsx` still 5/5.
- `ESLINT_USE_FLAT_CONFIG=false pnpm --filter @cip/web exec eslint <12 changed files>`: **0 errors, 7 warnings**, all pre-existing `react-hooks/exhaustive-deps` on memo arrays that were already there (e.g. `delRow.isPending`, `openDrawer`, `custOptions`).

## Left for pass 2 (not started)
- Computed-row grids (registry `static_keys`, no `model`): channel-ops sell-out (`SellOutTab` channel branch, add codes), channel-ops movements (2 mounts), channel-ops inventory (derived stock), plan-vs-executed drill, cover distribution, channel intelligence columns (also move its welded **product** label to name-only if Stage 2.5 decides so; only the customer label changed here).
- Listings (`MarketSurface.tsx`, `listing_to_dict`, customer name joined server-side) and customer-commercial-terms.
- Non-Tier-A name-only items from DESIGN.md section 5: `admin/shipment-evidence/page.tsx:406` and `admin/distributors` (the editable code select needs Warren, Q2).
- Closing stamps: BACKLOG-201 (close after pass 2) and BACKLOG-140's display half.
- A pytest parity case per computed grid (static keys ⊆ computed row keys).

## Findings and notes
- **Behaviour change (small):** the inbound optional list no longer offers `tenant_id`. It was always offered but never in the payload, so it only ever showed a blank column. The alias is otherwise identical; `test_inbound_alias_matches_registry_fact_group` pins it.
- **Beyond the design (small, recorded):** pricing facts, buy-plans and forecasts had **no** customer/distributor identity column, so their Reference group offers the *name* as well as the code. Otherwise a steward could add only a code, which works against D7's name-first intent. All are default-hidden, so the defaults don't change.
- **Performance note (not fixed; out of scope):** the list endpoints still resolve the product with `await db.get(DimProduct, id)` per row, which was already there (the session identity map caches repeats). The new code/name joins are batched as the design asks.
- Concurrent work: other sessions have staged and unstaged changes on this tree (settlement, CPOR, promotions files and `.eif/**`). Both commits used `git commit -- <explicit paths>`, so nothing of theirs is included. No N-0040 file (lineup resolver, catalog, BulkLineupBackfillDialog, lineupBackfillArchivePath) was touched.

## Questions for Warren (carried from DESIGN.md section 7, unchanged)
1. Filter dropdown options (`SellOutTab` distributor/customer autocompletes, ChannelOps, inbound, DSI strip) still show `name (code)`. Should they show the name only, with the code as secondary text? D7 names columns only, so I left them alone.
2. May the distributors admin editor show names while keeping the code as the stored value?
3. Should the exceptions inbox stay out of scope as a worklist?
