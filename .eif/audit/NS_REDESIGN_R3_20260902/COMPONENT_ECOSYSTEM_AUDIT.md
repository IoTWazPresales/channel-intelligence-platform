# CIP component ecosystem audit — settled from source

Run `NS_REDESIGN_R3_20260902`. Method: file inventory of `packages/ui/src`, `apps/web/src/components`,
`apps/web/src/features/*`; importing-file counts via `rg -l "\bName\b" apps/web/src --glob '!**/*.test.*'`
(2026-09-02); rendered inspection of shipped surfaces in `renders/current/`.

## 1. Where reusable UI actually lives

| Location | Files | Nature |
|---|---|---|
| `packages/ui/src` | 5 (`tokens`, `theme`, `agGridMuiTheme`, `AppThemeProvider`, `index`) | Tokens + MUI theme + AG Grid theme. **No components.** |
| `apps/web/src/components` | 13 components (+ tests) | **Shared behavioural primitives** — see §2 |
| `apps/web/src/features/import-steward` | 44 files | Generic steward engine (workspace, tabs, filters, bulk, plan, drawer, progress) |
| `apps/web/src/features/shell` | 11 | AppShell, WorkbenchSpine, ReadStrip, navConfig, spineNav, pagination helper |
| `apps/web/src/features/commercial-planner` | 33 | Lineup/CPOR workflow components (feature-local, several reusable) |
| `apps/web/src/features/{settlement,lineup,stock,brief}` | 13 / 12 / 7 / 2 | NS container kits (2026-08/09) — per-container ScopeBar/RegimeStrip/TaskCrumb/ReadStrip twins |
| `apps/web/src/features/dashboards` | 9 | DashboardWorkspace, DashboardGrid, DashboardWidgetCard, WidgetChart, MetricPalette + CanvasDropTarget, WidgetEditorDialog |
| `apps/web/src/features/{admin,background-tasks,steward-worklist,plan-vs-executed,shipping-mailer,cpor}` | 15 / 8 / 8 / 6 / 4 / 5 | Feature-local |

## 2. Shared primitives and genuine reuse (importing files, non-test)

| Component | Files | Verdict |
|---|---|---|
| `PageHeader` | 45 | Universal. Strong, plain. Keep; evolve visually (title/meta/actions slots). |
| `EnterpriseDataGrid` (AG Grid Enterprise wrapper) | 37 | The platform grid. Strong. Keep; add shared density/skin, column-state persistence conventions. |
| `ModuleDataSection` (loading/error/empty/`data_unavailable`) | 28 | Strong state treatment. Keep; make the standard state frame in the new shell. |
| `ModuleGridToolbar` | 23 | Consistent refresh/nav toolbar. Keep. |
| `BulkSelectionToolbar` | 12 | Reused across masters & imports. Keep. |
| `ImportStewardCandidateWorkspace` (engine root) | 7 | Benchmark-grade. Preserve; the shell must not degrade it. |
| `MasterDataGridShell` | 6 | Master grid chrome (search, column picker, drawers). Keep. |
| `CanonicalColumnMappingPanel` | 5 | Shared mapping step. Keep. |
| `BulkPasteDialog` | 4 | Keep. |
| `ColumnSelectorModal` / `MasterColumnPickerDialog` | 3 | Two column pickers → consolidate. |
| `ReadStrip` (shell) | 3 | Only used by Stock/Brief; Lineup has its own `LineupReadStrip`. Duplicate. |
| `KpiCard` | 2 | **Exists** in `components/` but the frozen design language discourages it → near-orphan. Revive as the Dashboard `kpi` widget body. |
| `EmptyWorkspace` | 3 | Fine; fold into ModuleDataSection empty variant. |

## 3. Duplicated / inconsistent

- **Scope bars:** `LineupScopeBar`, `SettlementScopeBar`, `SettlementShapeBar`, Stock lens filters, admin
  master search bars — five implementations of "scope + filters + dirty state". No shared one.
- **Regime strips:** `LineupRegimeStrip`, `SettlementRegimeStrip`, `StockRegimeStrip` — three copies
  of the same headline-figure strip (9.5px labels, right-aligned).
- **Task crumbs / lens switchers:** `LineupTaskCrumb`, `SettlementTaskCrumb`, `StockTaskCrumb`,
  `StockLensSwitcher` — same pattern, three files.
- **Grids:** MUI `Table` and AG Grid appear in roughly equal file counts; older admin/scaffold pages use
  MUI Table, workflow pages use AG Grid. Inconsistent density and interaction.
- **Charts:** Recharts in 4 files; Lineup/Settlement/Stock draw bars with hand-built `<div>`s. No shared
  chart primitive; `WidgetChart` (dashboards) is the only reusable chart wrapper.
- **Drawers:** steward engine drawer, master record drawers, settlement case pane — three chrome styles.
- **Navigation:** `spineNav.ts` (6 containers) and `navConfig.ts` (6 groups / 34 leaves) both live;
  AppShell renders the spine, admin pages still reference the legacy config. Double chrome OBS
  ("Channel Intelligence Platform" in AppBar and spine, `stock-cover-1280.png`).

## 4. Absent

Shared: scope/filter bar with saved views; headline-figure strip that scales (KPI-grade, not 9.5px);
chart primitives (bar/line/area/waterfall/heatmap) with shared axis/tooltip conventions; entity
context panel (product/customer/distributor "cards" with related workflows); global search /
command palette; capability directory (what CIP does); notification/attention inbox beyond the bell;
responsive summary-card fallback for grids.

## 5. Strongest vs weakest (rendered, 1280px)

Strongest: Import Center wizard (`imports-1280.png`), DSI steward job workspace
(`steward-dsi-job-1280.png`), Report builder (`reports-1280.png`), Lineup workspace (`lineup-1280.png`),
master grids, `ModuleDataSection` states, the Dashboard editor components (source-strong, rendered as
empty state).
Weakest: Brief (`brief-1280.png`: four rows, no figures), regime strips (compressed figures), Stock
grid identity columns (raw IDs, `stock-cover-390.png`), Dashboards first impression
(`dashboards-1280.png`), the 190px mono spine (low scent), scaffold pages (pricing/promotions/…).

## 6. The reconciliation inference — verdict

`CIP_FULL_PLATFORM_RECONCILIATION.md` §2.1: "`packages/ui` exports tokens and theme only — no shared
behavioural primitives." Premise true; conclusion **false**. 13 shared components in
`apps/web/src/components` with up to 45 importing files, a 44-file generic steward engine, and a
9-file dashboard builder exist. §2.2 of the same document lists many of them as "distinct
implementations" to be replaced. **Effect on N-0013:** the mockups recreated grids/filters/tabs in HTML
rather than composing real components; **effect on Phase B:** it was scoped as greenfield extraction
around the four NS container kits, treating the strongest assets as migration debt behind adapters.
Correct scope for a future Phase B is: consolidate the NS twins into shared `ScopeBar` /
`HeadlineStrip` / `LensTabs`; promote `KpiCard`, `WidgetChart`, `ModuleDataSection`,
`EnterpriseDataGrid` skin, steward drawer chrome into one component layer; add the absent primitives
in §4. Whether that layer lives in `packages/ui` or `apps/web/src/components` is a packaging choice,
not a capability gap.

## 7. Disposition of existing UI (input to prototype)

| Asset | Disposition |
|---|---|
| Steward engine, Import Center wizard, mapping panel | **Preserve**; re-host in new shell; improve drawer chrome consistency |
| EnterpriseDataGrid, MasterDataGridShell, BulkSelectionToolbar | **Preserve + improve visually** (skin, density, identity columns show names) |
| ModuleDataSection, PageHeader, ModuleGridToolbar | **Promote** to system primitives; extend slots |
| Report builder | **Preserve**; link with Dashboards ("pin to dashboard") |
| Dashboard editor components | **Promote to first-class**; new default (populated) state |
| NS kits: ScopeBar ×3, RegimeStrip ×3, TaskCrumb ×3, LensSwitcher | **Consolidate** into shared ScopeBar / HeadlineStrip / LensTabs |
| Hand-built bar `<div>`s | **Replace** with Recharts-based shared chart primitives |
| KpiCard | **Revive** as Dashboard KPI widget + headline figures |
| WorkbenchSpine (190px mono) + AppBar | **Replace** with new shell (see DIRECTION.md) |
| navConfig legacy | **Retire** after new IA maps all 34 leaves |
