# N-0116 execution test evidence — 24 October 2026

Run: `RUN-20261024-N0116-IMPL-CODEX`. Implementation evidence, not independent verification.

## Conditional colour

Corrected `table.test.ts`: 50 matches the existing >=20 rule; 5 probes the ignored fourth rule.
The production matcher is unchanged. Focused dashboard/workbench/report execution observed
`table.test.ts`: 10 passed. That broad execution overlapped addition of the regression tests;
its final result is not a clean baseline and will be superseded by the completed run below.

## Four correctness regressions, before fixes

Command (from root):

`pnpm --dir apps/web exec vitest run src/features/dashboards/builder/useDashboardRun.test.tsx src/features/dashboards/builder/clickFilters.test.ts src/features/dashboards/builder/fit.test.ts src/features/dashboards/builder/ViewRowsDrawer.test.tsx --no-cache --maxWorkers=2 --minWorkers=1`

Observed: 4 files failed; 8 failed / 12 passed (20 tests), duration 56.38s.

- Switching dashboard retained the prior customer's click selection.
- A disjoint bar/click selection replaced the bar customer instead of remaining empty.
- Shared-axis columns, line and area admitted currency and ratio measures together (three cases).
- View rows asserted widget equality without an original widget total for additive, stock and ratio measures (three cases).

These failures established defects before the behavior changes. Same-key widget-save refetch,
overlapping selection, chip clearing and other existing fit behavior remained controls.

## After the four fixes

`pnpm --dir apps/web exec vitest run src/features/dashboards/builder --no-cache --maxWorkers=2 --minWorkers=1 --reporter=json --outputFile=../../.eif/audit/PROGRAMME_20261024/builder-regressions.json`

Exit 0. Machine-readable results: `builder-regressions.json`. Includes the corrected colour test,
all four regression groups and existing builder unit tests. Changes stay in canonical workspace,
run-context, request-construction, visual-fit and drill-drawer modules; no new backend writer.

## Final-source checks

The final Unit C source set is identified by `source-sha256.json` (51 files). Browser runs use
isolated port 3106, `.tmp/builder-next`, and disable the API proxy. The temporary generated
`next-env.d.ts` reference was restored after browser execution; the running `.next` was untouched.

| Check | Observed result / referent |
| --- | --- |
| Request metadata guard, including measure present but model absent | 19/19 passed; `metadata-final.json` |
| Real query/card export lifecycle plus real workspace/editor integration | 10/10 passed; `export-workspace-final.json` |
| Complete final-source Unit C suite (builder plus workspace integration) | 104/104 passed, 15 files, exit 0; `unit-c-final.json` |
| Full web, `pnpm --filter @cip/web run test --maxWorkers=2 --minWorkers=1 --reporter=json --outputFile=../../.eif/audit/PROGRAMME_20261024/full-web-final.json` | 1,121/1,121 passed, 216 files, exit 0; 1,976 seconds; `full-web-final.json` |
| TypeScript, `pnpm --dir apps/web exec tsc --noEmit --incremental false` | Exit 0 after export and missing-model fixes |
| Root lint, `ESLINT_USE_FLAT_CONFIG=false pnpm lint` (PowerShell env syntax) | Exit 0; 0 errors, 50 existing warnings |
| Playwright, `pnpm --dir apps/web exec playwright test --config playwright.builder.config.ts` | 5/5 passed, 4.0 minutes; refreshed `browser-results.json` and `renders/accepted/` |
| Full API, `apps/api/.venv/Scripts/python.exe apps/api/scripts/db_on.py pytest --junitxml=../../.eif/audit/PROGRAMME_20261024/api-tests.xml` | 3,363 passed, 21 skipped, 7 warnings; exit 0; 580.73 seconds |

The test adapter's read-only identity probe returned `cip_test / 20261023_0048` before pytest.
No production database connection or migration was made. API warnings concern existing unawaited
AsyncMock calls in grid field/query-label tests. Lint required the documented compatibility variable;
the initial invocation without it failed before linting, then the corrected invocation passed.

The browser matrix covers 13 visuals and every widget in all three current starters (22 widgets),
light/dark verified with computed backgrounds at 1280 and 390 widths, no horizontal page overflow,
no page errors or API requests. The interaction case exercises scatter click/chip/Escape, full screen,
honestly labelled grouped rows and an actual PNG download. The dark mobile capture was inspected.
These are fictional fixtures, not authenticated test-DB or original missing business figures.

Historical failing artifacts are retained honestly: `full-web.json` is 1,118/1,119 (a request metadata
test collected while the guard changed); `final-focused.json` is 102/103 (create/edit test timeout).
The later metadata and workspace artifacts supersede those specific failures. Input simulation now
uses one field change rather than typing each character; no timeout was increased. The complete final
Unit C suite subsequently passed 104/104 and the full web run passed 1,121/1,121. These clean
referents supersede the historical failed runs. Source remained frozen through the final focused
suite and refreshed browser run; the full suite also overlaps the final small metadata/export additions,
which the later complete focused suite covers explicitly. No further product source changed.

The fresh-context review `VERIFY_UNIT_C_FINAL.md` is VERIFIED_WITH_LIMITATIONS for this bounded unit.
Its independent pure test rerun passed 31/31; it inspected source and the 19/19 and 10/10 artifacts.
It establishes at least R2 context separation; no completed R3 model-separation claim or node gate
is asserted. Its browser/full-suite limitations describe its earlier review cutoff. The interrupted
Astra review is separately recorded and is not a completed verdict.

EIF verify at programme revision 2759: integrity true, no integrity issues; exit 1 because of the same
nine acknowledged older-node gate issues (N-0006, N-0013, N-0014, N-0015, N-0016). No new gate pass,
operator acceptance or programme completion was recorded. Supported events and views remain local;
the protected control-plane checkpoint boundary was preserved.
