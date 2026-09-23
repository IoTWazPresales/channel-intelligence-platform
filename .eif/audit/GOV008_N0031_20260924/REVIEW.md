# GOV-008 independent review: N-0031 (R2, ui)

Reviewer: independent verifier (fresh context; lenses verification-controller, accessibility-specialist, frontend-engineer, test-engineering-specialist). Date 2026-09-24.
Evidence base: commits 5e70f33a and 459f4c94, the code at HEAD e52494fc, re-run tests, and the running app at http://127.0.0.1:3000 (signed in, own tab, closed at the end). I did not read the implementer's audit folder (STAGE2A_GRID_PARITY_20260921), docs/memory/CURRENT.md or CONTEXT.md. Statements in the commit message are treated as ASSERTED unless I re-observed them.
Independence rung: another session and fresh context, same model family. The implementation run was Claude Fable 5.1; this review is Claude Opus 5.5.

Logs in this folder: `vitest.log`, `tsc.log`, `pytest.log`, `eslint.log`.

## Per criterion

### 1. Single source for grid row/header heights: FAIL (one clause)
- VERIFIED: `apps/web/src/theme/gridDensity.ts:27-30` exports `GRID_DENSITY`. At HEAD it holds comfortable 40/40 and compact 34/36. The same file exports `gridRowMetrics()` and `gridDensityCssVars()`.
- VERIFIED consumers:
  - `EnterpriseDataGrid.tsx:13,47,50,129-130` sets the props and the inline CSS variables from this source.
  - `gridPagination.ts:1,13-18` re-exports the source's values.
  - `ExceptionCategoryGrid.tsx:143-144,258-259` and `PlanVsExecutedView.tsx:50,461-475` take their heights through `gridRowMetrics` and `paginatedGridHeight`.
  - `InboundShipmentsWorkspace.tsx:561` does the same.
  - A grep of `apps/web/src` found no other height literals outside the frozen design lab (`DensitySurface.tsx`).
- **FAIL clause:** the criterion requires "packages/ui CSS-variable emission reading the same values or removed as dead". Neither is true.
  - `packages/ui/src/agGridMuiTheme.ts:90-91` still emits its own literals: `'--ag-row-height': compact ? '34px' : '42px'` and `'--ag-header-height': compact ? '36px' : '42px'`.
  - After 459f4c94 these literals **disagree** with the single source (42 against 40).
  - VERIFIED live on /admin/customers: the emotion class rule `.css-1hv9xw.css-1hv9xw` still carries `--ag-row-height: 42px; --ag-header-height: 42px` (from the `...agVars` spread in `EnterpriseDataGrid` shellSx). It is masked only by the inline `style` override of 40px.
  - The code's own header (`gridDensity.ts:12-15`) says hoisting and deletion "remains open".
  - Functional impact today: none, because the inline override wins and `EnterpriseDataGrid` is the only consumer of `getAgGridMuiCssVariables`. It remains a live, divergent second source, which is exactly the drift this criterion was written to remove.
- Fix needed: delete the two keys at `agGridMuiTheme.ts:90-91`, or have them read `GRID_DENSITY` (hoisted into `@cip/ui`).

### 2. No visual change at comfortable/compact from the refactor itself: PASS (with limitation)
- VERIFIED by diff: at 5e70f33a, `GRID_DENSITY` was comfortable 42/42 and compact 34/36. These are identical to the literals it replaced in `EnterpriseDataGrid` (`compact ? 36 : 42`, `compact ? 34 : 42`) and in `gridPagination` (42/34/42/36). The refactor itself changed no value.
- The later change to 40/40 is 459f4c94 (operator decision D2). It is a one-file value change in `gridDensity.ts`, and every consumer followed it (see criterion 7).
- VERIFIED browser render on /admin/customers (comfortable, the current preference):
  - Inline `--ag-row-height` and `--ag-header-height` are 40px/40px, and the computed values are also 40px/40px.
  - The `.ag-row` rect is 40px (22 rows rendered), and the `.ag-header-row` rect is 40px (the outer `.ag-header` is 41px including its border).
  - The DOM therefore matches the source and the AgGridReact props.
- Existing tests: VERIFIED green (see criterion 6), including `ExceptionCategoryGrid.test.tsx`, which imports `STANDARD_ROW_HEIGHT`.
- Limitations:
  - Compact density was not rendered in the browser. Switching it means changing the operator's saved preference, a settings write I avoided. Compact is verified by code only: 34/36 is unchanged from before 5e70f33a through HEAD.
  - There is no dedicated unit test for `gridDensity.ts`.
  - The 5e70f33a tree (42/42) was not rendered by me. The running app is on the post-459f4c94 build.

### 3. Competitor-mappings grid in ModuleDataSection: PASS
- VERIFIED code: `MarketSurface.tsx` (5e70f33a hunk at about 1233-1263) wraps the grid in `ModuleDataSection` with `isLoading`, `isError`, `error`, `onRetry`, `isEmpty` and an empty state (title, description, Import Center → /admin/imports).
- VERIFIED: `git diff 5e70f33a^ HEAD -- MarketSurface.tsx` does not touch `SubstrateOrPlanned`, and the competitor-prices fallback at `:1312/1325/1334` is unchanged (BACKLOG-199 carve-out held).
- VERIFIED browser, /competition, Competitor mappings tab:
  - **Empty:** "No competitor mappings yet", the description, an "Import Center" link, and "0 mappings" appear inside `div[role=region][aria-label="No competitor mappings yet"]`.
  - **Loading:** I stubbed `window.fetch` in my tab to delay /competition/mappings by 4 s, then reset the TanStack query client-side. That rendered `div[role=status][aria-busy=true][aria-label="Loading competitor mappings…"]` with its text.
  - **Error:** I stubbed a 503 with detail "reviewer-injected 503". The page rendered `role=alert` with "reviewer-injected 503" and a **Retry** button. With the stub removed, I pressed Enter on Retry, which refetched and returned the page to the empty state.
  - No server data was written: only client-side fetch stubbing and cache reset in my own tab.
- Observation (environment, not product): my tab was `visibilityState=hidden` because another reviewer's tab was in front. TanStack paused retries/refetches while it was hidden, and I had to resume the paused query manually. While a first fetch is paused (`status=pending` plus `fetchStatus=paused`), `isLoading` is false and the section falls through to the **empty** state ("No competitor mappings yet") even though no data has loaded. This edge (hidden or offline tab on first load) is minor and pre-existing in `ModuleDataSection`'s contract. It is not something this node was asked to cover, so it is recorded as a finding and not as a failure.

### 4. LineupScopeBar inert Apply honest or wired: PASS
- VERIFIED: `git grep LineupScopeBar 5e70f33a^ -- apps/web/src` finds only its own definition and a comment at `workbench-ui/controls.tsx:67`. It had no importers, so it was dead code, and 5e70f33a deleted the file.
- VERIFIED: `LineupContainer.tsx:21,142` renders the shared `ScopeBar`.
- VERIFIED browser, /lineup/cases: the scope bar is `div[role=toolbar][aria-label="Scope"]` with three controls:
  - "All lines" chip (role=button, primary-filled, onClick present)
  - "Pending approval · 1646" chip (role=button, onClick present)
  - "Clear" button (primary colour, onClick present)
- No Apply control and no primary-styled control without a handler remains. Handler presence was checked through the React props on each element.

### 5. market.py reports substrate, and a test asserts it: PASS
- VERIFIED: `apps/api/app/api/v1/endpoints/market.py` returns `competitor_price_import` with `status: "substrate"` and an explanatory note.
- VERIFIED: `apps/api/tests/test_market_placeholders.py` asserts `status == "substrate"`, `!= "ready"`, `source == "imports"`, and the payload shape.
- Command: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_market_placeholders.py -q` gave `2 passed in 12.49s`, exit 0.

### 6. Tests, tsc, eslint: PASS
- vitest (relevant files): `pnpm --filter @cip/web exec vitest run` over the following files gave **9 files / 22 tests passed**, exit 0:
  - `EnterpriseDataGrid.test.tsx`
  - `ModuleDataSection.test.tsx`
  - `MarketSurface.test.tsx`
  - `ExceptionCategoryGrid.test.tsx`
  - `PlanVsExecutedView.test.tsx`
  - `lineup/cases/page.test.tsx`
  - `lineup/page.test.tsx`
  - `lineupViews.test.ts`
  - `cipTheme.test.ts`
- The full `pnpm test:web` was not run; its 695/695 result is ASSERTED by 459f4c94.
- `pnpm --filter @cip/web exec tsc --noEmit` exited **0**.
- eslint on the changed web files (`EnterpriseDataGrid`, `MarketSurface`, `gridPagination`, `SettlementDeskLive`, `gridDensity`) gave **0 errors, 1 warning**: `MarketSurface.tsx:288` react-hooks/exhaustive-deps on `listings`, a line outside the 5e70f33a hunks and so pre-existing.
  - Note: plain `pnpm --filter @cip/web exec eslint ...` fails on eslint 9 because of the legacy `eslintConfig` in package.json. It needs `ESLINT_USE_FLAT_CONFIG=false`. That is a developer-experience finding and not part of this node.
- Test-engineering gap: `MarketSurface.test.tsx` only mounts the surface with mappings returning `[]`. No test covers the mappings loading, error or Retry states. `ModuleDataSection.test.tsx` covers the generic component. There is also no unit test for `gridDensity.ts`.

### 7. Browser smoke: PASS
- /competition mappings lens: see criterion 3 (empty, loading and error with Retry all rendered).
- /lineup/cases scope bar: see criterion 4.
- Paginated grid, /stock?lens=execution (VERIFIED):

| Shell | Row rect | Header rect | Shell height | Formula | Paging summary |
|---|---|---|---|---|---|
| Exception grid | 40 | 40 | 688px | 40 + 15×40 + 48 | "1 to 11 of 11" |
| Drill grid | 40 | 40 | 888px | 40 + 20×40 + 48 | "1 to 20 of 234" |

  Both match `paginatedGridHeight()` from the single source.

### 8. Read-only on cip, no migrations, BACKLOG stamps: PASS
- VERIFIED: 5e70f33a touches no alembic or migration file (checked with `git show --stat`).
- VERIFIED: `docs/BACKLOG.md` has the N-0031 closure stamps at lines 2155 (BACKLOG-160), 2172 (BACKLOG-156) and 2908 (BACKLOG-199).
- Read-only on cip at runtime: ASSERTED. The diff contains no write path, so nothing contradicts it.

## Accessibility (quality.a11y)
VERIFIED in the browser (keyboard Tab/Shift+Tab via real key events, focusin logging, DOM/ARIA inspection):
- **Mappings empty state:**
  - `role=region` with aria-label equal to the title.
  - "Import Center" is a real `<a href="/admin/imports">`, reachable by Tab. The order is Pending chip → Approved chip → Import Center → the "Where this feeds" rows.
  - Its focus indicator is weak: `outline: none`, only the MUI elevation shadow and ripple, barely distinguishable on the dark theme. By comparison, the "Where this feeds" rows show a clear 2px blue outline.
- **Loading:** `role=status`, `aria-busy=true`, and an aria-label that matches the visible text. Good.
- **Error:** MUI Alert with `role=alert`, and the server message is shown. The Retry `<button>` has accessible name "Retry" and is reachable by Tab right after the Approved chip.
  - Focus: a filled-tint and ripple indicator, visible but with no outline.
  - After Retry, focus is lost to `<body>` because the button unmounts. Minor focus-management finding.
- **Deferred control in the same lens:** "Propose candidates" uses native `disabled` (tabIndex -1), not `aria-disabled`. Its explanation sits on the wrapper's `aria-label`/`title` ("Data only: a scorer exists…"), so keyboard users cannot reach it. This is outside the node's diff and pre-existing.
- **Lineup scope bar:**
  - `role=toolbar` with aria-label "Scope". Chips are `role=button` with tabIndex 0, and "Clear" is a native button. All are Tab-reachable in visual order, and focus is visible (ripple/tint).
  - The filter chips expose their selected state only by colour. There is no `aria-pressed` or `aria-checked`, which is a WCAG 4.1.2 / 1.4.1 concern and pre-existing.
  - `role=toolbar` without arrow-key roving is a minor pattern mismatch.
  - The "1647 plan lines" count is not in a live region, so a filter change is not announced.
- **Not tested:** screen reader output (NVDA/JAWS/VoiceOver), contrast ratios measured with a tool, 200%/400% zoom and reflow, and 390×844 viewport (resize not attempted given the known environment limit).

None of the a11y findings is in an acceptance criterion for this node, and the new states (status, alert, region, named Retry, reachable CTA) are sound. quality.a11y is therefore **pass**, with the findings above recommended for a follow-up.

## Verdict: **FAILED**
Criterion 1 fails on its explicit clause. The `packages/ui` CSS-variable emission still exists with its own literals, and after D2 (459f4c94) it carries a **different** value (42px) than the single source (40px). It is visible in the live stylesheet and masked only by an inline override. Criteria 2 to 8 pass (2 with the compact-density browser limitation).

The remediation is small: delete `agGridMuiTheme.ts:90-91`, or source them from `GRID_DENSITY`. `packages/ui` is now in change_paths according to `gridDensity.ts:13-15` (ASSERTED).
