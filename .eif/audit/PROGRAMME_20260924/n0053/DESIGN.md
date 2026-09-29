# N-0053 — Line identifier `both` as two columns (Stage 2.5)

Run `N0053_IMPL_20260929` · actor `impl-n0053` · branch `feat/ns-2-brief-nav-collapse` · base `a8755854`.

## Outcome

Tenant preference `line_identifier_preference` gains `both`. Under `both`, every grid that labels a
product line shows **two real field columns** — `SKU` and `Sales model` — each sortable and
filterable through the grid's `defaultColDef` (`EnterpriseDataGrid` sets `sortable`/`filter` true).
Under `sku` / `sales_model` nothing changes: one welded column with the existing fallback.

## One mechanism (AC1)

| Layer | Change |
|---|---|
| `features/tenant/lineIdentifier.ts` | `'both'` in the type. `lineIdentifierColumns(pref, {sku, salesModel})` is the **single source** of the identity ColDef(s): 1 welded column (`colId line_identifier`, unchanged) or 2 field columns (`line_identifier_sku`, `line_identifier_sales_model`). Text helpers (`header`/`value`) render `SKU · Sales model` / `sku · model` for non-grid text; `headers()`/`values()` arrays for MUI tables. |
| `services/grid_fields.py` | `GridFieldSpec.identity` = the grid's `(sku_key, sales_model_key)` pair, emitted by `grid_field_items` as group `identity` (default hidden). The registry is the field list; the preference decides which identity fields are pinned defaults. |
| `useFactColumns` | New option `lineIdentifier: {sku, salesModel}`. Reads the preference, returns `identityColDefs` from `lineIdentifierColumns`, and **removes from the picker items and from `optionalColDefs` any identity field the preference already shows**. So: `sku` → picker offers *Sales model* as an addable column; `sales_model` → offers *SKU*; `both` → identity group empty (both pinned). No second toggle system, no duplicate columns after a preference change. |
| `FactColumnPicker` | Renders the `identity` group ("Line identity") when the hook leaves anything in it. |
| Tier A hosts | Replace the welded ColDef with `...factColumns.identityColDefs`; pass `lineIdentifier` keys. |
| Non-picker hosts | Use `lineId.columns(...)` (AG Grid) or `lineId.headers()/values()` (MUI tables) — same helper, no picker. |
| `/settings` | Third option: "SKU and sales model number". API valid-values set + Literal gain `both`. |

## Column-by-column mapping (display only — no stored value changes)

| Host | grid_id | sku key | sales model key | Mechanism |
|---|---|---|---|---|
| ForecastsWorkspace | `forecasts` | `sku` | `sales_model_name` | picker |
| pricing (facts) | `pricing.facts` | `sku` | `sales_model_name` | picker |
| pricing (recommendations) | `pricing.recommendations` | `sku` | `sales_model_name` | picker |
| roadmap | `roadmap` | `sku` | `sales_model_name` | picker |
| buy-plans | `buy-plans` | `sku` | `sales_model_name` | picker |
| inventory | `inventory.customer` | `product_sku` | `product_sales_model_name` | picker |
| SellOutTab commercial lines | `sellout.commercial-lines` | `product_sku` | `product_sales_model_name` | picker |
| SellOutTab channel-ops | `channel-ops.sell-out` | `sku` | `sales_model_name` | picker |
| ChannelOpsInventoryTab | `channel-ops.inventory` | `sku` | `sales_model_name` | picker |
| ChannelOpsMovementsTab | `channel-ops.movements` | `sku` | `sales_model_name` | picker |
| CoverLensView | `cover.distribution` | text cell + subtitle | — | `value()` (`sku · model`) |
| SettlementDesk | — | `sku` | `salesModel` | `columns()` |
| commercial-planner grid | — | `product_sku` | `product_sales_model_name` | `columns()` |
| commercial-planner MUI tables ×3 | — | `product_sku` | `product_sales_model_name` (`?? model_raw`) | `headers()/values()` |
| CurrentLineupSection table | — | `product_sku ?? sku_raw` | `product_sales_model_name ?? model_raw` | `headers()/values()` |
| CurrentLineupSection workbench (`colId 'sku'`) | — | same | same | **text weld in one cell** — the workbench has its own column model (BACKLOG-190/198); two columns there is a workbench change, deferred |
| admin products | — | `sku` | `sales_model_name` | `columns()` |
| admin distributors ×2 | — | `product_sku` | `product_sales_model_name` | `columns()` |
| LineupPlanGrid | — | `sku` | `sales_model_name` | `columns()` |
| PromoPlanBuilderPanel | — | `product_sku` | `product_sales_model_name` | `columns()` |
| CporPromoLoadPanel | — | `product_sku` | `product_sales_model_name` | `columns()` |

Not touched: `inbound-shipments` (shipment-evidence identifier preference is still Warren's open item,
STAGED_WORK_PLAN §2), `pve.drill` and `listings` (already expose `product_sku` / `product_sales_model`
as pickable static keys; no welded identity column), `channel-intelligence`, `customer-terms`.

## Storage / cip

Preference persists in `{local_storage_path}/tenant_profiles/{tenant}.json` (file, not `cip`). Column
layouts stay in `cip.grid.<gridId>.optional.v1`. No DB writes, no migration.

## Verification plan

Unit: `lineIdentifier.test.ts` (both header/value/columns), `useFactColumns.test.tsx` (identity
pinning, complementary field offered, no duplicate on preference change), `test_grid_fields.py`
(identity group ⊆ serialized keys), `test_commercial_tenant_profile.py` (`both` roundtrip).
`tsc --noEmit` 0, eslint clean on changed files, `pnpm test:web` green.
Browser (1280×800, `:3000`): `/settings` → set `both` → forecasts + pricing + sell-out show two
pinned columns, sort and filter on each; picker no longer lists SKU / Sales model; set back to `sku`
→ one column, picker offers *Sales model*; reload persists.
