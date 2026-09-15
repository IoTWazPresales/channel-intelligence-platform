# NODE C recon — Grid parity and Case book

**Run:** `NS17_GRID_CASEBOOK_20260915`  
**Branch:** `feat/ns-2-brief-nav-collapse` @ `1804395e7527d53d9999c9389871bc31d5bbb589` (git)  
**This note is source recon.** The operator brief is observation, not acceptance.

Cites **D-0008** (accepted): Promotions & Funding Case book is the settlement half of the one `cpor_case` lifecycle; the lab `FundingSurface` book lens is the composition referent. Grid chrome is not a second product. **N-0027** introduced `StewardFailureQueue` on `EnterpriseDataGrid`. **N-0028** Lineup cases already uses `HeadlineStrip` + `ScopeBar` + `LineupPlanGrid`. Do not revert those. Do not remediate N-0025. Do not reopen N-0013.

---

## AG Grid consumer (VERIFIED)

`AgGridReact` is imported only from `apps/web/src/components/EnterpriseDataGrid.tsx`. That wrapper registers `AllCommunityModule` only (ag-grid-community). The name “Enterprise” is a misnomer — **VERIFIED** no `ag-grid-enterprise` import in `apps/web`.

Therefore the **grid widget** is already one implementation. What is not consistent is everything around it.

| Capability | In `EnterpriseDataGrid` today | Notes |
|---|---|---|
| Column picker | No | Two host pickers (below) |
| Clipboard | No | Community can copy selected cell **text** if `enableCellTextSelection` |
| Range selection | No | Requires Enterprise module — **UNCOVERED** this node (no license in tree) |
| Excel export | No | Requires Enterprise module — **UNCOVERED** |
| CSV export | No | Some hosts have their own download buttons, not AG Grid export |
| Empty state | No | Hosts that care wrap `ModuleDataSection` |
| Toolbar | No | `ModuleGridToolbar` or host buttons, or none |
| Row click affordance | No | Hosts pass `onRowClicked` ad hoc; cursor not set in the wrapper |
| Text selection | No | Default AG Grid suppresses native select |

**One place the convergence belongs:** `EnterpriseDataGrid` itself — community clipboard via native cell text selection + pointer cursor when `onRowClicked` is supplied. Do not add range/Excel here.

---

## Column pickers (VERIFIED) — not this node's one place

| Implementation | Consumers |
|---|---|
| `MasterColumnPickerDialog` | `MasterDataGridShell` (products / customers / distributors); `CstArticleAliasesSection` |
| `ColumnSelectorModal` | commercial-planner buy-plan grid (`page.tsx`) |

Unifying pickers is a separate product; commercial-planner groups are not admin master groups. **Routed out.**

---

## Grid consumers (VERIFIED from `EnterpriseDataGrid` import sites)

Wrapper is `EnterpriseDataGrid` for every row unless noted. Clipboard / range / AG export: none unless noted. Node A grid included.

| Surface | Picker | Empty | Toolbar | Row click |
|---|---|---|---|---|
| `StewardFailureQueue` (N-0027) | none | `ModuleDataSection` | `ModuleGridToolbar` | yes → existing steward href |
| `admin/mappings` legacy queue | none | none on the 280px grid | none | no |
| `CaseBookSurface` | none | `ModuleDataSection` | none (ScopeBar) | yes → `?case=` drawer |
| `PromotionPlannerSurface` | none | host | none | yes |
| `PlanWorkspace` | none | host | none | — |
| `PromoPlanBuilderPanel` | none | host | none | — |
| `LineupPlanGrid` | none | none | action bar in host | cell buttons; **ApprovalBadge** IBM Plex leftover |
| `CurrentLineupSection` | none | host | host | — |
| `CoverLensView` | none | host | none | — |
| `ChannelIntelligenceWorkspace` | none | host | none | — |
| `ForecastsWorkspace` | none | host | `ModuleGridToolbar` | — |
| `PlanVsExecutedView` / `ExceptionCategoryGrid` | none | host | host | — |
| `MarketSurface` (listings / map / prices) | none | host | host | yes on listings |
| `PoManagementView` | none | host | host | — |
| `ReportBuilderView` | none | host | host | — |
| `DashboardWidgetCard` | none | none | none | no |
| `MasterDataGridShell` | `MasterColumnPickerDialog` | `ModuleDataSection` | `ModuleGridToolbar` | bulk select |
| `CatalogDimensionGridPanel` | none | host | `ModuleGridToolbar` | — |
| `admin/imports` jobs | none | host | `ModuleGridToolbar` | — |
| `admin/cst-steward` | none | host | none | — |
| `CstArticleAliasesSection` | `MasterColumnPickerDialog` | host | `ModuleGridToolbar` | — |
| `ProductMasterGapWorklistView` | none | host | host | steward |
| `admin/shipment-evidence` | none | host | `ModuleGridToolbar` | — |
| `shipping` | none | host | `ModuleGridToolbar` | — |
| `admin/customer-commercial-terms` | none | none | none | — |
| `admin/distributors` extra grids | none | host | `ModuleGridToolbar` | — |
| `commercial-planner` lines | `ColumnSelectorModal` | host | `ModuleGridToolbar` | — |
| `pricing` / `exceptions` / `buy-plans` / `inventory` / `roadmap` / `budget-requests` | none | host | `ModuleGridToolbar` on several | no / weak |
| `CporCaseWorkspace` + payment/load panels | none | host | host | settlement desk |
| design-lab `FundingSurface` / `MarketSurface` / `StockSurface` / `DataSurface` / `PromotionPlannerSurface` | n/a | lab | lab | lab fixtures |

Design-lab copies are not production. Do not port lab fixtures.

---

## Chrome that pushes working content below the fold (VERIFIED / ASSERTED)

| Surface | What sits above the working grid | Class |
|---|---|---|
| **Case book** `CaseBookSurface` | Info `Alert` + `LifecycleRail`, then `HeadlineStrip`, then **`PaymentEvidenceOverlayPanel`** (figures + pending list + unmatched list), then ageing/blocked panels, **then** `ScopeBar` + grid | **VERIFIED** — this node |
| Lab `FundingSurface` book lens | `Alert` + rail, strip, ageing/blocked, **then** `ScopeBar` + grid (no payment overlay) | **VERIFIED** referent; overlay is product-only |
| Import Center | Guided wizard + many sections | **ASSERTED** — not this node |
| Market listings | domain chrome + multiple panels | **ASSERTED** — not this node |
| `/cpor-cases/<id>` `CporCaseWorkspace` | multi-panel settlement desk | **UNCOVERED** — no lab render |

**Decision for this node:** Case book working content is `HeadlineStrip` + `ScopeBar` + grid. Keep lab primitives. Do not copy lab Alert-first if that leaves the book unusable. Move overlay and ageing **below** the grid. Shrink the Alert to a caption so the lifecycle rail is not a second page of prose.

---

## Rows that look actionable but are not clickable (VERIFIED)

| Row | File | Looks like | Click today |
|---|---|---|---|
| Unmatched historical Case IDs | `PaymentEvidenceOverlay.tsx` `cpor-unmatched-file-evidence` | `PanelRow` list | **none** — no `href` / `onClick` |
| Pending — Latest Comment | same overlay | `PanelRow` | **none** |
| FX-blocked / negative-support on Case book | `CaseBookSurface` | `PanelRow` | **has** `onClick` → `?case=` |
| Steward queue Open | `StewardFailureQueue` | button + row click | **has** steward href |

`PanelRow` already supports `href` / `onClick` (`workbench-ui/Panel.tsx`). Do not invent a parallel list.

**Resolution path for unmatched file Case IDs (existing):** payment-evidence import steward at `/commercial-planner/cpor-cases/payment-evidence-import`. Exact Case ID match only; unmatched stays reviewable; **not minted** as `cpor_case` (overlay copy + API `match_rule`). Linked `case_id` stays on the Case book via `?case=` drawer — do not send this node to `/cpor-cases/<id>` (that desk is UNCOVERED).

---

## Settlement workspace (VERIFIED UNCOVERED)

`apps/web/src/app/(app)/commercial-planner/cpor-cases/[id]/page.tsx` mounts `CporCaseWorkspace`. There is **no** design-lab settlement-desk surface (lab book lens uses `EntityContextPanel` only). Designing that desk is not a migrate. **Out of this node** unless a lab composition exists — it does not.

---

## Coherent subset (implement)

1. `EnterpriseDataGrid`: `enableCellTextSelection` + `ensureDomOrder`; pointer cursor when `onRowClicked` is passed. Community clipboard of cell text. No range/Excel.
2. Case book: HeadlineStrip → ScopeBar → grid first; overlay + ageing after; Alert becomes a caption (LifecycleRail retained, not a full-width essay above the fold).
3. Unmatched historical Case ID `PanelRow`s (and pending-comment rows in the same overlay) get `href`/`onClick` into **existing** destinations: `?case=` when `case_id` is set; payment-evidence import `?code=` when not. No auto-create. FLAG ≠ BLOCK. Exact Case ID only.

## Routed out

- Dual column pickers (`MasterColumnPickerDialog` vs `ColumnSelectorModal`).
- AG Grid Enterprise range selection / Excel export (no module in tree).
- Settlement workspace `/cpor-cases/<id>` lab design.
- Lineup `ApprovalBadge` IBM Plex leftover (consumer cell renderer, not the wrapper).
- Import Center / Market chrome-below-fold.
- Legacy mapping-queue grid on `/admin/mappings` (D-0002).
- N-0025 remediation, N-0006, N-0013, D-0010, BACKLOG-181, Movement/Execution.
