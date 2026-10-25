# Original-scope continuation after the frontend checkpoint

Run `RUN-20261024-N0116-IMPL-CODEX`, N-0116 implement, acceptance pending.
Frontend checkpoint `32c65eaf` and memory pin `17d0d1b2` were pushed to
`feat/ns-2-brief-nav-collapse`. Those commits passed full web 1,121/1,121, final Unit C 104/104,
API 3,363 passed / 21 skipped on cip_test, browser 5/5, tsc and lint. These are checkpoint results,
not final verification of the new uncommitted continuation below.

## S19 case breakdown

Regression-first: `s19-red-api.xml` has three failures; `s19-red-web.json` has 18 passed / one failed.
Extended the existing local breakdown metadata with an optional validated name column, using
the existing CPOR case base join and tenant predicate. Case responses carry case_id/case_name;
duplicate names stay separate, null names read Unassigned, totals remain SQL totals.
The first integration pass was 80 passed / one failed: case IDs were coerced as text, producing
integer = varchar. Registered case in the existing integer-ID validator and added invalid-ID
controls. `s19-focused-api-final.xml`: 81 passed. This includes duplicate/null names, case-ID
filtering, tenant B isolation, unchanged portfolio rules, templates and endpoint tests.
The drawer prioritizes case when supported and retains old-catalog fallback. The CPOR starter's
existing table now lists cases and outcomes, still eight widgets. Snapshots regenerated without DB.
Browser assertions for the Case header and fictional names passed in the new 5/5 matrix.

## S17 filter/date overrides

Added optional `definition_v2.dashboard = {ignore_filters?, fixed_window?}` to the existing stored
definition. The same create/edit/duplicate/promote writers persist it; no migration or new writer.
Only dashboard filters are skipped; own query filters remain. Explicit exceptions are always
visible. Fixed dates are ISO-validated on both sides, govern latest-stock captions and exports,
and set v1_equivalent false so report delivery retains their dates. KPI comparisons use the
widget's own window; effective export captions exclude ignored dashboard settings.

Regression-first: `s17-red-api.xml` one failed / six passed (invalid settings were already refused
at the unknown-key boundary); `s17-red-web.json` two behavior failures. `s17-focused-api.xml` 47
passed and `s17-focused-web.json` passed after the implementation. Real editor save/reopen,
duplicate and fixed-window comparison tests were added; `s17-integration-web.json` passed 109/109.
Initial tsc found two unsupported `exact` options in the new RTL test; removed those test-only
options, preserving exact string accessible-name matching. Subsequent tsc exited 0.

Found a causal correctness gap: saved-report download always used v1, so a promoted fixed-window
report could download all-time figures. `s17-export-red.xml` reproduces this in both XLSX and PDF.
Wired v2-only saved downloads to the existing v2 delivery query helper, preserving access checks
and legacy execution. Added requested window and truncation/count context to v2 export vintage.
`s17-export-final.xml` passed 55 tests (mocked exports plus existing definitions/report tests).
`fixed-delivery-db-corrected.xml` passed 3 tests, including actual rolled-back delivery on cip_test:
January 13 units returned, February 900 excluded, requested dates declared in vintage. Earlier two
DB attempts failed on missing required customer/tenant fixture rows; both were corrected in tests.

## S16 comparison series and columns

Line/area/column charts now show raw current and muted dashed previous values; tables add previous
columns with original units. Editor, preview, cards, full screen and exports share the same merge.
Categories match by identity; periods align by calendar bucket position within the two ranges.
Prior-only categories remain visible, missing values remain null, duplicate grains are refused,
server totals stay authoritative, and truncated/partial-boundary context is explicit. Exports wait
for matching current and previous results rather than downloading a stale filter/window answer.

Independent review found a material gap: an interior calendar bucket absent from BOTH responses
was compressed out. `s16-gap-red.json` reproduced it (5 passed / 1 failed). The fix materializes all
calendar positions per observed category, leaves both-empty results empty, and refuses expansion
over 5,000 positions instead of blocking the browser. `s16-gap-fixed.json` passed 38/38, including
real Recharts dashed marks, units, ISO-year boundary, null gaps and request/filter rules. The prior
`original-scope-focused-web.json` (153 passed / 1 failed) had an incomplete measure metadata fixture;
the test now supplies the actual API measure columns and raw units, without changing unit behavior.

Fresh bounded review `VERIFY_ORIGINAL_SCOPE.md` re-executed comparison/request rules 28/28 and
returned VERIFIED_WITH_LIMITATIONS after the gap fix. R3 model separation remains unattested.

## Authenticated integration and renders

`test_dashboard_v2_authenticated.py` uses actual bearer login and the real ASGI app on cip_test,
inside a rolled-back outer transaction. No auth/query mock, migration or service process. Two tests
passed in `authenticated-api-corrected.xml`: anonymous/forged headers rejected; tenant and assigned,
empty and admin product scopes isolated across cached queries; revoked token rejected; all three
starters created; fixed-window widget edit/duplicate/layout/promote/export/delivery preserve context;
private items remain private. Initial test assertions assumed a list-shaped scope and object-shaped
layout body; corrected to the existing string scope and list body contracts. Ephemeral fixture token
prefixes in that historical failure artifact were redacted; future fixture repr omits credentials.

The configured test login is cip, non-superuser and without BYPASSRLS. The relevant tables have
FORCE ROW LEVEL SECURITY, but cip owns them. This proves enforced owner-role scope, not non-owner
RLS/performance proof. No database role was created or granted.

New Playwright matrix: 5/5 passed in 4.1 minutes, :3106/.tmp isolated web, proxy disabled. Tests assert
actual theme styles, comparison dashes and notes, previous table columns, fixed-date exception,
CPOR Case header/names, no page overflow/errors/API requests, plus existing click/Esc/rows/fullscreen/
PNG interactions. Captures are `renders/original-scope/`; old checkpoint captures are preserved.
Desktop light and mobile dark CPOR captures inspected. Restored Next's temporary generated route
reference after the isolated run. Tsc and root lint exited 0 (50 pre-existing warnings).

## Remaining work and boundaries

S16/S17/S19 are implemented with focused and browser evidence above. Full final API passed 3,376 tests with 21 skips and 7 existing warnings in 660.52 seconds
(`api-original-scope.xml`); the two later authenticated tests passed separately. Full web is running
before the explicit-path commit/push; the implementation is not node acceptance.
Original business/model requirements and authenticated/RLS evidence remain open, not retired.
Authenticated HTTP proof above narrows that gap; authenticated browser proof and non-owner-role
RLS/timings remain open. Original domain decisions D-0116–D-0124 and D-0127–D-0129 remain proposed,
not implicitly accepted by a passing test. No permanent deferral or new business figure was chosen.
No production DB connection, migration, deployment, API/worker restart, main change or acceptance.
All supported ledger events/views remain local under the existing control-plane staging boundary;
the protection was not bypassed. Preserve unrelated dirty state.

## Bounded keyboard check: unresolved focus defect

The new comparison chart keyboard check verifies Enter filtering, Escape clearing and a named
accessible data table, but opening full screen from the menu leaves focus outside the dialog.
Two runs failed: `browser-keyboard.json` (expected Close button focus) and
`browser-keyboard-corrected.json` (relaxed to any focus within the dialog, still false). No product
focus implementation was changed. The AGENTS two-attempt stop rule was invoked; a bounded
additional fix was requested from the operator while independent authenticated browser work
continues. This failure is not claimed passed and no accessibility/node acceptance is granted.

## Authenticated browser harness development

First opt-in browser attempt (`authenticated-browser-harness.xml`) failed because the test clicked
New before the asynchronous starter catalog loaded: that correctly opened the blank dialog directly,
so the test then waited for a nonexistent menu item. The test now waits for the documented menu state
before clicking. Unrelated global chrome also attempted host ops-log reads, which the OS refused;
the test ASGI wrapper now rejects all routes outside auth/dashboard/query/semantics/reports, so no
future host log reads occur. Existing services were not changed. The test runner has a 600-second
child bound and scoped cleanup, and browser API requests are restricted to the isolated Next host.
The corrected opt-in run is pending; no authenticated browser success is claimed yet.

## 25 October continuation

Operator said continue after the bounded keyboard stop. N-0116 lease re-acquired through the
installed CLI (node revision 12, programme 2764). Backend unit committed as `5aceee9a`; feature
branch only, push pending final frontend checkpoint. Full web completed **1,139/1,139 in 218 files,
2,016 seconds**, `web-original-scope.json`. Authenticated browser corrected run passed **1/1**
(`browser-authenticated.json`; pytest harness 164.31 seconds,
`authenticated-browser-harness-corrected.xml`). The saved fictional-data widget capture was inspected.
This is actual bearer/browser/Next proxy/ASGI/Postgres integration, not fixture-only route responses.
Unrelated chrome routes were rejected at the test listener; no host-log access on the corrected run.

Focus correction now moves focus after the dialog transition, when the menu has restored its old
focus, and restores the stable menu trigger after closing. The regression asserts Close focus,
reverse-Tab containment, Escape closure and trigger focus return. No query/writer/DB behavior changed.
Complete Unit C and all six browser cases are running on this final source; historical focus failures
remain retained. No result is upgraded to acceptance.

## Final execution-unit results

- Final-source Unit C: **121/121 in 16 files**, `unit-c-original-final.json`.
- Final fixture browser: **6/6 in 4.7 minutes**, `browser-original-final.json`, including the focus fix.
- Final auth/export module: **5 passed / one opt-in skip**, `auth-export-final.xml`; that opt-in has
  its own successful actual browser run above.
- Tsc exit 0; root lint exit 0, 50 unchanged warnings; restored generated Next route reference.
- `original-final-summary.json` marks evidence cutoffs honestly: full web 1,139 predates the final
  two-file focus correction, which the later complete focused/browser checks cover. No query or
  backend product source changed after the full suites. The 39-path SHA manifest pins source.
- Fresh verifier independently inspected final referents and recomputed the six primary focus/harness
  hashes; `VERIFY_ORIGINAL_SCOPE.md` is VERIFIED_WITH_LIMITATIONS, with no R3 attestation/acceptance.
- Programme update attempt ordering: progress evidence succeeded at 2762; a prematurely overlapping
  stage note received permission/integrity error. After it completed, the unchanged documented CLI
  verified integrity true (same nine acknowledged old-node gate issues), and the stage note succeeded
  at 2763. No runtime/protection edits or weaker path were used.

All earlier failed artifacts are historical attempts, retained rather than described as passes.
The rendered examples and authenticated DB data are fictional. No production connection, migration,
deployment, API/worker restart, main modification, DB identity/grant mutation or node acceptance.
Original N-0115/business/calculation/calendar/overlay and non-owner RLS requirements stay open.
