# Grid and column parity audit — `apps/web`

**Date:** 2026-09-21
**Branch:** `feat/ns-2-brief-nav-collapse`
**Tree audited:** `b9a58a3` (post unit 1)

> **What this doc is.** A full enumeration of every grid and table in `apps/web`,
> with every difference from the canonical chrome classified **MIGRATE** or
> **CORRECT**, plus column-picker coverage. Commits `306b17d`, `47ef8bb`,
> `0d65000` and `b9a58a3` already closed most of the MIGRATE set. **This doc
> records what was found and what remains — it does not redo that work.**
>
> Code is evidence; this doc is a claim. Every row below was read in the tree at
> `b9a58a3`, not inferred from a commit message.

---

## 1. Method and scope

Enumerated by grepping the tree, not by reading commit history:

- `<EnterpriseDataGrid` — the AG Grid wrapper
- `<MasterDataGridShell` — the master-data grid shell
- `<Table` — MUI tables
- `<ColumnPickerDialog` / `<ColumnSelectorModal` / `<MasterColumnPickerDialog`
- `<ModuleDataSection`

`*.test.tsx` / `*.test.ts` excluded from mount counts — mocks and fixtures are
not surfaces. `design-lab/` is counted separately and **excluded from the
MIGRATE set**: those are proposal surfaces, not shipped product, and
deliberately carry their own chrome.

### Inventory

| Kind | Count |
|------|-------|
| `EnterpriseDataGrid` mounts | **63** (53 production, 10 design-lab) |
| `MasterDataGridShell` mounts | **3** (customers, distributors, products) |
| Files containing at least one grid mount | **53** (46 production, 7 design-lab) |
| Files containing a MUI `<Table>` | **41** |
| ...of those, tables that own their own `useQuery` | **23** |
| Grid files mounting a column picker | **5** (covering 7 surfaces — `MasterDataGridShell` serves three) |
| Direct `<AgGridReact>` mounts outside the wrapper | **0** |

That last row matters. There is no grid in `apps/web` that bypasses
`EnterpriseDataGrid` — the only `AgGridReact` references in the tree are inside
`components/EnterpriseDataGrid.tsx` itself. The wrapper really is the single
grid substrate, so grid parity is a question about the chrome *around* the
wrapper, not about competing grid implementations.

---

## 2. The parity bar

Two shared components define canonical behaviour.

**`components/ModuleDataSection.tsx`** owns the four data states around a grid:

| State | Rendering |
|-------|-----------|
| loading | spinner in a dashed box, `role="status"`, `aria-busy`, `minHeight 360`, custom `loadingLabel` |
| error | `Alert severity="error"`, `role="alert"`, **Retry** action when `onRetry` given |
| empty | `EmptyWorkspace` — title, description, up to two CTAs |
| data | children (the grid) |

The critical property: **it does not mount the grid until rows are ready.** A
grid inside `ModuleDataSection` can never paint its own overlay, because it is
not rendered at all during loading, error or empty. This is why a leftover
`gridOptions.loading` on a wrapped grid is dead code rather than a double
spinner — see `CstArticleAliasesSection` in §4.1.

**`features/workbench-ui/ColumnPickerDialog.tsx`** owns the "Additional columns"
UX at two sizes (`md`, `wide`): grouped fields, search, per-group description /
loading / `emptyHint`, and an optional reset footer.

Two thin host wrappers re-export it and add nothing but a size:

- `features/commercial-planner/ColumnSelectorModal.tsx` → `size="wide"`
- `components/masterGrid/MasterColumnPickerDialog.tsx` → `size="md"`

---

## 3. Classification rule used

A grid is **MIGRATE** when it owns a fetch (`useQuery`) and expresses any of the
four data states differently from `ModuleDataSection` — including expressing a
state *not at all*, which is the most common and the most damaging case. An
unresolved or failed query renders an empty grid whose default overlay reads
"No Rows To Show": the UI asserts *there is no data* when the truth is *we do
not know yet* or *the request failed*.

A grid is **CORRECT** when any of:

- **C1 — parent owns the state.** The grid sits inside a `ModuleDataSection`, or
  inside a shell/parent that is.
- **C2 — derived rows, no fetch.** `rowData` is a client-side `useMemo` over data
  the parent already resolved. No request, so no loading or error state exists
  to express.
- **C3 — domain-specific empty state carries information the generic one cannot.**
  A substrate/"planned" explanation, or a `data_unavailable` contract response.
  Replacing these with a generic `EmptyWorkspace` would *lose* meaning.
- **C4 — refetch overlay over already-rendered rows.** A different contract from
  initial load. `ModuleDataSection` cannot express it, because it swaps the grid
  out rather than dimming it.
- **C5 — not a shipped surface.** `design-lab/`, or code that no route mounts.

---

## 4. MIGRATE set

### 4.1 Closed

| # | Surface(s) | Divergence found | Commit |
|---|-----------|------------------|--------|
| 1 | `shipping/page.tsx`, `admin/shipment-evidence/page.tsx` | Two bespoke "Additional columns" dialogs (`InboundShipmentsColumnsDialog`, `ShipmentEvidenceColumnsDialog`) forked the picker UX: draft-then-Apply vs immediate toggle, different search, different footers | `306b17d` |
| 2 | `admin/ops/page.tsx`, `admin/steward-audit/page.tsx`, `features/administration/UsersWorkspace.tsx` | AG Grid `overlayNoRowsTemplate` — while the query was pending the grid rendered and read "No ... yet"; error and empty chrome differed from every other page | `47ef8bb` |
| 3 | `SellOutTab` (x3), `ChannelOpsMovementsTab`, `ChannelOpsInventoryTab`, `admin/mappings` legacy queue, `ChannelIntelligenceWorkspace` | Hand-rolled `Loading...` Typography plus a plain caption for empty | `0d65000` |
| 3 | `admin/customer-commercial-terms`, `admin/cst-steward` (x2) | `gridOptions.loading` overlay plus AG Grid default "No Rows To Show" for empty | `0d65000` |
| 4 | `commercial-planner/page.tsx` (plan lines) | `gridOptions.loading` overlay; **with no plan selected, a blank bordered box with no copy at all**; the lines query's `isError`/`error` were destructured nowhere, so a failed load was silent | `b9a58a3` |
| 4 | `CporPaymentEvidencePanel` | Info `Alert` for empty, bare `Alert` for error with no Retry | `b9a58a3` |
| 4 | `CstArticleAliasesSection` | `gridOptions.loading` left behind after the section itself moved to `ModuleDataSection` at `0d65000` — dead, since the grid never mounts while loading | `b9a58a3` |

**`gridOptions.loading` is now fully closed.** No production grid passes it. The
only remaining `loading:` keys under `apps/web/src` (excluding design-lab and
test utils) are `ColumnPickerDialog` **group** flags at `shipping/page.tsx:1011`
and `admin/shipment-evidence/page.tsx:783` — a different contract (per-group
field-list loading *inside* the picker), correctly used.

### 4.2 Remaining — open

| Surface | Line | Divergence |
|---------|------|-----------|
| `features/market-listings/MarketSurface.tsx` — competitor **mappings** grid | `1230` | `const { data: mappings } = useQuery({...})` at `:272` destructures **neither `isLoading` nor `isError`**. The grid renders `rowData={mappings ?? []}` unconditionally, so during load *and on outright failure* it paints AG Grid's default "No Rows To Show". A fetch error is indistinguishable from "this customer has no competitor mappings". |

This is the **only** genuine MIGRATE left in the production grid set — one grid,
on one lens, of one surface. Left open rather than fixed in this pass so the
audit stays an audit; recorded in §7 and in `docs/BACKLOG.md`.

---

## 5. CORRECT set — the 14 grid files with no local `ModuleDataSection`

Every file that mounts a grid but contains no `<ModuleDataSection` was read
individually. None except §4.2 is a MIGRATE.

| File | Mounts | Why CORRECT |
|------|--------|-------------|
| `admin/customers/page.tsx` | 1 | **C1** — `MasterDataGridShell`, which wraps its own grid in `ModuleDataSection` |
| `admin/products/page.tsx` | 1 | **C1** — same shell |
| `features/lineup/LineupPlanGrid.tsx` | 1 | **C1** — pure presentation; `LineupWorkspace.tsx:34` wraps it in `ModuleDataSection` and owns the query |
| `features/plan-vs-executed/ExceptionCategoryGrid.tsx` | 1 | **C1/C2** — takes `rows` as a prop; `PlanVsExecutedView` owns fetch state. Its own `if (!rows.length)` returns a category-specific line ("None in range for ...") that beats a generic empty |
| `features/settlement/SettlementDesk.tsx` | 1 | **C1** — presentation only; `SettlementDeskLive.tsx:74-80` gates on `isLoading` / `isError` before mounting the desk at all |
| `features/promotions-funding/PlanWorkspace.tsx` | 1 | **C1** — rows arrive as props from `CaseBookSurface`, which is inside `ModuleDataSection` |
| `features/cpor/CporCaseWorkspace.tsx` | 2 | **C5** — **no route mounts this.** The only remaining reference is `page.fxReadiness.test.tsx`; the `[id]` route renders `SettlementDeskLive`. See §7.4 |
| `cpor-cases/[id]/CporPromoLoadPanel.tsx` | 1 | **C3** — early returns cover error, loading, and a `data_unavailable`/`no_cst` branch whose copy names the CST import steward and warns that DSI sell-out is not promo-load evidence. Generic chrome would delete that |
| `features/commercial-planner/PoManagementView.tsx` | 1 | **C3** — `gapQ.isLoading` → `LinearProgress`; `data_unavailable` → info; empty → **`Alert severity="success"`: "No gaps — every shipment PO is covered by a confirmed lineup."** Empty here is *good news*, not a call to action; `EmptyWorkspace` would misread it as a gap to fill |
| `features/commercial-planner/CurrentLineupSection.tsx` | 1 | **C3** — per-branch copy distinguishing "no case selected" from "No rows in the selected case yet. Upload a file or choose another case.", plus its own `isLoading` branches at `:1008`, `:1692`, `:1874`, `:1989` |
| `app/(app)/promotions/PromoPlanBuilderPanel.tsx` | 1 | **C2** — `rows` is builder draft state, not a fetch. The grid renders only inside the `b4-draft-summary` branch, after a draft is composed |
| `features/dashboards/DashboardWidgetCard.tsx` | 1 | **C3** — widget states already distinguish loading, error and a **`refused`** state (metric validation refusal) that no generic empty can express. Grid renders only under `q.data?.ok && visual === 'table'` |
| `design-lab/surfaces/DensitySurface.tsx` | 1 | **C5** — proposal surface (see the density proposal doc) |
| `design-lab/surfaces/SettlementDeskB.tsx` | 1 | **C5** — proposal surface |

### 5.1 Secondary grids inside files that *do* use `ModuleDataSection`

Six files mount more grids than they have `ModuleDataSection` wrappers. Each was
checked so the arithmetic is not mistaken for a gap.

| File | Wrapped | Unwrapped | Verdict |
|------|---------|-----------|---------|
| `admin/distributors/page.tsx` | `:1439` sell-out, `:1474` inbound | `:829` `MasterDataGridShell` | **C1** — shell owns its own state |
| `sell-out/SellOutTab.tsx` | `:362`; `:386` and `:392` share one section | — | Two grids under one `ModuleDataSection` is intended |
| `sell-out/ChannelOpsMovementsTab.tsx` | `:149` | `:158` "Inbound totals by product (filtered page)" | **C2** — `productTotals` is a `useMemo` (`:59`) over the already-loaded page, gated `.length > 0` |
| `features/market-listings/MarketSurface.tsx` | `:956` listings | `:1230` mappings, `:1275` prices | `:1230` → **MIGRATE** (§4.2). `:1275` → **C3**: falls back to `SubstrateOrPlanned` "Competitor prices — data only", explaining that the table and endpoint exist but no import template does |
| `design-lab/MarketSurface.tsx`, `design-lab/PromotionPlannerSurface.tsx` | — | — | **C5** |

---

## 6. Column picker coverage

### 6.1 Grids that have a picker — 5 call sites, 7 surfaces

| Surface | Picker | Size |
|---------|--------|------|
| `commercial-planner/page.tsx` (plan lines) | `ColumnSelectorModal` → `ColumnPickerDialog` | wide |
| `components/masterGrid/MasterDataGridShell.tsx` → `admin/customers`, `admin/products`, `admin/distributors` | `ColumnPickerDialog` direct | md |
| `shipping/page.tsx` | `ColumnPickerDialog` | md |
| `admin/shipment-evidence/page.tsx` | `ColumnPickerDialog` (canonical + `raw:`-prefixed import columns in one picker) | md |
| `admin/cst-steward/CstArticleAliasesSection.tsx` | `ColumnPickerDialog` | md |

**All five call sites now go through the one implementation.** After `306b17d`
there is no forked picker left in the tree.

### 6.2 Grids that have **no** column picker — the other ~46 mounts

This is the honest headline of the column half of the audit: **column choice is
the exception, not the rule.** Everything outside §6.1 ships a fixed
`columnDefs`. The only column control those users have is AG Grid's built-in
resize / move / (where enabled) column menu — no persisted layout, no grouped
field catalogue, no reset.

Three tiers, by whether that absence is a defect.

**Tier A — wide fact grids where a picker is arguably missing.** Broad
`fact_*`-backed operational grids over entities with far more columns than are
shown:

- `sell-out/SellOutTab.tsx` (x3), `ChannelOpsMovementsTab`, `ChannelOpsInventoryTab`
- `inventory/page.tsx`, `pricing/page.tsx` (x2)
- `buy-plans/page.tsx`, `roadmap/page.tsx`
- `exceptions/page.tsx`, `features/plan-vs-executed/PlanVsExecutedView.tsx`
- `features/stock/CoverLensView.tsx`, `ForecastsWorkspace.tsx`, `ChannelIntelligenceWorkspace.tsx`
- `features/market-listings/MarketSurface.tsx` (listings)
- `admin/customer-commercial-terms/page.tsx`

**Tier B — scoped worklists where the fixed column set is the design.** The grid
exists to drive one steward decision; extra columns would dilute it:

- `features/data-stewardship/StewardFailureQueue.tsx`
- `features/imports/ProductMasterGapWorklistView.tsx`
- `admin/mappings/page.tsx`, `admin/steward-audit/page.tsx`, `admin/ops/page.tsx`
- `features/administration/UsersWorkspace.tsx`
- `features/admin/CatalogDimensionGridPanel.tsx`
- `admin/cst-steward/page.tsx` (x2), `admin/imports/page.tsx`
- `budget-requests/page.tsx`

**Tier C — case-scoped detail panels where a picker would be noise.** A bounded
row set inside one case or one plan:

- `CporPaymentEvidencePanel`, `CporPromoLoadPanel`
- `features/settlement/SettlementDesk.tsx`, `features/promotions-funding/PlanWorkspace.tsx`, `CaseBookSurface.tsx`, `PromotionPlannerSurface.tsx`
- `features/commercial-planner/CurrentLineupSection.tsx`, `PoManagementView.tsx`
- `features/lineup/LineupPlanGrid.tsx`, `features/plan-vs-executed/ExceptionCategoryGrid.tsx`
- `promotions/PromoPlanBuilderPanel.tsx`, `features/dashboards/DashboardWidgetCard.tsx`
- `features/reports/ReportBuilderView.tsx` — columns *are* the report; the builder is the picker

Only **Tier A** is a candidate gap, and it is a product decision (which fact
columns a steward may surface), not a parity defect. **No Tier A grid is claimed
here as MIGRATE.**

---

## 7. Residuals and follow-ups

Deferrals belong in `docs/BACKLOG.md`, not chat. Recorded there by this pass:

1. **`MarketSurface` mappings grid** (§4.2) — the one open MIGRATE.
2. **`components/masterGrid/MasterColumnPickerDialog.tsx` is dead.**
   `MasterDataGridShell` imports `ColumnPickerDialog` directly (`:34`, `:485`).
   The wrapper's only remaining referent is its own
   `MasterColumnPickerDialog.test.tsx` — a test-only export.
3. **Tier A picker coverage** (§6.2) — needs a product call before any code.
4. **`CporCaseWorkspace` is unmounted.** It is the third such case found, after
   `SettlementPortfolioRead` and `CporPortfolioIntelligencePanel`. Its two grids
   and its `CporPaymentEvidencePanel` child cannot be browser-smoked, because no
   route reaches them. Whether this is dead code to delete or a surface to
   re-mount is a product call, not an audit finding.

---

## 8. MUI `<Table>` surfaces

41 files, of which **23 own a `useQuery`**. Parity only bites on those 23 — the
other 18 render props or local state.

Eight of the 23 are already inside `ModuleDataSection`:
`AliasScopeConflictsSection`, `NameSimilarityMergeSection`,
`DistributorNameSimilarityMergeSection`, `admin/imports/page.tsx`,
`admin/shipment-evidence/page.tsx`, `commercial-planner/page.tsx`,
`shipping/page.tsx`, `features/market-listings/MarketSurface.tsx`.

The remaining 15 are **dialog and strip bodies**: `CustomerBulkPromoteDialog`,
`CustomerDispositionDialog`, `DistributorBulkPromoteDialog`,
`DistributorDispositionDialog`, `BulkLineupBackfillDialog`,
`UnifiedLineupImportDialog`, `DsiCoveragePanel`, `DsiFileReviewStrip`,
`DsiChannelGeographicEvidenceSection`, `UnresolvedGeoStewardPanel`,
`PlannerDefaultsMaintenance`, `PoAutoLinkProposalsSection`,
`ShippingDigestRecipientsPanel`, `admin/sql-viewer/page.tsx`,
`CurrentLineupSection`.

**Classified CORRECT as a group, deliberately.** `ModuleDataSection` is
module-*section* chrome: a 360px-minimum dashed spinner box and a 6-unit-padded
`EmptyWorkspace` with CTAs. Inside a modal body or a one-line strip that chrome
is wrong at the size — it would blow out dialog height and offer CTAs that
navigate away from the dialog the user is part-way through. `admin/sql-viewer`
is a developer tool and sits outside the steward design language entirely.

**This is a stated scope boundary, not an unexamined gap.** Dialog-body data
states are their own contract and were never part of the grid parity bar. If
they should be unified, that needs a dialog-scale variant of the component
first — a design decision, not a migration.
