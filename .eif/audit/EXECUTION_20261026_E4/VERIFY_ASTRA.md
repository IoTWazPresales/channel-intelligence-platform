# E4 independent verification — preliminary, FAILED pending correction

Review run: RUN-20261026-N0116-E4-VER-ASTRA. Implementation run: RUN-20261026-N0116-E4-CODEX. Base d2200cb1f139d28642ad44a79dc6403f30d28c34; parent supplied EIF2788 / N0116 implement revision20 lease. Invocation separation: root GPT-6.1-Sol, reviewer GPT-6-Astra. Runtime attestation is UNVERIFIED, not ENFORCED.

Bounded review applies GOV-008 verification-controller, CR-008 implementation-reviewer, with previously read project onboarding reused. Scope is E4 saved execution fidelity and promotion, associated backend/frontend paths and tests. No product, ledger, memory, staging, service, migration or production writes by reviewer. Root owns final ledger and gate decisions. This is not node acceptance, original-scope completion or R3 completion.

## Independently reproduced preliminary findings

Evidence: astra_promotion_probe.py and astra-promotion-probe.txt, executed using API venv Python. Catalog loaded from disk; SQLAlchemy Engine.connect explicitly vetoed; no database connection. Executor row fixture is a stub, not a real SQL/HTTP proof.

1. **MAJOR: own null restriction can disappear in promotion.** `dashboard_definitions.definition_for_promotion` obtains `filters.get(key)` and wraps a missing key as `[None]`; this matches the valid original `bu:[null]`. Original dsi_sellout.units/by bu with null-only BU restriction promotes successfully using execution with no filters, yielding an unrestricted definition. `requestFor.asList` drops null values, so the normal browser resolver can produce the omission. Require presence and retain typed null semantics or explicitly refuse unsupported resolution.
2. **MAJOR: implicit row limit still invalidates v1 equivalence.** `_v1_mirror`/`runs_v1` reject explicit sort/limit only. A default support_spend/by customer definition remains v1_equivalent=true and runs_v1=true, yet `_run_governed` takes 500 of 501 rows and marks truncated, while v1 returns all501. Model queries additionally have implicit ordering in compiler.py (measure descending or period ordering), unlike legacy dimension ordering. Saved execution must retain these implicit semantics as well as explicit fields.

Both findings communicated to root before source freeze. No implementation changes by reviewer. Final tests and source pinning await correction/final-source-ready.

## Compatibility assessment

The original N0116_REVIEW S20 excludes full v2 editing in /reports but requires safe saved display/download/scheduling. A saved-definition mode using canonical saved export/send/schedule plus explicit new-report action is sufficient for this bounded repair. It disables legacy Run/edit-copy for migrated v1-expressible definitions too; record this as a visible UX limitation, not unchanged report-builder compatibility. Restoring the legacy form solely from v1_equivalent is unsafe given finding2 and its incomplete filter reconstruction. No full v2 editor is requested by this review.

## Limits

Preliminary mutable-source review only; no independent final focused pytest or rendered-browser execution yet. Root full suites/browser proof are separately owned. No non-owner RLS, concurrent recipient/runtime, comprehensive catalogue, original frontier or operator acceptance claim. Missing local engineering-rules.mdc from onboarding remains a documented context limitation.
