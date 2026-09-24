# N-0034 design — Stage 2.4 all-columns picker + grid parity

**Seat:** feature definition (moment b). **Lenses:** product-manager, product-interaction-designer, ui-visual-design-specialist, architecture-specialist, frontend-engineer. **Tree:** `feat/ns-2-brief-nav-collapse` (dirty), 2026-09-24. Read-only. Conforms to D3, D7, D-b, BACKLOG-200 held, BACKLOG-193 dropped.

## 1. Inbound-shipments optional-columns pattern (FACT)

- API `GET /api/v1/shipping/inbound-optional-columns` (`shipping.py:695-706`): every `FactInboundShipment` mapper column minus `INBOUND_GRID_DEFAULT_FACT_KEYS` (`:59-71`), labels via `_human_column_label` (`:114`) + overrides (`:89`).
- Web (`InboundShipmentsWorkspace.tsx`): fetch `:186-190`; localStorage `cip.commercial.inbound-shipments.grid.optional.v1` (`:48`, read `:192-208`, write `:216-223`, stores `{optionalFields,pageSize}`); prune unknown fields `:210-214`; optional ColDefs appended `:542-555`; md `ColumnPickerDialog` with one group, reset → `[]` (`:1007-1031`).

**Does it generalise?** Yes for the list and persistence halves, with two gaps:
1. The field list comes from the ORM mapper, but row payloads are **hand-built dicts** (`shipping.py:629-692`, `buy_plans.py`, `roadmap.py`, `pricing.py:47,126`, `inventory.py:46`, `forecasts.py` `_serialize`). Inbound works only because its serializer happens to emit nearly every column. Elsewhere a listed field would show blank.
2. Joined labels (`customer_code`, `distributor_code`) are not mapper columns, so introspection alone never offers them.

## 2. Decision: field-list source (PROPOSED, architecture)

**Generalise the inbound endpoint to a server-side registry. Do not build a web-side TS registry.**

- New `app/services/grid_fields.py`: `GRID_FIELDS: dict[grid_id, GridFieldSpec(model | None, default_keys, joined_extras, hidden_internal)]`, plus one route `GET /api/v1/grid-fields/{grid_id}` that returns `{items:[{field,label,group:'fact'|'reference',default_hidden:true}]}`. Inbound's route becomes a thin alias, so the URL does not change.
- `fact_row_dict(row, model)`: reads the same mapper `column_attrs` and is **merged under** each endpoint's existing dict (existing keys win, additive only). The list and the payload then come from one source, so D3's "every field" cannot drift.
- For computed rows (Cover, PVE drill, channel-ops derived stock) the spec declares a static key tuple next to the serializer.
- **Why not a web registry:** the TS row types are hand-written (`type Row`, `type IntelRow`), not generated. A web list would be a third hand-kept copy and would go stale quietly, which breaks D3.
- **D7:** `joined_extras` adds `customer_code` / `distributor_code` (labels "Customer code" / "Distributor code") in a "Reference" group, `default_hidden: true`. Identity columns keep name only.
- **Stage 2.5:** the 'both' identifier becomes two registry fields, `sku` and `sales_model_name`, so it needs no new mechanism.
- **No migration:** reads only; no DDL.
- **Persistence:** localStorage, key `cip.grid.<grid_id>.optional.v1`, same shape as inbound. No user-preference table was found (grep of `app/models` for `user_pref|preferences|grid_layout|ui_settings`; the grep only proves that search came up empty). The master shell persists AG column state in localStorage (`MasterDataGridShell.tsx:194,234,390`). Server-side layouts would be a later saved-views node (N-0042).

## 3. Tier A grids in scope

"Codes today" means the code is in the row payload now.

| # | Host | grid_id | Row source | Customer code / Distributor code today | In? |
|---|---|---|---|---|---|
| 1 | `sell-out/SellOutTab.tsx` commercial lines `:219-245` | `sellout.commercial-lines` | `FactSalesSellout` | both yes | Yes |
| 2 | `SellOutTab.tsx` channel sell-out `:168-210` | `channel-ops.sell-out` | `channel_ops.py:484` | names only; add codes | Yes |
| 3 | `SellOutTab.tsx` zero-sellout `:158-162` | — | aggregate | — | **No**: a 2-column exception list |
| 4 | `ChannelOpsMovementsTab.tsx` (2 mounts) | `channel-ops.movements` | `channel_ops.py:752` | distributor name only | Yes |
| 5 | `ChannelOpsInventoryTab.tsx` | `channel-ops.inventory` | derived (`derived_stock_rows_for_distributor`) | distributor name only | Yes (static keys) |
| 6 | `inventory/page.tsx` | `inventory.customer` | `FactInventoryCustomer` | code only, **no name** (`inventory.py:67`) | Yes, and add `customer_name` |
| 7 | `pricing/page.tsx` facts | `pricing.facts` | `FactPricing` (has `customer_id`, `channel_id`) | neither | Yes |
| 8 | `pricing/page.tsx` recs | `pricing.recommendations` | `PricingRecommendation` | neither | Yes |
| 9 | `buy-plans/page.tsx` | `buy-plans` | `FactBuyPlan` (`distributor_id`) | neither | Yes |
| 10 | `roadmap/page.tsx` | `roadmap` | `FactProductRoadmap` | n/a | Yes |
| 11 | `exceptions/page.tsx` | — | `ExceptionInboxItem` | n/a | **No**: an inbox worklist (Tier B shape), not `fact_*` |
| 12 | `PlanVsExecutedView.tsx` drill `:372` | `pve.drill` | computed | `customer_label` only; origin UNKNOWN | Yes (static keys) |
| 13 | `CoverLensView.tsx` | `cover.distribution` | computed | both yes | Yes (static keys) |
| 14 | `ForecastsWorkspace.tsx` | `forecasts` | `FactDemandForecast` | ids only (`customer_id`, `distributor_id`) | Yes |
| 15 | `ChannelIntelligenceWorkspace.tsx` | `channel-intelligence` | CST read model | code + name | Yes (static keys) |
| 16 | `MarketSurface.tsx` listings `:512` | `listings` | `CustomerListing` via `listing_to_dict` | `customer_id` only; name joined client-side | Yes |
| 17 | `admin/customer-commercial-terms/page.tsx` | `customer-terms` | `CommercialCustomerTerm` | both, already separate columns `:110-111` | Yes (D7 already met) |

That is 15 grids in, 2 out. Implementation should split this into about three PRs: ORM facts; computed rows; listings and terms.

## 4. Component contract

```ts
// workbench-ui/useFactColumns.ts
useFactColumns<T>(gridId: string, opts?: { formatters?: Record<string,(v)=>string> })
  => { optionalColDefs: ColDef<T>[]; pickerProps: FactColumnPickerProps; openPicker(): void; loading: boolean }
// workbench-ui/FactColumnPicker.tsx: wraps ColumnPickerDialog size="md"
FactColumnPicker({ open, onClose, gridId, items, selected, onToggle, onReset, gridReady })
```
The hook owns the fetch (`['grid-fields', gridId]`), localStorage read, write and prune (the same code as inbound `:192-223`, moved), and the generic formatter. Groups: "Fact fields", then "Reference" (codes). Reset clears the selection to `[]`, which is the default and has the codes hidden.

**Host before/after (roadmap):**
```tsx
// before
const colDefs = useMemo(() => [...base], []);
<EnterpriseDataGrid columnDefs={colDefs} .../>
// after
const fc = useFactColumns<Row>('roadmap');
const colDefs = useMemo(() => [...base, ...fc.optionalColDefs], [fc.optionalColDefs]);
<ModuleGridToolbar extra={<Button onClick={fc.openPicker}>Columns</Button>} />
<EnterpriseDataGrid columnDefs={colDefs} .../>
<FactColumnPicker {...fc.pickerProps} />
```
Inbound moves onto the hook, keeping its existing key through a `storageKey` override so no user's layout resets.

**Tests:**
- pytest, per `grid_id`: catalog fields are a subset of the serialized keys of a seeded row (this is the parity guard); codes are present and `default_hidden`; the inbound alias still returns the same list.
- vitest: the hook prunes unknown fields, survives a localStorage failure, reset restores the default, and toggling adds a ColDef; the `ColumnPickerDialog.test.tsx` cases still pass.
- One host smoke test per PR.

## 5. Name-only sweep (D7)

| Location | Now | Fix |
|---|---|---|
| `SellOutTab.tsx:230-231` | Customer = `name (code)` | `field:'customer_name'`; code becomes an optional column |
| `SellOutTab.tsx:233` | Distributor column shows `distributor_code` | `distributor_name` |
| `inventory/page.tsx:125` | Customer column shows `customer_code` | add `customer_name` to the API (`inventory.py:67`), then show the name |
| `ChannelIntelligenceWorkspace.tsx:57-59,111-114` | `customerLabel` = `name (code)` | name only |
| `admin/shipment-evidence/page.tsx:406` (not Tier A) | Distributor = code | name; code optional |
| `admin/distributors/page.tsx:735,739,763` (not Tier A) | code shown as Customer / Distributor; **editable** code select | name display plus a name-labelled editor: needs Warren (below) |
| `InboundShipmentsWorkspace.tsx:461-465` | tooltip `label (code)` | OK: the cell shows the name; the tooltip is not a column |

Filter autocompletes (`SellOutTab.tsx:330,342`, `ChannelOps*:128,166`, `InboundShipmentsWorkspace.tsx:780,799`, `DsiFileReviewStrip.tsx:97`) weld the code into **option labels**, not columns. D7 does not cover them, so they are left unchanged here and recorded as a question.

## 6. Criterion-4 per host (nothing silent)

Column filters are already present on all hosts (`EnterpriseDataGrid.tsx:52-57`). Density is global and already present (`AppShell.tsx:243`, D2), with no change.

| Host | Search | Chips / filter bar | Saved views | Export |
|---|---|---|---|---|
| SellOutTab | present (S) → N-0041 adopts | selects → N-0041 | N-0042 | N-0043 |
| ChannelOpsMovements / Inventory | N-0041 | selects | N-0042 | N-0043 |
| inventory, pricing, forecasts | N-0041 | date only | N-0042 | N-0043 |
| buy-plans, roadmap | N-0041 | none | N-0042 | N-0043 |
| PlanVsExecuted | N-0041 | toggles present | N-0042 | N-0043 |
| CoverLens | N-0041 | ScopeBar present | presets present, not persisted → N-0042 | N-0043 |
| ChannelIntelligence | N-0041 | none | N-0042 | N-0043 |
| MarketSurface listings | N-0041 | ScopeBar present | N-0042 | N-0043 |
| customer-commercial-terms | present (S) → N-0041 adopts | none | N-0042 | N-0043 |
| exceptions (excluded) | N-0041 | none | N-0042 | N-0043 |

## 7. Risks and questions for Warren

- **Risk (R2):** `fact_row_dict` makes payloads larger and exposes columns such as `raw_source_row` and `*_token`. `hidden_internal` per spec leaves out secrets and JSON blobs by default. An implementer must check each fact for [PII] columns before listing it.
- **Risk:** adding customer/distributor codes means extra joins on 5 endpoints. Batch them the way `shipping.py` does; do not look them up row by row.
- **Risk:** a label drawn from `_human_column_label` can read badly ("Erd Date"). The override map is the fix; a naming review goes in validate.
- **Warren, 1:** should filter-dropdown options also show name only, with the code as secondary text? D7 names columns only.
- **Warren, 2:** on the distributors admin sell-out and inbound grids, stewards edit the distributor by **code**. May that editor show names, keeping the code as the stored value?
- **Warren, 3:** should the exceptions inbox stay out of scope as a worklist?
