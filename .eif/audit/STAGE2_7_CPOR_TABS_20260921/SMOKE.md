# N-0032 verification record — five CPOR tabs on the settlement desk

**Run:** `STAGE2_7_CPOR_TABS_20260921` · **Actor:** `stage2b-001` · **Date:** 2026-09-21 · **Baseline:** `BLN-0003` @ `e264410` · **Commit:** `ff118ec`

## Implemented

`features/settlement/SettlementCaseTabs.tsx` mounted under the desk in `SettlementDeskLive` (tabs: USD pivot, Events, Exports, Promo load, Payments / recon; only the active tab mounts). New panels `features/cpor/CporUsdPivotPanel.tsx` (table, totals, verbatim `missing_roe` copy, empty state), `CporEventsPanel.tsx`, `CporExportsPanel.tsx` — each owning its fetch behind `ModuleDataSection`. `CporCaseWorkspace` refactored to use the same three panels (982 → 870 lines) and **kept**: the desk still lacks `CporFxAnchorPanel`, `CporSettleReadinessRow`, `CporComparableCasesPanel` and the lifecycle transition buttons (BACKLOG-202 stamped Partial with that list; BACKLOG-093 stamped Restored).

## Tests

Focused vitest 57/57 including 6 new: pivot renders as a table with row/column/grand totals and no `<pre>`; totals withheld and verbatim copy when `missing_roe`; module empty state when no cells; tab host exposes five tabs and mounts only the active one; Events renders API rows; existing Promo-load and Payments panels mount unchanged. `page.fxReadiness.test.tsx` still green for the refactored workspace. `tsc --noEmit` exit 0 (real exit code). eslint 0 errors (2 pre-existing exhaustive-deps warnings in the workspace).

## Browser smoke — **PENDING, not claimed**

`/commercial-planner/cpor-cases/46` was checked three times in Chrome. The API moved to `CIP_AUTH_MODE=session` during this node; the agent does not handle passwords, so its tab cannot authenticate. The desk sat in `ModuleDataSection`'s loading state (no `/login` redirect, which suggests a token is present in the shared profile) while the full API suite was loading `cip`; the tab host was not yet in the DOM when observed. `quality.rendered` on N-0032 stays **pending** until an authenticated render is captured — either by Warren in his Chrome (shared `localStorage` token) or by an independent reviewer.

## Independence

`verification.referent` is independence-required (R2). This record is implementation-side evidence only.
