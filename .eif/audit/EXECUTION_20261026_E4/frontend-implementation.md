# E4 frontend implementation handoff

Frontend Engineer AE-006 under the root E4 assignment; no independent verification claim. Branch observed `feat/ns-2-brief-nav-collapse`, entry HEAD `d2200cb1f139d28642ad44a79dc6403f30d28c34`. Existing dirty runtime, ledger and tsconfig files were preserved. The absent engineering-rules.mdc is the already recorded onboarding limitation in the frontier.

| UI / trigger | API route | Celery task | Sync writer | Commit model |
|---|---|---|---|---|
| Widget Promote | POST /api/v1/dashboards/{id}/widgets/{id}/promote | N/A | Existing saved-definition promotion route, root-owned | Existing route transaction |
| Reports model download | GET /api/v1/reports/saved/{id}/export?format=xlsx or pdf | N/A | N/A: read/export | N/A |
| Reports legacy form download | POST /api/v1/reports/export | N/A | N/A: read/export | N/A |
| Send / Schedule | Existing saved report delivery / schedules routes | Existing scheduling, unchanged | Root-owned delivery paths | Unchanged |

Canonical targets: DashboardWorkspace uses existing requestFor with the same current context passed to its cards; ReportBuilderView calls the existing saved export route for a loaded definition_v2. Existing divergence was context-free promotion and reconstruction through the legacy report form. Direction: wire these callers to canonical request/definition paths.

## Changed source

- apps/web/src/features/dashboards/DashboardWorkspace.tsx: promotion passes `{execution: plan.request}` for model definitions; legacy requests remain body-free. Blocked required/empty/catalog plans never POST. Refusals and success are visible, with actual fixed dates disclosed; saved reports cache is invalidated after success.
- apps/web/src/features/dashboards/DashboardWorkspace.integration.test.tsx: inherited unsaved bar, transient date/channel selections, own-filter intersection, sort/limit, ignored filters/fixed dates, required/empty/catalog refusal and legacy/server-error coverage.
- apps/web/src/features/reports/ReportBuilderView.tsx: loaded definition_v2 has a clear saved-question mode; legacy author controls and metadata are hidden, legacy Run/Save disabled with handler guards, and an explicit new-report action restores authoring. Excel/PDF use saved GET exports even with legacy grains empty. Send/Schedule use the saved id. Legacy loaded period_grain survives run/save/current-form export.
- apps/web/src/features/reports/ReportBuilderView.test.tsx: both export formats, saved-mode state/controls, Send/Schedule and new-report transition; edited legacy ad-hoc export and period-grain run/save preservation.

## Focused execution

- frontend-before.txt: 10 failed / 19 passed (29); reproduced promotion omission/refusal disclosure, saved export routing/state and legacy grain loss before source changes.
- frontend-after.txt: DashboardWorkspace + ReportBuilderView, 29 passed.
- frontend-final.txt: final ReportBuilderView (including save-grain assertion) + unchanged canonical requestFor, 34 passed.
- frontend-lint.txt: four changed source/test paths, exit 0.
- frontend-browser-lint.txt: new Playwright config/spec, exit 0.
- frontend-browser-list.txt: config parsed and one test listed, exit 0; no server or browser execution. Dummy dedicated loopback API was supplied only for configuration listing.

## Browser handoff (root executes)

New files: apps/web/playwright.e4-auth.config.ts; apps/web/e2e/e4-saved-query-auth.spec.ts; apps/web/tsconfig.e4-e2e.json. The config reuses the existing authenticated loopback guard, uses web 3107 and .tmp/e4-browser-next plus isolated tsconfig, disables traces/video, and writes only E4 JSON/screenshots. The spec uses the existing ephemeral bearer and real transactional cip_test API.

Scenario: UI creates E4 browser board / E4 January sorted, selects ascending units and limit1, then unsaved January dashboard dates plus Fixture customer0. Real query response must have row13 / total112 and exclude February900; promotion must carry that exact effective execution and save its dates/filters/sort/limit. Reports then downloads XLSX and PDF via GET; ZIP worksheet/PDF content must keep the single product0 row13, total112 and January dates. Send must use the saved id and return total112/January vintage.

This agent did not execute browser smoke, services, API tests, broad suites, builds, DB writes, ledger mutations, staging, commits or project-memory writes. Root owns browser/full gates, independent review, memory and delivery. Full v2 report editing and category rendering remain outside E4 scope.

## Independent-review null correction

Root reports the actual authenticated browser passed one test in 115.76 seconds; its JSON/screenshots remain preserved. The independent reviewer then found that the builder's `asList` omitted an owned JSON null filter and could broaden a promoted question. Additional ownership is limited to builder/requestFor.ts and requestFor.test.ts.

frontend-null-before.txt reproduces four failures (22 existing/positive tests pass): scalar null, [null], [null, "None"] and ["None", null]. The correction returns an `invalid_filter` blocked plan before converting an owned missing-value filter, with clear text that the builder cannot run or promote such filters yet. The original definition remains intact, even when the dashboard explicitly ignores that filter. Literal "None" remains ordinary text. Server model API support for JSON null is retained; broad picker/value-type support for null is excluded from E4. The root separately owns backend validation against missing/widened filters.

Saved-definition UI limitation: the read-only Reports state applies to every definition_v2, including migrated rows whose v1_equivalent flag is true. Those rows lose the former Reports legacy Run/edit-copy workflow; users can still download/send/schedule the saved question, or explicitly start a new report. This is a UX limitation of the excluded full v2 editor, not a claim of unchanged legacy edit compatibility.
