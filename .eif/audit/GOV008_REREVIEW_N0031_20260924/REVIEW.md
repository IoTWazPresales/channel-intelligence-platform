# GOV-008 re-review — N-0031 remediation (commit 99a89db8)

Reviewer model: Claude Sonnet 5 (claude-sonnet-5), acting as verification-controller (GOV-008), independent of the implementation run.
Scope: verification.referent only, per REVIEWER_BRIEF.md part B.
Independence rung: R2 — fresh session, same model family (Claude Opus 5.5 authored the remediation commit per its trailer); recorded as same-model, different-session review, not R3+ cross-model.

## Criterion under re-review

"Single source for grid row and header heights: one exported constant set consumed by EnterpriseDataGrid, gridPagination, ExceptionCategoryGrid and PlanVsExecutedView, with the packages/ui CSS-variable emission reading the same values or removed as dead."

## Evidence

### 1. Commit content — `git show 99a89db8`
`packages/ui/src/agGridMuiTheme.ts`, 2 lines removed, 2 comment lines added:
```
-    '--ag-row-height': theme.density === 'compact' ? '34px' : '42px',
-    '--ag-header-height': theme.density === 'compact' ? '36px' : '42px',
+    // Row and header heights are not emitted here: apps/web GRID_DENSITY is the single source,
+    // applied by EnterpriseDataGrid (the only consumer of these variables).
```
VERIFIED: the literal `34px/36px/42px` emission — which diverged from `GRID_DENSITY` (`40/40` comfortable, `34/36` compact) — is deleted, not merely aliased.

### 2. Grep for other literal/duplicate emitters
- `grep -rn "ag-row-height|ag-header-height|ROW_HEIGHT|HEADER_HEIGHT|rowHeight|headerHeight" packages/ui/src` → **no matches**. PASS — `packages/ui` no longer references these at all (removed as dead, per the criterion's second option).
- `grep -rn "42px|'34px'|'36px'|\"34px\"|\"36px\"" packages/ui/src` → no matches. No stray literals remain.
- `grep -rn "ag-row-height|ag-header-height" apps/web/src` → 3 hits, all inside `apps/web/src/theme/gridDensity.ts` (the constant-set/CSS-var-producer itself) plus a comment in `apps/web/src/design-lab/surfaces/DensitySurface.tsx`. No competing emitter.

### 3. Single source — `apps/web/src/theme/gridDensity.ts`
```
export const GRID_DENSITY: Readonly<Record<GridDensity, GridRowMetrics>> = {
  comfortable: { rowHeight: 40, headerHeight: 40 },
  compact: { rowHeight: 34, headerHeight: 36 },
};
export function gridRowMetrics(density) { return GRID_DENSITY[normalizeGridDensity(density)]; }
export function gridDensityCssVars(density) { ... '--ag-row-height': ..., '--ag-header-height': ... }
```
This is the one exported constant set. VERIFIED all four named consumers import from it:
- `apps/web/src/components/EnterpriseDataGrid.tsx:13` — `import { gridDensityCssVars, gridRowMetrics } from '@/theme/gridDensity'`; used at lines 46/50/129/130 for both the CSS vars and the `rowHeight`/`headerHeight` grid props.
- `apps/web/src/features/plan-vs-executed/gridPagination.ts:1` — `import { GRID_DENSITY, gridRowMetrics, ... } from '@/theme/gridDensity'`; re-exports `STANDARD_ROW_HEIGHT`/`COMPACT_ROW_HEIGHT`/etc. and `gridRowMetrics` derived from `GRID_DENSITY`, not independent literals.
- `apps/web/src/features/plan-vs-executed/ExceptionCategoryGrid.tsx:13,143` — imports `gridRowMetrics`, calls `gridRowMetrics(density)`.
- `apps/web/src/features/plan-vs-executed/PlanVsExecutedView.tsx:50,461,474` — imports `gridRowMetrics` (via `gridPagination.ts`), calls it twice.

All four named consumers trace to the same constant set. PASS.

### 4. Stale documentation (finding, not a criterion fail)
Three comments were **not** updated by the commit and now contradict the current code:
- `apps/web/src/theme/gridDensity.ts:12-15` — "`packages/ui/src/agGridMuiTheme.ts` still emits these two variables with its own literals... hoisting this file into `@cip/ui` and deleting that duplicate emission (N-0031 acceptance criteria) remains open and out of scope."
- `apps/web/src/components/EnterpriseDataGrid.tsx:43` — "`@cip/ui` still emits...".
- `apps/web/src/design-lab/surfaces/DensitySurface.tsx:21` — "packages/ui/agGridMuiTheme.ts also emits --ag-row-height/--ag-header-height (out of scope; ...)".
All three describe a state the commit already fixed. Functionally harmless (code is correct) but misleading for future maintainers; recorded as a finding, does not fail the criterion since the criterion is about the code path, which is now singular.

### 5. Live app — `/admin/customers`, Claude-in-Chrome
- Attempted `document.styleSheets` / `getBoundingClientRect` JS check via `javascript_tool`: **BLOCKED** by the extension's own safety filter (`[BLOCKED: Cookie/query string data]`) — `/admin/customers` client-side-redirects to append `?page=1&page_size=50&sort_by=...&sort_dir=...` immediately after navigation, and the extension blocks script execution on any tab whose current URL carries a query string, regardless of script content (confirmed JS execution works fine on query-string-free pages, e.g. `/brief`). Recorded as **UNABLE** for the DOM/stylesheet-iteration method specifically — this is an environment/tooling limitation, not evidence of a defect.
- Fallback: rendered-pixel measurement. Took a full-page screenshot, then a 633×389 zoomed capture of the header + first 6 rows (zoom region (243,528)-(620,760), scale factor ≈1.678×). Row-divider spacing measured at ≈67 zoomed px between consecutive boundaries → 67 / 1.678 ≈ 39.9px in page coordinates. VERIFIED (pixel measurement, ±1px tolerance) — rendered row height is ≈40px, matching `GRID_DENSITY.comfortable.rowHeight = 40`, i.e. consistent with the single source and inconsistent with the old dead `42px` literal.
- No stylesheet other than the grid's own inline style setting `--ag-row-height`/`--ag-header-height` could be positively ruled out via the DOM method (blocked); ruled out via static analysis instead (section 2: no matches for these variables anywhere in `packages/ui/src`).

### 6. Type checks
- `pnpm --filter @cip/web exec tsc --noEmit` → completed with no output (exit clean). PASS.
- `pnpm --filter @cip/ui exec tsc --noEmit` → completed with no output (exit clean). PASS.

## Verdict per criterion

| Criterion element | Result |
|---|---|
| One exported constant set | PASS — `GRID_DENSITY`/`gridRowMetrics`/`gridDensityCssVars` in `apps/web/src/theme/gridDensity.ts` |
| Consumed by EnterpriseDataGrid | PASS |
| Consumed by gridPagination | PASS |
| Consumed by ExceptionCategoryGrid | PASS |
| Consumed by PlanVsExecutedView | PASS |
| packages/ui CSS-var emission reads same values or removed as dead | PASS — removed (static-analysis confirmed, zero remaining references) |
| Rendered rows are 40px | VERIFIED via pixel measurement (DOM method blocked by tooling, not by evidence of failure) |
| tsc clean (web, ui) | PASS |

## Overall verdict: VERIFIED_WITH_LIMITATIONS

`verification.referent`: pass — all criterion sub-clauses hold under static analysis, commit diff, and tsc; the one live-DOM check (stylesheet iteration) could not run due to an extension-level safety block unrelated to the code under review, substituted with a pixel-measurement method that corroborates the same conclusion. Rated VERIFIED_WITH_LIMITATIONS rather than VERIFIED because the DOM/stylesheet method specified in the brief was not directly executable and the substitute has intrinsic measurement tolerance (±1px) and a smaller sample (6 rows).
