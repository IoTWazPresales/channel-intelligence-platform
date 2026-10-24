# N-0116 implementation execution — 24 October 2026

Run `RUN-20261024-N0116-IMPL-CODEX`; branch `feat/ns-2-brief-nav-collapse`; inherited base `a380b9fa`.
Authoritative scope: original overnight functional requirements, reaffirmed by Warren. This report
covers a bounded frontend execution unit, not completion of N-0116 or the overall programme.

## Implemented

- Recovered ownership via installed `node.lease.acquire`, recorded operator evidence and entered implement.
- Corrected the faulty conditional-colour test, preserving the correct existing matcher.
- Reproduced and fixed dashboard click/name/date state crossing dashboard boundaries; same-dashboard
  refetch retains unsaved bar edits. Saved bar reset happens before children commit a query.
- Preserved disjoint click/bar intersections as empty and blocked relevant query execution.
- Rejected mixed semantic units on shared axes. Implemented two-axis charts with per-series units,
  separate titles/tooltips and optional saved right-axis assignment; same-unit combo remains separate.
- Replaced unsupported drill/widget equality wording with the actual total at the drill grouping.
- Implemented scatter with named marks, signed/zero values, omitted-coordinate count and keyboard
  filter actions; pivot with safe cell fields, 24-column guard, additive complete-response marginals
  and authoritative server grand totals. Non-additive/truncated subtotals are never manufactured.
- Wired visual options into the existing v2 editor, card, preview and full-screen body. PNG frame
  includes HTML axis captions/units; pivot uses CSV. Existing v1 routes/definitions remain available.
- Added catalog-driven extra attribute filters; unsupported/pending catalog attributes are not invented.
- Snapshot all three code-defined backend starters (22 widgets) for fictional browser fixtures;
  starter selection renders every current definition instead of metadata only.
- Compatibility tests prove layout-only PATCH, missing-route fallback only, non-fallback on real errors,
  definition preservation, explicit starter creation and duplication. Workspace integration tests
  cover switching/refetch, create/edit/reopen, recoverable save errors, layout and starter context.
- Fixed follow-up review findings: block missing catalog/selected metadata instead of silently dropping
  filters, guard lossy v1 editing on catalog failure, clear hidden filters on model change, and cap named
  trend series without summing rates/distinct counts into an invented Other series.
- Prevented CSV/PNG from exporting a placeholder answer under newly selected filters or after a
  blocked request; the prior drawing still stays visible while a valid replacement loads.

## Verification

Reproducible commands/results are in `N0116_TEST_EVIDENCE.md` and machine-readable sibling artifacts.
Browser config uses :3106 and `.tmp/builder-next` with the API proxy disabled. No production service
or database is used by fixture tests. Only `renders/accepted/` counts as final render evidence.

Initial samples: builder 60/60, builder/shared charts 119/119, workspace/filter integration 10/10;
five browser cases passed with actual light/dark style assertions and 1280/390 widths, all current
starters and click/Esc/full-screen/rows/PNG interactions. Follow-up fixes require final suite results.
Final-source root lint passed with zero errors and 50 existing warnings; TypeScript passed. Full API
on cip_test passed 3,363 with 21 skips. The final browser refresh passed all five cases in 4.0 minutes.
Request metadata 19/19 and export/workspace 10/10 passed after follow-up fixes. The complete web
passed 1,121/1,121 (216 files); the complete final-source Unit C suite passed 104/104 (15 files).
Historical failures remain disclosed and are superseded by these clean runs.

Independent fresh-context/different-model reviewer sampled 42 tests and reproduced the non-additive
Other defect (nine .8 rates produced an invalid Other=1.6). Three findings above were addressed.
The verifier hit its usage limit before issuing its final artifact/verdict. This is partial external
review evidence, not a completed independent GOV-008 gate or acceptance.

A bounded alternate fresh-context review completed in `VERIFY_UNIT_C_FINAL.md`, with 31/31 pure tests
independently re-executed and source/evidence inspection. Verdict VERIFIED_WITH_LIMITATIONS, at least
R2 fresh-context separation, not a completed R3 gate. It also found absent referenced model metadata;
the added request guard and exact `models: []` regression passed. The subsequent export fix was reviewed.

Supported ledger events are local. The installed CLAUDE.md control-plane rule protects programme
paths from ordinary shell staging; this run has not tried to bypass that protection. Product and
evidence commits exclude the local programme ledger, generated views and unrelated runtime leftovers.

## Original requirements still open

- S16: line/area/column comparison series and table comparison columns beyond current KPI comparisons.
- S17: per-widget dashboard-filter overrides and fixed date windows.
- S19: CPOR case-name breakdown; current drawer remains honestly grouped rows.
- Original starter stock-cover/restock/value/open-case semantics and the original N-0115 model,
  tenant-calendar/configuration and calculation requirements are not retired by the temporary cuts.
- Authenticated test-database workflows, non-owner RLS/performance proof, accessibility review and
  complete independent verification remain required. Fixture evidence cannot substitute for them.
- `/reports` v2 editing/source-line drill and other original open requirements remain in programme scope.

No node acceptance/completion is asserted. No cip migration, deployment, API/worker restart or main
change is authorised. Production schema remains at the reported 0047 checkpoint; cip_test identity
was rechecked as 0048 before API tests. No production database connection was made in this run.
