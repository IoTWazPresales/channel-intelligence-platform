# N-0034 — implementation pass 2 of 2 (computed rows, listings, customer terms, close-out)

**Node:** N-0034 "Stage 2.4 + grid parity" (R2, ui) · **Design:** `n0034/DESIGN.md` (D-0030) · **Pass 1:** `n0034/IMPL_PASS1.md` · **Date:** 2026-09-24 · **Branch:** `feat/ns-2-brief-nav-collapse`
**Lenses applied:** frontend-engineer, backend-engineer, test-engineering-specialist, accessibility-specialist. The Skill tool was unavailable, so I applied each lens by name.
**Commits:** `43d521f4` (API registry, serializers and parity tests), `c18333fb` (web hosts, host test, BACKLOG). Not pushed. A commit from another session (`3624d7e7`, N-0049) landed between them; it is not mine.
**Verification rung:** self-check only (same session). GOV-008 verification still has to run separately.

## What was built

### API (`43d521f4`)
- `app/services/grid_fields.py`: eight new registry entries.
  - **Computed rows** (`model=None`, `static_keys` declared as named tuples with a comment that names the serializer):
    - `channel-ops.sell-out`: Product, Unit price; Reference: customer code and distributor code.
    - `channel-ops.movements`: Reference only (Distributor and Distributor code). The view is filtered to one distributor, so the name was never a default cell.
    - `channel-ops.inventory`: 14 row fields, including the ones shown by default only at a higher depth; Reference: distributor name and code.
    - `pve.drill`: lineup case, product name / SKU / description / marketing name / sales model, awaiting PO, 3 value fields; Reference: customer code.
    - `cover.distribution`: family, cover bucket, replenishment flag, cover as-of; Reference: distributor code.
    - `channel-intelligence`: reason, WoC reason, aged / dead stock; Reference: customer code.
  - **Listings** (`model=CustomerListing` plus `static_keys` for product SKU / name, URL verified, original URL). `registered_by` is in `hidden_internal` because it names a person ([PII]-like, the same rule as `reviewed_by` in pass 1). `meta_json` is never offered or merged, because the JSONB auto-hide rule covers it. Reference: customer code.
  - **Customer terms** (`model=CommercialCustomerTerm`; defaults are margin and rebate). It offers id, customer id, target cover weeks, created and updated. It has **no** Reference group: customer code is already its own default column on this steward grid (DESIGN.md row 17, "D7 already met"). I kept that, so the default view does not change.
  - New `customer_labels_sync(session, ids)`: the sync twin of `customer_labels`, one `IN (...)` query.
- Serializers pulled out as pure functions, so the parity guard exercises the real row shape. Existing keys are unchanged; the only additions are codes and registry keys.
  - `channel_ops.py`:
    - `channel_sellout_row_dict`: adds `customer_code` and `distributor_code`, **joined in the existing list query**.
    - `channel_movement_row_dict`: adds `distributor_code` through the existing join.
    - `channel_inventory_row_dict`: adds `distributor_code`. The single-distributor lookup now selects code and name in the one query it already ran.
    - `cover_item_dict`: the same keys as before.
  - `plan_vs_executed.py` `pve_drill_row_dict`: adds `customer_code` from **one batched** `customer_labels` query per response. It is wrapped in try/except with a log line, so a lookup failure leaves the code blank and does not fail the read model.
  - `listing_capture.py` `listing_grid_row_dict`: `{fact_row_dict, listing_to_dict, reference_fields}`. Customer name and code come from one `customer_labels_sync` query per page. `listing_to_dict` itself (used by create / patch / confirm) is unchanged.
  - `commercial_planner.py` `customer_term_grid_row_dict`: registry columns merged under `_customer_term_json`, on the list endpoint only.
- **customer_label origin (DESIGN.md row 12 said UNKNOWN).** It resolves to `DimCustomer.name` (`lineup_po_reconciliation.py:281-302` builds `customer_names` from `DimCustomer.name`, and `_customer_label` falls back to `Customer #id` or `Unattributed`). The drill "Customer" cell is therefore already name-only, and the code is now its own Reference column.

### Web (`c18333fb`)
All hosts use `useFactColumns(gridId)` + `<FactColumnPicker {...pickerProps}/>` + `FactColumnsButton`. No new dialog was added.
- `sell-out/SellOutTab.tsx`: a second hook, `channel-ops.sell-out`. The toolbar shows the button for whichever branch is live, and both pickers are mounted (only one opens).
- `sell-out/ChannelOpsMovementsTab.tsx`: hook on the movement-lines grid, button in the `ModuleDataSection` toolbar, **Retry added** (`onRetry` → `refetch`). One component serves both mounts (Stock workspace and sell-out page), via `ChannelOpsStockWorkspace`.
- `sell-out/ChannelOpsInventoryTab.tsx`: hook, toolbar button and **Retry added**. Optional ColDefs whose `field` is already a default column at the current depth are skipped, so there are no duplicate columns when the depth changes.
- `plan-vs-executed/PlanVsExecutedView.tsx`: the button sits in the drill header row, right-aligned. The row type documents that `customer_label` is the name.
- `stock/CoverLensView.tsx`: toolbar button on the desktop grid only; the mobile record cards are unchanged. The hook is called before the early returns.
- `stock/ChannelIntelligenceWorkspace.tsx`: button next to Refresh. The customer cell was already name-only from pass 1.
- `market-listings/MarketSurface.tsx`: the button sits in the listings ScopeBar `trailing` next to "Fetch now". `customer_name` now comes from the API, with the old page-level customer map as fallback. **ListingUrl behaviour from N-0039 is intact.** `listingUrlState` and `ListingUrl` are untouched, and the optional **URL** column renders through `ListingUrl` via `colDefFor`, so an unverified or dead URL is never an anchor in the grid either. "Original URL" is plain text.
- `admin/customer-commercial-terms/page.tsx`: button in the filter row, and the picker is mounted.
- `docs/BACKLOG.md`:
  - BACKLOG-201 **Closed — Done**. There is a pass-2 "Done" row, and the criterion-4 toolbar table now has a **Column picker (`grid_id`)** column per host. Search → N-0041, saved views → N-0042, export → N-0043, unchanged from DESIGN.md §6.
  - BACKLOG-140: the display half is stamped for grids. The mint half stays open. The stamp lists what did not change: filter labels, shipment-evidence, and the distributors editor (D-0031).

## Criteria (whole node)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | One generic picker on every in-scope Tier A grid through ColumnPickerDialog; no second picker | **PASS**: 15 of 15 DESIGN.md Tier A rows, plus inbound | Pass 1 covered rows 1, 6–10 and 14. Pass 2 covered rows 2, 4, 5, 12, 13, 15, 16 and 17. `grep -rln "<ColumnPickerDialog"` lists only the pre-existing callers (CST aliases, shipment-evidence, planner, master grid, ColumnSelectorModal) plus the one wrapper `FactColumnPicker.tsx`; there is no new dialog |
| 2 | Codes are their own pickable columns; identity columns show names only | **PASS**, with one recorded exception | Reference group on all computed grids and on listings; pytest `test_codes_are_reference_fields` covers 13 grids. Name cells: channel sell-out / inventory / movements / cover / CI / PVE / listings all show names. **Exception (by design):** customer-terms keeps "Customer code" as a default column, as DESIGN.md row 17 says |
| 3 | ModuleDataSection states kept | **PASS** | Every host still wraps its grid in `ModuleDataSection`. Movements and inventory gained `onRetry`; the others are unchanged |
| 4 | Toolbar parity table under BACKLOG-201 | **PASS** | `docs/BACKLOG.md` BACKLOG-201 table (picker + search / chips / saved views / export per host) |
| 5 | Tier B / C fixed | **PASS** | No Tier B/C host is in the diff. `admin/shipment-evidence` and `admin/distributors` are recorded only (below) |
| 6 | BACKLOG-200 held; BACKLOG-193 dropped; AgGridReact only in EnterpriseDataGrid | **PASS** | `grep -rln AgGridReact apps/web/src` finds `components/EnterpriseDataGrid.tsx` plus the pre-existing `design-lab/surfaces/DensitySurface.tsx`. That file is design-lab and was already there before N-0034, not in my diff; recorded, not changed. No new deps |
| 7 | Mechanism can carry Stage 2.5 | **PASS (by construction)** | `pve.drill` already offers `product_sku` and `product_sales_model` as separate registry fields; any registry key becomes a column with no web change |
| 8 | No density change, no migration, read-only on cip | **PASS** | No DDL or Alembic; no theme or density edits. The smoke is GET-only (below) |
| 9 | Tests: API parity guard per new grid_id; vitest on at least one pass-2 host; tsc 0; eslint clean on changed files | **PASS** | See Commands |
| 10 | Browser smoke | **UNABLE (not mine)**: the web runs a production build and the orchestrator rebuilds. Covered by the CI host vitest (open picker → add Reference code → cell shows the code → layout persisted) | `ChannelIntelligenceWorkspace.test.tsx` |
| 11 | BACKLOG-201 closed; BACKLOG-140 display half stamped | **PASS** | `docs/BACKLOG.md` |

## Commands and results
- `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_grid_fields.py -q`: **74 passed** (pass 1 had 38). The parity guard is parametrized over all 16 `grid_id`s. Each row is built by the endpoint's own serializer from transient ORM rows or plain objects, with no DB. The CST row goes through the real `compute_entity_metrics` + `_attach_display_names` with a fake session. New tests:
  - `test_listings_hide_person_and_json_columns`
  - `test_customer_labels_sync_is_one_batched_query`
  - `test_pve_drill_customer_label_stays_name_only`
  - `test_computed_grids_offer_only_declared_keys`
  - `test_customer_terms_keep_code_as_default_column`
  - codes-are-Reference cases for 7 new grids
- Related API tests: `test_channel_intelligence_u46`, `test_channel_ops_api`, `test_channel_ops_derived_stock`, `test_cpor_unit1_models` (it covers the customer-terms list), `test_listing_capture_lc_u1`, `test_listing_intelligence_v1`, `test_plan_vs_executed`: **75 passed**. `test_commercial_planner_api.py` **ERRORs at setup**: the conftest write guard refuses the write-capable module on `cip`. This is pre-existing and environmental, and I did not run it. Its customer-terms list test uses a `SimpleNamespace` term, which `fact_row_dict` handles through `getattr(..., None)`.
- Read-only smoke `n0034/ro_smoke_pass2.py`, run with `PGOPTIONS=-c default_transaction_read_only=on`. That setting guards the sync engine only; the async engine may ignore it. Every endpoint is a GET that selects and serializes. It prints **`current_database: cip`**. All 8 pass-2 list endpoints return **HTTP 200 with no offered field missing from any row**:
  - channel-ops sell-out: 50 rows
  - movements (distributor 29): 50 rows
  - inventory (distributor 29): 582 rows
  - cover: 2,481 rows
  - PVE drill (default period): 234 rows
  - channel intelligence: 50 rows
  - listings: 200 rows (of 218)
  - customer terms: 14 rows

  Reference keys are populated on **every** returned row (for example, `customer_code` on 234 of 234 drill rows and on 200 of 200 listings). All 16 `grid-fields/*` return 200.
- `pnpm --filter @cip/web exec tsc --noEmit`: **exit 0**.
- `pnpm --filter @cip/web exec vitest run` on sell-out page, MarketSurface, plan-vs-executed, stock, channel-intelligence, workbench-ui, roadmap and the new CI test: **17 files, 42 tests passed**. The new `features/stock/ChannelIntelligenceWorkspace.test.tsx` checks that the customer cell shows the name and not the code, that "Customer code" is not a default header, that the picker shows a Reference group, and that toggling the code adds the header and the `CUST-3` cell, shows "Columns (1)", and writes `cip.grid.channel-intelligence.optional.v1`.
- `ESLINT_USE_FLAT_CONFIG=false pnpm --filter @cip/web exec eslint <9 changed web files>`: **0 errors, 2 warnings**. Both are pre-existing `react-hooks/exhaustive-deps` on lines I did not touch (`MarketSurface.tsx` `listings` logical expression; `PlanVsExecutedView.tsx` `activeExceptionRows`).

## Recorded, not changed (non-Tier-A and out-of-scope items from DESIGN.md §5)
- `admin/shipment-evidence/page.tsx` (Tier B): the Distributor cell still shows the **code**. The D7 fix would be the name, with the code optional. I left it because the node limits changes to Tier A.
- `admin/distributors/page.tsx`: code shown as Customer / Distributor, with an **editable code select**. Unchanged; this is Warren's question D-0031.
- The movements tab's "Inbound totals by product (filtered page)" grid is a client-side 3-column roll-up of the visible page, like the zero-sellout exception list, so it gets no picker.
- CoverLens distributor **filter chips** use `d.code` as the label (`CoverLensView.tsx`, `chips` in the ScopeBar). Filter labels are not columns, so this goes under Warren Q1 and is unchanged.
- The ChannelIntelligence **product** cell is still `name (sku)`. It is product identity, which belongs to Stage 2.5 (line-identifier preference), not D7 customer / distributor codes.
- At strategic depth, `ChannelOpsInventoryTab`'s "Replenish" icon column has no `field`, so an optional "Replenishment flag" column can sit next to it. That is harmless, but it shows the same fact twice if a steward picks it.

## Findings and notes
- **Behaviour changes (small, additive):**
  - Channel-ops sell-out, movements and inventory rows carry codes.
  - PVE drill rows carry `customer_code`, at the cost of one extra batched query per response.
  - Listings rows carry `customer_name`, `customer_code` and the registry columns.
  - The customer-terms list carries `created_at` and `updated_at`.
  - No key was removed or renamed.
- **Performance:** each new code lookup is either a column on a join the endpoint already had, or one `IN (...)` query per response. There are no per-row lookups.
- **Concurrent work:** other sessions have unrelated modified files on this tree (`cpor_cases.py`, ingestion and import services, `.eif/**`). Both commits used `git commit -- <explicit paths>` (the new test file was `git add`-ed by its exact path first), so none of their changes are in my commits. The hook denied `git add` through `git -C .` ("broad path selectors"), and plain `git add <file>` worked.
- `IMPL.md` is named `IMPL_PASS2.md` here, as the prompt asked.

## Questions for Warren (carried, unchanged)
1. Should filter-dropdown options and filter chips show the name only, with the code as secondary text? Affected: `SellOutTab`, ChannelOps autocompletes, inbound, DSI strip, and now also the CoverLens distributor chips (`label: d.code`).
2. (D-0031) May the distributors admin editor show names while keeping the code as the stored value?
3. Should the exceptions inbox stay out of scope as a worklist?
4. (New, small) Should `admin/shipment-evidence`'s Distributor cell move to name-only with the code optional, even though it is Tier B?
