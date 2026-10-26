# E3 independent verification — VERIFIED_WITH_LIMITATIONS

Review run `RUN-20261026-N0115-E3-VER-ASTRA`; implementation run `RUN-20261026-N0115-E3-CODEX`. Separate GPT-6-Astra reviewer and GPT-6.1-Sol implementation root, from invocation provenance; no runtime model attestation. Applied identity-access SR-003 and GOV-008 contracts. Accepted D-0132 is the bounded policy: current same-tenant recipient access, active identity and existing report visibility.

Review covers report_delivery.py, report_schedule_runner.py, report_exports.py and new recipient-scope tests. No product/ledger/memory edits, production connection, service/migration/identity action or acceptance by reviewer.

**Final bounded verdict: VERIFIED_WITH_LIMITATIONS.** The two material findings raised during review are resolved in the final sources, with real regressions independently re-executed. No unresolved blocking E3 defect found. This is not original N-0115 completion, operator acceptance, production release or overall R3/runtime-attestation completion.

## Initial findings and final resolution

1. **MAJOR, resolved — Run now response crosses recipient scope boundary.** In the initial endpoint diff, a scoped viewer who can view a published report could create a schedule targeting a same-tenant admin, then run it. Both identities were legitimate, but the response serialized the admin's broader delivery to the viewer. Root's real HTTP regression reproduced `[70,10]` where only `[10]` was authorized (`review-findings-before.txt`). Final `report_exports.py:358–361` applies the existing inbox rule: admin may see tenant deliveries; other callers receive only their own delivery contents. The final test proves the viewer receives 10 while inbox rows still carry 70 for admin and 10 for viewer. The response no longer grants access to another recipient's figures.
2. **MAJOR, resolved — live transaction and ContextVars could diverge.** Initial `_scheduled_recipient_scope` reset only ContextVars. Commit followed by refresh opened a recipient-scoped transaction that survived wrapper exit. Root's success/error regressions reproduced GUCs `(*,*,admin)` instead of the caller's line/empty-edit/viewer tuple. Final `report_delivery.py:131–149` rolls back failed recipient work, restores context tokens, then restores any surviving live transaction's GUCs to the caller's scope (explicit open/reset-role for an unbound worker). Final tests prove successful commit/refresh, ordinary query failure and PostgreSQL-aborted SQL cleanup restore both caller context and the next same-session GUC read.
3. **Test assertion issue, corrected; not a demonstrated leak.** Initial independent focused run: 24 passed/1 failed in 29.94s (`astra_focused_initial.txt`, exit 1). The GUC-only pool test expected `*` after root rollback but observed empty text. Canonical scope semantics treat empty text as open. The corrected assertion accepts only the defined open representations and empty role, while still proving reuse of the same physical backend and absence of the former NB/viewer scope. It passes in the final run.

The reviewer paused for the source-ready checkpoint before final re-execution and made no implementation edits.

## Canonical implementation and policy review

Working diff reviewed against HEAD `03ec2221251bfba489b73f2d2a00742399b961d9`, branch `feat/ns-2-brief-nav-collapse`. Existing query/writer paths remain canonical:

| Trigger | Canonical path | Enforcement observed |
|---|---|---|
| Calendar/import background execution | `_deliver_schedule_async` -> `deliver_saved_report` -> `_scheduled_recipient_scope` -> existing v1/v2 query and inbox writer | Report/schedule tenant match; current active recipient in report tenant; existing visibility; recipient role and read/edit assignments bound before query/cache access |
| Schedule creation / Run now | Existing report_exports endpoints -> same resolver and delivery path | Caller report visibility plus recipient checks; no foreign/null recipient authorization; Run now output restricted to caller inbox visibility |
| Failed schedule | Existing catch/rollback -> `_write_failed_delivery` -> same recipient resolver | No failed-content inbox row for missing/inactive/foreign/invisible recipients or mismatched report tenant |
| Manual delivery | Existing manual path | Compatibility retained; `user=None` manual behavior is not presented as scheduled authorization |

`resolve_report_recipient` explicitly filters AppUser by current report tenant, recipient ID and active flag, then applies `can_view_owned_item`. Scope derives from the current server role and current `UserProductLineAccess` rows with the canonical `product_line_scope_for`; no owner delegation or role/grant writer was introduced. Cache keys already include tenant, read scope and role; the wrapper binds these before both governed and model queries. Current assignment revocation changes the effective cache scope on the next execution. Background query evidence preserves the distinction from the original investigation: E1 already kept CPOR totals within the report tenant; the proven old defect was same-tenant recipient overexposure and foreign recipient acceptance, not a demonstrated cross-tenant aggregate leak.

Failure notifications use the current identity/visibility resolver before creating inbox rows. The existing per-delivery commit model is retained; a later recipient failure does not roll back an already delivered authorized recipient's row. This review does not claim schedule-wide atomic delivery or redesign retry/idempotency behavior.

## Independently re-executed evidence

Exact final command:

```powershell
apps/api/.venv/Scripts/python.exe apps/api/scripts/db_on.py pytest tests/test_report_schedule_recipient_scope.py tests/test_report_export.py tests/test_report_delivery_alert.py
```

**29 passed in 68.88s, exit 0**, `astra_focused_final.txt`. The eight-path source manifest was captured before completion and all eight hashes matched at closeout. No broad suite was independently repeated.

Coverage directly observed in the final tests:

- Actual background runner with request ContextVars explicitly unset, governed CPOR values 70/10/0/10 and model values 1012/913/0/913 for admin/scoped/empty/repeated viewer recipients. Tenant B import-triggered execution returns its own 1000. Both v1 and v2 paths run real query/SQL code.
- Product assignment revocation between executions reduces viewer 10 to 0 on the next import-triggered run; repeated mixed scopes exercise cache separation. Current role resolution and role-containing keys were source-reviewed; concurrent role-change races were not separately stress-tested.
- Foreign, inactive, private-report, absent-identity and mismatched-report-tenant schedules refuse without delivering or notifying the disallowed identities. Contexts restore on these paths.
- Real bearer HTTP schedule creation rejects foreign IDs; Run now honors current recipient values, and a scoped triggering viewer cannot read the broader admin result.
- Live same-session read/edit/role GUC restoration after success, application failure and aborted SQL; physical pooled-backend reuse after a real root rollback clears the earlier scope/role.
- Existing export/delivery timing/helper/failure-alert contracts remain passing in the approved related modules. Failure-alert files in tests use temporary local paths; no external send occurs.

The inherited authenticated fixture asserts `cip_test` identity and a login without superuser/BYPASSRLS. Fictional account/report/schedule/inbox changes use savepoints under an outer rollback. The pool test uses a separate one-connection cip_test engine, changes transaction-local settings only, and closes/disposes it. Root's original clean red regression log (`failed-before-clean.txt`: 8 failures) and the later 3-failure review regression log were inspected; they are root evidence, not independently rerun pre-change work. Earlier harness teardown errors are retained separately and not counted as product failures.

## Limits and authority

- No browser, Celery broker, deployed service, production cip connection or actual external delivery was used. These are in-process authenticated API, actual runner and PostgreSQL tests, not production/browser smoke.
- The measured database login is not a newly provisioned non-owner role. Non-owner direct-SQL enforcement, exhaustive concurrency/revocation races, all data models and original programme performance/acceptance requirements remain unproven by this unit. Existing record-specific restrictions beyond current report visibility and product-line scope are not invented here.
- R3 model separation is recorded from actual agent invocation (root GPT-6.1-Sol, reviewer GPT-6-Astra, separate context), but runtime/model attestation remains UNVERIFIED. No missing guard is labelled ENFORCED. Root reported lease expiry during the interruption; supported reacquisition is evidenced by `lease-resume-result.txt` at programme 2783. This does not retrospectively prove uninterrupted lease enforcement. Root owns final programme/memory reconciliation and preserved-prefix proof.
- Root's larger suites/lint/typecheck are separate evidence, not independently repeated here. Overall node acceptance, original scope, release and production permissions remain unchanged. The prior missing engineering-rules.mdc onboarding limitation remains explicit.
- Reviewer wrote only this unit's audit report/logs/manifests. No product, ledger, memory, role/grant, migration, service, main, release or remote writes.

## Exact source provenance

Full manifest: `astra_source_sha256.json`; final match evidence: `astra_source_match_closeout.json` (all 8 true).

| E3 changed path | SHA-256 |
|---|---|
| apps/api/app/services/report_delivery.py | 13495f5e04e6f6072fe4781d1b6546ec14f137b5f685fea5cdb6b29596cb7df7 |
| apps/api/app/services/report_schedule_runner.py | 2865aecc901e7d8b5e7020516b166603b9e5dc0911a28d7010257a7bc8c8d922 |
| apps/api/app/api/v1/endpoints/report_exports.py | 7f60652fa5fc3795f4ce929d3c513ee4634ceaee6d25eae07ad1e562179c72be |
| apps/api/tests/test_report_schedule_recipient_scope.py | 0f11ba51be0caaa36022edb2957a36fb9b02b8651355d8725c60cd15e415906b |

