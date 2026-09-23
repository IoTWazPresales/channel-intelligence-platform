# N-0034 discovery — grid toolbar and column parity per host

**Run:** `STAGE2_4_GRID_PARITY_20260923` · **Actor:** `stage24-001` · **Tree:** `65dbed5` (branch `feat/ns-2-brief-nav-collapse`) · **Date:** 2026-09-23
**Scope:** read-only. No product source changed. Enumeration is reproducible with `python -B .eif/audit/STAGE2_4_GRID_PARITY_20260923/scan_grid_hosts.py` (heuristic hits, then every search / view / export / picker cell below was hand-traced to a line).

## Reconciliation (VERIFIED)

| Count | This scan | Audit `docs/audits/GRID_AND_COLUMN_PARITY_AUDIT.md` @ `b9a58a3` |
|---|---|---|
| `<EnterpriseDataGrid` mounts | **63** (53 production, 10 design-lab) | 63 (53 / 10) |
| Files hosting a grid (incl. `MasterDataGridShell` hosts) | **53** (46 production, 7 design-lab) | 53 (46 / 7) |
| Files with a literal `<EnterpriseDataGrid` | 51 | — |

Reconciles. The two files with no literal mount are `admin/customers/page.tsx` and `admin/products/page.tsx`, which host the grid through `<MasterDataGridShell>`. One path moved since the audit: `shipping/page.tsx` → `features/supply-inbound/InboundShipmentsWorkspace.tsx` (`21f242e`). No host added or lost.

## Shared features every host inherits (VERIFIED)

- **Column filters:** `EnterpriseDataGrid` sets `defaultColDef { sortable, filter: true, resizable, floatingFilter: false }` (`components/EnterpriseDataGrid.tsx:52-57`). Every grid therefore has AG Grid community header-menu filters. No host turns on floating filters. `filter: false` appears only on 1–2 action columns per file. `ExceptionCategoryGrid.tsx:260` passes `gridOptions.defaultColDef {resizable}`; whether that overrides the wrapper prop is ASSERTED unresolved.
- **Density:** one global toggle in the shell (`features/shell/AppShell.tsx:243-247`), persisted in `stores/uiStore.ts:35`, applied to every grid through `theme/gridDensity.ts`. **No per-grid density control exists anywhere**, so the density column is omitted from the table (it would be "global" on all 53 rows).

## Per-host table

Legend: **S** = server-side (value reaches the API query), **C** = client-side, `–` = none. Tier = audit §6.2 (A fact grid / B worklist / C case panel). Lab = design-lab surface that specifies the host; `DomainOverview` = the route's lab page is a domain overview with no grid spec.

| # | Host (`apps/web/src/…`) | Mounts | Tier | Toolbar search | Filter bar / chips | Saved views | Column picker | Export | Lab surface |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `app/(app)/admin/cst-steward/CstArticleAliasesSection.tsx` | 1 | B | **S** debounced → queryKey `:204` | select | – | ColumnPickerDialog `:653` | – | Data |
| 2 | `app/(app)/admin/cst-steward/page.tsx` | 2 | B | **S** `?q=` `:69-71` | select | – | – | – | Data |
| 3 | `app/(app)/admin/customer-commercial-terms/page.tsx` | 1 | A | **S** `?q=` `:55-57` | – | – | – | – | none |
| 4 | `app/(app)/admin/customers/page.tsx` | 0 (+shell) | shell | **S** URL `q` `:273,:334` | selects | – | via shell | – | Data (masters) |
| 5 | `app/(app)/admin/distributors/page.tsx` | 2 (+shell) | shell | **S** URL `q` `:244,:288` | selects | – | via shell (main grid only) | – | Data (masters) |
| 6 | `app/(app)/admin/imports/page.tsx` | 1 | B | – | selects, chip | – | – | – (`:2441` is a sample-template download) | Data (imports) |
| 7 | `app/(app)/admin/mappings/page.tsx` | 1 | B | – | – | – | – | – | Data (steward) |
| 8 | `app/(app)/admin/ops/page.tsx` | 1 | B | – | – | – | – | – | DomainOverview |
| 9 | `app/(app)/admin/products/page.tsx` | 0 (+shell) | shell | **S** URL `q` `:222,:293` | selects, dates | **bespoke** localStorage `:106` | via shell | **C** CSV of current page `:796` | Data (masters) |
| 10 | `app/(app)/admin/shipment-evidence/page.tsx` | 1 | — | **S** `search` `:156` | selects | – | ColumnPickerDialog `:766` | – | Data |
| 11 | `app/(app)/admin/steward-audit/page.tsx` | 1 | B | – | select | – | – | – | Data (audit) |
| 12 | `app/(app)/budget-requests/page.tsx` | 1 | B | – | – | – | – | – | Funding (budgets) |
| 13 | `app/(app)/buy-plans/page.tsx` | 1 | A | – | – | – | – | – | DomainOverview |
| 14 | `app/(app)/commercial-planner/cpor-cases/[id]/CporPaymentEvidencePanel.tsx` | 1 | C | – | – | – | – | – | Funding (payments) |
| 15 | `app/(app)/commercial-planner/cpor-cases/[id]/CporPromoLoadPanel.tsx` | 1 | C | – | – | – | – | – | Funding |
| 16 | `app/(app)/commercial-planner/page.tsx` | 1 | — | **C** on side tables only (`:954`, `:1093`), not the plan-lines grid | selects, dates | – | ColumnSelectorModal `:3604` | – | DomainOverview |
| 17 | `app/(app)/exceptions/page.tsx` | 1 | A | – | – | – | – | – | none |
| 18 | `app/(app)/inventory/page.tsx` | 1 | A | – | date | – | – | – | Stock (soh) |
| 19 | `app/(app)/pricing/page.tsx` | 2 | A | – | date | – | – | – | Market (price) ASSERTED |
| 20 | `app/(app)/promotions/PromoPlanBuilderPanel.tsx` | 1 | C | – | – | – | – | – | Funding (planner) |
| 21 | `app/(app)/roadmap/page.tsx` | 1 | A | – | – | – | – | – | DomainOverview |
| 22 | `app/(app)/sell-out/ChannelOpsInventoryTab.tsx` | 1 | A | – | select | – | – | – | Stock (soh) |
| 23 | `app/(app)/sell-out/ChannelOpsMovementsTab.tsx` | 2 | A | – | select | – | – | – | Stock (movement) |
| 24 | `app/(app)/sell-out/SellOutTab.tsx` | 3 | A | **S** `product_search` `:130` | selects | – | – | – | Stock (sellthrough) |
| 25 | `components/masterGrid/MasterDataGridShell.tsx` | 1 | shell | (host supplies) | select | – | ColumnPickerDialog `:485` | – | Data (masters) |
| 26 | `features/admin/CatalogDimensionGridPanel.tsx` | 1 | B | – | – | – | – | – | DomainOverview |
| 27 | `features/administration/UsersWorkspace.tsx` | 1 | B | – | select | – | – | – | DomainOverview |
| 28 | `features/commercial-planner/CurrentLineupSection.tsx` | 1 | C | – | ToggleButtonGroup `:4066` (**S** `workbench_scope` `:722`), selects | – | – | JSON steward export `:3918` | DomainOverview |
| 29 | `features/commercial-planner/PoManagementView.tsx` | 1 | C | – | – | – | – | – | DomainOverview |
| 30 | `features/cpor/CporCaseWorkspace.tsx` (unmounted) | 2 | C | – | – | – | – | – | none |
| 31 | `features/dashboards/DashboardWidgetCard.tsx` | 1 | C | – | – | – | – | – | Reports |
| 32 | `features/data-stewardship/StewardFailureQueue.tsx` | 1 | B | – | ScopeBar | – | – | – | Data (steward) |
| 33 | `features/imports/ProductMasterGapWorklistView.tsx` | 1 | B | – | selects | – | – | – | Data (imports) |
| 34 | `features/lineup/LineupPlanGrid.tsx` | 1 | C | – | parent `LineupContainer.tsx:142` ScopeBar | – | – | **S** XLSX `LineupPlanActionBar.tsx:88` | DomainOverview |
| 35 | `features/market-listings/MarketSurface.tsx` | 3 | A (listings) | – | ScopeBar ×2 | – | – | – | Market |
| 36 | `features/plan-vs-executed/ExceptionCategoryGrid.tsx` | 1 | C | – | – | – | – | – | Stock (execution) |
| 37 | `features/plan-vs-executed/PlanVsExecutedView.tsx` | 1 | A | – | toggles, BU select `:581` | – | – | – | Stock (execution) |
| 38 | `features/promotions-funding/CaseBookSurface.tsx` | 1 | C | **S** `q` via `caseScope.ts:67` → `:192-193` | ScopeBar + CaseScopeFilters | – | – | – | Funding (book) |
| 39 | `features/promotions-funding/PlanWorkspace.tsx` | 1 | C | – | – | – | – | **S** XLSX `:623` | Funding (planner) |
| 40 | `features/promotions-funding/PromotionPlannerSurface.tsx` | 1 | C | – | ScopeBar, selects, dates | – | – | – | Funding (planner) |
| 41 | `features/reports/ReportBuilderView.tsx` | 1 | C | – | toggle, selects | – | builder is the picker | **S** XLSX/PDF `:452-460` | Reports |
| 42 | `features/settlement/SettlementDesk.tsx` | 1 | C | – | ScopeBar ×2 | – | – | – | Funding (settle), SettlementDeskA |
| 43 | `features/stock/ChannelIntelligenceWorkspace.tsx` | 1 | A | – | – | – | – | – | Stock |
| 44 | `features/stock/CoverLensView.tsx` | 1 | A | – | ScopeBar | ScopeBar presets `:373` (local state, not persisted) | – | – | Stock (cover) |
| 45 | `features/stock/ForecastsWorkspace.tsx` | 1 | A | – | date | – | – | – | Stock (forecast) |
| 46 | `features/supply-inbound/InboundShipmentsWorkspace.tsx` | 1 | — | **S** `search` `:406` → `buildShippingLinesUrl.ts:38` | selects, dates, PO chip | – | ColumnPickerDialog `:1007` | – | DomainOverview |
| 47–53 | `design-lab/surfaces/{Data,Density,Funding,Market,PromotionPlanner,SettlementDeskB,Stock}Surface.tsx` | 2,1,1,2,2,1,1 | lab (C5) | lab fixtures | ScopeBar on 6 of 7 | StockSurface presets | – | – | self |

**Totals (production, 46 files):** toolbar search 12 (11 server, 1 client on side tables) · picker 6 files (5 call sites + the shell's 3 hosts) · saved views 2 (1 bespoke persisted, 1 ScopeBar preset not persisted) · grid export 5 (1 client CSV, 4 bespoke server) · density 0 per-grid.
**Tier A (18 mounts / 14 files, counting only the listings grid in MarketSurface):** search on 2 (customer-commercial-terms, SellOutTab) · picker on 0 · saved views on 1 (Cover, not persisted) · export on 0.

## Shared components versus bespoke copies (VERIFIED)

| Feature | Shared primitive | Hosts using it | Bespoke copies |
|---|---|---|---|
| Toolbar search | **none** | — | 12 hand-rolled `TextField`s, each wired to its own query param (`q`, `search`, `product_search`) |
| Column filters | `EnterpriseDataGrid` `defaultColDef` | all 53 | `InboundShipmentsWorkspace.tsx:560` re-declares the same defaults |
| Filter bar / chips | `workbench-ui/controls.tsx` `ScopeBar` (`:70`, chips + `filters` slot + `savedViews`) | 7 (StewardFailureQueue, MarketSurface, CaseBookSurface, PromotionPlannerSurface, SettlementDesk, CoverLensView, LineupContainer) | ~20 hosts with loose selects/dates; `SettlementScopeBar` (unmounted with `SettlementContainer`) |
| Saved views | `ScopeBar.savedViews` (presets, no persistence) | 1 (CoverLensView) | `admin/products` localStorage `:106`; `settlementViews.ts` (unmounted) |
| Column picker | `workbench-ui/ColumnPickerDialog` | 5 call sites | `ColumnSelectorModal` (thin wrapper, live), `MasterColumnPickerDialog` (dead, BACKLOG-200 held) |
| Export | **none** (AG Grid community `exportDataAsCsv` on 1 host) | — | 4 bespoke server exports (lineup XLSX, promo plan XLSX, reports XLSX/PDF, lineup steward JSON) |
| Density | shell toggle + `uiStore` + `theme/gridDensity.ts` | all (global) | — |
| Grid toolbar row | `components/ModuleGridToolbar.tsx` (refresh / add / upload / clear / imports link only) | 18 | — |

## BACKLOG check (VERIFIED by grep of `docs/BACKLOG.md` for picker / search / saved view / filter chip / filter bar / export)

- **BACKLOG-201** Tier A fact grids have no column picker — Decided 2026-09-21 (D3 all columns), Open. Its TRIGGER is Warren's product call; D3 is that call, so it has fired.
- **BACKLOG-200** dead `MasterColumnPickerDialog` — HELD on the N-0029 review.
- **BACKLOG-192** one column picker — Done `7656f67`.
- **BACKLOG-193** AG Grid range selection / Excel export — Dropped (licence).
- **BACKLOG-140** CIP-minted customer codes — the display half is in 2.4 (D7).
- **No entry** for toolbar search, saved views, filter chips or client/grid export parity. Those gaps are unrecorded. (Negative result covers the patterns above only.)

## What this means for N-0034 (PROPOSAL)

1. The picker half of 2.4 is plumbed: one `ColumnPickerDialog`, layout-key pattern in the shell. The missing piece is a per-fact **field list source**. No generic "all fields of fact X" endpoint was found in this pass (UNKNOWN; to confirm in design).
2. Search, saved views and export have **no shared primitive**. Parity needs either one small search slot on `ScopeBar` / `ModuleGridToolbar` or recorded BACKLOG entries. That choice is criterion 4 of N-0034.
3. Density needs nothing: it is global and D2 already landed.
4. Lab specs for Tier A exist only for Stock and Market. Buy-plans, roadmap, exceptions and customer-commercial-terms have no grid-level lab referent.
