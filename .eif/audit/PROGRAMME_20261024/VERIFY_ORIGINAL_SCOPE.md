# N-0116 original-scope bounded verification

Run: `RUN-20261024-N0116-VER-ORIGINAL`
Branch: `feat/ns-2-brief-nav-collapse`
Observed HEAD: `17d0d1b209645723594df62c4e386908cae504a4`
Scope: bounded source and evidence review of S16 comparisons, S17 dashboard overrides/fixed windows and S19 CPOR named cases. The uncommitted continuation does not change the observed HEAD. This is not acceptance of N-0116 or the original programme scope.

## Verdict

**VERIFIED_WITH_LIMITATIONS for the bounded S16–S19 implementation review; no node acceptance.** The earlier S16 missing-bucket finding is fixed in the currently reviewed source and the focused comparison/request sample passes. S17/S19 evidence is supported by source inspection and artifacts, with database/authentication and original business/model requirements still open.

## Finding recheck

The prior MAJOR finding was that calendar positions missing from both comparison results were omitted, compressing an interior time-series gap. The fix in `apps/web/src/features/dashboards/builder/comparison.ts` now materializes every current-window calendar slot for each observed category identity, with null current/prior values where neither answer had a row. It leaves a both-empty comparison empty and refuses expansion above 5,000 calendar/category positions. `comparison.test.ts` now includes a missing-both-sides regression.

Evidence: `s16-gap-red.json` reproduces the regression before the fix (5 passed, 1 failed; the new case expected six rows and received four). I independently ran the allowed sample to completion:

`pnpm --dir apps/web exec vitest run src/features/dashboards/builder/comparison.test.ts src/features/dashboards/builder/requestFor.test.ts --no-cache --maxWorkers=1 --minWorkers=1`

Observed: 2 files passed, 28 tests passed, exit 0; duration 49.82 seconds. This covers the gap regression and the request/filter behavior sample. It does not replace full-suite or browser verification.

## Reviewed evidence and observations

- S16 code aligns calendar buckets by position, matches categorical groups by identity, refuses duplicate grouping keys rather than summing them, retains nulls and prior-only categories, preserves server totals, and surfaces truncation. `ComparisonChart.tsx` renders separate current/prior series and comparison table columns. The bounded gap defect is resolved. I did not independently browser-check category truncation or multi-category chart usability.
- S17 API validation in `dashboard_definitions.py` restricts option keys, validates catalog filter IDs and canonical ISO dates, rejects reversed windows, and stores normalized settings. `requestFor.ts` omits only explicitly ignored dashboard filters; definition-owned filters remain and intersect other dashboard filters. Fixed windows override dashboard dates; ignored date removes the dashboard window. Create/edit/duplicate/promote carry the settings, and saved-report downloads use v2 for fixed-window definitions while retaining existing access checks and the legacy path for v1-equivalent definitions.
- S17 artifacts inspected: `s17-focused-api.xml` 47 passed; `s17-export-final.xml` 55 passed; `s17-focused-web.json` 21 passed. The 55-test export artifact covers mocked XLSX/PDF download cases; it is not real-DB delivery proof. The corrected `fixed-delivery-db-corrected.xml` reports 3 passed: two mocked XLSX/PDF saved-report export tests and one `cip_test` delivery integration. The corrected integration fixture inserts a tenant, customer, product and January/February sellout rows, verifies the January fixed-window delivery returns 13 and matching vintage, then rolls back and clears cache. This artifact was inspected but not rerun by this verifier.
- S19 compiler/loader/model changes use case `id` as the key/filter and `case_name` as the display name on the existing CPOR case join; case IDs use integer validation and tenant scope remains on the CPOR model tenant path. This supports duplicate names as distinct cases and null names as unassigned. `s19-focused-api-final.xml` reports 81 passed and includes named-case, tenant-isolation, compiler and DB tests; the focused web artifact is `s19-focused-web.json`. These artifacts were inspected, not freshly executed by this verifier.
- Original stock-cover/restock/value/open-case definitions, N-0115 model requirements, tenant calendar/configuration/calculation requirements, authenticated workflows and non-owner RLS evidence remain open. Fixture/UI tests do not close them; no production behavior is claimed.

## Limits and separation

No database connection, service action, migration, source edit or git mutation was performed. Full final suites were not rerun. The fresh focused Vitest sample was independently executed in this bounded agent context; model identity/separation is not attested, so this does not claim an R3 independent-model gate. No source SHA pin was independently generated for this moving, uncommitted continuation. No node acceptance is asserted, and temporary scope cuts remain unaccepted deferrals.

## Authenticated and browser follow-up (24 October)

Artifacts added after the bounded S16–S19 review were inspected; they were not rerun by this verifier.

- `api-original-scope.xml` reports 3,397 total, 3,376 passed, 21 skipped, 0 failed, with the same seven warnings reported by the implementation run.
- `authenticated-api-corrected.xml` reports 2 passed. The real bearer/ASGI fixture denies unauthenticated requests and spoofed identity headers, checks admin/viewer/no-product-line/other-tenant query totals and cache isolation, then logs out and checks revocation. The workflow test covers starter creation, fixed-window widget create/edit, promotion, saved-report export/delivery, and tenant privacy. It uses two seeded tenants, ephemeral credentials and a single outer transaction that is rolled back. No passwords or tokens are written to fixture repr or test assertions.
- The fixture asserts its connected role is neither superuser nor `BYPASSRLS`, and the requests execute through real auth and tenant/product-line scopes. This is authenticated application-level test evidence, but not non-owner RLS proof: the connection may own the tables, and forced RLS/owner bypass semantics are not established by this check. The fixture checks the DB identity after opening its connection; normal invocation is through `db_on.py` on `cip_test`, with the existing test conftest connect veto protecting `cip` absent explicit opt-in.
- `browser-original-scope.json` reports 5/5 fixture browser checks passed. These run with the API proxy disabled and fictional fixture data; they do not establish authenticated browser workflow coverage. `test_browser_builder_on_transactional_cip_test` is an opt-in third test (`CIP_RUN_BUILDER_BROWSER=1`) that starts a dynamic loopback ASGI listener over the same rolled-back test connection, serializes browser requests, passes an ephemeral bearer to the Next proxy, rejects dev API ports 8001/8010 in its Playwright config, and disables trace/video/screenshots in the runner. The browser test itself writes one deliberate fictional-data screenshot. Source review found no production service restart or migration path in this harness. Its pnpm child has Playwright and web-server timeouts internally but no outer `communicate()` timeout/termination guard, so a wedged child can hold pytest open; this is a non-blocking test-runner safety limitation. No `browser-authenticated.json` artifact exists yet, so that opt-in browser result remains pending and unverified here.
- `browser-keyboard.json` and `browser-keyboard-corrected.json` each fail the full-screen keyboard focus check. The first shows the close button never receives focus; the second checks containment and times out because focus remains outside the dialog. This is a repeated material accessibility failure, not resolved by the 5/5 visual/interaction artifact. The two-attempt stop rule was followed; bounded product fix is pending operator response. No further focus test or source change was attempted in this review.

These additional artifacts do not change the bounded S16–S19 verdict or close N-0116. No acceptance or R3 model-separation claim is made. Original business/model definitions and non-owner RLS evidence remain open; the keyboard focus defect and authenticated browser run remain outstanding.

## 25 October continuation review

Current committed backend checkpoint observed at `5aceee9a54e33f98030b2f02a571c652c9ad585a`; frontend focus and authenticated-harness hardening were uncommitted at review time. This continuation was source/artifact review only; no tests were run by this verifier.

- `web-original-scope.json` reports 1,139/1,139 passed. `api-original-scope.xml` reports 3,376 passed, 21 skipped, no failures, with the seven already reported warnings. These are implementation-run referents, inspected rather than re-executed here. The authenticated API proof remains 2/2 passed in `authenticated-api-corrected.xml`; the earlier limits on transaction rollback, test DB role ownership and non-owner RLS proof still apply.
- `browser-authenticated.json` reports 1/1 passed with no retry/flakiness. The spec uses the real browser app and proxy, seeds a real bearer into browser storage, checks the isolated DB identity, and exercises fixed-window create/edit/reopen, duplicate/reload, CSV export and promotion. It rejects browser API requests whose origin is not the isolated Next host. `playwright.builder-auth.config.ts` requires a dynamic loopback port other than 8001/8010, clears `NEXT_PUBLIC_API_URL`, and disables trace/video/automatic screenshots. The ASGI wrapper allows only the needed auth, dashboard, query, semantics and report endpoint prefixes plus the DB identity probe; unrelated browser routes receive a local 404 so the host ops/log endpoints cannot be read. The harness now bounds the pnpm child at 600 seconds and kills only its owned process tree on timeout. These controls address the earlier open authenticated-browser and unbounded-child concerns. I inspected `renders/original-scope/authenticated-fixed-widget.png`; it shows the fictional tenant's fixed-window table data and the fixed-date exception caption.
- The focus fix in `V2WidgetCard.tsx` passes a ref to the menu trigger and focuses the full-screen dialog close button after its transition enters; after exit it returns focus to that trigger. The updated browser check asserts initial close-button focus, reverse-tab containment, Escape dismissal and trigger focus restoration. The earlier two keyboard artifacts remain failing evidence for the prior implementation. At this initial 25 October review cutoff, the updated six-case fixture browser run and focused Unit C suite/TypeScript check were still in progress. The final results below supersede that interim status.

The bounded S16–S19 verdict remains VERIFIED_WITH_LIMITATIONS, with no node acceptance. Original stock-cover/restock/value/open-case semantics, remaining N-0115 model and tenant calendar/configuration/calculation requirements, and non-owner RLS proof remain open. The keyboard focus behavior is resolved for the pinned source by the final browser regression below. No R3 model separation is attested.

## Final focus-gate evidence (25 October)

The source is frozen at the reviewed 39-path pin in `original-scope-source-sha256.json`; I independently recomputed SHA-256 for the focus card/menu, keyboard browser spec, authenticated fixture/spec and config paths, and each matches the manifest.

- `browser-original-final.json` reports 6 expected, 6 passed, 0 skipped/unexpected/flaky. The comparison/keyboard spec passed, including initial focus on Close, reverse-Tab focus containment, Escape dismissal and focus restoration to the menu trigger. This supersedes both earlier failing keyboard artifacts for the corrected source.
- `unit-c-original-final.json` reports 121/121 passed across 16 files. Root lint exits 0 with zero errors and 50 existing warnings; TypeScript exits 0, per `original-final-summary.json`.
- `original-final-summary.json` records the full web run (1,139/1,139, 218 files) as preceding the two-file focus correction. The later focused suite, six-case final browser run, TypeScript and lint cover the frozen correction; I do not present the earlier full-web run as testing the corrected focus files.
- `auth-export-final.xml` has 5 passed and 1 skipped (the opt-in browser case is separate); `authenticated-browser-harness-corrected.xml` reports the separate authenticated browser case passed 1/1. The direct Playwright artifact likewise passes 1/1. No acceptance follows from these test results.

The keyboard focus finding is resolved for the reviewed source, based on the corrected runtime regression. The final bounded review remains VERIFIED_WITH_LIMITATIONS. Original stock-cover/restock/value/open-case business definitions, remaining N-0115 model requirements, tenant calendar/overlay/calculation requirements and non-owner RLS evidence remain open. No operator acceptance or R3 model-separation attestation is made.

