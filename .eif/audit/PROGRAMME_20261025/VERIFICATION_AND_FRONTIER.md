# Independent verification and next execution frontier — 25 October 2026

**Original-scope acceptance cannot pass.** N-0114 and N-0115 remain at verify with acceptance pending; N-0116 remains at implement with acceptance pending. Substantial implementation and historical evidence are valid, but newly reproduced query/export defects and missing original capabilities prevent completion. No node acceptance, production change or implementation is made by this run.

Run: `RUN-20261025-N0116-ASTRA`, primary reviewer Codex. Applied GOV-008 verification, GOV-002 isolation and GOV-001 routing; specialist product/architecture/UX reviews were routed as the EIF core requires. Specialist turns reached usage limits after persisting reports; this final synthesis and the N-0115 matrix are the primary reviewer's work. The review is complete as a targeted gap analysis, not as a successful product verification gate.

## 1. Verified checkpoint

| Item | Independently observed |
|---|---|
| Workspace | Existing `C:/Users/warren_eliason/channel-intelligence-platform`; Windows/local. No replacement, reset, clean, stash or restore. |
| Branch | `feat/ns-2-brief-nav-collapse` |
| Local HEAD / upstream / actual remote | All `d069f86c9232a735b87c64bb8f3fe3c7b5916b08`, checked with rev-parse and ls-remote. |
| Commit reconciliation | Backend `5aceee9a`, frontend/evidence `8ea51e9b`, memory `05a12607`, final delivery evidence `93217bf5`, handoff `1e3f5c8c`, handoff pin `d069f86c`. Earlier hashes are checkpoints, not conflicting current heads. |
| Evidence provenance | All 39 paths match the final source SHA manifest. All 16 evidence.add referents in events 2680–2767 resolve. Evidence tree `146b56ae3d0322b126c7c70b8c685ff4565b97cb` exists and equals the tree of `8ea51e9b`. |
| Inherited dirty files | All 20 hashes exactly match `HANDOFF_PERSISTENCE.json`. No product modifications. Historical untracked files preserved. New audit/memory files from this run are additional local work. |
| EIF entry revision | 2767, integrity true, zero integrity issues, nine acknowledged historical gate issues, no leases. Original Git prefix through 2679 unchanged; exactly 88 local-only events 2680–2767 at entry. |
| Nodes at entry | N-0114 revision17 verify/R2; N-0115 revision16 verify/R3; N-0116 revision14 implement/R3; all in_progress and acceptance pending. |
| Database observed | Read-only metadata queries only on `cip_test`: migration `20261023_0048`, login `cip`, neither superuser nor BYPASSRLS, transaction_read_only=on. |
| Production | No connection to `cip`. Its 0047 checkpoint remains reported, not freshly measured. No migration, service start/restart, deploy, main change, role/grant mutation or delivery send. |

Reproducible repository/Git check: `verify_checkpoint.py` and `checkpoint.json`. Fresh CLI commands: documented `status --node N-0116`, `verify`, and `frontier`. Final captured `verify` exited 2 because of the same gate debt, not ledger corruption (`programme-final-verify.json`, `closeout.json`). The installed programme CLI has no `start` verb; its integrity-checked entry and documented status command are the supported entry procedure. No synthetic start event or implementation lease was created.

The nine gate issues are N-0006 complete with invalid gates; five N-0013 provenance failures (disclaimed implementation run, design-sameness, rendered-comparison, referent and rendered verification); and invalid completion gates on N-0014, N-0015 and N-0016. All five affected nodes acknowledge their debt. These are not new N-0114/15/16 passes or failures.

`frontier` returns N-0098, N-0069, N-0084, N-0088, N-0094, N-0097, N-0099, N-0108 and N-0102. Runtime `engine.frontier` excludes in_progress nodes, and checks terminal dependencies for ready/proposed nodes. Thus this result is not a reason to abandon the explicitly requested active programme. N-0115 depends on N-0114 and N-0116 on N-0115; preserve those completion dependencies while resuming bounded work under original scope.

## 2. Evidence strength and independence

**Achieved rung: R2 fresh-context verification, not attested R3 different-model verification.** A separate session and specialist agents do not establish model separation from each implementation author. The installed runtime checks run/actor provenance, not model identity. `.eif/RUNTIME_CAPABILITIES.md` is unverified, with no current same-mode probe attestation; this run does not claim its controls ENFORCED. Keep R3 gate work open.

New executable evidence is deliberately narrow:

* `n0115_readonly_probes.py/.json`: final-source model/operator inventory, all 11 refusal texts, DSI/CST site wall, CPOR accepted-filter/total counterexamples, tenant semantic restriction counterexample. Portfolio I/O is mocked with fictional data; planner, handler and catalog code are real. SQLAlchemy connections are vetoed.
* `n0116_readonly_probes.py/.json`: final-source false v1 equivalence, in-memory XLSX formula interpretation, date-dependent promoted definition refusal. Primary reviewer reran these independently; no database or service access.
* `verify_checkpoint.py/.json`: Git, ledger prefix, node/decision snapshots, 39 source hashes and 20 inherited hashes; parsed primary historical test outputs.
* Read-only cip_test identity/role/table-policy metadata below. No test fixtures or persistent application rows were written.
* Persisted rendered pixels independently inspected by the UX seat: comparison columns, fixed area, dual-axis PNG, authenticated fixed widget and mobile visuals. Static screenshot review is not a newly observed live journey. No new browser/service was started.

Historical artifacts remain exactly: web 1,139/1,139 in 218 files; final Unit C 121/121 in16; API 3,376 passed/21 skipped; final fixture browser6/6; authenticated browser1/1; auth/export5 passed/one opt-in skip. Tsc/lint exit0 and 50 prior warnings are recorded in the final summary. Full web precedes the two-file focus fix; later final-source Unit C/browser cover it. Full API precedes the authenticated module; separate auth evidence covers that addition. None was relabelled as freshly rerun. No full suite repetition was needed to find these previously untested counterexamples.

The authenticated capture is a product bar chart with a hidden accessible table, not proof of a visible AG Grid table. Its bearer is seeded into the browser by the harness after real API authentication; it does not exercise the login form. Actual browser/Next/ASGI/Postgres integration is nevertheless present, with rolled-back fictional data. This is narrower than authenticated coverage of every visual, original caller, theme and mobile interaction.

## 3. Original-requirement acceptance matrices

Categories: **1** implemented and independently verified; **2** implemented with verification limitations; **3** partially implemented; **4** not implemented; **5** blocked by genuine operator/business decision; **6** explicitly excluded. These assess requirements, never grant acceptance. The original node-add criteria and D-0131 take precedence over temporary scope reductions.

### N-0114

| Original requirement | Category | Evidence and remaining issue |
|---|---:|---|
| Shared foundation, every dashboard/report caller | 3 | Shared charts exist; Unit C category paths bypass their grammar. Authenticated original caller matrix incomplete. |
| Every axis title and unit | 3 | Shared/dual-axis captions present; shipping quantity-or-count and sales-value caller units unresolved; some axes below inner viewport. |
| Multi-series legend, optional single | 2 | Wrapping shared legends, current fixture evidence; no complete authenticated/a11y pass. |
| Long names/full hover labels | 3 | Category tick wrapping/title present; comparison/two-measure categorical TrendChart bypasses it. |
| Automatic horizontal for long/many names | 3 | CategoryBars/PairedBars helper exists; corresponding Unit C comparison/multiple-measure paths bypass it. |
| Full pie legend names | 2 | Shared wrapping legend/full-total share; authenticated mobile long-name proof missing. |
| Top-N 5/10/15/25/all | 3 | Controls exist; saved bar top_n not forwarded; comparison/multiple-measure categories lack equivalent control. |
| Sort value/name/period | 3 | Helpers exist; saved sort overridden by renderer defaults; As listed disappears after changing sort; small sets hide controls. |
| R/US$/units/% formatting, unchanged values | 2 | Formatting/helpers implemented; ambiguity of actual caller unit remains separate decision; D-0121/0122 proposed. |
| 1280×800 and390×844, light/dark | 2 | Historical fixture matrix and computed-theme checks; authenticated all-caller/device proof absent. |
| Accessibility/keyboard | 3 | Named figures/tables and some keyboard datum controls; plain bars/tables/date marks and layout editing incomplete/unproven. |
| Shared regression after Unit C | 3 | Final focus correction covered; category/configuration gaps not covered by historical suites. |
| Authenticated application proof | 3 | One DSI widget workflow, not every original chart surface. |
| Prescribed libraries and full test gate | 2 | Existing stack preserved; historical suites parsed, cutoff explicit; original acceptance not satisfied. |

Detailed symbols, caller distinctions and visual observations: `CHART_UX_REVIEW.md`. Its source findings are not all freshly reproduced browser failures; label them accordingly.

### N-0115

The exhaustive matrix is `N0115_ACCEPTANCE_MATRIX.md`: all eight fact families; sum/count/distinct/average/min/max; every requested breakdown/calendar dimension; all eight calculated-measure kinds; original metric parity; governed handlers; every API/frontend caller; tenant/product-line/cache controls; performance. No missing original capability is retired.

Current executable inventory is **three models, 15 base measures, ten calculations across five kinds, nine walls**. Missing five model families, avg/min/max, specs_json, day, business calendar, model tenant configuration, prior-year/running-total/share-of-total remain original work. DSI/CST valuation and CPOR open/value remain decisions where authoritative meaning is unresolved. Customer cover/restock already has source logic and should first be evaluated for governed reuse.

### N-0116

This adjudicated table overrides optimistic whole-row statuses in the specialist draft where another review found a counterexample. Detailed implementation/test pointers and call paths are in `N0116_REVIEW.md`.

| Requirement | Category | Current result / boundary |
|---|---:|---|
| S1 additive0048 schema | 2 | Implemented, historical clone/cip_test migration proof, cip_test0048 freshly read. Production excluded. |
| S2 nine saved definitions migrate/idempotence/parity | 2 | Historical finite clone/cip_test proof retained; general export/query parity gaps remain. |
| S3 layout-only PATCH | 2 | Existing rows/one transaction, authenticated route evidence; full keyboard/drag browser proof limited. |
| S4 v1/v2 per-card execution/loading | 2 | Working dual dispatch/fallback, late catalog handling and switch resets. |
| S5 governed filter honours/refusals | 3 | Metadata present but CPOR filter/grain/total counterexample reproduced. |
| S6 dashboard filters/compare/exception captions | 2 | Implemented with earlier switch/intersection regressions fixed; calendar and large-option limitations. |
| S7 widget filters AND dashboard filters | 2 | Intersection/refusal/own-filter preservation implemented; historical focused coverage. |
| S8 catalog editor, sort/topN/display | 3 | Broad editor present; saved topN/order not consistently honored in rendering. Missing N-0115 metadata also limits original scope. |
| S9 required visuals/conditional colour | 3 | All visual types implemented; category grammar/configuration and full a11y need correction/proof. No need to rebuild all visuals. |
| S10 chart/table/period filtering | 3 | Pointer and selected keyboard paths work; plain bar/hbar/table/period keyboard equivalents incomplete. |
| S11 view grouped rows | 2 | Honest grouped-not-transactions drawer, CPOR case priority, scoped query/totals wording. Full authenticated drawer proof limited. |
| S12 duplicate/fullscreen/CSV/PNG/states | 2 | Implemented; corrected focus backed by final6-browser evidence; charts-only PNG disclosed. Export/query fidelity and full accessibility tracked separately. |
| S13 saved reports/schedules compatibility | 3 | Fixed-window backend path works; false equivalence, ordinary promotion dates/context, omitted v1 period_grain, frontend saved-v2 download and schedule scope remain. |
| S14 three complete editable starters | 3 | 8+6+8 widgets and template workflow present; cover/restock/value/open-case original outcomes missing. True semantic decisions5 apply only to unresolved subparts. |
| S15 dual axis/scatter/pivot | 2 | Implemented with tests/fixtures; wider authenticated/a11y proof limited. |
| S16 comparison series/table columns | 2 | Implemented; null/missing-both buckets fixed, previous values/dashes/table columns present. Category controls and business calendar remain cross-cutting gaps. |
| S17 ignored dashboard filters/fixed dates | 2 | Implemented end-to-end for explicit fixed dates; ordinary inherited-context promotion is a distinct defect. |
| S18 extra attribute filters | 2 | Catalog-driven current attributes present; specs_json/model overlay still missing under N-0115. |
| S19 named CPOR cases | 2 | id/name, duplicate/null-name handling, filters and drawer/starter integration present. Does not define “open” or “value.” |
| S20 explicit exclusions | 6 | Full v2 `/reports` editor, raw source-line drill, continuous table colour scale, note/text widgets, cross-model widgets. Current direct prompt establishes this exclusion boundary. Safe handling of already-saved v2 reports remains required, not full editor expansion. |

## 4. Defects, security and evidence gaps

| Priority | Finding | Proof and bounded correction |
|---|---|---|
| First security unit | XLSX untrusted label becomes formula | Pure workbook probe stores fictional `=1+1` as type f. Common `report_export.py` must keep text literal while retaining numeric values. Existing exporter predates Unit C but is a required current path. |
| First query unit | Governed CPOR accepts filters but does not apply them consistently | Real planner/handler + mocked I/O: bu=NB still total100/all customers; nonexistent customer -> rows[] but total100. Fix canonical handler/filter contract or refuse unsupported combinations; no new commercial formula. |
| Immediate security verification | Background governed query tenant/recipient scope | Source: CPOR handler relies on authenticated ORM ContextVar; scheduler calls user=None without binding it. Authenticated tenant leak NOT demonstrated. Prove two-tenant background execution first; report-tenant isolation is invariant, recipient scope policy is a decision. |
| High | Tenant semantic restrictions bypassed by model equivalents | In-memory tenant hides/narrows sellout_units: v1 refuses, v2 dsi units accepted/exposed. Define constrained model overlay/counterpart semantics, version cache; do not claim a row-data leak from this probe. |
| High | Saved query false v1-equivalence | Sort asc/limit1 retained in v2 but mirror loses both; downloads/delivery choose v1. Fix equivalence/execution boundary; include period_grain omitted by v1 calls. |
| High | Promotion/download changes the question | Ordinary dashboard dates/filters not captured in promotion; units_per_week saved with no dates is refused. `/reports` uses v1 form/ad-hoc export for saved v2. Preserve explicit context or refuse/warn, and route saved download correctly without building excluded v2 editor. |
| Medium | Category rendering/configuration regression | Saved bar topN/sort ignored; current/prior/two-measure category paths bypass shared category layout. Reuse shared category rendering; preserve units/nulls/server totals. |
| Accessibility | Missing equivalent keyboard actions | Plain bar/hbar/table/period filtering and layout change lack demonstrated equivalent; do not reopen the already corrected fullscreen focus bug. |
| Scale/evidence | 5,000-value filter prefix, PDF fidelity, representative performance | Search covers fetched prefix only; PDF is first40 text rows with truncation/Latin-1 limitations; owner timings are not scoped end-to-end scalability proof. Measure and bound rather than add unrelated infrastructure. |

Fresh cip_test metadata distinguishes enforcement: DSI/CST, cpor_case_line, other fact models, dim_product and commercial_lineup_line have RLS and FORCE RLS, owned by cip. cpor_case, commercial_lineup_case, dashboard, dashboard_widget and saved_report have neither enabled. Application predicates/context protect some of these paths; lack of table RLS alone is not proof of an exploitable leak. Existing owner cip has no superuser/BYPASSRLS, so FORCE policies matter. Historical owner/superuser clone timing bypasses RLS. Neither is **non-owner database-role enforcement**. No approved non-owner test connection was established, and no role/grant was created.

Required security proof: two tenants; scoped, empty, admin and revoked users; mixed query order/cache hits; exports; pooled transaction reset; background schedule; direct non-owner SQL on relevant tables. Required performance proof: approved representative clone, actual non-owner role, cache cold/warm, high-cardinality joins/spec/calendar/calculations, concurrency, query and full-widget timings under2s; capture plans and row counts. Optimize only measured gaps.

## 5. Decisions: preserve status, ask only what is needed

All **D-0116–D-0130 are still proposed**. D-0131 is accepted original-scope authority; it accepts none of the individual commercial proposals and grants no node acceptance.

| Decisions | Actual operator boundary versus engineering work |
|---|---|
| D-0116 day | Resolve v2 native-day behavior versus preserved v1 refusal; no invented splitting of CST weeks/months. |
| D-0117/0118 DSI/CST value | Confirm price basis/VAT/currency/coverage where code is insufficient. Existing code/coverage must be presented first; never change amounts to force parity. |
| D-0119 stock; D-0120 shipment dates | Latest snapshot/carry-forward and ship-confirm versus POD affect the question. Units-only plumbing can progress without inventing value or snapshot rules. |
| D-0121/0122 formatting/Other | Proposed display conventions are implemented in places but remain unaccepted. Do not undo or expand them in this audit. |
| D-0123 CPOR open/value | Choose lifecycle status semantics and support/estimate currency meaning from actual commercial evidence. Existing all-time support handler is not interchangeable with case-window model support. |
| D-0124 cover/restock; D-0127 starter naming | Existing overview definitions make blanket “blocked/no definition” inaccurate. Compare/reuse first; escalate only a real mismatch with intended starter meaning. Incomplete renamed starter does not satisfy original outcome. |
| D-0125 storage | Existing nullable definition shape already implemented. Formal proposal status is not a reason to ask permission again for routine in-scope bug fixes; it is also not approved acceptance. |
| D-0126 production migration | No production approval. Keep0048 off cip until explicitly authorized and separately release-verified. Clone/cip_test work is not that authorization. |
| D-0128 BU; D-0129 prior year | Product line versus business-unit attribute, calendar-year versus52-week alignment must remain explicit. Existing BusinessCalendar can be wired without inventing a tenant policy. |
| D-0130 render route | Historical “agent cannot sign in” rationale partly superseded by real authenticated fictional-data harness. Preserve proposal status; no need to repeat permission for existing safe harness. Real business-data/role provisioning remains separate. |
| New actual choices | Recorded-price family contradiction (FactPricing versus listing observations); saved-report rolling versus snapshot context if no canonical contract; schedule owner/recipient visibility; provision/use an approved non-owner clone identity. Each needs concrete alternatives only when its execution unit reaches that boundary. |

No need to ask Warren to approve elementary filter consistency, literal XLSX text, preservation of saved sort/limit/grain, restoring keyboard activation, reuse of known calendar configuration, or adding already-requested model/calculation infrastructure. No production or identity permission is implied.

## 6. Bounded continuation plan

Each unit uses supported lease/stage/revision ownership, stays on this feature branch and the existing checkout, and records failed-before/passed-after evidence. A new implementation session must not carry this review's evidence as its own independent verification.

| Order / owner | Unit, dependencies and stop boundary | Acceptance / verification |
|---|---|---|
| E1 N-0115 backend + verification | Correct governed CPOR accepted-filter contract; canonical a2 handler/portfolio, graph honours metadata. No business-value substitution. Independent of missing models. | Filter×grain×zero/multi-match matrix; row/total consistency or explicit refusal; v1/v2/export/delivery; real SQL cip_test proof after pure regression. |
| E2 N-0116 backend/security | Common XLSX literal safety; separate small unit from query architecture. | Formula-looking text remains string, legitimate numbers unchanged, v1/v2 saved/ad-hoc endpoint samples. |
| E3 N-0115 security/backend | Reproduce background tenant scope, bind report tenant; assess scheduled recipient authorization. Reuse transaction scope. New role/grant only with permission. | Two tenants, pooled sessions, no-context background runner, cache ordering, scoped recipients/empty scope. If policy unresolved, prevent broader silent delivery; no production send. |
| E4 N-0116 full-stack | One saved-query fidelity unit: equivalence/sort/limit/period grain, promotion context, saved-v2 download routing. No excluded full v2 report editor. | Same question/rows/totals/order/window through card→promote→savedPDF/XLSX→delivery; legacy rows unchanged; fixed/rolling policy explicit. |
| E5 N-0114 + N-0116 frontend/a11y | Canonical category rendering/control wiring and keyboard equivalents. Preserve focus fix and advanced visuals. | Long labels12+, top5/name sort, As listed return, plain bar/hbar/table/date keyboard, grid layout alternative; browser both widths/themes, zoom/contrast/accessibility checks. |
| E6 N-0115 architecture/backend | Tenant model overlay + legacy counterpart restrictions; allowed specs_json extraction; avg/min/max. No arbitrary tenant SQL. | Hide/narrow/label parity, cycle/unknown-key/injection/null tests, tenant/cache version isolation; use existing config ownership. |
| E7 N-0115 model units | Returns first (tenant-via-product exists); lineup; shipment/sell-in; inventory; recorded pricing after source/date/snapshot/currency reconciliation. Each one bounded unit. | Correct fact grain/source/tenancy/walls, representative DB totals+names+nulls, governed compatibility. No new writers/ingestion paths. |
| E8 N-0115 calendar/calculation | Reuse BusinessCalendar, then native day and prior-year/running-total/share-of-total; preserve existing ratio/difference/prior/pct/per-week rules. | Fiscal/retail/custom/leap/53-week/gaps/partial buckets, totals/denominator and division-by-zero; model query, comparisons, export and delivery agree. |
| E9 N-0115→N-0116 product/backend | Reuse known cover/restock governed logic; resolve remaining value/open semantics; complete all three original starters. Depends on relevant E6–E8 and actual decisions only. | Each original starter question answered, honest missing/zero distinctions, editable/filterable, parity to owning surface; no fake figures. |
| E10 independent GOV-008/GOV-009 | Non-owner RLS/performance, full original caller/authenticated/a11y matrix, final-source regression and model separation. Preserve historic gate debt. | Evidence pinned to final source; required quality/journey gates through CLI, actual R3 attestation where available; operator acceptance separately requested after completion. |

No production deployment unit is authorized. Historical gate debt and missing onboarding `engineering-rules.mdc` are recorded, not silently repaired. The generic frontier's unrelated nodes are not this task's next work.

## 7. Exact next implementation checkpoint

Start **E1: N-0115 governed CPOR filter/total fidelity**, at unchanged product HEAD `d069f86c`. Read this report, `N0115_ACCEPTANCE_MATRIX.md`, and `n0115_readonly_probes.py/.json`. First supported read:

```powershell
apps/api/.venv/Scripts/python.exe .eif/runtime/programme/program.py --run RUN-NEXT-N0115-FILTER-FIDELITY --actor codex status --node N-0115
```

Then run `verify` separately and wait for completion. Read the new node revision; **16 is this review's observation, never a future expected revision assumption**. Acquire the implementation lease using `event node.lease.acquire --payload-file <audit-payload>` for N-0115/fresh run/TTL, then record `node.stage` to implement with the freshly returned revision. Do not edit generated views, reuse the review run as implementation, or overwrite previous evidence. One CLI mutation at a time. The runtime stamps only the first implementation run, so retain explicit later commit/source provenance rather than assuming a new stage event resets historical pass evidence.

Before product edits deliver the AGENTS path map. This is a query/read-path fix, so Celery/sync writer/commit columns are N/A except report scheduling/delivery; no importer action or new fact writer is involved. Canonical target is `query/handlers/a2_cpor.py` plus its portfolio service and `query/model/graph.py` contract. Current divergence: metadata says a filter is honoured while handler post-filters already-aggregated rows and leaves unmatched totals. **One direction: extend the existing governed path to apply its advertised scope consistently, or explicitly refuse unsupported combinations; do not add another metric writer or change support semantics.**

Exit that unit with focused regression/real SQL/caller evidence, validate stage, released lease and acceptance still pending. Continue E2/E3 next; no need to wait for unrelated commercial decisions to correct the demonstrated contract defect. Any production migration/restart/main/identity action remains a separate explicit operator boundary.

## Persistence closeout

The original 88 local-only events are essential and preserved: finalization recomputed the exact original prefix SHA-256 `20faf23a68be8227c01ea6ec0a8f563521e8281128ebf7d6be492c3f5264bd25`. Supported evidence.add event **2768 / EV-0199** records this review; there are now **89 local-only events** beyond Git2679. Final integrity is true, the same nine gate issues are acknowledged, node revisions/stages/acceptance and empty leases are unchanged, all39 source hashes still match, product diff is empty and inherited runtime/policy hashes are unchanged. See `closeout.json` and `programme-final-verify.json`.

This run's audit files, CURRENT/CONTEXT and BACKLOG-217 are local and uncommitted; no push was made. No implementation lease was acquired, and no quality/verification gate was marked pass. One initial event invocation used an invalid --type option and was rejected by argparse before mutation; help was consulted and the supported positional command succeeded once. The programme ledger/views were written only by that supported command. Read closeout before the next run instead of assuming entry revision2767 remains current.
