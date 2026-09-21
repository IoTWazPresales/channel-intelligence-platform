# N-0031 implementation baseline — observed at `83ff3c5`

**Run:** `STAGE2A_GRID_PARITY_20260921` · **Actor:** `stage2a-001` · **Date:** 2026-09-21 · **Provenance:** implementation-observation

## Observed behaviour before change

| Surface | Observed |
|---|---|
| Grid heights | Four literals in three files: `components/EnterpriseDataGrid.tsx:121-122` (`36 : 42`, `34 : 42` hard-coded), `features/plan-vs-executed/gridPagination.ts:7-10` (`STANDARD_/COMPACT_` constants, comment "must match EnterpriseDataGrid"), `packages/ui/src/agGridMuiTheme.ts:78-79` (`--ag-row-height`/`--ag-header-height` emission, overridden by the explicit props so dead for height). Rendered: comfortable 42/42, compact 34/36. |
| `MarketSurface` competitor-mappings grid | `useQuery` at `:272` destructures only `data`; grid at `:1230` renders `rowData={mappings ?? []}` unconditionally → pending and failed fetches both paint AG Grid "No Rows To Show". |
| `LineupScopeBar` | From/To/BU/Customer are static `Typography` pseudo-selects; **Apply** (`:106`) and **Reset** are `Button`s with no handler, Apply styled as primary. Saved-view `Select` is real (URL `?approval=`). |
| `market.py` `/placeholders` | `competitor_price_import: status "ready"` while `fact_competitor_price` has 0 rows and `template_definitions.py` has no such template. |

## Latent capabilities to preserve

- `gridRowMetrics('comfortable')` spread into `gridOptions` (`app/(app)/shipping/page.tsx:554`)
- `paginatedGridHeight()` shell sizing in `ExceptionCategoryGrid.tsx:143-144` and `PlanVsExecutedView.tsx:461,474-475`
- Compact density toggle (`uiStore.density` → `CipThemeProvider` → `theme.density`)
- Lineup saved-view `Select` writing `?approval=pending`
- Competition mapping row click → `setSelectedMapping` → approve/reject in the context panel
- `/api/v1/market/placeholders` payload shape (`category_trends`, `share_panel`, `competitive_benchmark_hooks[]`, `note`)

All six are kept unchanged by N-0031; only their sources of truth or their honesty change.
