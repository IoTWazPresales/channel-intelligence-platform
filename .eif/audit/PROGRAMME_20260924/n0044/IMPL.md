# N-0044 implementation: D-c + rest of 2.7

Implementer (fresh context, resumed after the previous implementer hit a usage limit mid-check). Lenses: frontend-engineer, test-engineering-specialist, accessibility-specialist. Date 2026-09-24. Branch `feat/ns-2-brief-nav-collapse`.

## Resume review

The previous implementer's uncommitted web changes were reviewed file by file against DISCOVERY.md and the deleted workspace (read from git blob `d566192…`, `CporCaseWorkspace.tsx` at HEAD). Payloads were checked against the old workspace: `transition {action, confirm_over_budget_reapproval, fx_rate}`, `PATCH {fx_mode}` / `{fx_proposed_rate}`, `intelligence-exclude {exclude, confirm: true}`, `settlement/rollup {}`, action→target map (end→ended, cancel→cancelled). All match.

Defects found and fixed in this session:
1. **Misleading USD line when unbooked.** `DualMoney` prints `usdNote` *in place of* the USD when `missingRoe` is true. So the desk's Approved support read "Σ line USD at the booked rate" on an unbooked case. The same applied to the portfolio panel's per-unit figure when `support_per_unit_sold_usd` is null. Fix: pass `usdNote` only when a booked USD exists (`SettlementDesk.tsx` Approved support; `PortfolioReadPanel.tsx` both tiles). This was the one failing test (`page.fxReadiness.test.tsx` "withholds the approved USD…").
2. **Delivery-rate formatting.** `PortfolioReadPanel` used `format.fmtPct`, which multiplies by 100 only when |v| ≤ 1. A delivery rate above 100% (over-delivery) would render as, say, "1%". Replaced with a local `fmtRatio` (`(v*100).toFixed(1)%`, as the old panel did). **Finding:** `FundingChrome` header meta uses the same `fmtPct` on `delivery_rate`, so it has the same latent bug above 100%. Not changed here (out of scope).
3. **Gap closed:** the PM `last_comment` (a workspace header item) had no home. Added it as an Alert on `PlanWorkspace` (warning when the plan is rejected). `last_comment` was typed on `CporCaseDetail`.
4. **Test gap:** added a desk test that the intelligence-exclude switch and re-rollup post to their existing endpoints, and a PlanWorkspace test for the PM comment.

## Criteria

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | FX anchor facts, settle readiness row, comparable cases (lazy tab, a11y wiring) and transition buttons on the desk; existing endpoints only | **PASS** | `SettlementDesk.tsx`: Approved support `HeadlineFigure` (DualMoney, booked by/at or proposed/source caption); basis line in the header meta when FX is not blocked; readiness chips (`role="group" aria-label="Settle readiness"`) at the top of Next action; End/Cancel from `allowedNext` (confirm dialog in `SettlementDeskLive.tsx`, `aria-labelledby`); "Open in planner" for pre-approval targets. `SettlementCaseTabs.tsx`: `comparables` tab, only the active tab mounts. Tests: tab `aria-controls` = tabpanel id, tabpanel named "Comparable cases"; zero comparable calls before the click and one after. No API files touched by this node. |
| 2 | CporCaseWorkspace deleted only if nothing is lost | **PASS** (with recorded display-only residue) | Parity against discovery §1e: (1) exclude switch → desk; (2) FX mode toggle, (3) proposed-rate edit → PlanWorkspace (draft/rejected only, same as before); (4) approve-and-book `fx_rate` + over-budget reapproval → PlanWorkspace approve dialog; (5) re-rollup, (6) out-of-window toggle, (7) diagnostics, (8) import summary → desk; (9) header items: evidence basis is in the readiness chip, PM comment → PlanWorkspace. Not ported, all display-only and recorded in BACKLOG-202: `workflow_status` and `export_version` chips (export version is in the Exports tab), the first-6-flags chip row (PlanWorkspace has a flags panel), and the per-line Ttl result money columns on the settlement grid (discovery marked these optional). (10) lines/add line were already in the planner. (12) tabs were already ported (N-0032). No write capability is lost. |
| 3 | SettlementPortfolioRead deleted; the rest of the orphan SettlementContainer subtree kept | **PASS** | File deleted; its only mount at `SettlementBookRead.tsx` removed. `SettlementContainer`, `SettlementBookRead`, `SettlementScopeBar`, `settlementViews` etc. are untouched, and their tests still run green (`SettlementScopeBar.test.tsx`, `settlementViews.test.ts`). |
| 4 | CporPortfolioIntelligencePanel mounted trimmed, collapsed, on CaseBookSurface with DualMoney | **PASS** | Moved to `features/promotions-funding/PortfolioReadPanel.tsx`, mounted in `CaseBookSurface.tsx` after the ageing grid. Collapsed by default: the body and its two queries mount only when opened; the toggle has `aria-expanded`/`aria-controls`. Trimmed: no incremental-unit tile, no support-bias block, claim-evidenced-only line hidden at 0 cases. Money (spend, per unit, top BU/promo, norms) goes through `DualMoney`, local currency primary. |
| 5 | ModuleDataSection states for every fetching tab/panel; no migrations; read-only on cip | **PASS** | `CporComparableCasesPanel` now uses ModuleDataSection (loading, error with retry, empty). Both portfolio queries (portfolio, norms) use ModuleDataSection. The other tabs were already on it (N-0032). The desk gate was already on it. No migrations; no DB access at all in this session. |
| 6 | Tests; vitest on touched dirs green; tsc 0; eslint clean; BACKLOG-202 stamped | **PASS** | See Checks. BACKLOG-202 status now reads "Closed — workspace retired", with what moved where. |

## Checks (commands, from the repo root)

- `pnpm --filter @cip/web exec tsc --noEmit` → exit 0, no output.
- `pnpm --filter @cip/web exec vitest run src/features/settlement src/features/promotions-funding src/features/cpor fxReadiness` → exit 0, **Test Files 22 passed (22), Tests 78 passed (78)**.
  - An earlier run of the same scope passed all tests but reported two vitest "Unhandled Error: UNKNOWN: unknown error, open '…\AppData\Local\Temp\…\web\<hash>'". That was a Windows temp-file write in vitest's own module cache, not in a test, and it did not recur on the re-run. It is recorded as an environment flake.
- `ESLINT_USE_FLAT_CONFIG=false pnpm --filter @cip/web exec eslint <the 18 changed files>` → exit 0: **0 errors, 3 warnings**. All 3 warnings are pre-existing `react-hooks/exhaustive-deps` at `CaseBookSurface.tsx:207,220`. This node changed only the import and the mount line at about line 731.
- New and changed tests:
  - `page.fxReadiness.test.tsx` was retargeted to `SettlementDeskLive`. It has 6 tests: approved support, readiness, reapproval, diagnostics and settle hidden when FX blocks; the basis line in the meta; the unbooked USD withheld; the cancel confirm then POST; exclude and re-rollup POSTs; and comparables loading lazily.
  - `SettlementDesk.test.tsx`: 3 new tests (end/cancel, the reapproval banner and planner link, and the approved-support figure).
  - `SettlementCaseTabs.test.tsx`: comparables tab wiring and its empty state.
  - `PlanWorkspace.test.tsx` (new): 6 tests covering approve with `fx_rate` and reapproval true, then false; FX mode and proposed-rate PATCH; the lock outside draft/rejected; settle routed to the desk; and the PM comment.
  - `CaseBookSurface.test.tsx`: the portfolio panel mounts collapsed after the ageing grid, the DualMoney figures, and the trimmed sections.

## Files changed (commit below)

- Deleted: `apps/web/src/features/cpor/CporCaseWorkspace.tsx`, `apps/web/src/features/cpor/CporFxAnchorPanel.tsx`, `apps/web/src/features/settlement/SettlementPortfolioRead.tsx`, `apps/web/src/app/(app)/commercial-planner/cpor-cases/CporPortfolioIntelligencePanel.tsx`.
- Added: `apps/web/src/features/promotions-funding/PortfolioReadPanel.tsx`, `apps/web/src/features/promotions-funding/PlanWorkspace.test.tsx`.
- Modified: `features/settlement/{SettlementDesk,SettlementDeskLive,SettlementCaseTabs,SettlementBookRead}.tsx`, `features/settlement/{mapSettlementDeskView,settlementDeskModel}.ts`, `features/settlement/{SettlementDesk,SettlementCaseTabs}.test.tsx`, `features/promotions-funding/{PlanWorkspace,CaseBookSurface}.tsx`, `features/promotions-funding/types.ts`, `features/promotions-funding/CaseBookSurface.test.tsx`, `features/cpor/{CporUsdPivotPanel,DualMoney}.tsx` (comments only), `app/(app)/commercial-planner/cpor-cases/[id]/{CporComparableCasesPanel.tsx,page.fxReadiness.test.tsx}`, `docs/BACKLOG.md` (BACKLOG-202).
- The N-0048 files under `apps/api/**` were not touched and not staged.

Commit: `657dd1ed` (not pushed). IMPL.md and the `_tsc.txt` / `_vitest*.txt` logs in this folder are left uncommitted for the orchestrator.

## Not done / limits

- **UNABLE_TO_RENDER:** the web runs a production build. The node did not ask for a rebuild, so no browser smoke was done. The orchestrator must rebuild before any rendered check. Suggested foreground smoke: `/commercial-planner/cpor-cases/46` (ended, needs_reapproval: Cancel visible, End hidden, reapproval banner, Comparable cases tab), `/promotions?plan=<a proposed case>` (approve dialog; do not confirm), and `/commercial-planner/cpor-cases` (Portfolio read → Show).
- **Backend fix #4 from discovery** (`lines_missing_usd` and a per-currency guard in `portfolio_intelligence.py`) was not done. That file is under `apps/api/app/services/cpor/**`, where N-0048 is working concurrently, and the acceptance criteria do not require it. Live impact is nil today (all cases are fx_declared). Deferred.
- The approve dialog is prefilled with `fx_proposed_rate ?? roe_snapshot`, the same as the old workspace. `CaseBookSurface`'s drawer approve still posts a plain approve without `fx_rate`, as it did before this node.

## Open questions for Warren

- None blocking. The portfolio panel placement on the Case book is still the reversible default under D-0032.
