# N-0116 Unit C independent verification

Run: `RUN-20261024-N0116-VER-SOL`
Date: 2026-10-24
Branch / inherited HEAD: `feat/ns-2-brief-nav-collapse` / `a380b9fa3935ada99db6cd5339cffb59b35cb8fa`
Mode: implementation and evidence verification, bounded frontend unit
Verdict: **VERIFIED_WITH_LIMITATIONS**

This verdict covers the implemented Unit C frontend behaviors sampled below. It is **not** acceptance of N-0116, its original S16/S17/S19 requirements, the N-0115 data model, authenticated workflows, or production readiness. The work item remains `in_progress / implement`. I made no source, ledger, service, database, migration, deployment, or main-branch changes.

## Independence and authority

This report was produced in a fresh delegated context using GPT-6.1 Sol, separate from the implementation execution. The earlier GPT-6 Astra reviewer was a different model and reported a 42-test sample plus three findings, but did not issue a final verdict because of a usage limit. The current reviewer is different from that partial reviewer. This completed review establishes at least the fresh-context R2 rung; model separation from the implementing orchestrator was not independently attested here, so the completed artifact alone does not claim the full R3 rung. The partial Astra review remains separate evidence, not a substituted final gate.

The operator instruction authorizes development and verification, with no incomplete-node acceptance and no cip production migration/deployment. The review stayed within that boundary. The prescribed `.cursor/rules/engineering-rules.mdc` was absent in this checkout; the other listed context and GOV-008 contract were read. That missing context file does not establish permission to widen this verification.

## Direct sample and results

| Claim | Independent observation |
| --- | --- |
| Missing catalog metadata does not silently drop dashboard filters | `requestFor.ts` now blocks a null/undefined catalog, absent measure, and a present model measure whose referenced model is absent. The exact absent-model case is in `requestFor.test.ts`. I found this gap before the new guard and reported it to the implementer; the current tree contains the guard and regression. `V2WidgetCard.tsx` suppresses query execution for blocked plans. |
| Disjoint click/bar and widget/dashboard values remain empty | `clickFilters.ts` retains an explicit empty intersection; `requestFor.ts` blocks the applicable empty selection and widget-own intersection. The request tests and independent sample pass. |
| Switching dashboards clears transient clicks and names without losing unsaved same-board bar edits | `useDashboardRun.ts` resets transient state during the dashboard-ID render change; `DashboardWorkspace.tsx` keys saved filter state by dashboard ID and saved content, preserving local edits on same-board refetch. Hook and workspace integration tests cover the intended behavior. The workspace component test was inspected as test evidence, not independently rerun in this pass. |
| Mixed units cannot use a shared chart axis | `fit.ts` rejects mixed `semanticUnit` values for bar, line, area and combo; dual-axis requires two distinct units. `V2WidgetBody.tsx` renders separate left/right headings and per-series units for dual-axis. Fit, advanced-shape and body tests cover the cases. |
| View rows does not assert false equality with the widget | `ViewRowsDrawer.tsx` labels the server total as `Total at this grouping` and identifies model rows as grouped rows. Its component test covers additive, stock, and rate examples. |
| Changing model/family clears hidden widget-own filters | `BuilderEditorDialog.tsx` clears `own` before selecting the new family. The real workspace/editor integration test asserts the saved definition has no retained old filter. |
| Non-additive period series do not manufacture `Other` | `shape.ts` caps named series and reports an omitted count; it does not sum rates or distinct counts into an Other series. `shape.test.ts` checks null preservation and omitted categories; `V2WidgetBody.tsx` displays the omitted count. |
| Exports use the current query answer | `BuilderData.tsx` keeps a previous answer as visual placeholder only while a new request runs; a blocked request supplies no placeholder. `V2WidgetCard.tsx` requires a ready plan, an OK answer and `!main.isPlaceholderData` for CSV/PNG, and repeats the guard in each click handler. Its real QueryClient/card test holds the new request pending, confirms the old drawing stays visible with both exports disabled, then confirms export re-enables on the new answer and blocks again on an impossible filter selection. |

Independent command from repo root:

```text
pnpm --dir apps/web exec vitest run src/features/dashboards/builder/fit.test.ts src/features/dashboards/builder/shape.test.ts src/features/dashboards/builder/requestFor.test.ts --no-cache --maxWorkers=1 --minWorkers=1
Test Files 3 passed (3); Tests 31 passed (31); exit 0; 49.68s
```

I also inspected the actual JSON/XML referents rather than adopting the execution report's summary. `metadata-final.json` reports 19/19 passed, including the later catalog regression. `export-workspace-final.json` reports 10/10 passed: nine real workspace/editor integration assertions and one real QueryClient/card export assertion. The previously timed-out create/edit/reopen assertion passed in that later artifact after the input simulation was made a single `fireEvent.change`; the test timeout was not increased. `browser-results.json` reports five fixture browser cases passed. `api-tests.xml` contains a pytest suite with 3,384 tests, zero failures/errors and 21 skips; this review did not connect to the database or rerun it. The API adapter and advanced visual tests were reviewed for contract/edge coverage, not independently rerun.

## Material limitations and unresolved evidence

- `full-web.json` is a failing historical run: 1,118/1,119 passed, with the missing-catalog request test failing before the guard. `final-focused.json` is also a failing historical run: 102/103 passed, with one `DashboardWorkspace` create/edit/reopen test timing out at 15 seconds. The later `metadata-final.json` and `export-workspace-final.json` supersede those two specific failures, but the earlier broad artifacts cannot be cited as clean final-suite proof. A clean post-fix full web result was still pending at this review cutoff.
- Accepted screenshots under `renders/accepted/` and `browser-results.json` are fixture-only browser evidence at light/dark and 1280/390 widths. They precede later source changes (including 13:01 visual/editor changes and the 21:47 request guard). They cannot prove the exact final source tree or authenticated test-DB behavior. I did not start a browser or service.
- S16 line/area/column and table comparison beyond KPI, S17 per-widget dashboard-filter overrides/fixed windows, S19 CPOR case breakdown, original starter stock-cover/restock/value definitions, and original N-0115 model/calendar/configuration requirements remain open. Authenticated test-DB integration, non-owner RLS/performance evidence, accessibility review, saved reports/scheduled delivery and full original node acceptance are outside this bounded result.
- Existing dirty work includes unrelated paths. This review neither attributes those changes nor verifies a fresh-checkout committed unit. The production `cip` schema remains at the reported 0047 boundary; no production claim follows from the `cip_test`/fixture evidence.

No operator acceptance, node completion, or production safety conclusion is granted by this report.
