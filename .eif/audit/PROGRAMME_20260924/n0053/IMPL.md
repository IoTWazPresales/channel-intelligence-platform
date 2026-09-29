# N-0053 implementation record — line identifier `both` as two columns

Run `N0053_IMPL_20260929`, actor `impl-n0053`, baseline BLN-0017 @ `a8755854`. Design: `DESIGN.md` (same folder).

## What shipped (working tree, this run)

**API (file-backed tenant preference, no `cip` write)**
- `apps/api/app/services/commercial_tenant_profile.py` — `LineIdentifierPreference = Literal["sku","sales_model","both"]`; `both` accepted by the validator.
- `apps/api/app/services/grid_fields.py` — `GridFieldSpec.identity` (sku/sales-model row-key pair), `identity_items()` emits two `group: "identity"` items (`default_hidden: True`); `grid_field_items()` leads with them and drops the pair from the fact keys. Identity set on the 10 hosts that render a line column: `sellout.commercial-lines`, `inventory.customer` (prefixed keys) and `pricing.facts`, `pricing.recommendations`, `buy-plans`, `roadmap`, `forecasts`, `channel-ops.sell-out`, `channel-ops.movements`, `channel-ops.inventory`.
- Tests: `apps/api/tests/test_commercial_tenant_profile.py` (+1), `apps/api/tests/test_grid_fields.py` (+3, group set now `{identity, fact, reference}`). **91 passed** (both files).

**Web — one helper is the only source of identity ColDefs**
- `apps/web/src/features/tenant/lineIdentifier.ts` — `LineIdentifierPreference` gains `both`; `lineIdentifierColumns(pref, fields, base)` returns one welded column (`colId line_identifier`, valueGetter with fallback) for `sku`/`sales_model`, or two real `field` columns (`line_identifier_sku`, `line_identifier_sales_model`, fixed headers `SKU` / `Sales model`, `—` for empty) for `both`. Real fields ⇒ sortable/filterable via `EnterpriseDataGrid` defaultColDef. `lineIdentifierHeaders/Values` for MUI tables; `lineIdentifierCoveredFields` for the picker.
- `apps/web/src/features/tenant/useLineIdentifierPreference.ts` — returns `{ preference, header, value, headers, values, columns }`.
- `apps/web/src/features/workbench-ui/useFactColumns.ts` — new opts `lineIdentifier` + `lineIdentifierColDef`; returns `identityColDefs`; preference-covered identity keys are removed from the picker items and from `optionalColDefs` (no duplicate column after a preference flip; stored picks pruned against the *full* registry so they come back on a flip back). `FactColumnPicker` renders a leading **Line identity** group when the registry offers the identifier the preference does not pin.
- `apps/web/src/app/(app)/settings/page.tsx` — third option `SKU and sales model number (two columns)`; type imported from the shared module.
- Tier A picker hosts → `...factColumns.identityColDefs`: `ForecastsWorkspace`, `pricing/page` (both grids), `roadmap/page`, `buy-plans/page`, `inventory/page`, `sell-out/SellOutTab` (fact + channel grids; zero-sellout list via `lineId.columns`), `sell-out/ChannelOpsInventoryTab`, `sell-out/ChannelOpsMovementsTab` (movements via hook; product totals via `lineId.columns`).
- Non-picker AG Grid hosts → `lineId.columns<Row>(fields, base)`: `SettlementDesk`, `PromoPlanBuilderPanel`, `CporPromoLoadPanel`, `LineupPlanGrid`, `admin/products/page` (pinned identity; the master grid's own `sku`/`sales_model_name` columns are untouched), `admin/distributors/page` (sell-out + inbound grids), `commercial-planner/page` lines grid (`both` → two columns; single modes keep the `#product_id` fallback column).
- MUI tables → `lineIdent.headers` / `lineIdent.values(...)` one cell per column: `commercial-planner/page` (coverage lineup rows, product gaps, coverage lines), `CurrentLineupSection` case-lines table.
- Text-slot consumers (`CoverLensView` caption/subtitle, `SettlementDesk` drawer title, planner drawer heading, `CurrentLineupSection` workbench `colId === 'sku'` cell/label/search) keep `lineId.value/header` — under `both` these read `SKU · Sales model` / `sku · model`. Recorded as a deferred finding (below), not a second column mechanism.

## Column-by-column mapping (display only; stored keys unchanged)

| Host row keys | `sku` / `sales_model` | `both` |
|---|---|---|
| `sku` + `sales_model_name` | 1 welded col, fallback to the other | `field: sku` (SKU) + `field: sales_model_name` (Sales model) |
| `product_sku` + `product_sales_model_name` | same | `field: product_sku` + `field: product_sales_model_name` |
| `sku` + `salesModel` (settlement desk) | same | `field: sku` + `field: salesModel` |

## Validation (this run)
- `tsc --noEmit` exit 0 (web).
- eslint on the 23 changed web files: 0 errors, 11 warnings — all pre-existing `react-hooks/exhaustive-deps` on untouched delete-mutation hooks.
- Focused vitest: `features/tenant`, `useFactColumns.test.tsx`, `features/settlement`, `cpor-cases` — 13 files / 58 tests green (incl. 8 new lineIdentifier cases, 3 new useFactColumns identity cases, 1 new picker group case).
- Full `pnpm test:web` — see CURRENT.md line for the count.
- API pytest (`test_grid_fields.py`, `test_commercial_tenant_profile.py`) 91 passed.
- No SQL written; no `cip` write (tenant preference is a JSON file under `local_storage_path/tenant_profiles/`).

## Rendered check (browser, same run — self-verification, not independent)
Browser MCP (`cursor-ide-browser`) was denied by the EIF guard for the first part of the run, then admitted. Smoke performed against the live stack after restarting both processes:

- **Stale runtime found and fixed.** The API on :8001 was an orphaned uvicorn server child (PID 36560, started 09-24) whose `--reload` parent was gone, so it had been serving 5-day-old code — saving `both` returned `invalid value 'both'; expected one of ['sales_model','sku']`. Killed it and relaunched `pnpm dev:api`; `/health` ok. Web :3000 is a `next start` production build — rebuilt (`pnpm --filter @cip/web build`, exit 0, `BUILD_ID 3-o-C3zRc7wIPbQZahIiq`) and restarted.
- `/settings` → Line identifier offers `SKU` / `Sales model number` / `SKU and sales model number (two columns)`; saved `both` → *Overrides currently set* lists `line_identifier_preference`; value survives reload.
- `/forecasts`, `/pricing` render empty states (no forecast/pricing data on this DB) — not usable as identity-column proof.
- `/stock?lens=movement` → Inventory tab (`channel-ops.inventory`), distributor Mustek (DIST-000009), under `both`: headers `Product | SKU | Sales model | Reported SOH | Derived stock | Calculated SOH | Variance | Recon status`; both identity columns carry the filter icon; clicking the `Sales model` header sorts ascending with the sort arrow. Columns picker shows only `Fact fields` + `Reference` (no SKU / Sales model, no Line identity group).
- Flip back: `/settings` → `SKU` → Save; same Inventory grid renders one `SKU` column; Columns picker shows a leading **Line identity** group offering `Sales model`, then `Fact fields`, `Reference`.
- Tenant preference left at `sku` (the original default).

`quality.rendered` = pass by **self-verification** in the implementation run; R2 independence for the referent still requires a different run/actor.
